"""会签回复回填修复脚本（2026-11-26）

背景：
    会签回复识别此前依赖 AI 判定 is_simple_approval，AI 返回解析异常时降级到关键词，
    而关键词表缺繁体/口语变体（"無異議""没有异议""我无补充"…），导致大量真实签署回复
    被判为"实质性回复"而未写入 cosign_replied_signers，24h 自动完成永远不触发。

做法：
    对每个 status=pending 的会签工作项，重新扫描它自己的回复邮件（email_logs.work_item_id），
    用「关键词判定」重建 cosign_replied_signers；若全部指定会签人都已简单批示，
    则按「最后一封签署回复 + 24h」补写 cosign_auto_complete_at
    （时间已过则由每 10 分钟运行的 check_and_auto_complete_cosign 自动完成）。

用法：
    python tests/repair_cosign_tracking.py --path /app/backend/data/gws.db --dry-run
    python tests/repair_cosign_tracking.py --path /app/backend/data/gws.db --apply
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3

from services.cosign_service import extract_reply_text, extract_sender_prefix, _simple_cosign_analysis


def load_items(conn):
    conn.row_factory = sqlite3.Row
    return list(conn.execute(
        """select id, title, status, message_id, cosign_designated_signers,
                  cosign_replied_signers, cosign_auto_complete_at, cosign_blocked
           from work_items where item_type='cosign' and status='pending' order by id"""
    ))


def replies_of(conn, item_id, own_message_id):
    return list(conn.execute(
        """select id, message_id, from_addr, subject, body, received_at
           from email_logs where work_item_id=? order by received_at, id""",
        (item_id,),
    ))


def analyze_item(conn, item):
    """返回 (replied, last_reply_at, blocked, detail)"""
    designated = json.loads(item["cosign_designated_signers"] or "[]")
    if not designated:
        return [], None, False, "无指定会签人"

    replied, last_at, blocked, detail = [], None, False, []
    for log in replies_of(conn, item["id"], item["message_id"]):
        if item["message_id"] and log["message_id"] == item["message_id"]:
            continue  # 建项那封本身不算回复
        sender = extract_sender_prefix(log["from_addr"] or "")
        text = extract_reply_text(log["body"] or "")
        res = _simple_cosign_analysis(text)
        if res.get("mentions_xiangxin"):
            blocked = True
            detail.append(f"{sender}:提到向总→阻止")
            continue
        if sender in designated and res.get("is_simple_approval"):
            if sender not in replied:
                replied.append(sender)
            last_at = log["received_at"]
            detail.append(f"{sender}:简单批示✓")
        elif sender in designated:
            detail.append(f"{sender}:实质性回复✗")
    return replied, last_at, blocked, "; ".join(detail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="/app/backend/data/gws.db")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        args.dry_run = True

    conn = sqlite3.connect(args.path)
    items = load_items(conn)
    print(f"待处理会签项: {len(items)} 个（{args.path}）\n")

    stat = {"will_complete": 0, "planned": 0, "partial": 0, "none": 0, "blocked": 0}
    changes = []

    for item in items:
        old_replied = json.loads(item["cosign_replied_signers"] or "[]")
        replied, last_at, blocked, detail = analyze_item(conn, item)
        designated = json.loads(item["cosign_designated_signers"] or "[]")

        new_auto = None
        if blocked:
            stat["blocked"] += 1
        elif not designated:
            stat["none"] += 1
        elif all(s in replied for s in designated):
            new_auto = (datetime.fromisoformat(last_at) + timedelta(hours=24)) if last_at else None
            if new_auto and new_auto <= datetime.utcnow():
                stat["will_complete"] += 1
            else:
                stat["planned"] += 1
        elif replied:
            stat["partial"] += 1
        else:
            stat["none"] += 1

        if replied != old_replied or new_auto:
            changes.append((item, replied, new_auto, blocked, detail))
            if args.verbose or new_auto:
                flag = "→立即完成" if (new_auto and new_auto <= datetime.utcnow()) else (
                    f"→计划 {new_auto:%m-%d %H:%M}" if new_auto else "→仅记录")
                print(f"#{item['id']} {item['title'][:32]:32} {old_replied}→{replied} {flag}")
                if detail:
                    print(f"      {detail}")

    print("\n统计：")
    print(f"  可立即自动完成: {stat['will_complete']}")
    print(f"  已排定 24h 后完成: {stat['planned']}")
    print(f"  部分签署（等其余人）: {stat['partial']}")
    print(f"  无有效签署记录: {stat['none']}")
    print(f"  被阻止（提到向总）: {stat['blocked']}")
    print(f"  需更新记录数: {len(changes)}")

    if args.apply and changes:
        for item, replied, new_auto, blocked, _ in changes:
            conn.execute(
                """update work_items set cosign_replied_signers=?,
                       cosign_auto_complete_at=coalesce(?, cosign_auto_complete_at),
                       cosign_blocked=?
                   where id=?""",
                (json.dumps(replied), new_auto.isoformat(sep=" ") if new_auto else None,
                 1 if blocked else item["cosign_blocked"], item["id"]),
            )
        conn.commit()
        print(f"\n已写入 {len(changes)} 条")
    else:
        print("\n[dry-run] 未写入任何数据")


if __name__ == "__main__":
    main()
