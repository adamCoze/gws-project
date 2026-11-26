"""主办人自动更正（2026-11-26）

业务口径：
  - 邮件发出人 = 主办人；
  - 事项「交第二人**决定**」（会签 / 审批 / 审核 / 审阅 / 批示 / 复核…）→ 第二人只是审批人，主办人不变；
  - 事项「交第二人**完成**」（完成 / 办理 / 处理 / 发布 / 协助 / 开通 / 提交…）→ 主办人改为具体做事的人。
"""
import logging
import re
from typing import Optional, Tuple

from sqlalchemy import select

from models import StatusChangeLog, User, WorkItem

logger = logging.getLogger(__name__)

# 决定类动词：出现这些说明第二人只是拍板/把关，不改主办人
DECIDE_VERBS = [
    "会签", "审批", "审核", "审阅", "批示", "决定", "批准", "复核",
    "核定", "签署", "确认", "同意", "裁定", "审签", "批复", "把关",
]
# 完成类动词：出现这些说明第二人是实际做事的人，主办人应改为他
DONE_VERBS = [
    "完成", "办理", "处理", "执行", "发布", "协助", "跟进", "落实",
    "制作", "提交", "开通", "上传", "采购", "实施", "对接", "修改",
    "整理", "准备", "撰写", "起草", "盖章", "寄出", "寄送", "发放",
    "派发", "联络", "回覆", "回复",
]
# 指派语气：只有明确"交给某人"才算，避免"与某人沟通"这类噪音
DIRECT_PATTERN = r'(?:请|交由|交|由|要求|需|安排|委托|指派|责成)'


def detect_doer(text: str, doer_name: str) -> Optional[Tuple[str, str]]:
    """
    判断 doer_name 是否被"交办完成"。
    返回 (命中的动词短语, 原文片段)；不命中或属"决定"类返回 None。
    """
    if not text or not doer_name:
        return None
    pattern = DIRECT_PATTERN + r'\s*' + re.escape(doer_name) + r'\s*([^\s，。；,;：:]{0,10})'
    for m in re.finditer(pattern, text):
        verb = m.group(1) or ""
        has_decide = any(k in verb for k in DECIDE_VERBS)
        has_done = any(k in verb for k in DONE_VERBS)
        if has_decide and not has_done:
            return None                      # 交第二人决定 → 不改主办人
        if has_done and not has_decide:
            return verb, m.group(0)
    return None


async def maybe_reassign_sponsor(db, item: WorkItem, text: str) -> bool:
    """
    若正文表明"交负责人完成"，把主办人改为实际做事的人（原主办人转为负责人）。
    返回是否发生变更。
    """
    if not item.assignee_id or not item.sponsor_id:
        return False
    if item.assignee_id == item.sponsor_id:
        return False
    doer = await db.get(User, item.assignee_id)
    if not doer or not doer.real_name:
        return False
    hit = detect_doer(text or "", doer.real_name)
    if not hit:
        return False

    verb, snippet = hit
    old_sponsor = await db.get(User, item.sponsor_id)
    old_name = old_sponsor.real_name if old_sponsor else str(item.sponsor_id)

    item.sponsor_id, item.assignee_id = item.assignee_id, item.sponsor_id
    note = f"[系统] 主办人自动更正：{old_name} → {doer.real_name}（依据：正文「{snippet}」）"
    item.latest_progress = (item.latest_progress + "\n" + note) if item.latest_progress else note
    db.add(StatusChangeLog(
        work_item_id=item.id,
        old_status=item.status.value if hasattr(item.status, "value") else str(item.status),
        new_status=item.status.value if hasattr(item.status, "value") else str(item.status),
        operator_id=None,
        remark=f"主办人自动更正：{old_name} → {doer.real_name}（交办完成「{verb}」）",
    ))
    logger.info(f"工作项 #{item.id} 主办人自动更正 {old_name} → {doer.real_name}（{snippet}）")
    return True
