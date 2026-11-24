"""IMAP 邮件监听服务"""
import asyncio
import email
import imaplib
import logging
import os
from datetime import datetime, timedelta
import re
from difflib import SequenceMatcher
from email.header import decode_header
from typing import Optional
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models import EmailConfig, WorkItem, Department, User, EmailLog, EmailProcessResult, WorkItemStatus, StatusChangeLog
from services.ai_service import analyze_email_with_ai
from services.alimail_api import cache_conversation_ids_for_message
from services.cosign_service import (
    initialize_cosign_tracking,
    update_cosign_tracking,
    analyze_cosign_reply,
    extract_sender_prefix,
)

logger = logging.getLogger(__name__)

# ── 沙箱只读抓取（2026-11-24）────────────────────────────────
# 沙箱实例与生产共用同一个邮箱时，必须满足：
#   ① 只读打开 INBOX（readonly），绝不改动 \Seen 等标志，生产实例不受影响
#   ② 按 SINCE 日期窗口取信，而不是 UNSEEN（生产每 5 分钟就把新信标已读）
#   ③ 每轮上限可调（默认 50 封/轮，5 分钟一轮，按最旧优先逐步推进）
# 默认关闭（SANDBOX_FETCH_DAYS=0），香港生产实例行为完全不变。
SANDBOX_FETCH_DAYS = int(os.getenv("SANDBOX_FETCH_DAYS", "0") or 0)
SANDBOX_FETCH_LIMIT = int(os.getenv("SANDBOX_FETCH_LIMIT", "50") or 50)


# 系统默认管理员邮箱（用于主动缓存 conversationId）
DEFAULT_ADMIN_EMAIL = "adam.wang@ntg.com.hk"

# ── 报告/汇报类邮件关键词（用于AI识别兜底） ──
# 标题含以下关键词且不含会签/审批类关键词时，强制标记为 report（汇报类）
REPORT_KEYWORDS = [
    "周报", "月报", "日报", "季报", "年报",
    "汇总", "报表", "简报", "报告", "情况说明",
    "每日电邮", "每日简历", "例会纪要", "例会纲要",
    "信息汇总", "工作总结", "工作汇报", "进展汇报",
    "进度汇报", "周报汇总", "月度汇总",
]
# 排除关键词：如果含这些词，即使有report关键词也不强制（交给AI判断）
REPORT_EXCLUDE_KEYWORDS = ["会签", "审批", "签批", "签署", "批复", "征求意见", "审核", "签核"]

_monitor_task: Optional[asyncio.Task] = None
_running = False
MAX_RETRY_COUNT = 2

# ── AI 失败告警通知（防刷屏：同一小时内最多1封）──
_last_alert_time: float = 0
_alert_cooldown_seconds = 3600  # 1小时冷却
_pending_failures: list = []  # 累积的失败信息


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




def _extract_sender_email(email_from: str) -> str:
    """从 email_from 字段提取发件人邮箱地址"""
    if not email_from:
        return ""
    match = re.search(r'<([^>]+)>', email_from)
    if match:
        return match.group(1).strip()
    if '@' in email_from and '<' not in email_from:
        return email_from.strip()
    return ""

def _normalize_subject(subject: str) -> str:
    """去除邮件主题中的 Re:/Fwd:/转发:/回复:/回覆:/轉寄: 等前缀，用于相似度比较和存储"""
    if not subject:
        return ""
    pattern = r"^(?:re|fw|fwd|转发|回复|转寄|回覆|轉寄)\s*[:：]\s*"
    normalized = subject.strip()
    prev = None
    while prev != normalized:
        prev = normalized
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE).strip()
    return normalized


def _subject_similarity(s1: str, s2: str) -> float:
    """计算两个邮件主题的相似度（0-1）"""
    n1 = _normalize_subject(s1)
    n2 = _normalize_subject(s2)
    if not n1 or not n2:
        return 0.0
    return SequenceMatcher(None, n1, n2).ratio()


# ── 邮件线程标识（L1，2026-11-23）────────────────────────────────
# 用标准邮件头 In-Reply-To / References 建立精确的线程关系，
# 不再依赖主题字符串相似度。主题相似度降级为兜底。

_MSG_ID_RE = re.compile(r"<[^<>]+>")


