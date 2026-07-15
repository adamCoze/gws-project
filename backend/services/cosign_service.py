"""会签自动完成服务"""
import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List

import httpx
from sqlalchemy import select

from config import settings
from database import async_session
from models import WorkItem, WorkItemStatus, User, StatusChangeLog

logger = logging.getLogger(__name__)

# 向总(xiangxin)的邮箱前缀
XIANGXIN_PREFIX = "xiangxin"

# vincent.xiang的邮箱前缀（无指定会签人时，vincent.xiang的简单批示触发自动完成）
VINCENT_XIANG_PREFIX = "vincent.xiang"

# 简单批示关键词（AI 辅助判断的 fallback）
SIMPLE_APPROVAL_KEYWORDS = [
    "无异议", "无补充意见", "同意", "已阅", "照准", "如拟",
    "已阅知", "无意见", "拟同意", "同意以上", "确认",
    "已审核，同意", "已阅，同意",
]

# 支付确认关键词（必须带有"已完成"等前缀才算）
PAYMENT_CONFIRM_KEYWORDS = [
    "已完成支付", "已给支票", "已支付完成", "已完成付款",
    "已开出支票", "已交付支票", "已完成汇款",
]


# ────────────────────────────────────────────
# 工具函数
# ────────────────────────────────────────────

def extract_reply_text(body: str) -> str:
    """从邮件正文中提取回复内容（去掉引用的原始邮件和签名）"""
    if not body:
        return ""

    # 常见的引用分割标记
    markers = [
        "\nOn ",
        "\n在 ",
        "\n>",
        "\n发件人:",
        "\nFrom:",
        "---------- Forwarded message ----------",
        "---------- 转发的邮件 ----------",
        "---------- Forwarded Message ----------",
        "-----Original Message-----",
        "----- 原始邮件 -----",
        "Begin forwarded message:",
        "转发邮件：",
        "\n____________\n",
    ]
    result = body
    for marker in markers:
        idx = result.find(marker)
        if idx > 0:
            result = result[:idx]

    # 去签名
    for sig in ["\n-- \n", "\nBest regards,", "\n此致\n", "\nSent from my"]:
        idx = result.find(sig)
        if idx > 0:
            result = result[:idx]

    return result.strip()[:2000]


def extract_sender_prefix(from_addr: str) -> str:
    """从 from_addr 提取邮箱前缀"""
    if not from_addr:
        return ""
    match = re.search(r'<([^>]+)>', from_addr)
    addr = match.group(1).strip() if match else from_addr.strip()
    if '@' in addr:
        return addr.split('@')[0].strip().lower()
    return addr.strip().lower()


def parse_designated_signers(assignee_prefix: str) -> List[str]:
    """解析指定会签人列表"""
    if not assignee_prefix:
        return []
    signers = []
    for p in re.split(r'[,，、;\s]+', assignee_prefix):
        p = p.strip().lower()
        if p:
            signers.append(p)
    return signers


# ────────────────────────────────────────────
# AI 分析会签回复
# ────────────────────────────────────────────

