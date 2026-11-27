"""统一数据范围（2026-11-27）

考核项（待考核项目）与工作项共用同一套可见范围口径，避免两处各写一套：

| 角色 | 可见范围 |
|---|---|
| 管理员 / 总裁 / 监察主任(L6) / 集团总监(L7) | 全集团 |
| 人事/商务部经理(L3，按档案所属区域) | 本区域，且主办人等级 ≤ 区总(L4) |
| 区总(L4) | 本区域，且主办人等级 ≤ 区总(L4) |
| 部门总监(L5) | 本部门全部 |
| 其他部门经理(L3) | 本人主办 + 本部门专员(L2)主办 |
| 各部门专员(L2 及以下) | 本人主办 |

补充口径：
- 工作项额外保留「本人是负责人(assignee)」可见，考核项只看主办人。
- 人事/商务部保留全集团写权限（编辑/改状态/补录），仅列表可见范围收窄。
- 主办人等级按 users.role_level（主角色）判断；工作项无主办人时，区域口径下视为可见。
"""

from typing import List, Optional

from sqlalchemy import and_, or_, select

from models import RoleLevel, User, WorkItem

HR_COMMERCE_DEPT_ID = 1          # 人事/商务部
HONGKONG_DISTRICT_ID = 1         # 未分配区域的兜底


def _user_roles(user: User) -> List[dict]:
    """主角色 + 副角色，统一成 {level, department_id, district_id}"""
    roles = [{
        "level": user.role_level or 0,
        "department_id": user.department_id,
        "district_id": user.district_id,
    }]
    for sr in (user.secondary_roles or []):
        if not isinstance(sr, dict):
            continue
        try:
            lv = int(sr.get("role_level") or 0)
        except (TypeError, ValueError):
            lv = 0
        roles.append({
            "level": lv,
            "department_id": sr.get("department_id"),
            "district_id": sr.get("district_id"),
        })
    return roles


def _role_str(user: User) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


def resolve_scope(user: User) -> dict:
    """解析用户数据范围。

    返回：
      all       是否全集团
      write_all 是否全集团可写（人事/商务部保留）
      clauses   [{"type": "dept"|"district", "dept_id"/"district_id", "cap": 主办人等级上限|None}]
      dept_ids / district_ids  兼容旧调用方的扁平集合
      top_level 有效最高等级
    """
    roles = _user_roles(user)
    top_level = max((r["level"] for r in roles), default=0)

    if _role_str(user) in ("admin", "president") or top_level >= RoleLevel.REGULATOR:
        return {
            "all": True, "write_all": True, "clauses": [],
            "dept_ids": set(), "district_ids": set(), "top_level": top_level,
        }

    clauses: List[dict] = []
    write_all = False
    dept_ids: set = set()
    district_ids: set = set()

    for r in roles:
        lv = r["level"]
        dept = r["department_id"]
        dist = r["district_id"]

        if lv >= RoleLevel.REGULATOR:
            return {
                "all": True, "write_all": True, "clauses": [],
                "dept_ids": set(), "district_ids": set(), "top_level": top_level,
            }

        if lv >= RoleLevel.DEPT_DIRECTOR and dept:
            # 部门总监：本部门全部
            clauses.append({"type": "dept", "dept_id": dept, "cap": None})
            dept_ids.add(dept)
        elif lv == RoleLevel.DISTRICT_MANAGER and dist:
            # 区总：本区域，主办人等级 ≤ 区总
            clauses.append({"type": "district", "district_id": dist,
                            "cap": RoleLevel.DISTRICT_MANAGER})
            district_ids.add(dist)
        elif lv == RoleLevel.MANAGER and dept:
            if dept == HR_COMMERCE_DEPT_ID:
                # 人事/商务部经理：本区域全部（主办人等级 ≤ 区总），写权限全集团
                write_all = True
                if dist:
                    clauses.append({"type": "district", "district_id": dist,
                                    "cap": RoleLevel.DISTRICT_MANAGER})
                    district_ids.add(dist)
            else:
                # 其他部门经理：本人主办 + 本部门专员(L2)主办
                clauses.append({"type": "dept", "dept_id": dept,
                                "cap": RoleLevel.STAFF})
                dept_ids.add(dept)
        elif dept == HR_COMMERCE_DEPT_ID:
            # 人事/商务部专员：可见只本人，但保留全集团写权限
            write_all = True

    return {
        "all": False, "write_all": write_all, "clauses": clauses,
        "dept_ids": dept_ids, "district_ids": district_ids, "top_level": top_level,
    }


