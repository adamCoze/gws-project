"""离线邮件注入器 —— 不连 IMAP、不调真实 AI，直接喂 RFC822 头信息给 _process_email。

用途：香港服务器没有真实邮件数据，用本脚本在独立测试库上验证
      L1（邮件线程去重）+ L2（状态层）行为是否符合预期。

运行：
    cd backend && python3 tests/offline_inject.py

每次运行都会重建 backend/data/gws_test.db，不触碰生产库 gws.db。
"""
import asyncio
import os
import sys

# 必须在 import database 之前指定测试库
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
sys.path.insert(0, _BACKEND)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + os.path.join(_BACKEND, "data", "gws_test.db")
os.environ["DEBUG"] = "false"

import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from sqlalchemy import select, func  # noqa: E402

import services.email_service as es  # noqa: E402
from database import Base, engine, async_session  # noqa: E402
from models import WorkItem, EmailLog, StatusChangeLog, WorkItemStatus  # noqa: E402


# ────────────────────────── AI 桩 ──────────────────────────
# 场景脚本：按主题关键词决定 AI 返回，模拟真实 AI 判定
_AI_SCRIPT = {}


def _ai_for(subject: str, body: str):
    # 长关键词优先匹配，避免「周报」抢走「会签」这类场景串味
    for kw in sorted(_AI_SCRIPT.keys(), key=len, reverse=True):
        if kw in subject or kw in body:
            payload = dict(_AI_SCRIPT[kw])
            if payload.get("summary") == "AUTO":
                payload["summary"] = body[:200]
            return payload
    return {
        "type": "task",
        "title": subject[:60],
        "summary": body[:200],
        "department": "行政/产品部",
        "assignee_prefix": None,
        "due_date": None,
        "completion_assessment": "in_progress",
        "is_confidential": False,
    }


async def fake_analyze_email_with_ai(subject, body, to_addrs="", cc_addrs=""):
    return _ai_for(subject, body)


_cosign_calls = []


async def fake_update_cosign_tracking(work_item_id, sender_prefix, reply_analysis, subject, reply_body=""):
    _cosign_calls.append((work_item_id, sender_prefix, subject))


async def fake_initialize_cosign_tracking(work_item_id, *a, **kw):
    _cosign_calls.append((work_item_id, "INIT", ""))


async def fake_analyze_cosign_reply(subject, body):
    return {"is_simple_reply": True, "sentiment": "agree", "raw": body[:50]}


async def fake_cache_url(*a, **kw):
    return None


es.analyze_email_with_ai = fake_analyze_email_with_ai
es._cache_email_url_for_recipients = fake_cache_url
es.update_cosign_tracking = fake_update_cosign_tracking
es.initialize_cosign_tracking = fake_initialize_cosign_tracking
es.analyze_cosign_reply = fake_analyze_cosign_reply


# ────────────────────────── 工具 ──────────────────────────
_results = []


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  [{detail}]" if detail and not cond else ""))


async def send(subject, body, msg_id, in_reply_to="", references="", frm="Adam Wang <adam.wang@ntg.com.hk>"):
    """模拟收到一封邮件"""
    r = await es._process_email(
        message_id=msg_id,
        subject=subject,
        from_addr=frm,
        date_str="2026-11-23 10:00:00",
        body=body,
        retry_count=0,
        to_addrs="gws@ntg.com.hk",
        cc_addrs="",
        in_reply_to=in_reply_to,
        references=references,
    )
    return r


async def count_items():
    async with async_session() as db:
        r = await db.execute(select(func.count()).select_from(WorkItem))
        return r.scalar_one()


async def all_items():
    async with async_session() as db:
        r = await db.execute(select(WorkItem).order_by(WorkItem.id))
        return list(r.scalars().all())


async def item_by_title(kw):
    async with async_session() as db:
        r = await db.execute(select(WorkItem).where(WorkItem.title.contains(kw)))
        return r.scalars().first()


async def set_status(item_id, status):
    async with async_session() as db:
        r = await db.execute(select(WorkItem).where(WorkItem.id == item_id))
        it = r.scalar_one()
        it.status = status
        await db.commit()


