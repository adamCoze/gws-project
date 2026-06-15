"""IMAP 邮件监听服务"""
import asyncio
import email
import imaplib
import logging
from datetime import datetime
from email.header import decode_header
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models import EmailConfig, WorkItem, Department, User
from services.ai_service import analyze_email_with_ai

logger = logging.getLogger(__name__)

_monitor_task: Optional[asyncio.Task] = None
_running = False


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


def _get_email_body(msg) -> str:
    """提取邮件正文"""
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
    return body


async def _check_email_config(config: EmailConfig):
    """检查单个邮箱配置的新邮件"""
    try:
        loop = asyncio.get_event_loop()
        # IMAP 是同步的，在线程池中执行
        mail = await loop.run_in_executor(None, _imap_connect, config)
        if not mail:
            return

        _, messages = mail.search(None, "UNSEEN")
        email_ids = messages[0].split()

        for eid in email_ids[:10]:  # 每次最多处理10封
            _, msg_data = mail.fetch(eid, "(RFC822)")
            if msg_data and msg_data[0]:
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                subject = _decode_str(msg.get("Subject"))
                from_addr = _decode_str(msg.get("From"))
                date_str = msg.get("Date", "")
                body = _get_email_body(msg)

                if subject and body:
                    await _process_email(config, subject, from_addr, date_str, body)

        mail.logout()

        # 更新最后检查时间
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


async def _process_email(config: EmailConfig, subject: str, from_addr: str, date_str: str, body: str):
    """处理邮件：AI分析并入库"""
    try:
        # 使用 AI 分析邮件内容
        analysis = await analyze_email_with_ai(subject, body)
        if not analysis:
            logger.warning(f"AI分析失败，跳过邮件: {subject}")
            return

        async with async_session() as db:
            # 查找或创建部门
            dept_name = analysis.get("department", "运营部")
            result = await db.execute(select(Department).where(Department.name == dept_name))
            dept = result.scalar_one_or_none()
            if not dept:
                dept = Department(name=dept_name, code=dept_name[:2])
                db.add(dept)
                await db.flush()

            # 解析日期
            due_date = analysis.get("due_date")

            # 创建工作项
            item = WorkItem(
                title=analysis.get("title", subject[:100]),
                content=analysis.get("summary", body[:500]),
                item_type=analysis.get("type", "task"),
                status="pending",
                department_id=dept.id,
                assignee_email_prefix=analysis.get("assignee_prefix"),
                due_date=due_date,
                is_confidential=analysis.get("is_confidential", False),
                email_subject=subject,
                email_from=from_addr,
                email_date=datetime.utcnow(),
            )
            db.add(item)
            await db.commit()
            logger.info(f"成功创建工作项: {item.title}")

    except Exception as e:
        logger.error(f"处理邮件失败: {e}")


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

        # 等待指定间隔
        await asyncio.sleep(300)  # 5分钟


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
