"""工作项路由"""
from urllib.parse import quote
import re
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from database import get_db
from models import WorkItem, WorkItemStatus, Department, User, StatusChangeLog, EmailLog, EmailUrlCache
from schemas import (
    WorkItemCreate, WorkItemUpdate, WorkItemOut,
    StatusChangeRequest, StatusChangeLogOut,
    EmailUrlResponse, EmailLinkStatusResponse,
)
from auth import get_current_user, ROLE_LEVELS
from models import RoleType, RoleLevel
from services.alimail_api import get_email_url
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/work-items", tags=["work-items"])

# 人事/商务部ID
HR_COMMERCE_DEPT_ID = 1


async def _upsert_cache(db: AsyncSession, user_email: str, work_item_id: int, conversation_id: Optional[str], status: str):
    """插入或更新邮件URL缓存 - 使用原生SQL确保可靠性"""
    try:
        from sqlalchemy import text as sa_text
        from datetime import datetime as dt
        # 先删除旧记录
        await db.execute(
            sa_text("DELETE FROM email_url_cache WHERE user_email = :email AND work_item_id = :wid"),
            {"email": user_email, "wid": work_item_id}
        )
        # 写入新记录（用Python生成时间，避免SQL函数兼容问题）
        now_str = dt.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            sa_text("INSERT INTO email_url_cache (user_email, work_item_id, conversation_id, status, created_at) VALUES (:email, :wid, :cid, :status, :cat)"),
            {"email": user_email, "wid": work_item_id, "cid": conversation_id, "status": status, "cat": now_str}
        )
        await db.flush()
        logger.info(f"缓存写入: work_item={work_item_id}, user={user_email}, status={status}")
    except Exception as e:
        logger.error(f"缓存写入失败: work_item={work_item_id}, user={user_email}, error={e}")

def _apply_completion_fields(item: WorkItem, old_status: Optional[str], operator_id: int):
    """状态流转时同步 completed_at / completed_by

    手动新建或手动改状态为已完成的工作项，原先不会写入完成时间与完成人，
    导致待考核列表按月份筛选失效、跳过规则无法判断「由谁确认完成」。
    """
    if item.status == "completed" and old_status != "completed":
        if not item.completed_at:
            item.completed_at = datetime.utcnow()
        if not item.completed_by:
            item.completed_by = operator_id
    elif item.status != "completed" and old_status == "completed":
        # 从已完成回退，清空完成信息
        item.completed_at = None
        item.completed_by = None


def _effective_role_level(user: User) -> int:
    """有效角色等级 = 主角色与所有副角色中的最高等级"""
    level = user.role_level or 0
    for sr in (user.secondary_roles or []):
        try:
            lv = int(sr.get("role_level") or 0)
        except (TypeError, ValueError):
            lv = 0
        if lv > level:
            level = lv
    return level


def work_item_scope(user: User) -> dict:
    """工作项数据范围（2026-11-18 引入）

    返回 {all: bool, dept_ids: set, district_ids: set}
    - 全集团：管理员/总裁、L6 监察及以上、人事/商务部（负责全集团补录与状态变更）
    - 部门：本人各角色（主+副）所属部门（L3 经理 / L5 部门总监 / L2 专员看本部门）
    - 区域：L4 区总及以上角色所属区域
    实际过滤时三者取并集，并额外包含「本人主办或本人负责」的工作项。
    """
    roles = [{
        "role_level": user.role_level or 0,
        "department_id": user.department_id,
        "district_id": user.district_id,
    }]
    for sr in (user.secondary_roles or []):
        try:
            lv = int(sr.get("role_level") or 0)
        except (TypeError, ValueError):
            lv = 0
        roles.append({
            "role_level": lv,
            "department_id": sr.get("department_id"),
            "district_id": sr.get("district_id"),
        })

    level = max((r["role_level"] for r in roles), default=0)
    role_str = user.role.value if hasattr(user.role, "value") else str(user.role)

    if role_str in ("admin", "president") or level >= RoleLevel.REGULATOR:
        return {"all": True, "dept_ids": set(), "district_ids": set()}

    if any(r["department_id"] == HR_COMMERCE_DEPT_ID for r in roles):
        return {"all": True, "dept_ids": set(), "district_ids": set()}

    dept_ids = {r["department_id"] for r in roles if r["department_id"]}
    district_ids = {
        r["district_id"] for r in roles
        if r["district_id"] and r["role_level"] >= RoleLevel.DISTRICT_MANAGER
    }
    return {"all": False, "dept_ids": dept_ids, "district_ids": district_ids}


