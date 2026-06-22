"""阿里邮箱 API 服务 - 用于查询邮件并构造跳转URL"""
import base64
import json
import logging
import time
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Token 缓存
_token_cache: dict = {"token": None, "expires_at": 0}


async def _get_access_token() -> str:
    """获取阿里邮箱API访问令牌，带缓存和自动刷新"""
    now = time.time()
    # 提前1小时刷新
    if _token_cache["token"] and _token_cache["expires_at"] > now + 3600:
        return _token_cache["token"]

    async with httpx.AsyncClient(timeout=30) as client:
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


async def _search_messages(
    user_email: str,
    subject: str,
    sender_email: Optional[str] = None,
) -> list:
    """用KQL搜索用户邮箱中的邮件，返回消息列表"""
    token = await _get_access_token()

    # 构建KQL查询
    kql_parts = [f'subject:"{subject}"']
    if sender_email:
        kql_parts.append(f'fromEmail:"{sender_email}"')
    kql_query = " AND ".join(kql_parts)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.ALIMAIL_API_BASE}/v2/users/{user_email}/messages/query",
            json={"kql": kql_query, "size": 50},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code != 200:
            logger.error(f"KQL搜索失败: {resp.status_code} {resp.text}")
            return []
        data = resp.json()
        return data.get("messages", [])


async def _get_message_detail(
    user_email: str,
    message_id: str,
) -> Optional[dict]:
    """获取邮件详情，包含conversationId"""
    token = await _get_access_token()

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.ALIMAIL_API_BASE}/v2/users/{user_email}/messages/{message_id}",
            params={"$select": "id,conversationId,internetMessageId,subject"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            logger.error(f"获取邮件详情失败: {resp.status_code} {resp.text}")
            return None
        data = resp.json()
        return data.get("message")


async def get_email_url(
    user_email: str,
    email_subject: str,
    internet_message_id: str,
    sender_email: Optional[str] = None,
) -> Optional[str]:
    """
    获取阿里邮箱中指定邮件的跳转URL
    
    Args:
        user_email: 当前登录用户的邮箱 (如 adam.wang@ntg.com.hk)
        email_subject: 邮件主题
        internet_message_id: RFC Message-ID (不含尖括号)
        sender_email: 发件人邮箱地址 (可选，用于缩小搜索范围)
    
    Returns:
        阿里邮箱跳转URL，找不到返回None
    """
    try:
        # Step 1: KQL搜索
        messages = await _search_messages(user_email, email_subject, sender_email)
        if not messages:
            logger.warning(f"KQL搜索无结果: subject={email_subject}, user={user_email}")
            return None

        # Step 2: 遍历结果匹配internetMessageId
        for msg in messages:
            msg_id = msg.get("id")
            if not msg_id:
                continue

            # 获取详情（含conversationId）
            detail = await _get_message_detail(user_email, msg_id)
            if not detail:
                continue

            msg_internet_id = detail.get("internetMessageId", "")
            # internetMessageId可能有不同的格式，做宽松匹配
            if msg_internet_id and internet_message_id in msg_internet_id:
                conversation_id = detail.get("conversationId")
                if conversation_id:
                    # Step 3: 构造URL
                    url_payload = json.dumps({"id": conversation_id, "type": "session"})
                    encoded = base64.b64encode(url_payload.encode()).decode()
                    url = f"{settings.ALIMAIL_WEBMAIL_BASE}{encoded}"
                    logger.info(f"找到邮件URL: conversationId={conversation_id}")
                    return url

        logger.warning(f"未找到匹配的邮件: internetMessageId={internet_message_id}")
        return None

    except Exception as e:
        logger.error(f"获取邮件URL失败: {e}")
        return None
