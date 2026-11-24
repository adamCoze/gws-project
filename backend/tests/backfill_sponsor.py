"""主办人回填脚本（2026-11-24）

口径：主办人 = 该工作项线程「第一封邮件」的发件人。
发件人不在系统里（外部客户 / 未建账号的同事）→ 挂到该工作项所属部门的负责人。

只处理 sponsor_id 为空的记录，不动已有主办人。

用法（在容器内跑）：
    # 沙箱库（只读预览）
    docker exec -w /app/backend gws-sandbox python tests/backfill_sponsor.py --dry-run
    # 沙箱库（写入）
    docker exec -w /app/backend gws-sandbox python tests/backfill_sponsor.py --apply
    # 生产库
    docker exec -w /app/backend gws-app python tests/backfill_sponsor.py --dry-run
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime

DB_PATH = "/app/backend/data/gws.db"


def load_users(conn):
    rows = conn.execute(
        "SELECT id, email, real_name, role_level, department_id, secondary_roles, is_active FROM users"
    ).fetchall()
    users = []
    for uid, email, real_name, role_level, dept_id, sec, active in rows:
        try:
            sec_roles = json.loads(sec) if sec else []
        except Exception:
            sec_roles = []
        users.append({
            "id": uid,
            "email": (email or "").strip().lower(),
            "real_name": real_name,
            "role_level": role_level or 0,
            "department_id": dept_id,
            "secondary_roles": sec_roles,
            "is_active": bool(active),
        })
    return users


def pick_dept_leader(users, department_id):
    """本部门内 role_level 最高者（含副角色），同级取 id 最小"""
    if not department_id:
        return None
    best = None
    for u in users:
        in_dept = (u["department_id"] == department_id)
        lvl = (u["role_level"] or 0) if in_dept else -1
        for sr in u["secondary_roles"]:
            try:
                if int(sr.get("department_id") or 0) == int(department_id):
                    in_dept = True
                    lvl = max(lvl, int(sr.get("role_level") or 0))
            except Exception:
                continue
        if not in_dept:
            continue
        if best is None or lvl > best[0]:
            best = (lvl, u["id"])
    return best[1] if best else None


def first_sender(conn, item_id, thread_id, stored_sender):
    """线程内最早一封邮件的发件人；找不到就用工作项上存着的发件人"""
    if thread_id:
        row = conn.execute(
            "SELECT from_addr FROM email_logs WHERE thread_id = ? "
            "ORDER BY received_at ASC, id ASC LIMIT 1",
            (thread_id,),
        ).fetchone()
        if row and row[0]:
            return row[0], "thread_first"
    row = conn.execute(
        "SELECT from_addr FROM email_logs WHERE work_item_id = ? "
        "ORDER BY received_at ASC, id ASC LIMIT 1",
        (item_id,),
    ).fetchone()
    if row and row[0]:
        return row[0], "item_log_first"
    if stored_sender:
        return stored_sender, "stored_sender"
    return None, "none"


def extract_email(addr):
    if not addr:
        return ""
    s = str(addr)
    if "<" in s and ">" in s:
        s = s[s.find("<") + 1:s.rfind(">")]
    return s.strip().lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=DB_PATH)
    ap.add_argument("--dry-run", action="store_true", help="只预览不写库（默认）")
    ap.add_argument("--apply", action="store_true", help="实际写入")
    args = ap.parse_args()
    apply = args.apply and not args.dry_run

    conn = sqlite3.connect(args.path)
    users = load_users(conn)
    by_email = {u["email"]: u["id"] for u in users if u["email"]}
    by_id = {u["id"]: u for u in users}

    items = conn.execute(
        "SELECT id, thread_id, sender_email, department_id, title FROM work_items WHERE sponsor_id IS NULL"
    ).fetchall()
    print(f"库：{args.path}")
    print(f"待处理（sponsor 为空）：{len(items)} 条\n")

    stats = {"thread_first": 0, "item_log_first": 0, "stored_sender": 0, "none": 0}
    hit_sender = 0
    hit_leader = 0
    unresolved = []
    plans = []

    for item_id, thread_id, sender_email, dept_id, title in items:
        addr, src = first_sender(conn, item_id, thread_id, sender_email)
        stats[src] += 1
        email_l = extract_email(addr)
        uid = by_email.get(email_l)
        how = "sender"
        if not uid:
            uid = pick_dept_leader(users, dept_id)
            how = "dept_leader"
        if uid:
            if how == "sender":
                hit_sender += 1
            else:
                hit_leader += 1
            plans.append((item_id, uid, how, email_l, (title or "")[:24]))
        else:
            unresolved.append((item_id, email_l, dept_id, (title or "")[:24]))

    print("发件人来源：", stats)
    print(f"命中发件人本人：{hit_sender} 条")
    print(f"回退部门负责人：{hit_leader} 条")
    print(f"无法认定：{len(unresolved)} 条")
    if unresolved:
        for row in unresolved[:15]:
            print(f"  · #{row[0]} 发件人={row[1] or '(无)'} 部门={row[2]} {row[3]}")

    print("\n前 10 条预览：")
    for item_id, uid, how, email_l, title in plans[:10]:
        u = by_id.get(uid, {})
        print(f"  · #{item_id} → {u.get('real_name') or '?'}({u.get('email')}) [{how}] 发件人={email_l} {title}")

    if not apply:
        print("\n[DRY-RUN] 未写入。加 --apply 执行写入。")
        return 0

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.executemany(
        "UPDATE work_items SET sponsor_id = ? WHERE id = ? AND sponsor_id IS NULL",
        [(uid, item_id) for item_id, uid, _how, _e, _t in plans],
    )
    conn.commit()
    left = conn.execute("SELECT COUNT(*) FROM work_items WHERE sponsor_id IS NULL").fetchone()[0]
    print(f"\n[APPLIED {stamp}] 写入 {len(plans)} 条，剩余 sponsor 为空 {left} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
