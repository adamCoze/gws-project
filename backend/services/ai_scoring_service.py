"""AI 初评服务：考核发起（跳过部门确认时）/ 部门总监确认完成后，自动调用考核 Bot 评分（PRD 6.7）

- 单 Bot 双任务（PRD 11.5）：消息以【任务：评分】开头
- 输出解析：建议得分（手册标准分 1 或 5）/ 评分理由 / 依据条款 / 疑点提示
- 标准未覆盖时 ai_score=None（不强行给分）；调用失败重试 1 次，仍失败标记「AI未评分」，不阻塞流程
- 并发限制 ≤3，避免 Coze API 限流
- 全跳过场景（评分层全跳过）仍执行一次并归档，作为异议期出异议时的裁定参考
"""
import asyncio
import logging
import re
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from database import async_session
from models import (
    Assessment,
    AssessmentStatus,
    EmailLog,
    ScoreLevel,
    WorkItem,
)
from services.appeal_ai_service import _call_coze_bot

logger = logging.getLogger(__name__)

# PRD 6.7：同一批次多件考核同时进入评分时限并发 ≤3
_AI_SCORING_SEMAPHORE = asyncio.Semaphore(3)

# PRD 6.7：超时 120 秒
_AI_SCORING_TIMEOUT_SECONDS = 120

# 输入材料长度上限（防止超长 prompt）
_MAX_TIMELINE_CHARS = 12000
_MAX_BODY_PER_MAIL = 2000

_SCORE_PATTERN = re.compile(r"建议得分[：:]\s*(\d+)\s*分")
_REASON_PATTERN = re.compile(r"评分理由[：:]\s*(.+)")
_BASIS_PATTERN = re.compile(r"依据条款[：:]\s*(.+)")


def get_ai_bot_configured() -> bool:
    """考核 AI Bot 是否已配置（GWS_AI_BOT_ID）"""
    return bool((settings.GWS_AI_BOT_ID or "").strip())


def ai_scoring_enabled() -> bool:
    """AI 初评环节是否启用：需同时满足开关打开（GWS_AI_SCORING_ENABLED）且 Bot 已配置。

    2026-11-05：预判表与 9 月人手打分比对发现 AI 评分规则尚需大量训练，暂时停用
    区总前的自动 AI 初评，仅保留异议期 AI 中立审查（appeal_ai_service，不受本开关影响）。
    恢复方法：服务器 .env 设 GWS_AI_SCORING_ENABLED=true 后 docker compose restart app。
    """
    return bool(getattr(settings, "GWS_AI_SCORING_ENABLED", True)) and get_ai_bot_configured()


def parse_ai_score_answer(answer: str) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """解析评分回答 → (建议得分|None, 评分理由, 依据条款)

    标准未明确时无「建议得分：N分」→ score=None（Bot 正常响应但标准未覆盖）
    """
    score = None
    m = _SCORE_PATTERN.search(answer)
    if m:
        score = int(m.group(1))
    reason = None
    m = _REASON_PATTERN.search(answer)
    if m:
        reason = m.group(1).strip()
    basis = None
    m = _BASIS_PATTERN.search(answer)
    if m:
        basis = m.group(1).strip()
    return score, reason, basis


def advance_status_after_ai(assessment: Assessment) -> None:
    """AI 评分（成功/失败/未明确）后流转到第一个评分层（不阻塞）"""
    if assessment.skip_regulator_score:
        assessment.status = AssessmentStatus.pending_group_score.value
        assessment.current_level = ScoreLevel.group.value
    elif assessment.skip_district_score:
        assessment.status = AssessmentStatus.pending_regulator_score.value
        assessment.current_level = ScoreLevel.regulator.value
    else:
        assessment.status = AssessmentStatus.pending_district_score.value
        assessment.current_level = ScoreLevel.district.value


def _normalize_dept_name(name: str) -> str:
    """把系统部门名（如「行政/产品」「财审/投资」）规范为手册口径（行政部/财审部），
    避免 AI 因部门名称与手册不一致而找不到对应条目。"""
    raw = (name or "").strip()
    if not raw:
        return raw
    head = raw.split("/")[0].split("／")[0].strip()
    if head.endswith("部"):
        return f"{head}（系统部门名：{raw}）" if head != raw else head
    if head in ("财审", "行政", "法务", "人事"):
        return f"{head}部（系统部门名：{raw}）"
    return raw


async def _build_scoring_input(db: AsyncSession, assessment: Assessment) -> str:
    """组装评分输入：工作项目名称、内容、部门、邮件时间线（事中留存，11.1）"""
    wi = assessment.work_item
    parts = ["【任务：评分】"]

    if wi:
        parts.append(f"工作项目名称：{wi.title}")
        if wi.content:
            parts.append(f"工作内容：{wi.content[:2000]}")
        if wi.department and getattr(wi.department, "name", None):
            parts.append(f"所属部门：{_normalize_dept_name(wi.department.name)}")

        # 关联邮件时间线（正文留存 or 主题降级）
        result = await db.execute(
            select(EmailLog)
            .where(EmailLog.work_item_id == wi.id, EmailLog.process_result == "success")
            .order_by(EmailLog.received_at.asc())
        )
        logs = list(result.scalars().all())
        if logs:
            no_body_count = sum(1 for x in logs if not x.body)
            timeline = ["邮件时间线（按时间先后，反映工作项信息演变）："]
            if no_body_count == len(logs):
                timeline.append("（注：历史邮件正文未留存，仅提供主题时间线）")
            elif no_body_count > 0:
                timeline.append(f"（注：其中 {no_body_count} 封历史邮件正文未留存，仅显示主题）")
            used = 0
            for i, log in enumerate(logs, 1):
                recv = log.received_at.strftime("%Y-%m-%d") if log.received_at else "日期未知"
                line = f"{i}. [{recv}] 主题：{log.subject or '无'}"
                if log.body:
                    line += f"\n正文：{log.body[:_MAX_BODY_PER_MAIL]}"
                timeline.append(line)
                used += len(line)
                if used > _MAX_TIMELINE_CHARS:
                    timeline.append(f"（其余 {len(logs) - i} 封略）")
                    break
            parts.append("\n".join(timeline))

    return "\n".join(parts)