def scope_conditions(user: User, scope: Optional[dict] = None):
    """把数据范围转成 SQL 条件列表；全集团返回 None"""
    scope = scope or work_item_scope(user)
    if scope["all"]:
        return None
    conds = [WorkItem.sponsor_id == user.id, WorkItem.assignee_id == user.id]
    if scope["dept_ids"]:
        conds.append(WorkItem.department_id.in_(list(scope["dept_ids"])))
    if scope["district_ids"]:
        conds.append(WorkItem.district_id.in_(list(scope["district_ids"])))
    return conds


def in_scope(item: WorkItem, user: User, scope: Optional[dict] = None) -> bool:
    """判断单条工作项是否在用户数据范围内（用于写操作校验）"""
    scope = scope or work_item_scope(user)
    if scope["all"]:
        return True
    if item.sponsor_id == user.id or item.assignee_id == user.id:
        return True
    if item.department_id and item.department_id in scope["dept_ids"]:
        return True
    if item.district_id and item.district_id in scope["district_ids"]:
        return True
    return False


async def resolve_district_id(db: AsyncSession, assignee_id: Optional[int],
                              assignee_prefix: Optional[str],
                              sponsor_id: Optional[int]) -> Optional[int]:
    """推导工作项区域：负责人区域 → 负责人邮箱前缀对应账号区域 → 主办人区域 → 默认香港

    2026-11-18 业务口径：没有区域的人/推不出来的工作项，区域一律归香港。
    """
    HONGKONG_DISTRICT_ID = 1
    if assignee_id:
        row = await db.execute(select(User.district_id).where(User.id == assignee_id))
        d = row.scalar_one_or_none()
        if d:
            return d
    if assignee_prefix:
        prefixes = [p.strip() for p in re.split(r"[,\s]+", assignee_prefix.strip()) if p.strip()]
        if prefixes:
            rows = await db.execute(
                select(User.district_id).where(User.email_prefix.in_(prefixes))
            )
            districts = {r[0] for r in rows.all() if r[0]}
            if len(districts) == 1:
                return districts.pop()
    if sponsor_id:
        row = await db.execute(select(User.district_id).where(User.id == sponsor_id))
        d = row.scalar_one_or_none()
        if d:
            return d
    return HONGKONG_DISTRICT_ID


def can_change_status(user: User) -> bool:
    """检查用户是否有权限变更工作项状态

    权限（2026-11-16 调整）：
    - 区域总监（L4）及以上：可以（含部门总监、监察主任、集团总监、总裁、管理员）
    - 人事/商务部的经理与专员：可以
    """
    if _effective_role_level(user) >= RoleLevel.DISTRICT_MANAGER:
        return True
    if _effective_role_level(user) >= RoleLevel.STAFF and user.department_id == HR_COMMERCE_DEPT_ID:
        return True
    return False


def extract_sender_email(email_from: str) -> Optional[str]:
    """从 email_from 字段提取发件人邮箱地址
    格式示例: "王辰元" <adam.wang@ntg.com.hk> 或 adam.wang@ntg.com.hk
    """
    if not email_from:
        return None
    # 尝试匹配 <email> 格式
    match = re.search(r'<([^>]+)>', email_from)
    if match:
        return match.group(1).strip()
    # 如果整个字符串就是邮箱
    if '@' in email_from and '<' not in email_from:
        return email_from.strip()
    return None


