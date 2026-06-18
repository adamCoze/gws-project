"""IMAP 邮件监听服务"""
import asyncio
import email
import imaplib
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from email.header import decode_header
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models import EmailConfig, WorkItem, Department, User, EmailLog, EmailProcessResult, WorkItemStatus
from services.ai_service import analyze_email_with_ai

logger = logging.getLogger(__name__)

_monitor_task: Optional[asyncio.Task] = None
_running = False
MAX_RETRY_COUNT = 2


def _decode_str(s) -> str:
    """解码邮件头字符串"""
    if s is None:
        return ""
    if isinstance(s, bytes):
        s = s.decode("utf-8", errors="replace")
    parts = decode_header(s)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def _normalize_subject(subject: str) -> str:
    """去除邮件主题中的 Re:/Fwd:/转发:/回复: 等前缀，用于相似度比较"""
    if not subject:
        return ""
    prefixes = ["re:", "fwd:", "转发:", "回复:", "转寄:", "fw:", "Re:", "Fwd:", "Fw:"]
    normalized = subject.strip()
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if normalized.lower().startswith(prefix.lower()):
                normalized = normalized[len(prefix):].strip()
                changed = True
    return normalized


def _subject_similarity(s1: str, s2: str) -> float:
    """计算两个邮件主题的相似度（0-1）"""
    n1 = _normalize_subject(s1)
    n2 = _normalize_subject(s2)
    if not n1 or not n2:
        return 0.0
    return SequenceMatcher(None, n1, n2).ratio()