async def analyze_cosign_reply(subject: str, body: str) -> Dict:
    """
    用 AI 分析会签回复邮件内容。
    返回:
        {
            "is_simple_approval": bool,
            "mentions_xiangxin": bool
        }
    """
    reply_text = extract_reply_text(body)

    prompt = (
        "分析以下会签回复邮件，判断两个问题：\n\n"
        f"邮件主题：{subject[:200]}\n"
        f"回复内容：{reply_text[:1000]}\n\n"
        "判断规则：\n"
        "1. is_simple_approval：回复内容是否仅为简单批示/确认？\n"
        '   - 算简单批示："无异议"、"同意"、"已阅"、"照准"、"如拟"、"无补充意见"、"已阅知"、"无意见"、"拟同意"、"确认"\n'
        "   - 不算简单批示：回复中带有条件、疑问、修改意见、反对、补充说明，或内容超过一句话的实质性讨论\n"
        '2. mentions_xiangxin：回复内容中是否提到了"向总"、"xiangxin"或要求向总审批/确认/指导？\n\n'
        "直接输出 JSON，不要任何其他文字：\n"
        '{"is_simple_approval": false, "mentions_xiangxin": false}'
    )

    if not settings.COZE_API_TOKEN or not settings.COZE_BOT_ID:
        logger.warning("Coze API 未配置，使用简单关键词分析")
        return _simple_cosign_analysis(reply_text)

    try:
        headers = {
            "Authorization": f"Bearer {settings.COZE_API_TOKEN}",
            "Content-Type": "application/json",
        }
        base_url = settings.COZE_API_BASE.rstrip("/")

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{base_url}/v3/chat",
                headers=headers,
                json={
                    "bot_id": settings.COZE_BOT_ID,
                    "user_id": "gws-cosign",
                    "additional_messages": [
                        {"role": "user", "content": prompt, "content_type": "text"}
                    ],
                    "stream": True,
                },
            )
            resp.raise_for_status()

            bot_content = ""
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    data_str = line[5:]
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if data.get("status") == "complete" or "conversation.message.completed" in str(data):
                        content_val = data.get("content", "")
                        if content_val.startswith("{"):
                            bot_content = content_val

            if not bot_content:
                return _simple_cosign_analysis(reply_text)

            content = bot_content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
                content = content.strip()

            result = json.loads(content)
            is_simple = bool(result.get("is_simple_approval", False))
            mentions = bool(result.get("mentions_xiangxin", False))
            logger.info(f"AI 分析会签回复: is_simple_approval={is_simple}, mentions_xiangxin={mentions}")
            return {"is_simple_approval": is_simple, "mentions_xiangxin": mentions}

    except Exception as e:
        logger.error(f"AI 分析会签回复异常: {e}")
        return _simple_cosign_analysis(reply_text)


def detect_payment_confirmation(text: str) -> bool:
    """检测回复文本中是否包含支付确认表述"""
    if not text:
        return False
    return any(kw in text for kw in PAYMENT_CONFIRM_KEYWORDS)


def is_xiangxin_agreement(reply_analysis: Dict, sender_prefix: str) -> bool:
    """判断是否为 xiangxin 回复了"同意"（不阻止自动完成）"""
    if sender_prefix.lower().strip() != XIANGXIN_PREFIX:
        return False
    # xiangxin 回复"同意"（简单批示）→ 不阻止
    return reply_analysis.get("is_simple_approval", False)


def _simple_cosign_analysis(text: str) -> Dict:
    """简单的关键词分析（AI 不可用时的降级方案）"""
    text_lower = text.lower()
    is_simple = any(kw in text for kw in SIMPLE_APPROVAL_KEYWORDS)
    mentions = any(kw in text_lower for kw in ["向总", "xiangxin", "向总审批", "向总确认", "向总指导"])
    return {"is_simple_approval": is_simple, "mentions_xiangxin": mentions}


# ────────────────────────────────────────────
# 会签追踪管理
# ────────────────────────────────────────────

async def initialize_cosign_tracking(work_item_id: int):
    """
    初始化会签追踪。
    从 assignee_email_prefix 解析指定会签人，判断是否需要向总。
    """
    async with async_session() as db:
        result = await db.execute(select(WorkItem).where(WorkItem.id == work_item_id))
        item = result.scalar_one_or_none()
        if not item or item.item_type != "cosign":
            return

        # 如果已经初始化过（不是 None），跳过
        if item.cosign_designated_signers is not None:
            return

        signers = parse_designated_signers(item.assignee_email_prefix or "")
        requires_xiangxin = XIANGXIN_PREFIX in signers

        item.cosign_designated_signers = json.dumps(signers)
        item.cosign_replied_signers = json.dumps([])
        item.cosign_requires_xiangxin = requires_xiangxin
        item.cosign_blocked = False
        item.cosign_auto_complete_at = None  # NULL 表示尚未计划
        item.cosign_payment_confirmed = False

        await db.commit()
        logger.info(
            f"初始化会签追踪: wi={work_item_id}, signers={signers}, "
            f"requires_xiangxin={requires_xiangxin}"
        )