async def _resolve_assignee_names(db: AsyncSession, items: list) -> None:
    """Resolve assignee_email_prefix to real names, set as assignee_names attribute."""
    all_prefixes = set()
    for item in items:
        if item.assignee_email_prefix:
            raw = item.assignee_email_prefix.replace(' ', ',')
            prefixes = [p.strip() for p in raw.split(',') if p.strip()]
            all_prefixes.update(prefixes)
    
    prefix_to_name = {}
    if all_prefixes:
        result = await db.execute(
            select(User.email_prefix, User.real_name).where(User.email_prefix.in_(list(all_prefixes)))
        )
        prefix_to_name = {row[0]: row[1] for row in result.all() if row[1]}
    
    for item in items:
        if item.assignee_email_prefix:
            raw = item.assignee_email_prefix.replace(' ', ',')
            prefixes = [p.strip() for p in raw.split(',') if p.strip()]
            names = []
            for p in prefixes:
                if p in prefix_to_name:
                    names.append(prefix_to_name[p])
                # 未匹配的前缀跳过不显示
            item.assignee_names = ', '.join(names) if names else None
        elif item.assignee and hasattr(item.assignee, 'real_name') and item.assignee.real_name:
            item.assignee_names = item.assignee.real_name
        else:
            item.assignee_names = None


@router.get("", response_model=List[WorkItemOut])
async def list_work_items(
    status: Optional[str] = None,
    department_id: Optional[int] = None,
    district_id: Optional[int] = None,
    assignee_id: Optional[int] = None,
    assignee_email_prefix: Optional[str] = None,
    sponsor_id: Optional[int] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取工作项列表（按当前用户的数据范围过滤，2026-11-18）"""
    query = select(WorkItem).options(
        selectinload(WorkItem.department),
        selectinload(WorkItem.district),
        selectinload(WorkItem.district),
        selectinload(WorkItem.sponsor).selectinload(User.district),
        selectinload(WorkItem.sponsor).selectinload(User.department),
        selectinload(WorkItem.assignee).selectinload(User.department),
        selectinload(WorkItem.assignee).selectinload(User.district),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.department),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.district),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
    )

    # 数据范围：全集团用户不加限制；其余按 部门∪区域∪本人主办/负责 过滤
    scope_conds = scope_conditions(current_user)
    if scope_conds is not None:
        query = query.where(or_(*scope_conds))

    if status:
        query = query.where(WorkItem.status == status)
    if department_id:
        query = query.where(WorkItem.department_id == department_id)
    if district_id:
        query = query.where(WorkItem.district_id == district_id)
    if assignee_id:
        query = query.where(WorkItem.assignee_id == assignee_id)
    if sponsor_id:
        query = query.where(WorkItem.sponsor_id == sponsor_id)
    if assignee_email_prefix:
        # 支持多个邮箱前缀（逗号分隔）
        email_prefixes = [ep.strip() for ep in assignee_email_prefix.split(',')]
        conditions = [WorkItem.assignee_email_prefix.contains(ep) for ep in email_prefixes]
        query = query.where(or_(*conditions))
    if keyword:
        query = query.where(WorkItem.title.contains(keyword))

    query = query.order_by(WorkItem.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()
    # 计算派生状态：pending 且过期 → overdue
    now = datetime.utcnow()
    for item in items:
        if item.status == "pending" and item.due_date and item.due_date < now:
            set_committed_value(item, "status", "overdue")
    await _resolve_assignee_names(db, items)
    return items


@router.get("/my", response_model=List[WorkItemOut])
async def list_my_work_items(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的工作项"""
    query = select(WorkItem).options(
        selectinload(WorkItem.department),
        selectinload(WorkItem.district),
        selectinload(WorkItem.sponsor).selectinload(User.district),
        selectinload(WorkItem.sponsor).selectinload(User.department),
        selectinload(WorkItem.assignee).selectinload(User.department),
        selectinload(WorkItem.assignee).selectinload(User.district),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.department),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.district),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
    )

    # 查找分配给当前用户的工作项（通过 assignee_id 或 assignee_email_prefix）
    conditions = []
    if current_user.id:
        conditions.append(WorkItem.assignee_id == current_user.id)
    if current_user.email_prefix:
        conditions.append(WorkItem.assignee_email_prefix.contains(current_user.email_prefix))

    if conditions:
        query = query.where(or_(*conditions))

    query = query.order_by(WorkItem.created_at.desc())
    result = await db.execute(query)
    items = result.scalars().all()
    # 计算派生状态：pending 且过期 → overdue
    now = datetime.utcnow()
    for item in items:
        if item.status == "pending" and item.due_date and item.due_date < now:
            set_committed_value(item, "status", "overdue")
    await _resolve_assignee_names(db, items)
    return items