# ────────────────────────── 场景 ──────────────────────────
async def scene_thread_dedup():
    print("\n【场景1】同一邮件串 5 封（含改标题 / 加 Re: / 加部门前缀 / 缺 References）")
    _AI_SCRIPT["采购电话号码"] = {
        "type": "task", "title": "上海地区采购电话号码", "summary": "请提供上海地区可用电话号段",
        "department": "行政/产品部", "assignee_prefix": None, "due_date": None,
        "completion_assessment": "in_progress", "is_confidential": False,
    }
    before = await count_items()
    await send("上海地区采购电话号码", "请提供上海地区可用电话号段", "<m1@ntg>")
    await send("Re: 上海地区采购电话号码", "已联系电信", "<m2@ntg>", "<m1@ntg>", "<m1@ntg>")
    await send("Re: Re: 上海地区采购电话号码", "号段清单见附件", "<m3@ntg>", "<m2@ntg>", "<m1@ntg> <m2@ntg>")
    # 改标题 + 加部门前缀（真实数据里就是这种把同串拆成多项）
    await send("回复: 上海地区采购电话号码（行政部）", "再补充一个号码", "<m4@ntg>",
               "<m3@ntg>", "<m1@ntg> <m2@ntg> <m3@ntg>")
    # 只有 In-Reply-To、没有 References（走「引用链反查」）
    await send("Re: 上海地区采购电话号码（行政部）", "收到，谢谢", "<m5@ntg>", "<m4@ntg>")

    after = await count_items()
    check("5 封同串邮件只生成 1 个工作项", after - before == 1, f"新增 {after - before} 个")

    it = await item_by_title("采购电话号码")
    check("thread_id 落在根邮件 Message-ID", it and it.thread_id == "<m1@ntg>", f"thread_id={it.thread_id if it else None}")

    async with async_session() as db:
        r = await db.execute(select(EmailLog).where(EmailLog.work_item_id == it.id))
        logs = list(r.scalars().all())
    check("5 封邮件全部挂到同一工作项", len(logs) == 5, f"{len(logs)} 封")
    check("email_logs 记录了 in_reply_to", any(l.in_reply_to for l in logs))
    check("email_logs 记录了 references", any(l.references_header for l in logs))

    # 反例：不同主题、无引用链 → 应该新建
    await send("关于办公室搬迁的通知", "下月搬至新址", "<m6@ntg>")
    after2 = await count_items()
    check("无关新邮件仍新建工作项", after2 - after == 1, f"新增 {after2 - after} 个")


async def scene_report():
    print("\n【场景2】汇报类：AI 误判为 task，靠关键词兜底纠正；收到回复不复活")
    _AI_SCRIPT["周报"] = {
        "type": "task",  # 故意让 AI 判错
        "title": "11月第三周周报", "summary": "本周完成 3 项",
        "department": "行政/产品部", "assignee_prefix": None, "due_date": None,
        "completion_assessment": "in_progress", "is_confidential": False,
    }
    await send("11月第三周周报", "本周完成 3 项", "<r1@ntg>")
    it = await item_by_title("周报")
    check("含「周报」被纠正为 report", it and it.item_type == "report", f"type={it.item_type if it else None}")
    check("汇报类建单即 completed", it and it.status == WorkItemStatus.completed.value, f"status={it.status if it else None}")

    _AI_SCRIPT["补充一版数据"] = {
        "type": "task", "title": "11月第三周周报", "summary": "AUTO",
        "department": "行政/产品部", "assignee_prefix": None, "due_date": None,
        "completion_assessment": "in_progress", "is_confidential": False,
    }
    await send("Re: 11月第三周周报", "补充一版数据，请以这版为准", "<r2@ntg>", "<r1@ntg>", "<r1@ntg>")
    it = await item_by_title("周报")
    check("汇报收到回复仍保持 completed", it.status == WorkItemStatus.completed.value, f"status={it.status}")
    check("汇报打上 has_new_reply 标记", bool(it.has_new_reply))
    check("汇报追加了 latest_progress", "补充一版数据" in (it.latest_progress or ""), f"progress={it.latest_progress}")

    # 会签类不应被关键词兜底抢走
    _AI_SCRIPT["模板修订"] = {
        "type": "cosign", "title": "关于模板修订的会签", "summary": "请会签确认",
        "department": "行政/产品部", "assignee_prefix": "eva.bai", "due_date": None,
        "completion_assessment": "in_progress", "is_confidential": False,
    }
    await send("关于模板修订的会签（附周报格式）", "请会签确认", "<c0@ntg>")
    it = await item_by_title("模板修订")
    check("含「会签」的邮件不被纠正为 report", it and it.item_type == "cosign", f"type={it.item_type if it else None}")


