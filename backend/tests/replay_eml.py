"""真实邮件回放器 —— 把导出的 .eml 文件按时间顺序灌进系统，走完整真实链路（含 AI 分析）。

用途：香港服务器没有真实邮件数据。把阿里邮箱导出的 .eml（或手工构造的样例邮件）
      放进一个目录，本脚本按 Date 升序逐封投喂，验证 L1 线程去重 / L2 状态层的真实效果。

用法：
    # 灌进独立测试库（安全，不碰生产数据）
    docker exec -w /app/backend gws-app python tests/replay_eml.py --dir /app/backend/data/emls --db test

    # 灌进生产库（需显式 --yes，脚本会先打印将影响的库）
    docker exec -w /app/backend gws-app python tests/replay_eml.py --dir /app/backend/data/emls --db prod --yes

    # 只解析不入库，检查头信息是否读对
    python tests/replay_eml.py --dir ./emls --dry-run

参数：
    --dir / --file   邮件目录或单个文件（可重复 --file）
    --db             test（默认，data/gws_test.db）| prod（data/gws.db）
    --reset          先清空测试库再灌（仅 --db test 生效）
    --dry-run        只解析并打印头信息，不入库
    --yes            目标为 prod 时的确认开关
"""
import argparse
import asyncio
import email
import glob
import os
import sys
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime

os.environ.setdefault("DEBUG", "false")

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
sys.path.insert(0, _BACKEND)


def _decode(value) -> str:
    if not value:
        return ""
    # 注意：不能先 str(value)，Header.__str__ 会用 ascii/replace 把 8bit 头变成乱码
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                # 未知字符集（如 unknown-8bit）按 utf-8 兜底
                out.append(text.decode("utf-8", errors="replace"))
        else:
            # 未编码的 8bit 头会带 surrogateescape 代理字符，转回原始字节再解
            try:
                out.append(text.encode("utf-8", "surrogateescape").decode("utf-8", errors="replace"))
            except Exception:
                out.append(text)
    return "".join(out).strip()


def parse_eml(path: str) -> dict:
    with open(path, "rb") as f:
        msg = email.message_from_bytes(f.read())
    return {
        "path": path,
        "subject": _decode(msg.get("Subject")),
        "from_addr": _decode(msg.get("From")),
        "to_addrs": _decode(msg.get("To")),
        "cc_addrs": _decode(msg.get("Cc")),
        "message_id": (msg.get("Message-ID") or f"<replay-{os.path.basename(path)}>").strip(),
        "in_reply_to": _decode(msg.get("In-Reply-To")),
        "references": _decode(msg.get("References")),
        "date_str": msg.get("Date", ""),
        "raw": msg,
    }


def sort_key(rec: dict):
    try:
        dt = parsedate_to_datetime(rec["date_str"])
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        return dt
    except Exception:
        return datetime(1970, 1, 1)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir")
    ap.add_argument("--file", action="append", default=[])
    ap.add_argument("--db", choices=["test", "prod"], default="test")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mock-ai", action="store_true", help="用规则桩替代真实 AI（不消耗 AI 额度，仅验证线程/状态逻辑）")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    files = list(args.file)
    if args.dir:
        files += sorted(glob.glob(os.path.join(args.dir, "**", "*.eml"), recursive=True))
        files += sorted(glob.glob(os.path.join(args.dir, "**", "*.EML"), recursive=True))
    if not files:
        print("没有找到 .eml 文件，请用 --dir 或 --file 指定")
        return 1

    records = sorted((parse_eml(p) for p in files), key=sort_key)
    print(f"共 {len(records)} 封邮件，按 Date 升序投喂：\n")
    for i, r in enumerate(records, 1):
        root = r["references"].split()[0] if r["references"] else (r["in_reply_to"] or r["message_id"])
        print(f"[{i}] {r['date_str'][:25]:<25} {r['subject'][:44]:<44} root={root}")

    if args.dry_run:
        print("\n--dry-run：仅解析，未入库")
        return 0

    db_file = os.path.join(_BACKEND, "data", "gws_test.db" if args.db == "test" else "gws.db")
    if args.db == "prod" and not args.yes:
        print(f"\n目标为生产库 {db_file}，需加 --yes 确认")
        return 1
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + db_file
    if args.db == "test" and args.reset:
        for suffix in ("", "-wal", "-shm"):
            p = db_file + suffix
            if os.path.exists(p):
                os.remove(p)
        print(f"\n已清空测试库 {db_file}")

    # 环境变量必须在 import 前设置好，这里才导入业务模块
    from database import Base, engine, async_session  # noqa: E402
    import services.email_service as es  # noqa: E402
    from models import WorkItem, EmailLog  # noqa: E402
    from sqlalchemy import select, func  # noqa: E402

    if args.mock_ai:
        async def _mock_ai(subject, body, to_addrs="", cc_addrs=""):
            low = (subject or "") + (body or "")
            itype = "cosign" if "会签" in low else ("report" if any(k in low for k in ("周报", "月报", "汇报", "汇总", "报告")) else "task")
            return {
                "type": itype,
                "title": (subject or "")[:60],
                "summary": (body or "")[:200],
                "department": "行政/产品部",
                "assignee_prefix": None,
                "due_date": None,
                "completion_assessment": "in_progress",
                "is_confidential": False,
            }
        es.analyze_email_with_ai = _mock_ai
        print("（已启用 --mock-ai：AI 用规则桩替代）")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    before_items = before_logs = 0
    async with async_session() as db:
        before_items = (await db.execute(select(func.count()).select_from(WorkItem))).scalar_one()
        before_logs = (await db.execute(select(func.count()).select_from(EmailLog))).scalar_one()

    class _Cfg:
        email_address = "replay@localhost"

    print(f"\n开始入库（{db_file}）...\n")
    for i, r in enumerate(records, 1):
        body = es._get_email_body(r["raw"])
        result = await es._process_email_with_retry(
            _Cfg(), r["message_id"], r["subject"], r["from_addr"], r["date_str"], body,
            r["to_addrs"], r["cc_addrs"],
            in_reply_to=r["in_reply_to"], references=r["references"],
        )
        async with async_session() as db:
            row = (await db.execute(
                select(EmailLog).where(EmailLog.message_id == r["message_id"])
            )).scalar_one_or_none()
            if row and row.work_item_id:
                item = (await db.execute(
                    select(WorkItem).where(WorkItem.id == row.work_item_id)
                )).scalar_one_or_none()
                tag = f"→ 工作项 #{item.id} [{item.item_type}/{item.status}]" if item else "→ 无工作项"
            else:
                tag = f"→ 处理结果 {result}"
        print(f"[{i}/{len(records)}] {r['subject'][:50]:<50} {tag}")

    async with async_session() as db:
        after_items = (await db.execute(select(func.count()).select_from(WorkItem))).scalar_one()
        after_logs = (await db.execute(select(func.count()).select_from(EmailLog))).scalar_one()
    print(f"\n完成：邮件 {after_logs - before_logs} 封入库，新增工作项 {after_items - before_items} 个"
          f"（去重合并 {after_logs - before_logs - (after_items - before_items)} 封）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
