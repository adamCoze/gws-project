"""异议 AI 中立审查服务：3 个不同基础模型的 Coze Bot 并行审查"""
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from database import async_session
from models import (
    Assessment,
    AssessmentAppeal,
    AssessmentAppealAiOpinion,
    AssessmentScore,
    EmailLog,
)

logger = logging.getLogger(__name__)

_COZE_CHAT_URL = "/v3/chat"

# 审查结论解析关键词
_CONCLUSION_PATTERNS = [
    ("maintain", "建议维持原评分"),
    ("maintain", "建议维持原分"),
    ("maintain", "建议维持"),
    ("review", "建议复核"),
    ("undetermined", "无法判断"),
]


def _get_configured_bots() -> List[Tuple[int, str, str]]:
    """读取已配置的审查 bot 列表：[(槽位, bot_id, 显示名)]"""
    bots = []
    for idx in (1, 2, 3):
        bot_id = getattr(settings, f"APPEAL_REVIEW_BOT_{idx}_ID", "").strip()
        bot_name = getattr(settings, f"APPEAL_REVIEW_BOT_{idx}_NAME", "").strip() or f"模型{idx}"
        if bot_id:
            bots.append((idx, bot_id, bot_name))
    return bots


def _parse_conclusion(opinion: str) -> Optional[str]:
    """从意见文本解析结论：maintain / review / undetermined"""
    if not opinion:
        return None
    # 只看结论段（末尾300字），避免正文提词误判
    tail = opinion[-300:]
    for key, phrase in _CONCLUSION_PATTERNS:
        if phrase in tail:
            return key
    return None


async def _build_review_input(db: AsyncSession, assessment: Assessment, appeal: AssessmentAppeal) -> str:
    """组装审查输入材料"""
    parts = []

    # 1. 工作项标题与当前描述
    wi = assessment.work_item
    parts.append("【工作项】")
    parts.append(f"标题：{wi.title if wi else assessment.id}")
    if wi and wi.content:
        parts.append(f"当前描述：{wi.content}")

    # 2. 关联邮件时间线（正文留存 or 主题降级）
    if wi:
        result = await db.execute(
            select(EmailLog)
            .where(EmailLog.work_item_id == wi.id, EmailLog.process_result == "success")
            .order_by(EmailLog.received_at.asc())
        )
        logs = list(result.scalars().all())
        if logs:
            no_body_count = sum(1 for x in logs if not x.body)
            parts.append("\n【关联邮件时间线】（按时间先后，反映工作项信息演变）")
            if no_body_count == len(logs):
                parts.append("（注：历史邮件正文未留存，仅提供主题时间线）")
            elif no_body_count > 0:
                parts.append(f"（注：其中 {no_body_count} 封历史邮件正文未留存，仅显示主题）")
            for i, log in enumerate(logs, 1):
                recv = log.received_at.strftime('%Y-%m-%d') if log.received_at else '日期未知'
                line = f"{i}. [{recv}] 主题：{log.subject or '无'}"
                if log.body:
                    line += f"\n正文：{log.body[:3000]}"
                parts.append(line)

    # 3. 各层评分记录
    parts.append("\n【各层评分记录】")
    for score in sorted(assessment.scores, key=lambda s: s.created_at or datetime.utcnow()):
        level_map = {"district": "区总", "regulator": "监察主任", "group": "集团总监"}
        line = f"- {level_map.get(score.level, score.level)}：{score.total_score} 分"
        if score.opinion:
            line += f"，理由：{score.opinion}"
        parts.append(line)

    # 4. 员工异议理由
    parts.append("\n【员工异议】")
    parts.append(f"异议理由：{appeal.reason}")

    # 5. 补充意见（如有）
    if appeal.regulator_comment:
        parts.append(f"\n监察主任补充意见：{appeal.regulator_comment}")
    if appeal.group_director_comment:
        parts.append(f"集团总监补充意见：{appeal.group_director_comment}")

    return "\n".join(parts)