def _parse_msg_ids(raw: str) -> list[str]:
    """从 References / In-Reply-To 头解析 Message-ID 列表（保留尖括号）"""
    if not raw:
        return []
    ids = _MSG_ID_RE.findall(str(raw))
    if not ids:
        # 兜底：部分客户端不带尖括号，只收含 @ 的 token，避免把噪声当 Message-ID
        ids = [x.strip() for x in str(raw).split() if "@" in x]
    return [i.strip() for i in ids if i.strip()]


def _thread_root(message_id: str, references: str, in_reply_to: str) -> str:
    """线程根 ID：References 首个 ID > In-Reply-To > 自身 Message-ID"""
    refs = _parse_msg_ids(references)
    if refs:
        return refs[0]
    irt = _parse_msg_ids(in_reply_to)
    if irt:
        return irt[0]
    return (message_id or "").strip()


def _thread_lookup_ids(message_id: str, references: str, in_reply_to: str) -> list[str]:
    """用于反查工作项的 ID 集合：引用链 + In-Reply-To + 自身"""
    ids = _parse_msg_ids(references) + _parse_msg_ids(in_reply_to)
    if message_id:
        ids.append(message_id.strip())
    # 去重保序
    seen = set()
    out = []
    for i in ids:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


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


_EMAIL_BODY_STORAGE_LIMIT = 20000  # 存储正文最大字符数


def _html_to_text(html: str) -> str:
    """HTML 转纯文本（简单实现，不依赖第三方库）"""
    if not html:
        return ""
    # 去 script/style
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    # 块级标签与换行标签转换行
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|div|tr|li|h[1-6]|table|blockquote)>", "\n", text, flags=re.I)
    # 去其余标签
    text = re.sub(r"<[^>]+>", "", text)
    # 常见实体
    for entity, char in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")]:
        text = text.replace(entity, char)
    # 压缩空白行
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _extract_body_for_storage(body: str) -> Optional[str]:
    """将邮件正文转为可存纯文本：HTML去标签，截断2万字符"""
    if not body:
        return None
    text = body
    # 判断是否 HTML：包含标签即转换
    if re.search(r"<[a-zA-Z][^>]*>", text):
        text = _html_to_text(text)
    if not text:
        return None
    if len(text) > _EMAIL_BODY_STORAGE_LIMIT:
        text = text[:_EMAIL_BODY_STORAGE_LIMIT]
    return text


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


async def _message_id_exists(message_id: str) -> bool:
    """该邮件是否已入库（沙箱回填用，避免每轮重复拉全文）"""
    if not message_id:
        return False
    async with async_session() as db:
        result = await db.execute(select(EmailLog.id).where(EmailLog.message_id == message_id).limit(1))
        return result.scalar_one_or_none() is not None


async def _check_email_config(config: EmailConfig):
    """检查单个邮箱配置的新邮件

    沙箱模式（SANDBOX_FETCH_DAYS>0）：只读打开 INBOX + 按 SINCE 窗口取信 +
    不改邮件标志，可与生产实例共用同一邮箱做数据对照。
    """
    sandbox_mode = SANDBOX_FETCH_DAYS > 0
    try:
        loop = asyncio.get_event_loop()
        mail = await loop.run_in_executor(None, _imap_connect, config, sandbox_mode)
        if not mail:
            return

        if sandbox_mode:
            since = (datetime.utcnow() - timedelta(days=SANDBOX_FETCH_DAYS)).strftime("%d-%b-%Y")
            _, messages = mail.search(None, f'(SINCE "{since}")')
            email_ids = messages[0].split()
            per_round = SANDBOX_FETCH_LIMIT
        else:
            _, messages = mail.search(None, "UNSEEN")
            email_ids = messages[0].split()
            per_round = 10

        if sandbox_mode:
            # 先只看 Message-ID 头，跳过已入库的，避免每轮把窗口内全部正文重拉一遍。
            # 注意：必须"边扫边收集"，否则处理过的邮件会一直占住前 N 个位置，永远推进不到新的。
            total_in_window = len(email_ids)
            pending = []
            for eid in email_ids:
                if len(pending) >= per_round:
                    break
                mid = ""
                try:
                    _, hdr = mail.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
                    if hdr and hdr[0]:
                        raw_hdr = hdr[0][1] if isinstance(hdr[0], tuple) else hdr[0]
                        if raw_hdr:
                            mid = (email.message_from_bytes(raw_hdr).get("Message-ID") or "").strip()
                except Exception:
                    mid = ""
                if mid and await _message_id_exists(mid):
                    continue
                pending.append(eid)
            logger.info(f"沙箱抓取：窗口内 {total_in_window} 封，本轮待处理 {len(pending)} 封")
            email_ids = pending
            per_round = len(email_ids)

        for eid in email_ids[:per_round]:
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
                in_reply_to = _decode_str(msg.get("In-Reply-To", ""))
                references = _decode_str(msg.get("References", ""))
                body = _get_email_body(msg)

                if subject and body:
                    await _process_email_with_retry(
                        config, message_id, subject, from_addr, date_str, body,
                        to_addrs, cc_addrs, in_reply_to=in_reply_to, references=references
                    )
                    if not sandbox_mode:
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


