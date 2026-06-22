"""阿里邮箱 API 服务 - 用于查询邮件并构造跳转URL

策略：
1. 优先查本地缓存 email_url_cache（毫秒级）
2. 缓存未命中时，用 list API 按日期过滤列出邮件，匹配 internetMessageId
3. 找到后写入缓存，构造URL返回
4. 使用单一 httpx.AsyncClient 实例复用连接
"""
import base64
import json
import logging
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


async def _find_conversation_id(
    user_email: str,
    internet_message_id: str,
    email_date: Optional[datetime] = None,
) -> Optional[str]:
    """在用户邮箱中查找邮件的 conversationId"""
    start_time = time.time()
    token = await _get_access_token()
    client = await _get_client()
    
    # 确定日期范围：邮件日期前后7天
    date_start = None
    date_end = None
    if email_date:
        date_start = email_date - timedelta(days=7)
        date_end = email_date + timedelta(days=7)
    
    # 构建filter字符串
    filter_str = None
    if date_start and date_end:
        filter_str = (
            f"receivedDateTime ge {date_start.strftime('%Y-%m-%dT00:00:00Z')} "
            f"and receivedDateTime le {date_end.strftime('%Y-%m-%dT23:59:59Z')}"
        )
    
    logger.info(f"开始搜索: user={user_email}, filter={filter_str}")
    
    # 搜索收件箱(2)和已发送(1)
    for folder_id in [2, 1]:
        next_cursor = None
        pages = 0
        
        while pages < MAX_PAGES:
            pages += 1
            elapsed = time.time() - start_time
            if elapsed > MAX_SEARCH_TIME:
                logger.warning(f"搜索超时({elapsed:.1f}s)，停止翻页")
                break
            
            params = {
                "size": PAGE_SIZE,
                "$select": "id,conversationId,internetMessageId",
            }
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
                    logger.error(f"列出邮件失败: folder={folder_id}, page={pages}, status={resp.status_code}")
                    break
                
                data = resp.json()
                
                if "detailErrorCode" in data:
                    logger.error(f"API错误: {data.get('detailErrorCode')} - {data.get('message')}")
                    # 如果filter参数有问题，去掉重试
                    if filter_str and pages == 1:
                        logger.info("去掉filter参数重试")
                        filter_str = None
                        params.pop("filter", None)
                        resp = await client.get(
                            f"{settings.ALIMAIL_API_BASE}/v2/users/{user_email}/mailFolders/{folder_id}/messages",
                            params=params,
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        data = resp.json()
                        if "detailErrorCode" in data:
                            break
                    else:
                        break
                
                messages = data.get("messages", [])
                
                # 在当前页匹配 internetMessageId
                for msg in messages:
                    msg_internet_id = msg.get("internetMessageId", "")
                    if msg_internet_id and internet_message_id in msg_internet_id:
                        conversation_id = msg.get("conversationId")
                        if conversation_id:
                            logger.info(
                                f"找到邮件: folder={folder_id}, page={pages}, "
                                f"convId={conversation_id}, elapsed={time.time()-start_time:.2f}s"
                            )
                            return conversation_id
                
                # 检查是否还有更多
                if not data.get("hasMore"):
                    break
                next_cursor = data.get("nextCursor")
                if not next_cursor:
                    break
                    
            except Exception as e:
                logger.error(f"列出邮件异常: folder={folder_id}, page={pages}, error={e}")
                break
        
        elapsed = time.time() - start_time
        logger.info(f"folder={folder_id}搜索完成: pages={pages}, elapsed={elapsed:.2f}s")
    
    logger.warning(f"未找到邮件: internetMessageId={internet_message_id}, elapsed={time.time()-start_time:.2f}s")
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
        )
        
        if conversation_id:
            url = _build_url(conversation_id)
            logger.info(f"构造邮件URL: convId={conversation_id}")
            return url
        
        return None

    except Exception as e:
        logger.error(f"获取邮件URL失败: {e}")
        return None