async def _call_coze_bot(bot_id: str, content: str) -> Optional[str]:
    """调用 Coze Bot API（流式），返回回复文本；失败返回 None"""
    if not settings.COZE_API_TOKEN:
        logger.error("Coze API Token 未配置")
        return None

    headers = {
        "Authorization": f"Bearer {settings.COZE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    base_url = settings.COZE_API_BASE.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{base_url}{_COZE_CHAT_URL}",
                headers=headers,
                json={
                    "bot_id": bot_id,
                    "user_id": "gws-appeal-review",
                    "additional_messages": [
                        {"role": "user", "content": content, "content_type": "text"}
                    ],
                    "stream": True,
                },
            )
            resp.raise_for_status()

            full_content = ""
            delta_accumulator = ""
            current_event = ""
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("event:"):
                    current_event = line[6:]
                    continue
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:])
                    except json.JSONDecodeError:
                        continue
                    if current_event == "conversation.message.delta" and "content" in data:
                        delta_accumulator += data["content"]
                    if current_event == "conversation.message.completed" and "content" in data:
                        msg_type = data.get("type", "")
                        if msg_type == "answer" and data.get("content"):
                            full_content = data["content"]

            answer = full_content or delta_accumulator
            answer = answer.strip()
            # 去掉可能包裹的代码块标记
            if answer.startswith("```"):
                answer = re.sub(r"^```(?:\w+)?\s*", "", answer)
                answer = re.sub(r"\s*```$", "", answer).strip()
            return answer if answer else None

    except httpx.HTTPError as e:
        logger.error(f"审查 Bot ({bot_id}) API 调用失败: {e}")
        return None
    except Exception as e:
        logger.error(f"审查 Bot ({bot_id}) 调用异常: {e}", exc_info=True)
        return None


async def _review_with_bot(bot_index: int, bot_id: str, bot_name: str, review_input: str) -> "AssessmentAppealAiOpinion":
    """单 bot 审查（内存对象，由调用方落库）"""
    opinion = AssessmentAppealAiOpinion(
        bot_index=bot_index,
        bot_name=bot_name,
        status="processing",
    )
    answer = await _call_coze_bot(bot_id, review_input)
    if answer:
        opinion.status = "completed"
        opinion.opinion = answer
        opinion.conclusion = _parse_conclusion(answer)
        opinion.completed_at = datetime.utcnow()
    else:
        opinion.status = "failed"
        opinion.error_message = "模型未返回有效内容（Token失效/超时/配置错误）"
        opinion.completed_at = datetime.utcnow()
    return opinion


async def run_appeal_ai_review(appeal_id: int) -> None:
    """执行 AI 审查全流程（独立 session，供后台任务调用）

    - 无已配置 bot：appeal.ai_status=not_configured，考核直接流转「待裁定」，意见区显示"暂未接入模型"
    - 有 bot：并行调用全部槽位，逐个落库；全部结束后流转「待裁定」
    """
    try:
        async with async_session() as db:
            result = await db.execute(
                select(AssessmentAppeal)
                .options(
                    selectinload(AssessmentAppeal.assessment).selectinload(Assessment.work_item),
                    selectinload(AssessmentAppeal.assessment).selectinload(Assessment.scores).selectinload(AssessmentScore.scorer),
                )
                .where(AssessmentAppeal.id == appeal_id)
            )
            appeal = result.scalar_one_or_none()
            if not appeal:
                logger.error(f"AI审查：异议 {appeal_id} 不存在")
                return

            assessment = appeal.assessment
            bots = _get_configured_bots()

            if not bots:
                # 未配置任何 bot：固定"暂未接入模型"，直接流转待裁定
                appeal.ai_status = "not_configured"
                assessment.status = "pending_ruling"
                assessment.updated_at = datetime.utcnow()
                await db.commit()
                logger.info(f"AI审查：异议 {appeal_id} 无审查模型配置，已流转待裁定")
                return

            # 已配置：组装材料，并行审查
            appeal.ai_status = "processing"
            assessment.status = "ai_reviewing"
            assessment.updated_at = datetime.utcnow()
            review_input = await _build_review_input(db, assessment, appeal)
            await db.commit()

            # 并行调用
            tasks = [_review_with_bot(idx, bid, bname, review_input) for idx, bid, bname in bots]
            opinions = await asyncio.gather(*tasks)

            for op in opinions:
                op.appeal_id = appeal.id
                db.add(op)
            appeal.ai_status = "completed"
            appeal.ai_completed_at = datetime.utcnow()
            assessment.status = "pending_ruling"
            assessment.updated_at = datetime.utcnow()
            await db.commit()
            logger.info(
                f"AI审查：异议 {appeal_id} 完成，{sum(1 for o in opinions if o.status=='completed')}/{len(opinions)} 成功"
            )

    except Exception as e:
        logger.error(f"AI审查：异议 {appeal_id} 执行失败: {e}", exc_info=True)
        # 失败兜底：流转待裁定，保证流程不卡死
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(AssessmentAppeal).where(AssessmentAppeal.id == appeal_id)
                )
                appeal = result.scalar_one_or_none()
                if appeal:
                    appeal.ai_status = "failed"
                    result = await db.execute(
                        select(Assessment).where(Assessment.id == appeal.assessment_id)
                    )
                    assessment = result.scalar_one_or_none()
                    if assessment and assessment.status == "ai_reviewing":
                        assessment.status = "pending_ruling"
                        assessment.updated_at = datetime.utcnow()
                    await db.commit()
        except Exception as e2:
            logger.error(f"AI审查：异议 {appeal_id} 失败兜底也异常: {e2}")
