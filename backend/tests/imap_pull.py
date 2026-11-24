"""IMAP 历史回填 —— 只读方式把某段时间的真实邮件灌进当前实例的库。

用途：沙箱实例与生产共用同一邮箱时，用本脚本把生产已处理过的邮件
      按日期窗口重新跑一遍新逻辑，用于和生产的旧结果做差距对比。

安全要点：
  - INBOX 以 readonly 打开，绝不改动 \\Seen 等标志，生产实例收件不受影响
  - 已入库的 Message-ID 自动跳过（幂等，可重复跑）
  - 按 Date 升序（IMAP 序列号天然最旧优先），保证父邮件先于回复入库

用法（在容器内执行，DATABASE_URL 决定写哪个库）：
    # 先看会处理多少封，不入库
    docker exec -w /app/backend gws-sandbox python tests/imap_pull.py --days 7 --dry-run

    # 真正回填（默认最多 100 封）
    docker exec -w /app/backend gws-sandbox python tests/imap_pull.py --days 7 --limit 100

    # 指定配置 id / 指定库
    docker exec -w /app/backend gws-sandbox python tests/imap_pull.py --config-id 1 --limit 300
"""
import argparse
import asyncio
import email
import os
import sys
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
sys.path.insert(0, _BACKEND)
os.environ.setdefault("DEBUG", "false")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="回溯天数（SINCE 今天-N 天）")
    ap.add_argument("--limit", type=int, default=100, help="本次最多处理多少封（最旧优先）")
    ap.add_argument("--config-id", type=int, help="指定 email_configs.id，默认取第一个启用的")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不入库")
    args = ap.parse_args()

    from sqlalchemy import select  # noqa: E402
    import services.email_service as es  # noqa: E402
    from database import async_session  # noqa: E402
    from models import EmailConfig, EmailLog, WorkItem  # noqa: E402

    async with async_session() as db:
        q = select(EmailConfig)
        if args.config_id:
            q = q.where(EmailConfig.id == args.config_id)
        else:
            q = q.where(EmailConfig.is_active == True)  # noqa: E712
        cfg = (await db.execute(q)).scalars().first()
    if not cfg:
        print("没有可用的邮箱配置（email_configs 为空或未启用）")
        return 1
    print(f"邮箱配置: {cfg.email_address} @ {cfg.imap_host}:{cfg.imap_port}")

    loop = asyncio.get_event_loop()
    mail = await loop.run_in_executor(None, es._imap_connect, cfg, True)  # 只读
    if not mail:
        print("IMAP 连接失败")
        return 1

    since = (datetime.utcnow() - timedelta(days=args.days)).strftime("%d-%b-%Y")
    _, messages = mail.search(None, f'(SINCE "{since}")')
    ids = messages[0].split() if messages and messages[0] else []
    print(f"SINCE {since}：共 {len(ids)} 封（只读，不改任何邮件标志）")
    if not ids:
        mail.logout()
        return 0

    todo = ids[: args.limit]
    if args.dry_run:
        print(f"--dry-run：本次会尝试处理最旧的 {len(todo)} 封，未入库")
        mail.logout()
        return 0

    async with async_session() as db:
        n_items0 = (await db.execute(select(WorkItem.id))).scalars().all()
        n_logs0 = (await db.execute(select(EmailLog.id))).scalars().all()
    print(f"开始回填：处理 {len(todo)} 封，当前库有工作项 {len(n_items0)} 个 / 邮件日志 {len(n_logs0)} 条\n")

    ok = skipped = failed = 0
    for i, eid in enumerate(todo, 1):
        try:
            _, msg_data = mail.fetch(eid, "(RFC822)")
            if not (msg_data and msg_data[0]):
                failed += 1
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            subject = es._decode_str(msg.get("Subject"))
            from_addr = es._decode_str(msg.get("From"))
            to_addrs = es._decode_str(msg.get("To"))
            cc_addrs = es._decode_str(msg.get("Cc"))
            date_str = msg.get("Date", "")
            message_id = msg.get("Message-ID", f"unknown-{datetime.utcnow().timestamp()}")
            in_reply_to = es._decode_str(msg.get("In-Reply-To", ""))
            references = es._decode_str(msg.get("References", ""))
            body = es._get_email_body(msg)

            if not subject or not body:
                skipped += 1
                print(f"[{i}/{len(todo)}] （跳过：主题或正文为空）{subject[:40]}")
                continue

            if await es._message_id_exists(message_id):
                skipped += 1
                continue

            await es._process_email_with_retry(
                cfg, message_id, subject, from_addr, date_str, body,
                to_addrs, cc_addrs, in_reply_to=in_reply_to, references=references,
            )
            ok += 1

            async with async_session() as db:
                row = (await db.execute(
                    select(EmailLog).where(EmailLog.message_id == message_id)
                )).scalar_one_or_none()
                tag = ""
                if row and row.work_item_id:
                    item = (await db.execute(
                        select(WorkItem).where(WorkItem.id == row.work_item_id)
                    )).scalar_one_or_none()
                    if item:
                        tag = f"→ #{item.id} [{item.item_type}/{item.status}] {item.title[:30]}"
                if not tag:
                    tag = "→ 未建项"
            print(f"[{i}/{len(todo)}] {subject[:42]:<42} {tag}")
        except Exception as ex:
            failed += 1
            print(f"[{i}/{len(todo)}] 处理异常: {type(ex).__name__}: {ex}")

    mail.logout()

    async with async_session() as db:
        n_items1 = (await db.execute(select(WorkItem.id))).scalars().all()
        n_logs1 = (await db.execute(select(EmailLog.id))).scalars().all()
    print(f"\n完成：成功 {ok} 封 / 跳过 {skipped} 封 / 失败 {failed} 封")
    print(f"邮件日志 {len(n_logs0)} → {len(n_logs1)}；工作项 {len(n_items0)} → {len(n_items1)}"
          f"（合并 {len(n_logs1) - len(n_logs0) - (len(n_items1) - len(n_items0))} 封）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
