"""重建考核模块不完整的表（测试环境，表里无数据）
- 保留：assessments, assessment_scores, assessment_operation_logs（已一致）
- 重建：non_assessment_items, assessment_score_participants,
        assessment_attachments, assessment_supplement_requests, assessment_appeals
"""
import sqlite3
import sys
import os

sys.path.insert(0, "/app/backend")

DB_PATH = "/app/backend/data/gws.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 先备份
    backup_path = f"{DB_PATH}.backup_{int(__import__('time').time())}"
    import shutil
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ 已备份数据库到: {backup_path}")

    # 要重建的表（按依赖顺序，先删子表再删父表，再按相反顺序建）
    tables_to_rebuild = [
        "assessment_appeals",
        "assessment_supplement_requests",
        "assessment_attachments",
        "assessment_score_participants",
        "non_assessment_items",
    ]

    # 先全部删除（从子到父）
    for t in tables_to_rebuild:
        cursor.execute(f"DROP TABLE IF EXISTS {t}")
        print(f"🗑️  已删除表: {t}")

    conn.commit()

    # 用 SQLAlchemy create_all 重新建表
    from sqlalchemy import create_engine
    from models import Base  # noqa

    engine = create_engine(f"sqlite:///{DB_PATH}")
    Base.metadata.create_all(bind=engine)
    print("✅ create_all 完成")

    # 验证
    for t in tables_to_rebuild:
        cols = [row[1] for row in cursor.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"  {t}: {cols}")

    conn.close()
    print("\n🎉 全部重建完成")


if __name__ == "__main__":
    main()