async def update_cosign_tracking(
    work_item_id: int,
    sender_prefix: str,
    reply_analysis: Dict,
    email_subject: str = "",
    reply_body: str = "",
):
    """
    更新会签追踪（收到回复邮件后调用）。

    逻辑：
    1. 规则3（最高）：回复提到向总 → blocked=True，永不自动完成
    2. 支付确认规则：回复包含"已完成支付"等 → 标记支付确认 + 24h后自动完成
       （xiangxin 回复非"同意"内容则阻止）
    3. 规则1：有指定会签人 → 所有会签人简单批示 → 24h后自动完成
    4. xiangxin 特殊逻辑：回复"同意"不阻止自动完成，回复其他内容阻止
    5. 非指定会签人的其他人回复，不影响自动完成机制
    """
    async with async_session() as db:
        result = await db.execute(
            select(WorkItem).where(WorkItem.id == work_item_id)
        )
        item = result.scalar_one_or_none()
        if not item or item.item_type != "cosign":
            return

        # 如果已经被自动完成了或取消了，不再处理
        if item.status in (WorkItemStatus.completed, WorkItemStatus.cancelled):
            return

        is_simple = reply_analysis.get("is_simple_approval", False)
        mentions_xiangxin = reply_analysis.get("mentions_xiangxin", False)
        sender = sender_prefix.lower().strip()

        # 规则3（最高优先级）: 任何邮件提到向总会签/指导/确认 → 阻止自动完成
        if mentions_xiangxin:
            if not item.cosign_blocked:
                item.cosign_blocked = True
                item.cosign_auto_complete_at = None
                await db.commit()
                logger.info(f"会签 #{work_item_id} 因提到向总而阻止自动完成")
            return

        # xiangxin 特殊逻辑：回复"同意"不阻止，回复其他内容阻止
        if sender == XIANGXIN_PREFIX:
            if is_simple:
                # xiangxin 回复"同意" → 不阻止自动完成
                logger.info(f"会签 #{work_item_id} xiangxin 回复同意，不阻止自动完成")
            else:
                # xiangxin 回复非"同意"内容 → 阻止自动完成
                if not item.cosign_blocked:
                    item.cosign_blocked = True
                    item.cosign_auto_complete_at = None
                    await db.commit()
                    logger.info(f"会签 #{work_item_id} xiangxin 实质性回复，阻止自动完成")
                return

        # 支付确认检测：回复中包含"已完成支付""已给支票"等表述
        reply_text = extract_reply_text(reply_body) if reply_body else ""
        if detect_payment_confirmation(reply_text):
            if not item.cosign_payment_confirmed:
                item.cosign_payment_confirmed = True
                if not item.cosign_blocked and not item.cosign_auto_complete_at:
                    item.cosign_auto_complete_at = datetime.utcnow() + timedelta(hours=24)
                    await db.commit()
                    logger.info(f"会签 #{work_item_id} 检测到支付确认，计划24h后自动完成")
                else:
                    await db.commit()
                    logger.info(f"会签 #{work_item_id} 检测到支付确认，但已被阻止或已计划自动完成")
            return  # 支付确认后不再执行后续规则

        # 规则1：有指定会签人的情况
        designated = json.loads(item.cosign_designated_signers or "[]")

        if designated:
            if sender in designated and is_simple:
                # 是指定会签人的简单批示 → 记录
                replied = json.loads(item.cosign_replied_signers or "[]")
                if sender not in replied:
                    replied.append(sender)
                    item.cosign_replied_signers = json.dumps(replied)

                # 检查是否所有指定会签人都已回复
                all_replied = all(s in replied for s in designated)
                if all_replied and not item.cosign_auto_complete_at:
                    item.cosign_auto_complete_at = datetime.utcnow() + timedelta(hours=24)
                    await db.commit()
                    logger.info(
                        f"会签 #{work_item_id} 所有会签人已回复，计划24h后自动完成"
                    )
                else:
                    await db.commit()
            elif sender in designated and not is_simple:
                # 指定会签人的实质性回复 → 取消自动完成
                if item.cosign_auto_complete_at:
                    item.cosign_auto_complete_at = None
                    await db.commit()
                    logger.info(f"会签 #{work_item_id} 指定会签人 {sender} 实质性回复，取消自动完成")
            # 非指定会签人的回复不影响自动完成机制