def sponsor_level_condition(cap: int, include_null: bool = False):
    """主办人等级 ≤ cap 的条件（按 users.role_level 主角色）"""
    conds = [
        WorkItem.sponsor_id.in_(
            select(User.id).where(User.role_level <= cap)
        )
    ]
    if include_null:
        conds.append(WorkItem.sponsor_id.is_(None))
    return or_(*conds)


def district_condition(district_ids: List[int]):
    """工作项区域条件；未分配区域按香港处理"""
    conds = [WorkItem.district_id.in_(list(district_ids))]
    if HONGKONG_DISTRICT_ID in district_ids:
        conds.append(WorkItem.district_id.is_(None))
    return or_(*conds)


def scope_conditions(user: User, scope: Optional[dict] = None,
                     include_assignee: bool = True):
    """把数据范围转成 SQL 条件列表；全集团返回 None。

    include_assignee: 工作项传 True（本人负责也可见），考核项传 False。
    """
    scope = scope or resolve_scope(user)
    if scope["all"]:
        return None

    conds = [WorkItem.sponsor_id == user.id]
    if include_assignee:
        conds.append(WorkItem.assignee_id == user.id)

    for c in scope["clauses"]:
        if c["type"] == "dept":
            parts = [WorkItem.department_id == c["dept_id"]]
            if c["cap"] is not None:
                parts.append(sponsor_level_condition(
                    c["cap"], include_null=c["cap"] >= RoleLevel.DISTRICT_MANAGER))
            conds.append(and_(*parts))
        elif c["type"] == "district":
            parts = [district_condition([c["district_id"]])]
            if c["cap"] is not None:
                parts.append(sponsor_level_condition(
                    c["cap"], include_null=c["cap"] >= RoleLevel.DISTRICT_MANAGER))
            conds.append(and_(*parts))

    return conds


def item_in_scope(item, user: User, scope: Optional[dict] = None,
                  sponsor_level: Optional[int] = None,
                  include_assignee: bool = True) -> bool:
    """单条记录是否在用户数据范围内（写操作校验用）"""
    scope = scope or resolve_scope(user)
    if scope["all"] or scope.get("write_all"):
        return True
    if item.sponsor_id == user.id:
        return True
    if include_assignee and item.assignee_id == user.id:
        return True

    if sponsor_level is None:
        sponsor_level = -1 if item.sponsor_id is None else None
        if sponsor_level is None:
            sp = getattr(item, "sponsor", None)
            if sp is not None:
                sponsor_level = sp.role_level or 0
            else:
                sponsor_level = 0

    for c in scope["clauses"]:
        cap = c["cap"]
        if cap is not None:
            if sponsor_level < 0:
                # 无主办人：仅在区域口径（cap ≥ 区总）下视为可见
                if cap < RoleLevel.DISTRICT_MANAGER:
                    continue
            elif sponsor_level > cap:
                continue
        if c["type"] == "dept":
            if item.department_id == c["dept_id"]:
                return True
        elif c["type"] == "district":
            item_dist = item.district_id or HONGKONG_DISTRICT_ID
            if item_dist == c["district_id"]:
                return True
    return False


def delegate_district_ids(user: User) -> List[int]:
    """可代发起考核的区域：人事/商务部经理 = 本区域全部（不限主办人等级）"""
    ids = set()
    for r in _user_roles(user):
        if r["level"] == RoleLevel.MANAGER and r["department_id"] == HR_COMMERCE_DEPT_ID and r["district_id"]:
            ids.add(r["district_id"])
    return list(ids)


def is_hr_manager(user: User) -> bool:
    """是否人事/商务部经理（L3）"""
    return any(
        r["level"] == RoleLevel.MANAGER and r["department_id"] == HR_COMMERCE_DEPT_ID
        for r in _user_roles(user)
    )
