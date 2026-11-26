"""
会签规则回填脚本（2026-11-26）

规则：
  1) 1000 元以内的本地报销/审批 → 签署人收敛为区总；区总本人发起 → 收敛为财务部审批人；
  2) 本地区总（非发起人）已在往来邮件中明确批示 → 签署人收敛为区总一人；
  3) 签署人的批示可能散落在：建项邮件正文、引用的历史回复、同项其他邮件 → 一律计入已签。

用法：
  python tests/repair_small_amount_cosign.py --dry-run
  python tests/repair_small_amount_cosign.py --apply
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from database import async_session  # noqa: E402
from models import WorkItem, WorkItemStatus, EmailLog, User  # noqa: E402
from services.cosign_service import (  # noqa: E402
    DISTRICT_DIRECTOR_LEVEL,
    XIANGXIN_PREFIX,
    _simple_cosign_analysis,
    detect_director_approval,
    detect_quoted_reply_signers,
    detect_stated_approvals,
    extract_amount,
    extract_reply_text,
    extract_sender_prefix,
    parse_designated_signers,
    resolve_small_amount_signers,
)


async def run(apply: bool):
    stat = {"收敛签署人": 0, "区总批示收敛": 0, "补记已签": 0, "排定24h": 0, "被阻止跳过": 0}
    async with async_session() as db:
        items = (await db.execute(
            select(WorkItem).where(
                WorkItem.item_type == "cosign",
                WorkItem.status == WorkItemStatus.pending,
            )
        )).scalars().all()

        for item in items:
            sponsor = await db.get(User, item.sponsor_id) if item.sponsor_id else None
            sponsor_prefix = (sponsor.email_prefix or "").lower() if sponsor else ""
            district_id = (sponsor.district_id if sponsor and sponsor.district_id else item.district_id)

            signers = parse_designated_signers(item.assignee_email_prefix or "")
            changes = []

            logs = (await db.execute(
                select(EmailLog).where(EmailLog.work_item_id == item.id).order_by(EmailLog.received_at)
            )).scalars().all()
            create_log = next((l for l in logs if l.message_id and l.message_id == item.message_id), None)

            # 规则一：小额本地事项收敛
            new_signers = await resolve_small_amount_signers(db, item)
            # 规则二：区总已批示（非发起人）→ 收敛为区总一人
            if not new_signers:
                for log in logs:
                    if not log.body:
                        continue
                    prefix = extract_sender_prefix(log.from_addr or "")
                    if not prefix or prefix == sponsor_prefix:
                        continue
                    if not _simple_cosign_analysis(extract_reply_text(log.body)).get("is_simple_approval"):
                        continue
                    u = (await db.execute(
                        select(User).where(User.email_prefix == prefix, User.is_active == True)
                    )).scalars().first()
                    if u and u.role_level == DISTRICT_DIRECTOR_LEVEL and u.district_id == district_id:
                        new_signers = [prefix]
                        stat["区总批示收敛"] += 1
                        break
            if new_signers and new_signers != signers:
                changes.append(f"签署人 {signers} → {new_signers}")
                signers = new_signers
                stat["收敛签署人"] += 1

            # 规则三：汇总所有已表态的签署人
            replied = []
            if create_log and create_log.body:
                for p in await detect_stated_approvals(db, signers, create_log.body):
                    replied.append(p)
                for p in await detect_quoted_reply_signers(db, signers, create_log.body):
                    if p not in replied:
                        replied.append(p)
            for log in logs:
                if not log.body:
                    continue
                prefix = extract_sender_prefix(log.from_addr or "")
                if prefix and prefix in signers and prefix not in replied:
                    if _simple_cosign_analysis(extract_reply_text(log.body)).get("is_simple_approval"):
                        replied.append(prefix)
            old_replied = json.loads(item.cosign_replied_signers or "[]")
            for p in replied:
                if p not in old_replied:
                    changes.append(f"补记已签 {p}")
                    stat["补记已签"] += 1

            if not changes:
                continue

            auto = item.cosign_auto_complete_at
            if item.cosign_blocked:
                stat["被阻止跳过"] += 1
            elif signers and all(s in replied for s in signers) and not auto:
                auto = datetime.utcnow() + timedelta(hours=24)
                stat["排定24h"] += 1

            print(f"#{item.id} {item.title[:36]}")
            print(f"   金额={extract_amount(f'{item.title or ''} {item.content or ''}')} "
                  f"签署人={signers} 已签={replied} blocked={item.cosign_blocked}")
            for c in changes:
                print(f"   - {c}")
            if apply:
                item.cosign_designated_signers = json.dumps(signers)
                item.cosign_replied_signers = json.dumps(replied)
                item.cosign_requires_xiangxin = XIANGXIN_PREFIX in signers
                item.cosign_auto_complete_at = auto

        if apply:
            await db.commit()
            print("\n已写入数据库")
        else:
            print("\n[dry-run] 未写入")
    print("统计:", stat)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(a.apply))