@router.get("/email-link-status", response_model=EmailLinkStatusResponse)
async def get_email_link_status(
    ids: str = Query(..., description="逗号分隔的工作项ID列表"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量查询工作项的邮件链接状态（只查缓存，不调API）"""
    user_email = current_user.email
    if not user_email:
        return EmailLinkStatusResponse(items={})

    try:
        item_ids = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
    except Exception:
        return EmailLinkStatusResponse(items={})
    
    if not item_ids:
        return EmailLinkStatusResponse(items={})

    # 限制最多1000个ID
    item_ids = item_ids[:1000]

    # 查缓存
    result = await db.execute(
        select(EmailUrlCache).where(
            EmailUrlCache.user_email == user_email,
            EmailUrlCache.work_item_id.in_(item_ids),
        )
    )
    cache_rows = result.scalars().all()
    
    # 构建返回：found=True, not_found=False
    link_status = {}
    for row in cache_rows:
        link_status[row.work_item_id] = (row.status == "found")
    
    # 对于没有缓存记录的，查work_items是否有message_id
    cached_ids = set(link_status.keys())
    missing_ids = [i for i in item_ids if i not in cached_ids]
    
    if missing_ids:
        items_result = await db.execute(
            select(WorkItem.id, WorkItem.message_id).where(WorkItem.id.in_(missing_ids))
        )
        for row in items_result.all():
            # 有message_id但还没缓存 → 乐观返回True（点击时再确认）
            # 无message_id → 肯定没有链接，返回False
            if row[1]:
                link_status[row[0]] = True  # 乐观：先显示按钮
            else:
                link_status[row[0]] = False
    

    # 对于缓存为not_found的项，如果有message_id，仍然乐观显示按钮
    not_found_ids = [wid for wid, status in link_status.items() if not status]
    if not_found_ids:
        items_result = await db.execute(
            select(WorkItem.id, WorkItem.message_id).where(WorkItem.id.in_(not_found_ids))
        )
        for row in items_result.all():
            if row[1]:
                link_status[row[0]] = True  # 有message_id，乐观显示按钮
    return EmailLinkStatusResponse(items=link_status)

@router.get("/{item_id}", response_model=WorkItemOut)
async def get_work_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """获取单个工作项"""
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.district),
        selectinload(WorkItem.sponsor).selectinload(User.district),
        selectinload(WorkItem.sponsor).selectinload(User.department),
            selectinload(WorkItem.assignee).selectinload(User.department),
        selectinload(WorkItem.assignee).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.department),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")
    # 计算派生状态：pending 且过期 → overdue
    now = datetime.utcnow()
    if item.status == "pending" and item.due_date and item.due_date < now:
        set_committed_value(item, "status", "overdue")
    await _resolve_assignee_names(db, [item])
    return item


def _build_email_search_url(email_subject, title, user_email):
    """生成阿里邮箱搜索URL，用于找不到原邮件时的备选"""
    keyword = email_subject or title or ""
    email_prefix = user_email.split("@")[0] if user_email else ""
    base = "https://mail.sg.aliyun.com/alimail/entries/v5.1/search"
    return f"{base}?keyword={quote(keyword)}&emailPrefix={quote(email_prefix)}"

@router.get("/{item_id}/email-url", response_model=EmailUrlResponse)
async def get_work_item_email_url(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取工作项原邮件的阿里邮箱跳转URL（带缓存）"""
    # 获取工作项
    result = await db.execute(select(WorkItem).where(WorkItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")

    # 检查是否有关联邮件
    if not item.email_subject:
        return EmailUrlResponse(url=None, error="该工作项无关联邮件", search_url=_build_email_search_url(item.email_subject, item.title, current_user.email or ""))

    # 获取当前用户邮箱
    user_email = current_user.email
    if not user_email:
        return EmailUrlResponse(url=None, error="当前用户未设置邮箱地址", search_url=_build_email_search_url(item.email_subject, item.title, current_user.email or ""))

    # === Tier 1: 查缓存 ===
    cache_result = await db.execute(
        select(EmailUrlCache).where(
            EmailUrlCache.user_email == user_email,
            EmailUrlCache.work_item_id == item_id,
        )
    )
    cache_row = cache_result.scalar_one_or_none()
    if cache_row:
        if cache_row.status == "found" and cache_row.conversation_id:
            # 缓存命中且找到，直接构造URL
            import base64 as b64
            import json as json_mod
            url_payload = json_mod.dumps({"id": cache_row.conversation_id, "type": "session"})
            encoded = b64.b64encode(url_payload.encode()).decode()
            cached_url = f"{settings.ALIMAIL_WEBMAIL_BASE}{encoded}"
            logger.info(f"缓存命中(found): work_item={item_id}, user={user_email}")
            return EmailUrlResponse(url=cached_url)
        # not_found 不直接返回：先尝试其他用户的 found 缓存，最后才认输

    # === Tier 1.5: 当前用户无缓存时，回退到该工作项任意 found 缓存（同一邮箱域内会话ID通用）===
    # 场景：历史/迁移数据只有部分用户点过邮件按钮，其他用户点开时不应重新调API
    fb_result = await db.execute(
        select(EmailUrlCache)
        .where(
            EmailUrlCache.work_item_id == item_id,
            EmailUrlCache.status == "found",
            EmailUrlCache.conversation_id.isnot(None),
        )
        .order_by(EmailUrlCache.id)
        .limit(1)
    )
    fb_row = fb_result.scalar_one_or_none()
    if fb_row and fb_row.conversation_id:
        import base64 as b64
        import json as json_mod
        url_payload = json_mod.dumps({"id": fb_row.conversation_id, "type": "session"})
        encoded = b64.b64encode(url_payload.encode()).decode()
        fallback_url = f"{settings.ALIMAIL_WEBMAIL_BASE}{encoded}"
        # 顺带写入当前用户缓存，下次直接命中
        try:
            import sqlite3 as _sqlite3
            from datetime import datetime as dt
            now_str = dt.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            _conn = _sqlite3.connect("/app/backend/data/gws.db")
            _conn.execute("DELETE FROM email_url_cache WHERE user_email = ? AND work_item_id = ?", (user_email, item_id))
            _conn.execute(
                "INSERT INTO email_url_cache (user_email, work_item_id, conversation_id, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_email, item_id, fb_row.conversation_id, "found", now_str),
            )
            _conn.commit()
            _conn.close()
        except Exception as e:
            logger.warning(f"回退缓存写入失败（不影响URL返回）: {e}")
        logger.info(f"回退命中: work_item={item_id}, user={user_email}, from={fb_row.user_email}")
        return EmailUrlResponse(url=fallback_url)

    # === Tier 1.6: 各用户缓存都没有 → 若当前用户曾判定 not_found，如实返回 ===
    if cache_row and cache_row.status == "not_found":
        logger.info(f"缓存命中(not_found): work_item={item_id}, user={user_email}")
        return EmailUrlResponse(url=None, error="未找到原邮件，可能已被删除或移动到其他文件夹",
                                search_url=_build_email_search_url(item.email_subject, item.title, user_email))

    # === Tier 2: 缓存未命中，调API查找 ===
    # 阿里邮箱API未配置时，直接提示配置缺失（避免误报「邮件已删除」）
    if not settings.ALIMAIL_APP_ID or not settings.ALIMAIL_APP_SECRET:
        logger.warning(f"阿里邮箱API未配置，无法实时查找: work_item={item_id}")
        return EmailUrlResponse(
            url=None,
            error="邮箱接口未配置（ALIMAIL_APP_ID / ALIMAIL_APP_SECRET 为空），暂时无法定位原邮件",
            search_url=_build_email_search_url(item.email_subject, item.title, user_email),
        )
    # 获取 internetMessageId
    internet_message_id = None
    if item.message_id:
        internet_message_id = item.message_id.strip('<>')
    else:
        log_result = await db.execute(
            select(EmailLog.message_id).where(EmailLog.work_item_id == item_id).limit(1)
        )
        log_row = log_result.first()
        if log_row:
            internet_message_id = log_row[0].strip('<>')

    if not internet_message_id:
        # 无message_id也缓存为not_found
        try:
            import sqlite3 as _sqlite3
            from datetime import datetime as dt
            now_str = dt.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            _conn = _sqlite3.connect("/app/backend/data/gws.db")
            _conn.execute("DELETE FROM email_url_cache WHERE user_email = ? AND work_item_id = ?", (user_email, item_id))
            _conn.execute("INSERT INTO email_url_cache (user_email, work_item_id, conversation_id, status, created_at) VALUES (?, ?, ?, ?, ?)", (user_email, item_id, None, "not_found", now_str))
            _conn.commit()
            _conn.close()
        except Exception as e:
            logger.error(f"缓存写入失败: {e}")
        return EmailUrlResponse(url=None, error="未找到邮件的Message-ID", search_url=_build_email_search_url(item.email_subject, item.title, user_email))

    # 获取邮件日期（用于缩小API搜索范围）
    email_date = item.email_date or item.created_at

    # 调用阿里邮箱API获取URL
    url = await get_email_url(
        user_email=user_email,
        email_subject=item.email_subject,
        internet_message_id=internet_message_id,
        sender_email=item.sender_email,
        email_date=email_date,
    )

    if url:
        # 提取conversationId并写缓存
        try:
            import base64 as b64
            import json as json_mod
            url_parts = url.split("/")
            b64_part = url_parts[-1]
            padding = 4 - len(b64_part) % 4
            if padding != 4:
                b64_part += "=" * padding
            decoded = json_mod.loads(b64.b64decode(b64_part))
            conversation_id = decoded.get("id")
            
            if conversation_id:
                # 直接用sqlite3写缓存
                import sqlite3 as _sqlite3
                from datetime import datetime as dt
                now_str = dt.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                _conn = _sqlite3.connect("/app/backend/data/gws.db")
                _conn.execute("DELETE FROM email_url_cache WHERE user_email = ? AND work_item_id = ?", (user_email, item_id))
                _conn.execute("INSERT INTO email_url_cache (user_email, work_item_id, conversation_id, status, created_at) VALUES (?, ?, ?, ?, ?)", (user_email, item_id, conversation_id, "found", now_str))
                _conn.commit()
                _conn.close()
                logger.info(f"缓存写入(found): work_item={item_id}, user={user_email}, convId={conversation_id}")
        except Exception as e:
            logger.warning(f"缓存写入失败（不影响URL返回）: {e}")
        
        return EmailUrlResponse(url=url)
    else:
        # 查找失败也缓存 - 直接用sqlite3写入，避免SQLAlchemy事务问题
        logger.info(f"准备写入not_found缓存: work_item={item_id}, user={user_email}")
        try:
            import sqlite3 as _sqlite3
            from datetime import datetime as dt
            now_str = dt.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            _conn = _sqlite3.connect("/app/backend/data/gws.db")
            _conn.execute("DELETE FROM email_url_cache WHERE user_email = ? AND work_item_id = ?", (user_email, item_id))
            _conn.execute("INSERT INTO email_url_cache (user_email, work_item_id, conversation_id, status, created_at) VALUES (?, ?, ?, ?, ?)", (user_email, item_id, None, "not_found", now_str))
            _conn.commit()
            _conn.close()
            logger.info(f"not_found缓存写入成功: work_item={item_id}, user={user_email}")
        except Exception as cache_err:
            logger.error(f"not_found缓存写入失败: work_item={item_id}, user={user_email}, error={cache_err}")
        return EmailUrlResponse(url=None, error="未找到原邮件，可能已被删除或移动到其他文件夹", search_url=_build_email_search_url(item.email_subject, item.title, user_email))


@router.post("", response_model=WorkItemOut, status_code=201)
async def create_work_item(
    data: WorkItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建工作项"""
    item = WorkItem(**data.model_dump(exclude={"sponsor_id"}))
    # 未显式指定区域时，按负责人/主办人自动推导（补录、邮件抓取同样生效）
    if not item.district_id:
        item.district_id = await resolve_district_id(
            db, item.assignee_id, item.assignee_email_prefix, item.sponsor_id or current_user.id
        )

    # 设置主办人（sponsor_id）
    if data.sponsor_id and data.sponsor_id != current_user.id:
        # 指定了不同的主办人，需要权限校验
        user_level = current_user.role_level or 2
        if user_level >= 6:  # REGULATOR 及以上：可以指定任何人
            target_result = await db.execute(select(User).where(User.id == data.sponsor_id))
            target = target_result.scalar_one_or_none()
            if not target:
                raise HTTPException(status_code=400, detail="指定的主办人不存在")
            item.sponsor_id = data.sponsor_id
        elif user_level >= 5:  # DEPT_DIRECTOR：只能指定本部门/有权限部门的人
            target_result = await db.execute(select(User).where(User.id == data.sponsor_id))
            target = target_result.scalar_one_or_none()
            if not target:
                raise HTTPException(status_code=400, detail="指定的主办人不存在")
            # 收集当前用户有权限的部门
            allowed_depts = set()
            if current_user.department_id:
                allowed_depts.add(current_user.department_id)
            if current_user.secondary_roles:
                for sr in current_user.secondary_roles:
                    if sr.get("role_level", 0) >= 5 and sr.get("department_id"):
                        allowed_depts.add(sr["department_id"])
            if target.department_id not in allowed_depts:
                raise HTTPException(status_code=403, detail="无权限：只能指定本部门的人为主办人")
            item.sponsor_id = data.sponsor_id
        else:
            # 经理及以下：不能指定别人
            item.sponsor_id = current_user.id
    else:
        item.sponsor_id = current_user.id
    # 新建时若已是完成状态（如忘记抄送邮件、手工补录），补完成时间与完成人
    if item.status == WorkItemStatus.completed.value:
        item.completed_at = item.completed_at or datetime.utcnow()
        item.completed_by = item.completed_by or current_user.id
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # 重新加载关系
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.district),
        selectinload(WorkItem.sponsor).selectinload(User.district),
        selectinload(WorkItem.sponsor).selectinload(User.department),
            selectinload(WorkItem.assignee).selectinload(User.department),
        selectinload(WorkItem.assignee).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.department),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item.id)
    )
    item = result.scalar_one()
    now = datetime.utcnow()
    if item.status == "pending" and item.due_date and item.due_date < now:
        set_committed_value(item, "status", "overdue")
    await _resolve_assignee_names(db, [item])
    return item


@router.put("/{item_id}", response_model=WorkItemOut)
async def update_work_item(
    item_id: int, data: WorkItemUpdate, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新工作项"""
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.district),
        selectinload(WorkItem.sponsor).selectinload(User.district),
        selectinload(WorkItem.sponsor).selectinload(User.department),
            selectinload(WorkItem.assignee).selectinload(User.department),
        selectinload(WorkItem.assignee).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.department),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")

    # 数据范围校验：越权修改他人部门/区域的工作项直接拒绝（2026-11-18）
    if not in_scope(item, current_user):
        raise HTTPException(status_code=403, detail="无权修改该工作项（不在你的数据范围内）")

    update_data = data.model_dump(exclude_unset=True)
    old_status = item.status

    # 如果状态变更，检查权限；无权限或尝试设置overdue则静默忽略状态字段
    if "status" in update_data and update_data["status"] != item.status:
        if update_data["status"] == "overdue":
            update_data.pop("status", None)
        elif not can_change_status(current_user):
            update_data.pop("status", None)
        else:
            log = StatusChangeLog(
                work_item_id=item.id,
                old_status=item.status,
                new_status=update_data["status"],
                operator_id=current_user.id,
                remark="通过编辑更新状态",
            )
            db.add(log)

    for key, value in update_data.items():
        setattr(item, key, value)

    # Sync assignee_id and assignee_email_prefix for consistency
    if "assignee_email_prefix" in update_data and "assignee_id" not in update_data:
        # assignee_email_prefix was updated but assignee_id wasn't → sync from first prefix
        if item.assignee_email_prefix:
            first_prefix = item.assignee_email_prefix.replace(' ', ',').split(',')[0].strip()
            if first_prefix:
                user_result = await db.execute(
                    select(User.id).where(User.email_prefix == first_prefix)
                )
                user_row = user_result.first()
                if user_row:
                    item.assignee_id = user_row[0]
                else:
                    item.assignee_id = None
        else:
            item.assignee_id = None
    elif "assignee_id" in update_data and "assignee_email_prefix" not in update_data:
        # assignee_id was updated but assignee_email_prefix wasn't → sync from user
        if item.assignee_id:
            user_result = await db.execute(
                select(User.email_prefix).where(User.id == item.assignee_id)
            )
            user_row = user_result.first()
            if user_row:
                item.assignee_email_prefix = user_row[0]
        else:
            item.assignee_email_prefix = None

    # 负责人/主办人变更且未显式指定区域时，重算区域
    if "district_id" not in update_data and ({"assignee_id", "assignee_email_prefix", "sponsor_id"} & set(update_data.keys())):
        item.district_id = await resolve_district_id(
            db, item.assignee_id, item.assignee_email_prefix, item.sponsor_id
        )

    # 状态变更时同步完成信息
    _apply_completion_fields(item, old_status, current_user.id)

    item.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(item)

    # 重新加载关系
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.district),
        selectinload(WorkItem.sponsor).selectinload(User.district),
        selectinload(WorkItem.sponsor).selectinload(User.department),
            selectinload(WorkItem.assignee).selectinload(User.department),
        selectinload(WorkItem.assignee).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.department),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item.id)
    )
    item = result.scalar_one()
    now = datetime.utcnow()
    if item.status == "pending" and item.due_date and item.due_date < now:
        set_committed_value(item, "status", "overdue")
    await _resolve_assignee_names(db, [item])
    return item