async def _call_scoring_bot(content: str) -> Optional[str]:
    """调用评分 Bot（120 秒超时，失败由调用方重试 1 次）"""
    try:
        return await asyncio.wait_for(
            _call_coze_bot(settings.GWS_AI_BOT_ID.strip(), content),
            timeout=_AI_SCORING_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("AI 初评调用超时（%ds）", _AI_SCORING_TIMEOUT_SECONDS)
        return None


async def run_ai_scoring(assessment_id: int) -> None:
    """执行 AI 初评全流程（独立 session，供后台任务调用）

    - Bot 未配置：不进入本函数（调用方已判断）；防御性再查一次
    - 成功：ai_score/ai_reason/ai_basis 落库，ai_status=completed
    - 标准未明确：ai_score=None，ai_status=completed（Bot 正常响应）
    - 失败（重试 1 次后仍失败/超时）：ai_status=failed（前端显示「AI未评分」）
    - 无论结果均流转到第一个评分层，不阻塞流程
    """
    async with _AI_SCORING_SEMAPHORE:
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(Assessment)
                    .options(
                        selectinload(Assessment.work_item).selectinload(WorkItem.department),
                    )
                    .where(Assessment.id == assessment_id)
                )
                assessment = result.scalar_one_or_none()
                if not assessment:
                    logger.error("AI 初评：考核 %s 不存在", assessment_id)
                    return
                if assessment.status != AssessmentStatus.ai_scoring.value:
                    logger.info("AI 初评：考核 %s 状态已不是 ai_scoring（%s），跳过", assessment_id, assessment.status)
                    return
                if not ai_scoring_enabled():
                    # 防御：开关关闭或未配置时直接流转（不调用 Bot）
                    advance_status_after_ai(assessment)
                    assessment.updated_at = datetime.utcnow()
                    await db.commit()
                    return

                assessment.ai_status = "scoring"
                assessment.updated_at = datetime.utcnow()
                await db.commit()

                # 组装材料并调用（失败重试 1 次）
                scoring_input = await _build_scoring_input(db, assessment)
                answer = await _call_scoring_bot(scoring_input)
                if not answer:
                    answer = await _call_scoring_bot(scoring_input)

                bot_name = (settings.GWS_AI_BOT_NAME or "GWS考核AI助手").strip()
                if answer:
                    score, reason, basis = parse_ai_score_answer(answer)
                    assessment.ai_score = score
                    assessment.ai_reason = reason or answer[:200]
                    assessment.ai_basis = basis
                    assessment.ai_status = "completed"
                    assessment.ai_scored_at = datetime.utcnow()
                    log_detail = (
                        f"AI 初评完成（{bot_name}）：建议得分 {'标准未明确' if score is None else f'{score}分'}"
                        + (f"，依据：{basis[:80]}" if basis else "")
                    )
                else:
                    assessment.ai_status = "failed"
                    assessment.ai_scored_at = datetime.utcnow()
                    log_detail = f"AI 初评失败（{bot_name}）：标记「AI未评分」，不阻塞流程"

                advance_status_after_ai(assessment)
                assessment.updated_at = datetime.utcnow()

                # 操作日志
                from models import AssessmentOperationLog
                db.add(AssessmentOperationLog(
                    assessment_id=assessment.id,
                    work_item_id=assessment.work_item_id,
                    operator_id=1,  # 系统操作
                    action="ai_score",
                    detail=log_detail,
                ))
                await db.commit()
                logger.info("AI 初评：考核 %s %s", assessment_id, assessment.ai_status)

        except Exception as e:
            logger.error("AI 初评：考核 %s 执行失败: %s", assessment_id, e, exc_info=True)
            # 失败兜底：流转到第一个评分层，保证流程不卡死
            try:
                async with async_session() as db:
                    result = await db.execute(
                        select(Assessment).where(Assessment.id == assessment_id)
                    )
                    assessment = result.scalar_one_or_none()
                    if assessment and assessment.status == AssessmentStatus.ai_scoring.value:
                        assessment.ai_status = "failed"
                        advance_status_after_ai(assessment)
                        assessment.updated_at = datetime.utcnow()
                        await db.commit()
            except Exception as e2:
                logger.error("AI 初评：考核 %s 失败兜底也异常: %s", assessment_id, e2)


def trigger_ai_scoring(assessment_id: int) -> None:
    """启动 AI 初评后台任务（开关关闭或 Bot 未配置时不启动）"""
    if not ai_scoring_enabled():
        logger.info("AI 初评已停用（GWS_AI_SCORING_ENABLED=false），考核 %s 跳过自动评分", assessment_id)
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(run_ai_scoring(assessment_id))
    except RuntimeError:
        asyncio.run(run_ai_scoring(assessment_id))