def _get_email_body(msg) -> str:
    """提取邮件正文（包括转发邮件的转发体）"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
            elif content_type == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")

    body = _extract_forwarded_content(body)
    return body


def _extract_forwarded_content(body: str) -> str:
    """提取转发邮件中的完整原始邮件内容"""
    if not body:
        return body

    forward_markers = [
        "---------- Forwarded message ----------",
        "---------- 转发的邮件 ----------",
        "---------- Forwarded Message ----------",
        "-----Original Message-----",
        "----- 原始邮件 -----",
        "Begin forwarded message:",
        "转发邮件：",
    ]

    for marker in forward_markers:
        if marker in body:
            return body

    return body


async def _check_email_config(config: EmailConfig):
    """检查单个邮箱配置的新邮件"""
    try:
        loop = asyncio.get_event_loop()
        mail = await loop.run_in_executor(None, _imap_connect, config)
        if not mail:
            return

        _, messages = mail.search(None, "UNSEEN")
        email_ids = messages[0].split()

        for eid in email_ids[:10]:
            _, msg_data = mail.fetch(eid, "(RFC822)")
            if msg_data and msg_data[0]:
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                subject = _decode_str(msg.get("Subject"))
                from_addr = _decode_str(msg.get("From"))
                to_addrs = _decode_str(msg.get("To"))
                cc_addrs = _decode_str(msg.get("Cc"))
                date_str = msg.get("Date", "")
                message_id = msg.get("Message-ID", f"unknown-{datetime.utcnow().timestamp()}")
                body = _get_email_body(msg)

                if subject and body:
                    await _process_email_with_retry(config, message_id, subject, from_addr, date_str, body, to_addrs, cc_addrs)
                    mail.store(eid, '+FLAGS', '\\Seen')

        mail.logout()

        async with async_session() as db:
            result = await db.execute(select(EmailConfig).where(EmailConfig.id == config.id))
            cfg = result.scalar_one_or_none()
            if cfg:
                cfg.last_check_at = datetime.utcnow()
                await db.commit()

    except Exception as e:
        logger.error(f"检查邮箱 {config.email_address} 失败: {e}")


def _imap_connect(config: EmailConfig) -> Optional[imaplib.IMAP4_SSL]:
    """IMAP 连接（同步）"""
    try:
        mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port, timeout=30)
        mail.login(config.username, config.password)
        mail.select("INBOX")
        return mail
    except Exception as e:
        logger.error(f"IMAP连接失败 {config.email_address}: {e}")
        return None


async def _process_email_with_retry(
    config: EmailConfig,
    message_id: str,
    subject: str,
    from_addr: str,
    date_str: str,
    body: str,
    to_addrs: str = "",
    cc_addrs: str = ""
):
    """处理邮件，支持重试机制"""
    retry_count = 0

    while retry_count <= MAX_RETRY_COUNT:
        result = await _process_email(message_id, subject, from_addr, date_str, body, retry_count, to_addrs, cc_addrs)

        if result == EmailProcessResult.SUCCESS:
            return
        elif result == EmailProcessResult.AI_FAILED:
            retry_count += 1
            if retry_count <= MAX_RETRY_COUNT:
                logger.info(f"AI分析失败，第 {retry_count} 次重试: {subject}")
                await asyncio.sleep(2)
            else:
                logger.warning(f"AI分析失败，已达最大重试次数: {subject}")
                return
        else:
            retry_count += 1
            if retry_count <= MAX_RETRY_COUNT:
                logger.info(f"处理失败，第 {retry_count} 次重试: {subject}")
                await asyncio.sleep(2)
            else:
                logger.warning(f"处理失败，已达最大重试次数: {subject}")
                return


async def _find_matching_work_item(db: AsyncSession, subject: str, item_type: str) -> Optional[WorkItem]:
    """查找标题相似的工作项（相似度 > 80%），用于合并"""
    result = await db.execute(
        select(WorkItem).where(WorkItem.status != WorkItemStatus.completed)
    )
    existing_items = result.scalars().all()

    for item in existing_items:
        sim = _subject_similarity(subject, item.email_subject or item.title)
        if sim > 0.8:
            logger.info(f"标题相似度匹配: {sim:.2f}，合并到工作项 #{item.id}: {item.title[:50]}")
            return item

    return None


async def _process_email(
    message_id: str,
    subject: str,
    from_addr: str,
    date_str: str,
    body: str,
    retry_count: int = 0,
    to_addrs: str = "",
    cc_addrs: str = ""
) -> EmailProcessResult:
    """处理邮件：AI分析并入库，返回处理结果"""
    async with async_session() as db:
        try:
            # 检查是否已处理过该邮件
            existing = await db.execute(select(EmailLog).where(EmailLog.message_id == message_id))
            if existing.scalar_one_or_none():
                logger.info(f"邮件已处理过，跳过: {message_id}")
                return EmailProcessResult.SUCCESS

            # 使用 AI 分析邮件内容
            analysis = await analyze_email_with_ai(subject, body, to_addrs, cc_addrs)
            if not analysis:
                log = EmailLog(
                    message_id=message_id,
                    subject=subject,
                    from_addr=from_addr,
                    received_at=datetime.utcnow(),
                    process_result=EmailProcessResult.AI_FAILED,
                    retry_count=retry_count,
                    error_message="AI分析返回空结果",
                    work_item_id=None,
                )
                db.add(log)
                await db.commit()
                return EmailProcessResult.AI_FAILED

            # 查找或创建部门
            dept_name = analysis.get("department", "行政/产品部")
            result = await db.execute(select(Department).where(Department.name == dept_name))
            dept = result.scalar_one_or_none()
            if not dept:
                dept = Department(name=dept_name, code=dept_name[:2])
                db.add(dept)
                await db.flush()

            due_date_raw = analysis.get("due_date")
            due_date = None
            if due_date_raw and isinstance(due_date_raw, str):
                try:
                    due_date = datetime.strptime(due_date_raw, "%Y-%m-%d")
                except ValueError:
                    due_date = None
            elif isinstance(due_date_raw, datetime):
                due_date = due_date_raw
            item_type = analysis.get("type", "task")
            # 设置默认截止日期：task=7个自然日，cosign=24小时
            if not due_date:
                if item_type == "cosign":
                    due_date = datetime.utcnow() + timedelta(days=1)
                else:
                    due_date = datetime.utcnow() + timedelta(days=7)
            completion = analysis.get("completion_assessment", "in_progress")

            # 确定工作项状态
            if completion == "completed":
                new_status = WorkItemStatus.completed
            elif completion == "in_progress":
                new_status = WorkItemStatus.pending
            else:
                new_status = WorkItemStatus.pending

            # 查找是否有相似的工作项（重复合并）
            matching_item = await _find_matching_work_item(db, subject, item_type)

            if matching_item:
                # 合并到已有工作项：更新内容、责任人、状态
                logger.info(f"合并邮件到工作项 #{matching_item.id}")
                matching_item.content = analysis.get("summary", matching_item.content)
                new_prefix = analysis.get("assignee_prefix", matching_item.assignee_email_prefix)
                matching_item.assignee_email_prefix = new_prefix
                # Also update assignee_id if single assignee
                if new_prefix and ',' not in new_prefix and not matching_item.assignee_id:
                    user_result = await db.execute(
                        select(User).where(User.email_prefix == new_prefix)
                    )
                    user = user_result.scalar_one_or_none()
                    if user:
                        matching_item.assignee_id = user.id
                if due_date:
                    matching_item.due_date = due_date
                # 状态只升级，不降级（completed > pending）
                status_priority = {"pending": 0, "completed": 1, "cancelled": 0}
                if status_priority.get(new_status.value, 0) > status_priority.get(matching_item.status.value, 0):
                    matching_item.status = new_status
                matching_item.updated_at = datetime.utcnow()

                work_item_id = matching_item.id
            else:
                # 创建新工作项
                assignee_prefix = analysis.get("assignee_prefix")
                # Resolve assignee_id from email_prefix (only for single assignee)
                assignee_id = None
                if assignee_prefix and ',' not in assignee_prefix:
                    user_result = await db.execute(
                        select(User).where(User.email_prefix == assignee_prefix)
                    )
                    user = user_result.scalar_one_or_none()
                    if user:
                        assignee_id = user.id

                item = WorkItem(
                    title=analysis.get("title", subject[:100]),
                    content=analysis.get("summary", body[:500]),
                    item_type=item_type,
                    status=new_status,
                    department_id=dept.id,
                    assignee_id=assignee_id,
                    assignee_email_prefix=assignee_prefix,
                    due_date=due_date,
                    is_confidential=analysis.get("is_confidential", False),
                    email_subject=subject,
                    email_from=from_addr,
                    email_date=datetime.utcnow(),
                )
                db.add(item)
                await db.flush()
                work_item_id = item.id
                logger.info(f"成功创建工作项: {item.title} (状态: {new_status.value})")

            # 记录邮件日志
            log = EmailLog(
                message_id=message_id,
                subject=subject,
                from_addr=from_addr,
                received_at=datetime.utcnow(),
                process_result=EmailProcessResult.SUCCESS,
                retry_count=retry_count,
                error_message=None,
                work_item_id=work_item_id,
            )
            db.add(log)
            await db.commit()
            return EmailProcessResult.SUCCESS

        except Exception as e:
            error_msg = str(e)
            logger.error(f"处理邮件失败: {error_msg}")

            try:
                await db.rollback()
                log = EmailLog(
                    message_id=message_id,
                    subject=subject,
                    from_addr=from_addr,
                    received_at=datetime.utcnow(),
                    process_result=EmailProcessResult.RETRY,
                    retry_count=retry_count,
                    error_message=error_msg,
                    work_item_id=None,
                )
                db.add(log)
                await db.commit()
            except Exception as log_error:
                logger.error(f"记录日志失败: {log_error}")

            return EmailProcessResult.RETRY


async def _monitor_loop():
    """邮件监听主循环"""
    global _running
    _running = True
    logger.info("邮件监听服务已启动")

    while _running:
        try:
            async with async_session() as db:
                result = await db.execute(select(EmailConfig).where(EmailConfig.is_active == True))  # noqa: E712
                configs = result.scalars().all()

            for config in configs:
                if not _running:
                    break
                await _check_email_config(config)

        except Exception as e:
            logger.error(f"邮件监听循环错误: {e}")

        await asyncio.sleep(300)


async def start_email_monitor():
    """启动邮件监听"""
    global _monitor_task
    if _monitor_task is None or _monitor_task.done():
        _monitor_task = asyncio.create_task(_monitor_loop())


async def stop_email_monitor():
    """停止邮件监听"""
    global _running, _monitor_task
    _running = False
    if _monitor_task and not _monitor_task.done():
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
    _monitor_task = None
