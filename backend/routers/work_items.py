"""工作项路由"""
import re
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import WorkItem, WorkItemStatus, Department, User, StatusChangeLog, EmailLog, EmailUrlCache
from schemas import (
    WorkItemCreate, WorkItemUpdate, WorkItemOut,
    StatusChangeRequest, StatusChangeLogOut,
    EmailUrlResponse, EmailLinkStatusResponse,
)
from auth import get_current_user, ROLE_LEVELS
from models import RoleType
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

# 允许变更状态的角色
STATUS_CHANGE_ROLES = {RoleType.regulator, RoleType.president, RoleType.admin}
# 人事/商务部中允许变更状态的角色
HR_COMMERCE_ALLOWED = {RoleType.manager, RoleType.staff}


def can_change_status(user: User) -> bool:
    """检查用户是否有权限变更工作项状态"""
    user_role = RoleType(user.role) if isinstance(user.role, str) else user.role
    # 规管、总裁、管理员始终可以
    if user_role in STATUS_CHANGE_ROLES:
        return True
    # 人事/商务部的经理和专员可以
    if user_role in HR_COMMERCE_ALLOWED and user.department_id == HR_COMMERCE_DEPT_ID:
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
    assignee_id: Optional[int] = None,
    assignee_email_prefix: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """获取工作项列表"""
    query = select(WorkItem).options(
        selectinload(WorkItem.department),
        selectinload(WorkItem.assignee),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
    )

    if status:
        query = query.where(WorkItem.status == status)
    if department_id:
        query = query.where(WorkItem.department_id == department_id)
    if assignee_id:
        query = query.where(WorkItem.assignee_id == assignee_id)
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
            item.status = "overdue"
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
        selectinload(WorkItem.assignee),
        selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
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
            item.status = "overdue"
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

    # 查询所有ID
    # 不限制ID数量

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
    
    return EmailLinkStatusResponse(items=link_status)

@router.get("/{item_id}", response_model=WorkItemOut)
async def get_work_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """获取单个工作项"""
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
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
        item.status = "overdue"
    await _resolve_assignee_names(db, [item])
    return item


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
        return EmailUrlResponse(url=None, error="该工作项无关联邮件")

    # 获取当前用户邮箱
    user_email = current_user.email
    if not user_email:
        return EmailUrlResponse(url=None, error="当前用户未设置邮箱地址")

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
        elif cache_row.status == "not_found":
            logger.info(f"缓存命中(not_found): work_item={item_id}, user={user_email}")
            return EmailUrlResponse(url=None, error="未找到原邮件，可能已被删除或移动到其他文件夹")

    # === Tier 2: 缓存未命中，调API查找 ===
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
        return EmailUrlResponse(url=None, error="未找到邮件的Message-ID")

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
        return EmailUrlResponse(url=None, error="未找到原邮件，可能已被删除或移动到其他文件夹")


@router.post("", response_model=WorkItemOut, status_code=201)
async def create_work_item(data: WorkItemCreate, db: AsyncSession = Depends(get_db)):
    """创建工作项"""
    item = WorkItem(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # 重新加载关系
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item.id)
    )
    item = result.scalar_one()
    now = datetime.utcnow()
    if item.status == "pending" and item.due_date and item.due_date < now:
        item.status = "overdue"
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
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")

    update_data = data.model_dump(exclude_unset=True)

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

    item.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(item)

    # 重新加载关系
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item.id)
    )
    item = result.scalar_one()
    now = datetime.utcnow()
    if item.status == "pending" and item.due_date and item.due_date < now:
        item.status = "overdue"
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
        raise HTTPException(status_code=403, detail="无权限变更工作项状态，仅规管、总裁、管理员及人事/商务部经理/专员可操作")
    if data.status == "overdue":
        raise HTTPException(status_code=400, detail="已逾时是系统自动状态，不可手动设置")
    result = await db.execute(
        select(WorkItem)
        .options(
            selectinload(WorkItem.department),
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")

    old_status = item.status
    item.status = data.status
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
            selectinload(WorkItem.assignee),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.operator),
            selectinload(WorkItem.status_logs).selectinload(StatusChangeLog.work_item),
        )
        .where(WorkItem.id == item.id)
    )
    item = result.scalar_one()
    now = datetime.utcnow()
    if item.status == "pending" and item.due_date and item.due_date < now:
        item.status = "overdue"
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