def _imap_connect(config: EmailConfig, readonly: bool = False) -> Optional[imaplib.IMAP4_SSL]:
    """IMAP 连接（同步）

    readonly=True 时以只读方式打开 INBOX：服务器会拒绝 STORE 等写操作，
    确保沙箱实例不可能影响生产实例依赖的 \Seen 标志。
    """
    try:
        mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port, timeout=30)
        mail.login(config.username, config.password)
        mail.select("INBOX", readonly=readonly)
        return mail
    except Exception as e:
        logger.error(f"IMAP连接失败 {config.email_address}: {e}")
        return None


def _extract_email_prefixes(addr_str: str) -> list[str]:
    """从 To/Cc 字段提取所有邮箱前缀（@ 前面的部分）"""
    if not addr_str:
        return []
    prefixes = []
    # 匹配邮箱地址
    emails = re.findall(r'[\w.+-]+@[\w.-]+', addr_str)
    for email_addr in emails:
        prefix = email_addr.split('@')[0].strip('<>').strip()
        if prefix:
            prefixes.append(prefix)
    return prefixes



async def _send_ai_failure_alert(config_email: str, failures: list):
    """发送 AI 分析失败告警邮件到管理员。
    
    Args:
        config_email: 监控邮箱地址
        failures: 失败列表，每项为 {"subject": ..., "from": ..., "error": ...}
    """
    import time
    global _last_alert_time, _pending_failures
    
    now = time.time()
    _pending_failures.extend(failures)
    
    # 冷却期内不发送，累积失败
    if now - _last_alert_time < _alert_cooldown_seconds:
        logger.info(f"AI告警冷却中，累积 {_pending_failures} 条失败记录")
        return
    
    # 读取 SMTP 配置
    try:
        async with async_session() as db:
            result = await db.execute(
                select(EmailConfig).where(EmailConfig.is_active == True).limit(1)
            )
            smtp_config = result.scalar_one_or_none()
        
        if not smtp_config:
            logger.error("无可用SMTP配置，无法发送AI失败告警")
            return
        
        # 构建邮件内容
        failure_count = len(_pending_failures)
        failure_details = "\n".join([
            f"  • 主题: {f['subject'][:60]} | 发件人: {f.get('from', '未知')} | 错误: {f.get('error', '未知')}"
            for f in _pending_failures
        ])
        
        subject = f"[GWS告警] AI邮件分析失败 ({failure_count}封邮件)"
        body = f"""集团工作跟进系统 - AI分析失败告警
{'='*50}

监控邮箱: {config_email}
告警时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
失败数量: {failure_count} 封邮件

失败详情:
{failure_details}

{'='*50}
可能原因:
  1. Coze API Token 已过期（最常见 - 需每月更新）
  2. Coze Bot 服务异常
  3. 网络连接问题

处理方式:
  请登录 Coze 开放平台 (https://www.coze.cn) 重新生成 API Token，
  然后更新服务器 /opt/gws-project/.env 中的 COZE_API_TOKEN 并重启容器:
    cd /opt/gws-project && docker compose down && docker compose up -d

此邮件由系统自动发送，冷却时间1小时内不会重复告警。
"""
        
        # 发送 SMTP 邮件
        msg = MIMEMultipart()
        msg['From'] = smtp_config.username
        msg['To'] = DEFAULT_ADMIN_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _smtp_send, smtp_config, msg)
        
        _last_alert_time = now
        _pending_failures.clear()
        logger.info(f"AI失败告警邮件已发送至 {DEFAULT_ADMIN_EMAIL}")
        
    except Exception as e:
        logger.error(f"发送AI失败告警邮件失败: {e}")