@router.patch("/{item_id}/status", response_model=WorkItemOut)
async def change_status(
    item_id: int,
    data: StatusChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """变更工作项状态"""
    if not can_change_status(current_user):
        raise HTTPException(status_code=403, detail="无权限变更工作项状态：需区域总监及以上，或人事/商务部的经理/专员")
    if data.status == "overdue":
        raise HTTPException(status_code=400, detail="已逾时是系统自动状态，不可手动设置")
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.district),
        selectinload(WorkItem.sponsor).selectinload(User.district),
        selectinload(WorkItem.sponsor).selectinload(User.department),
            selectinload(WorkItem.assignee).selectinload(User.department),
        selectinload(WorkItem.assignee).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.department),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")

    old_status = item.status
    item.status = data.status
    _apply_completion_fields(item, old_status, current_user.id)
    item.updated_at = datetime.utcnow()

    log = StatusChangeLog(
        work_item_id=item.id,
        old_status=old_status,
        new_status=data.status,
        operator_id=current_user.id,
        remark=data.remark,
    )
    db.add(log)
    await db.commit()
    await db.refresh(item)

    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.district),
        selectinload(WorkItem.sponsor).selectinload(User.district),
        selectinload(WorkItem.sponsor).selectinload(User.department),
            selectinload(WorkItem.assignee).selectinload(User.department),
        selectinload(WorkItem.assignee).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.department),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator).selectinload(User.district),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item.id)
    )
    item = result.scalar_one()
    now = datetime.utcnow()
    if item.status == "pending" and item.due_date and item.due_date < now:
        set_committed_value(item, "status", "overdue")
    await _resolve_assignee_names(db, [item])
    return item


@router.get("/{item_id}/status-logs", response_model=List[StatusChangeLogOut])
async def get_status_logs(item_id: int, db: AsyncSession = Depends(get_db)):
    """获取工作项状态变更日志"""
    result = await db.execute(
        select(StatusChangeLog)
        .where(StatusChangeLog.work_item_id == item_id)
        .order_by(StatusChangeLog.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{item_id}", status_code=204)
async def delete_work_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除工作项 - 仅管理员和总裁可操作"""
    user_role = RoleType(current_user.role) if isinstance(current_user.role, str) else current_user.role
    if user_role not in {RoleType.admin, RoleType.president}:
        raise HTTPException(status_code=403, detail="无权限删除工作项，仅管理员和总裁可操作")
    result = await db.execute(select(WorkItem).where(WorkItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")
    await db.delete(item)
    await db.commit()