async def check_and_auto_complete_cosign() -> List[int]:
    """
    检查并执行到期的会签自动完成。
    返回被自动完成的工作项 ID 列表。
    """
    completed_ids = []
    now = datetime.utcnow()

    async with async_session() as db:
        result = await db.execute(
            select(WorkItem).where(
                WorkItem.item_type == "cosign",
                WorkItem.status != WorkItemStatus.completed,
                WorkItem.status != WorkItemStatus.cancelled,
                WorkItem.cosign_auto_complete_at.isnot(None),
                WorkItem.cosign_auto_complete_at <= now,
                WorkItem.cosign_blocked == False,  # noqa: E712
            )
        )
        items = result.scalars().all()

        for item in items:
            old_status = item.status
            item.status = WorkItemStatus.completed
            item.updated_at = now
            ts = now.strftime('%Y-%m-%d %H:%M')

            # 根据自动完成原因生成不同的消息
            if item.cosign_payment_confirmed:
                item.latest_progress = (
                    f"[系统自动完成] 支付确认后24小时内无异议，系统自动标记完成 ({ts})"
                )
                remark = "会签自动完成：支付确认后24小时内无异议"
            else:
                item.latest_progress = (
                    f"[系统自动完成] 会签人已批复完毕，24小时无异议后系统自动标记完成 ({ts})"
                )
                remark = "会签自动完成：所有会签人24小时内无异议"

            # 记录状态变更日志
            log = StatusChangeLog(
                work_item_id=item.id,
                old_status=old_status,
                new_status="completed",
                operator_id=None,
                remark=remark,
            )
            db.add(log)
            completed_ids.append(item.id)
            logger.info(f"会签 #{item.id} 「{item.title[:40]}」已自动完成")

        if completed_ids:
            await db.commit()

    return completed_ids


async def backfill_existing_cosign_items():
    """为已有的 cosign 工作项初始化追踪字段（一次性迁移）"""
    async with async_session() as db:
        result = await db.execute(
            select(WorkItem).where(
                WorkItem.item_type == "cosign",
                WorkItem.cosign_designated_signers.is_(None),
            )
        )
        items = result.scalars().all()

        count = 0
        for item in items:
            signers = parse_designated_signers(item.assignee_email_prefix or "")
            requires_xiangxin = XIANGXIN_PREFIX in signers
            item.cosign_designated_signers = json.dumps(signers)
            item.cosign_replied_signers = json.dumps([])
            item.cosign_requires_xiangxin = requires_xiangxin
            item.cosign_blocked = False
            item.cosign_auto_complete_at = None
            item.cosign_payment_confirmed = False
            count += 1

        if count > 0:
            await db.commit()
            logger.info(f"已为 {count} 个已有会签工作项初始化追踪字段")

async def migrate_add_payment_column():
    """为 work_items 表添加 cosign_payment_confirmed 列（如果不存在）"""
    from database import engine
    import aiosqlite

    db_url = str(engine.url).replace("sqlite+aiosqlite:///", "")
    try:
        async with aiosqlite.connect(db_url) as db:
            cursor = await db.execute("PRAGMA table_info(work_items)")
            columns = [row[1] for row in await cursor.fetchall()]

            if "cosign_payment_confirmed" not in columns:
                await db.execute(
                    "ALTER TABLE work_items ADD COLUMN cosign_payment_confirmed BOOLEAN DEFAULT 0"
                )
                logger.info("已为 work_items 表添加 cosign_payment_confirmed 列")
            else:
                logger.info("cosign_payment_confirmed 列已存在，跳过迁移")
    except Exception as e:
        logger.error(f"数据库迁移失败: {e}", exc_info=True)