def _smtp_send(config, msg):
    """同步发送 SMTP 邮件（在线程池中执行）"""
    try:
        if config.use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, context=context, timeout=30) as server:
                server.login(config.username, config.password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(config.username, config.password)
                server.send_message(msg)
    except Exception as e:
        logger.error(f"SMTP发送失败: {e}")
        raise


async def _cache_email_url_for_recipients(
    message_id: str,
    to_addrs: str,
    cc_addrs: str,
    work_item_id: int,
):
    """收件时主动缓存 conversationId（方案A）

    为 adam.wang + 邮件收件人 缓存 conversationId，
    这样用户点击"查看原邮件"时可以直接从缓存读取。

    Args:
        message_id: 邮件的 Message-ID（带尖括号）
        to_addrs: To 字段
        cc_addrs: Cc 字段
        work_item_id: 工作项 ID
    """
    try:
        # 提取收件人邮箱前缀
        recipient_prefixes = _extract_email_prefixes(to_addrs) + _extract_email_prefixes(cc_addrs)
        recipient_prefixes = list(set(recipient_prefixes))  # 去重

        # 构建目标用户列表
        target_emails = [DEFAULT_ADMIN_EMAIL]

        # 查询系统中对应的用户邮箱
        if recipient_prefixes:
            async with async_session() as db:
                result = await db.execute(
                    select(User.email).where(User.email_prefix.in_(recipient_prefixes))
                )
                for row in result:
                    if row[0] and row[0] != DEFAULT_ADMIN_EMAIL:
                        target_emails.append(row[0])

        # 调用 API 缓存 conversationId
        results = await cache_conversation_ids_for_message(
            internet_message_id=message_id,
            target_emails=target_emails,
            work_item_id=work_item_id,
        )

        # 记录结果
        found_count = sum(1 for v in results.values() if v)
        logger.info(
            f"主动缓存完成: work_item={work_item_id}, "
            f"目标用户={len(target_emails)}, 成功={found_count}"
        )

    except Exception as e:
        # 缓存失败不影响邮件处理结果
        logger.warning(f"主动缓存 conversationId 失败（不影响邮件处理）: {e}")


async def _process_email_with_retry(
    config: EmailConfig,
    message_id: str,
    subject: str,
    from_addr: str,
    date_str: str,
    body: str,
    to_addrs: str = "",
    cc_addrs: str = "",
    in_reply_to: str = "",
    references: str = ""
):
    """处理邮件，支持重试机制"""
    retry_count = 0

    while retry_count <= MAX_RETRY_COUNT:
        result = await _process_email(
            message_id, subject, from_addr, date_str, body, retry_count, to_addrs, cc_addrs,
            in_reply_to=in_reply_to, references=references
        )

        if result == EmailProcessResult.SUCCESS:
            return
        elif result == EmailProcessResult.AI_FAILED:
            retry_count += 1
            if retry_count <= MAX_RETRY_COUNT:
                logger.info(f"AI分析失败，第 {retry_count} 次重试: {subject}")
                await asyncio.sleep(2)
            else:
                logger.warning(f"AI分析失败，已达最大重试次数: {subject}")
                # 发送告警邮件通知管理员
                try:
                    await _send_ai_failure_alert(
                        config.email_address,
                        [{"subject": subject, "from": from_addr, "error": "AI分析失败(重试耗尽)"}]
                    )
                except Exception as e:
                    logger.error(f"发送AI失败告警异常: {e}")
                return
        else:
            retry_count += 1
            if retry_count <= MAX_RETRY_COUNT:
                logger.info(f"处理失败，第 {retry_count} 次重试: {subject}")
                await asyncio.sleep(2)
            else:
                logger.warning(f"处理失败，已达最大重试次数: {subject}")
                return


async def _find_matching_work_item(
    db: AsyncSession,
    subject: str,
    item_type: str,
    lookup_ids: Optional[list] = None,
) -> Optional[WorkItem]:
    """查找可合并的工作项。

    优先级（L1，2026-11-23）：
      ① 邮件线程精确匹配：工作项记录的 thread_id 出现在本邮件的引用链里
      ② 引用链反查：引用链里的某封历史邮件曾归属哪个工作项
      ③ 主题相似度兜底（仅未完成项，避免误并）

    ① ② 不受工作项状态限制——已完成/已取消的工作项同样接收后续邮件，
    这正是此前「同一邮件串生成多个工作项」的根因。
    """
    if lookup_ids:
        # ① 线程精确匹配
        result = await db.execute(
            select(WorkItem).where(WorkItem.thread_id.in_(lookup_ids))
        )
        for item in result.scalars().all():
            logger.info(f"线程匹配到工作项 #{item.id}（状态 {item.status}）")
            return item

        # ② 引用链反查历史邮件
        result = await db.execute(
            select(EmailLog.work_item_id)
            .where(EmailLog.message_id.in_(lookup_ids), EmailLog.work_item_id.isnot(None))
            .order_by(EmailLog.id)
            .limit(1)
        )
        wid = result.scalar_one_or_none()
        if wid:
            result = await db.execute(select(WorkItem).where(WorkItem.id == wid))
            item = result.scalar_one_or_none()
            if item:
                logger.info(f"引用链反查命中工作项 #{item.id}（状态 {item.status}）")
                return item

    # ③ 主题相似度兜底
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
    cc_addrs: str = "",
    in_reply_to: str = "",
    references: str = ""
) -> EmailProcessResult:
    """处理邮件：AI分析并入库，返回处理结果"""
    # 线程标识：同一邮件串的所有邮件共享同一个 thread_root
    thread_root = _thread_root(message_id, references, in_reply_to)
    lookup_ids = _thread_lookup_ids(message_id, references, in_reply_to)
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
            # ── report类型关键词兜底（防止AI漏识别报告/周报/汇总类邮件） ──
            # 如果标题含明确报告类关键词，且不含会签审批类词，强制为report
            if item_type != "cosign":
                _norm_subj = _normalize_subject(subject)
                _has_report_kw = any(kw in _norm_subj for kw in REPORT_KEYWORDS)
                _has_exclude_kw = any(kw in _norm_subj for kw in REPORT_EXCLUDE_KEYWORDS)
                if _has_report_kw and not _has_exclude_kw:
                    if item_type != "report":
                        logger.info(f"标题含汇报关键词，类型修正 {item_type} → report: {_norm_subj[:50]}")
                    item_type = "report"
            # 设置默认截止日期：cosign/report=24小时，task=7个自然日
            if not due_date:
                if item_type in ("cosign", "report"):
                    due_date = datetime.utcnow() + timedelta(days=1)
                else:
                    due_date = datetime.utcnow() + timedelta(days=7)
            completion = analysis.get("completion_assessment", "in_progress")

            # 确定工作项状态：report类型强制completed
            if item_type == "report":
                new_status = WorkItemStatus.completed
            elif completion == "completed":
                new_status = WorkItemStatus.completed
            elif completion == "in_progress":
                new_status = WorkItemStatus.pending
            else:
                new_status = WorkItemStatus.pending

            # 查找是否有相似的工作项（重复合并）
            matching_item = await _find_matching_work_item(db, subject, item_type, lookup_ids)

            if matching_item:
                # 合并到已有工作项：更新内容、责任人、状态
                logger.info(f"合并邮件到工作项 #{matching_item.id}")
                matching_item.content = analysis.get("summary", matching_item.content)
                # 注意：合并邮件不更新负责人（assignee）和主办人（sponsor）。
                # 主办人/负责人以最早（创建）邮件为准：主办人=最早邮件发起人，
                # 会签类的负责人=创建邮件提取的签署人名单。
                # 若随后续邮件更新，会覆盖签署人名单、导致主办人漂移到回复人。
                if due_date:
                    matching_item.due_date = due_date
                # 本次邮件到达前的工作项状态（L2 判定用，须在状态升级之前取）
                _prev_status = matching_item.status
                # 状态只升级，不降级（completed > pending）
                status_priority = {"pending": 0, "completed": 1, "cancelled": 0}
                if status_priority.get(new_status.value, 0) > status_priority.get(matching_item.status, 0):
                    matching_item.status = new_status
                matching_item.updated_at = datetime.utcnow()

                # 补全线程标识（历史工作项可能没有）
                if not matching_item.thread_id and thread_root:
                    matching_item.thread_id = thread_root

                # ── L2：已完成工作项收到邮件串后续回复的处理（2026-11-23）──
                # 汇报：只留痕不复活（它是知会件，且考核取数只认 completed）
                # 任务：本次回复若未表示「已完成」，复活为待办；回复本身说已完成则保持完成
                # 会签：状态交给 L3 会签追踪，这里不动
                if matching_item.item_type == "report":
                    matching_item.has_new_reply = True
                    _prog = (analysis.get("summary") or "").strip()
                    if _prog:
                        _line = f"[{datetime.utcnow():%Y-%m-%d %H:%M}] {_prog[:300]}"
                        _old = (matching_item.latest_progress or "").strip()
                        matching_item.latest_progress = ((_old + "\n" + _line).strip())[-2000:]
                    logger.info(f"汇报 #{matching_item.id} 收到后续邮件，已追加进度（不复活）")
                elif (
                    matching_item.item_type == "task"
                    and _prev_status == WorkItemStatus.completed.value
                    and new_status != WorkItemStatus.completed
                ):
                    matching_item.status = WorkItemStatus.pending.value
                    matching_item.completed_at = None
                    matching_item.completed_by = None
                    db.add(StatusChangeLog(
                        work_item_id=matching_item.id,
                        old_status=WorkItemStatus.completed.value,
                        new_status=WorkItemStatus.pending.value,
                        operator_id=None,
                        remark="收到邮件串后续回复，系统自动重新打开",
                    ))
                    logger.info(f"任务 #{matching_item.id} 收到后续回复，已自动重新打开")

                work_item_id = matching_item.id

                # ── 会签回复追踪 ──
                # 如果是会签工作项收到回复邮件，分析回复内容并更新追踪
                if matching_item.item_type == "cosign":
                    try:
                        sender_prefix = extract_sender_prefix(from_addr)
                        reply_analysis = await analyze_cosign_reply(subject, body)
                        await update_cosign_tracking(
                            work_item_id, sender_prefix, reply_analysis, subject, reply_body=body
                        )
                    except Exception as e:
                        logger.warning(f"会签追踪更新失败 (wi={work_item_id}): {e}")
            else:
                # 创建新工作项
                # report类型不需要责任人
                if item_type == "report":
                    assignee_prefix = None
                    assignee_id = None
                else:
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

                # 自动带出区域：负责人 → 负责人邮箱前缀 → 发件人（2026-11-18）
                district_id = None
                if assignee_id:
                    _r = await db.execute(select(User.district_id).where(User.id == assignee_id))
                    district_id = _r.scalar_one_or_none()
                if not district_id and assignee_prefix:
                    _prefixes = [x.strip() for x in str(assignee_prefix).replace(' ', ',').split(',') if x.strip()]
                    if _prefixes:
                        _r = await db.execute(select(User.district_id).where(User.email_prefix.in_(_prefixes)))
                        _ds = {row[0] for row in _r.all() if row[0]}
                        if len(_ds) == 1:
                            district_id = _ds.pop()
                if not district_id:
                    try:
                        _sender_prefix = extract_sender_prefix(from_addr)
                    except Exception:
                        _sender_prefix = None
                    if _sender_prefix:
                        _r = await db.execute(select(User.district_id).where(User.email_prefix == _sender_prefix))
                        district_id = _r.scalar_one_or_none()
                # 都推不出来 → 按业务口径归香港（2026-11-18）
                if not district_id:
                    district_id = 1

                item = WorkItem(
                    title=analysis.get("title", subject[:100]),
                    content=analysis.get("summary", body[:500]),
                    item_type=item_type,
                    status=new_status,
                    department_id=dept.id,
                    district_id=district_id,
                    assignee_id=assignee_id,
                    assignee_email_prefix=assignee_prefix,
                    due_date=due_date,
                    is_confidential=analysis.get("is_confidential", False),
                    message_id=message_id,
                    email_subject=_normalize_subject(subject),
                    email_from=from_addr,
                    sender_email=_extract_sender_email(from_addr),
                    email_date=datetime.utcnow(),
                    thread_id=thread_root,
                )
                db.add(item)
                await db.flush()
                work_item_id = item.id
                logger.info(f"成功创建工作项: {item.title} (状态: {new_status.value})")

                # 如果是会签类型，初始化追踪
                if item_type == "cosign":
                    await initialize_cosign_tracking(work_item_id)

            # 记录邮件日志
            log = EmailLog(
                message_id=message_id,
                subject=subject,
                from_addr=from_addr,
                received_at=datetime.utcnow(),
                body=_extract_body_for_storage(body),
                process_result=EmailProcessResult.SUCCESS,
                retry_count=retry_count,
                error_message=None,
                work_item_id=work_item_id,
                thread_id=thread_root,
                in_reply_to=in_reply_to or None,
                references_header=references or None,
            )
            db.add(log)
            await db.commit()

            # ── 方案A：主动缓存 conversationId ──
            # 在邮件刚到达时，为目标用户缓存 conversationId，避免后续查询时邮件已超出 API 范围
            await _cache_email_url_for_recipients(message_id, to_addrs, cc_addrs, work_item_id)

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
