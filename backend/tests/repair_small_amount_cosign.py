"""
小额本地事项规则回填脚本（2026-11-26）

规则：
  1) 1000 元以内的本地报销/审批 → 签署人收敛为区总；区总本人发起 → 收敛为财务部审批人；
  2) 建项邮件正文已写明「X同意 / X确认」→ 视为该人已签署。

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
from models import WorkItem, WorkItemStatus, EmailLog  # noqa: E402
from services.cosign_service import (  # noqa: E402
    resolve_small_amount_signers,
    detect_stated_approvals,
    detect_quoted_reply_signers,
    detect_director_approval,
    parse_designated_signers,
    extract_amount,
)


async def run(apply: bool):
    stat = {"收敛签署人": 0, "补记已签": 0, "可立即完成": 0, "排定24h": 0}
    async with async_session() as db:
        items = (await db.execute(
            select(WorkItem).where(
                WorkItem.item_type == "cosign",
                WorkItem.status == WorkItemStatus.pending,
            )
        )).scalars().all()

        for item in items:
            changed = []
            signers = parse_designated_signers(item.assignee_email_prefix or "")
            log0 = None
            if item.message_id:
                log0 = (await db.execute(
                    select(EmailLog).where(EmailLog.message_id == item.message_id)
                )).scalars().first()
            new_signers = await resolve_small_amount_signers(db, item)
            if not new_signers and log0 and log0.body:
                _d = await detect_director_approval(db, item, log0.body)
                if _d and _d not in signers:
                    new_signers = [_d]
            if new_signers and new_signers != signers:
                changed.append(f"签署人 {signers} → {new_signers}")
                signers = new_signers
                stat["收敛签署人"] += 1

            # 建项邮件正文
            log = None
            if item.message_id:
                log = (await db.execute(
                    select(EmailLog).where(EmailLog.message_id == item.message_id)
                )).scalars().first()
            replied = json.loads(item.cosign_replied_signers or "[]")
            if log and log.body:
                found = await detect_stated_approvals(db, signers, log.body)
                for p in await detect_quoted_reply_signers(db, signers, log.body):
                    if p not in found:
                        found.append(p)
                for p in found:
                    if p not in replied:
                        replied.append(p)
                        stat["补记已签"] += 1
                        changed.append(f"补记已签 {p}")

            if not changed:
                continue

            auto = item.cosign_auto_complete_at
            if all(s in replied for s in signers) and signers:
                if not auto:
                    auto = datetime.utcnow() + timedelta(hours=24)
                    stat["排定24h"] += 1
            amount = extract_amount(f"{item.title or ''} {item.content or ''}")
            print(f"#{item.id} {item.title[:34]}")
            print(f"   金额={amount} 签署人={signers} 已签={replied}")
            for c in changed:
                print(f"   - {c}")
            if apply:
                item.cosign_designated_signers = json.dumps(signers)
                item.cosign_replied_signers = json.dumps(replied)
                item.cosign_requires_xiangxin = "xiangxin" in signers
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
