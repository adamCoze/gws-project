"""阿里邮箱 API 服务 - 用于查询邮件并构造跳转URL

策略：
1. 优先查本地缓存 email_url_cache（毫秒级）
2. 缓存未命中时，用 list API 按日期过滤列出邮件，匹配 internetMessageId
3. 精确匹配失败时，降级为按主题关键词搜索同会话邮件
4. 找到后写入缓存，构造URL返回
5. 使用单一 httpx.AsyncClient 实例复用连接
"""
import base64
import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Token 缓存
_token_cache: dict = {"token": None, "expires_at": 0}

# 共享的 httpx client（复用连接，避免每次请求都建立TLS）
_shared_client: Optional[httpx.AsyncClient] = None

# 最大翻页数限制
MAX_PAGES = 10
# 每页数量
PAGE_SIZE = 50
# 单次查找最大耗时（秒）
MAX_SEARCH_TIME = 10


async def _get_client() -> httpx.AsyncClient:
    """获取共享的 httpx client"""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=30)
    return _shared_client


async def _get_access_token() -> str:
    """获取阿里邮箱API访问令牌，带缓存和自动刷新"""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 3600:
        return _token_cache["token"]

    client = await _get_client()
    resp = await client.post(
        f"{settings.ALIMAIL_API_BASE}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": settings.ALIMAIL_APP_ID,
            "client_secret": settings.ALIMAIL_APP_SECRET,
            "scope": "Mail.Read.All",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["access_token"]
    expires_in = data.get("expires_in", 172799)

    _token_cache["token"] = token
    _token_cache["expires_at"] = now + expires_in

    logger.info(f"阿里邮箱API token已刷新，有效期 {expires_in}s")
    return token


def _build_url(conversation_id: str) -> str:
    """根据 conversationId 构造阿里邮箱跳转URL"""
    url_payload = json.dumps({"id": conversation_id, "type": "session"})
    encoded = base64.b64encode(url_payload.encode()).decode()
    return f"{settings.ALIMAIL_WEBMAIL_BASE}{encoded}"


def _clean_subject(subject: str) -> str:
    """去除邮件主题前缀，提取核心关键词用于降级搜索"""
    prefixes = [
        r'^转发[：:]\s*', r'^Fwd[：:]\s*', r'^Fw[：:]\s*',
        r'^RE[：:]\s*', r'^Re[：:]\s*', r'^回复[：:]\s*', r'^答复[：:]\s*',
    ]
    cleaned = subject
    for _ in range(5):  # 递归去除多层前缀
        before = cleaned
        for p in prefixes:
            cleaned = re.sub(p, '', cleaned, flags=re.IGNORECASE)
        if cleaned == before:
            break
    return cleaned.strip()


async def _list_folder_messages(
    client: httpx.AsyncClient,
    token: str,
    user_email: str,
    folder_id: int,
    filter_str: Optional[str],
    select_fields: str,
    start_time: float,
    max_pages: int = MAX_PAGES,
    max_time: float = MAX_SEARCH_TIME,
) -> list:
    """翻页获取指定文件夹的所有邮件，返回消息列表"""
    all_messages = []
    next_cursor = None
    pages = 0

    while pages < max_pages:
        pages += 1
        if time.time() - start_time > max_time:
            logger.warning(f"翻页超时({time.time()-start_time:.1f}s)，停止")
            break

        params = {"size": PAGE_SIZE, "$select": select_fields}
        if filter_str:
            params["filter"] = filter_str
        if next_cursor:
            params["nextCursor"] = next_cursor

        try:
            resp = await client.get(
                f"{settings.ALIMAIL_API_BASE}/v2/users/{user_email}/mailFolders/{folder_id}/messages",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                logger.error(f"列出邮件失败: folder={folder_id}, status={resp.status_code}")
                # 去掉 filter 重试一次
                if filter_str and pages == 1:
                    params.pop("filter", None)
                    resp = await client.get(
                        f"{settings.ALIMAIL_API_BASE}/v2/users/{user_email}/mailFolders/{folder_id}/messages",
                        params=params,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if resp.status_code != 200:
                        break
                else:
                    break

            data = resp.json()
            if "detailErrorCode" in data:
                logger.error(f"API错误: {data.get('detailErrorCode')} - {data.get('message')}")
                break

            messages = data.get("messages", [])
            all_messages.extend(messages)

            if not data.get("hasMore"):
                break
            next_cursor = data.get("nextCursor")
            if not next_cursor:
                break
        except Exception as e:
            logger.error(f"列出邮件异常: folder={folder_id}, page={pages}, error={e}")
            break

    return all_messages


async def _find_conversation_id(
    user_email: str,
    internet_message_id: str,
    email_date: Optional[datetime] = None,
    email_subject: Optional[str] = None,
) -> Optional[str]:
    """在用户邮箱中查找邮件的 conversationId

    策略：
    1. 优先精确匹配 internetMessageId
    2. 失败时降级：用清洗后的主题关键词按主题搜索同会话邮件
    """
    start_time = time.time()
    token = await _get_access_token()
    client = await _get_client()

    # 确定日期范围：邮件日期前后7天
    date_start = None
    date_end = None
    if email_date:
        date_start = email_date - timedelta(days=7)
        date_end = email_date + timedelta(days=7)

    filter_str = None
    if date_start and date_end:
        filter_str = (
            f"receivedDateTime ge {date_start.strftime('%Y-%m-%dT00:00:00Z')} "
            f"and receivedDateTime le {date_end.strftime('%Y-%m-%dT23:59:59Z')}"
        )

    logger.info(f"开始搜索: user={user_email}, msgId={internet_message_id}, filter={filter_str}")

    # ── 阶段1：精确匹配 internetMessageId ──
    for folder_id in [2, 1]:  # 收件箱, 发件箱
        messages = await _list_folder_messages(
            client, token, user_email, folder_id, filter_str,
            "id,conversationId,internetMessageId", start_time,
        )
        for msg in messages:
            msg_internet_id = msg.get("internetMessageId", "")
            if msg_internet_id and internet_message_id in msg_internet_id:
                conv_id = msg.get("conversationId")
                if conv_id:
                    logger.info(f"精确匹配成功: folder={folder_id}, convId={conv_id}, elapsed={time.time()-start_time:.2f}s")
                    return conv_id

    elapsed_s1 = time.time() - start_time
    logger.info(f"精确匹配未命中，耗时 {elapsed_s1:.1f}s")

    # ── 阶段2：降级 — 按主题关键词搜索 ──
    if not email_subject:
        logger.warning("无主题信息，无法降级搜索")
        return None

    keyword = _clean_subject(email_subject)
    if not keyword:
        logger.warning("主题清洗后为空，无法降级搜索")
        return None

    # 降级搜索使用更宽的时间范围（前后30天）
    fallback_start = None
    fallback_end = None
    if email_date:
        fallback_start = email_date - timedelta(days=30)
        fallback_end = email_date + timedelta(days=30)
    fallback_filter = None
    if fallback_start and fallback_end:
        fallback_filter = (
            f"receivedDateTime ge {fallback_start.strftime('%Y-%m-%dT00:00:00Z')} "
            f"and receivedDateTime le {fallback_end.strftime('%Y-%m-%dT23:59:59Z')}"
        )

    logger.info(f"降级搜索: keyword=\"{keyword}\", filter={fallback_filter}")

    for folder_id in [2, 1]:
        remaining_time = MAX_SEARCH_TIME * 2 - (time.time() - start_time)
        if remaining_time <= 0:
            break
        messages = await _list_folder_messages(
            client, token, user_email, folder_id, fallback_filter,
            "id,conversationId,subject", start_time,
            max_pages=MAX_PAGES, max_time=MAX_SEARCH_TIME * 2,
        )
        for msg in messages:
            subj = msg.get("subject", "")
            if keyword in subj:
                conv_id = msg.get("conversationId")
                if conv_id:
                    logger.info(
                        f"主题降级匹配成功: folder={folder_id}, subject=\"{subj}\", "
                        f"convId={conv_id}, elapsed={time.time()-start_time:.2f}s"
                    )
                    return conv_id

    logger.warning(f"所有搜索均未找到: msgId={internet_message_id}, elapsed={time.time()-start_time:.2f}s")
    return None


async def get_email_url(
    user_email: str,
    email_subject: str,
    internet_message_id: str,
    sender_email: Optional[str] = None,
    email_date: Optional[datetime] = None,
) -> Optional[str]:
    """获取阿里邮箱中指定邮件的跳转URL"""
    try:
        conversation_id = await _find_conversation_id(
            user_email=user_email,
            internet_message_id=internet_message_id,
            email_date=email_date,
            email_subject=email_subject,
        )
        
        if conversation_id:
            url = _build_url(conversation_id)
            logger.info(f"构造邮件URL: convId={conversation_id}")
            return url
        
        return None

    except Exception as e:
        logger.error(f"获取邮件URL失败: {e}")
        return None
