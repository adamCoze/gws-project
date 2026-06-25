"""阿里邮箱 API 服务 - 用于查询邮件并构造跳转URL

v1.8.5 策略（方案A - 收件时主动缓存）：
1. 收件时（IMAP处理完成后），立即为目标用户缓存 conversationId
   - 邮件刚到达时一定在收件人邮箱的最新 ~99 封内
   - 此时调 API 一定能找到并缓存
2. 用户点击 🔗 时：先查缓存 → 未命中再实时查找（最近~99封范围内精确匹配）
3. API 已知限制（不修复，绕过）：
   - filter 参数被忽略
   - nextCursor 翻页不工作
   - 只能获取每个文件夹最新的 ~99 封邮件
4. 使用单一 httpx.AsyncClient 实例复用连接
"""
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

# 共享的 httpx client（复用连接，避免每次请求都建立TLS）
_shared_client: Optional[httpx.AsyncClient] = None


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


async def _get_latest_messages(
    user_email: str,
    folder_id: int,
    size: int = 99,
) -> list:
    """获取用户指定文件夹的最新邮件（不翻页，API不支持）

    Args:
        user_email: 目标用户邮箱
        folder_id: 文件夹ID（2=收件箱, 1=发件箱）
        size: 获取数量，最大99

    Returns:
        邮件列表，每封包含 id, conversationId, internetMessageId 等
    """
    token = await _get_access_token()
    client = await _get_client()

    params = {
        "size": size,
        "$select": "id,conversationId,internetMessageId",
    }

    try:
        resp = await client.get(
            f"{settings.ALIMAIL_API_BASE}/v2/users/{user_email}/mailFolders/{folder_id}/messages",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            logger.error(f"获取邮件列表失败: user={user_email}, folder={folder_id}, status={resp.status_code}")
            return []

        data = resp.json()
        if "detailErrorCode" in data:
            logger.error(f"API错误: {data.get('detailErrorCode')} - {data.get('message')}")
            return []

        messages = data.get("messages", [])
        logger.info(f"获取到 {len(messages)} 封邮件: user={user_email}, folder={folder_id}")
        return messages

    except Exception as e:
        logger.error(f"获取邮件列表异常: user={user_email}, folder={folder_id}, error={e}")
        return []


def _match_message_id(api_message_id: str, target_message_id: str) -> bool:
    """匹配 internetMessageId，处理尖括号差异

    API返回的可能带或不带尖括号，统一去掉后比较。
    使用包含匹配以兼容不同的格式变体。
    """
    if not api_message_id or not target_message_id:
        return False
    # 去掉尖括号
    clean_api = api_message_id.strip("<>").strip()
    clean_target = target_message_id.strip("<>").strip()
    return clean_api == clean_target or clean_target in clean_api


async def find_conversation_id(
    user_email: str,
    internet_message_id: str,
) -> Optional[str]:
    """在用户邮箱中查找邮件的 conversationId（公开方法）

    只使用精确匹配 internetMessageId，在收件箱和发件箱的最新99封中查找。

    Args:
        user_email: 目标用户邮箱
        internet_message_id: 邮件的 Message-ID（可带或不带尖括号）

    Returns:
        conversationId 或 None
    """
    start_time = time.time()
    msg_id_clean = internet_message_id.strip("<>")

    for folder_id in [2, 1]:  # 收件箱, 发件箱
        messages = await _get_latest_messages(user_email, folder_id)
        for msg in messages:
            api_id = msg.get("internetMessageId", "")
            if _match_message_id(api_id, msg_id_clean):
                conv_id = msg.get("conversationId")
                if conv_id:
                    elapsed = time.time() - start_time
                    logger.info(
                        f"精确匹配成功: user={user_email}, folder={folder_id}, "
                        f"convId={conv_id}, elapsed={elapsed:.2f}s"
                    )
                    return conv_id

    elapsed = time.time() - start_time
    logger.warning(f"未找到匹配: user={user_email}, msgId={msg_id_clean}, elapsed={elapsed:.2f}s")
    return None


# ── 方案A：收件时主动缓存 ──────────────────────────────────


async def cache_conversation_ids_for_message(
    internet_message_id: str,
    target_emails: list[str],
) -> dict[str, Optional[str]]:
    """收件时主动为目标用户缓存 conversationId

    邮件刚到达时，一定在每个收件人邮箱的最新 ~99 封内。
    此时调 API 一定能找到并缓存。

    Args:
        internet_message_id: 邮件的 Message-ID（可带或不带尖括号）
        target_emails: 需要缓存的目标用户邮箱列表，如 ["adam.wang@ntg.com.hk", "zhangheng@ntg.com.hk"]

    Returns:
        dict: {user_email: conversation_id or None}
    """
    if not internet_message_id or not target_emails:
        return {}

    results = {}
    for user_email in target_emails:
        try:
            conv_id = await find_conversation_id(user_email, internet_message_id)
            results[user_email] = conv_id
            if conv_id:
                logger.info(f"主动缓存成功: user={user_email}, convId={conv_id}")
            else:
                logger.warning(f"主动缓存未找到: user={user_email}, msgId={internet_message_id}")
        except Exception as e:
            logger.error(f"主动缓存异常: user={user_email}, error={e}")
            results[user_email] = None

    return results


# ── 方案A：收件时主动缓存 ──────────────────────────────────


async def cache_conversation_ids_for_message(
    internet_message_id: str,
    target_emails: list[str],
    work_item_id: int,
) -> dict[str, Optional[str]]:
    """收件时主动为目标用户缓存 conversationId

    邮件刚到达时，一定在每个收件人邮箱的最新 ~99 封内。
    此时调 API 一定能找到并缓存。

    Args:
        internet_message_id: 邮件的 Message-ID（可带或不带尖括号）
        target_emails: 需要缓存的目标用户邮箱列表
        work_item_id: 对应的工作项 ID

    Returns:
        dict: {user_email: conversation_id or None}
    """
    if not internet_message_id or not target_emails:
        return {}

    # 导入数据库相关模块（延迟导入避免循环依赖）
    import sqlite3
    from datetime import datetime

    results = {}
    msg_id_clean = internet_message_id.strip("<>")

    for user_email in target_emails:
        try:
            conv_id = await find_conversation_id(user_email, internet_message_id)
            results[user_email] = conv_id

            # 写入缓存
            try:
                conn = sqlite3.connect("/app/backend/data/gws.db")
                conn.execute(
                    "DELETE FROM email_url_cache WHERE user_email = ? AND work_item_id = ?",
                    (user_email, work_item_id)
                )
                now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                if conv_id:
                    conn.execute(
                        "INSERT INTO email_url_cache (user_email, work_item_id, conversation_id, status, created_at) VALUES (?, ?, ?, ?, ?)",
                        (user_email, work_item_id, conv_id, "found", now_str)
                    )
                    logger.info(f"主动缓存成功: user={user_email}, work_item={work_item_id}, convId={conv_id}")
                else:
                    conn.execute(
                        "INSERT INTO email_url_cache (user_email, work_item_id, conversation_id, status, created_at) VALUES (?, ?, ?, ?, ?)",
                        (user_email, work_item_id, None, "not_found", now_str)
                    )
                    logger.warning(f"主动缓存未找到: user={user_email}, work_item={work_item_id}, msgId={msg_id_clean}")
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"缓存写入失败: user={user_email}, error={e}")

        except Exception as e:
            logger.error(f"主动缓存异常: user={user_email}, error={e}")
            results[user_email] = None

    return results


# ── 向后兼容：get_email_url（用户点击时的实时查找） ──────────


async def get_email_url(
    user_email: str,
    email_subject: str,
    internet_message_id: str,
    sender_email: Optional[str] = None,
    email_date=None,
) -> Optional[str]:
    """获取阿里邮箱中指定邮件的跳转URL

    只在最新~99封邮件范围内精确匹配。
    如果邮件已不在范围内，返回 None（此时应由缓存提供）。
    """
    try:
        conversation_id = await find_conversation_id(
            user_email=user_email,
            internet_message_id=internet_message_id,
        )

        if conversation_id:
            url = _build_url(conversation_id)
            logger.info(f"构造邮件URL: convId={conversation_id}")
            return url

        return None

    except Exception as e:
        logger.error(f"获取邮件URL失败: {e}")
        return None