async def scene_task_revive():
    print("\n【场景3】任务类：已完成项收到回复 → 复活；回复本身说完成 → 保持完成")
    _AI_SCRIPT["宽带"] = {
        "type": "task", "title": "宽带及电话迁移", "summary": "申请迁移宽带",
        "department": "行政/产品部", "assignee_prefix": None, "due_date": None,
        "completion_assessment": "in_progress", "is_confidential": False,
    }
    await send("宽带及电话迁移", "申请迁移宽带", "<t1@ntg>")
    it = await item_by_title("宽带")
    await set_status(it.id, WorkItemStatus.completed.value)

    await send("Re: 宽带及电话迁移", "还有一条线路没通，请跟进", "<t2@ntg>", "<t1@ntg>", "<t1@ntg>")
    it = await item_by_title("宽带")
    check("已完成任务收到后续回复被重新打开", it.status == WorkItemStatus.pending.value, f"status={it.status}")
    check("completed_at 已清空", it.completed_at is None)

    async with async_session() as db:
        r = await db.execute(select(StatusChangeLog).where(StatusChangeLog.work_item_id == it.id))
        logs = list(r.scalars().all())
    check("写入了状态变更记录", len(logs) == 1, f"{len(logs)} 条")

    # 回复本身说「已完成」
    _AI_SCRIPT["线路已通"] = {
        "type": "task", "title": "宽带及电话迁移", "summary": "AUTO",
        "department": "行政/产品部", "assignee_prefix": None, "due_date": None,
        "completion_assessment": "completed", "is_confidential": False,
    }
    await set_status(it.id, WorkItemStatus.completed.value)
    await send("Re: 宽带及电话迁移", "线路已通，全部完成", "<t3@ntg>", "<t2@ntg>", "<t1@ntg> <t2@ntg>")
    it = await item_by_title("宽带")
    check("回复本身表示完成 → 不再重复复活", it.status == WorkItemStatus.completed.value, f"status={it.status}")


async def scene_cosign():
    print("\n【场景4】会签类：状态不由 L2 改动，回复交给会签追踪")
    _AI_SCRIPT["用章"] = {
        "type": "cosign", "title": "用章申请会签", "summary": "请会签",
        "department": "行政/产品部", "assignee_prefix": "eva.bai", "due_date": None,
        "completion_assessment": "in_progress", "is_confidential": False,
    }
    await send("用章申请会签", "请会签", "<s1@ntg>")
    it = await item_by_title("用章申请")
    await set_status(it.id, WorkItemStatus.completed.value)
    _cosign_calls.clear()
    await send("Re: 用章申请会签", "无异议", "<s2@ntg>", "<s1@ntg>", "<s1@ntg>")
    it = await item_by_title("用章申请")
    check("会签状态不被 L2 改动", it.status == WorkItemStatus.completed.value, f"status={it.status}")
    check("会签回复触发了 cosign 追踪", len(_cosign_calls) >= 1, f"{_cosign_calls}")


async def scene_header_parse():
    print("\n【场景5】邮件头解析边界")
    check("References 多 ID 取第一个为根",
          es._thread_root("<x3@n>", "<x1@n> <x2@n>", "<x2@n>") == "<x1@n>")
    check("无 References 时用 In-Reply-To",
          es._thread_root("<x3@n>", "", "<x2@n>") == "<x2@n>")
    check("都没有时用自身 Message-ID",
          es._thread_root("<x3@n>", "", "") == "<x3@n>")
    check("lookup_ids 去重且含自身",
          es._thread_lookup_ids("<x3@n>", "<x1@n> <x2@n>", "<x2@n>") == ["<x1@n>", "<x2@n>", "<x3@n>"])
    check("畸形 References 不炸",
          es._thread_root("<x1@n>", "not-a-msgid garbage", "") == "<x1@n>")


async def main():
    db_file = os.path.join(_BACKEND, "data", "gws_test.db")
    for suffix in ("", "-wal", "-shm"):
        p = db_file + suffix
        if os.path.exists(p):
            os.remove(p)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"测试库已重建：{db_file}")

    await scene_thread_dedup()
    await scene_report()
    await scene_task_revive()
    await scene_cosign()
    await scene_header_parse()

    ok = sum(1 for _, p, _ in _results if p)
    total = len(_results)
    print(f"\n{'='*60}\n结果：{ok}/{total} 通过")
    if ok != total:
        print("失败项：")
        for n, p, d in _results:
            if not p:
                print(f"  - {n}  {d}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
