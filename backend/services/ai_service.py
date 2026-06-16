"""Coze AI 邮件分析服务"""
import json
import logging
import re
from typing import Optional, Dict, Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业的工作邮件分析引擎。你的唯一任务是：接收邮件内容，输出结构化的 JSON 工作项数据。

重要约束：
- 你只输出 JSON，不输出任何解释、问候、markdown 格式
- 不要输出 ```json 代码块标记，直接输出纯 JSON 字符串
- 不要添加任何额外字段，严格按照指定格式

输出格式：
{
    "title": "工作项标题",
    "summary": "AI总结归纳的工作内容",
    "type": "task",
    "department": "部门名称",
    "assignee_prefix": "邮箱前缀或null",
    "due_date": "YYYY-MM-DD或null",
    "is_confidential": false
}

字段说明：

title（必填）
- 从邮件主题和内容中提取核心工作事项
- 简明扼要，不超过50个中文字
- 格式：动词 + 对象，如"完成Q3财务报表编制"、"推进XX项目审批"

summary（必填）
- 用简洁语言总结：谁/做什么/为何做
- 100字以内
- 必须阅读完整邮件内容（包括转发体）后进行归纳总结，不是简单截取原文
- 例如："向炜兴对王辰元调休事假申请提出会签意见，转发至陶金城等继续会签审批"

type（必填，二选一）
- "task"：普通工作任务（默认值）
- "cosign"：会签/审批类任务
- 判断依据：邮件中包含"会签"、"审批"、"签批"、"签署"、"批复"、"征求意见"等关键词时，type 为 "cosign"

department（必填，从以下4个部门中选择1个）
可选值：
- 人事/商务部
- 财审/投资部
- 行政/产品部
- 法务/媒体部
判断规则：
1. 涉及招聘、薪酬、绩效考核、商务合同、客户合作 → 人事/商务部
2. 涉及财务审计、预算、资金、投资、融资、股权 → 财审/投资部
3. 涉及行政管理、办公用品、产品规划、产品设计、日常运营 → 行政/产品部
4. 涉及法律事务、合规、合同审核、媒体公关、品牌宣传 → 法务/媒体部
5. 无法判断时，默认返回 "行政/产品部"

assignee_prefix（可选）
- 如果邮件中明确指定了责任人，提取其邮箱前缀（通常是中文姓名的拼音）
- 例如：邮件提到"请张三负责"，则返回 "zhangsan"
- 如果无法确定责任人，返回 null

责任人提取规则（重要）：
1. 优先从邮件正文中提取明确指定的责任人
2. 会签类邮件兜底：如果AI无法从正文中提取责任人，且邮件涉及会签/审批，则将收件人（非抄送人）作为责任人
3. 转发邮件规则：转发人不作为责任人，需解析转发体中的实际执行人/会签人
   - 例如：adam.wang转发了一封会签邮件，adam.wang不是责任人，应从转发体中找到实际会签人

due_date（可选）
- 如果邮件中有明确的截止日期，提取为 YYYY-MM-DD 格式
- 如果没有明确截止时间，返回 null

is_confidential（必填，布尔值）
- true：邮件涉及敏感内容（机密、保密、并购、重组、高管人事变动、敏感财务数据）
- false：普通邮件

转发邮件处理规则（重要）：
- 必须解析转发体，提取完整原始邮件内容
- 不能仅提取外层附言，要理解转发体中的完整邮件链
- 转发人不是责任人，要从转发体中找到实际执行人"""

# Coze API 端点
_COZE_CONVERSATION_URL = "/v3/conversation/create"
_COZE_CHAT_URL = "/v3/chat"
_COZE_CHAT_RETRIEVE_URL = "/v3/chat/retrieve"
_COZE_CHAT_MESSAGES_URL = "/v3/chat/message/list"


async def analyze_email_with_ai(subject: str, body: str, to_addrs: str = "", cc_addrs: str = "") -> Optional[Dict[str, Any]]:
    """使用 Coze Bot API 分析邮件内容

    Args:
        subject: 邮件主题
        body: 邮件正文（已包含转发体内容）
        to_addrs: 收件人地址（用于责任人兜底提取）
        cc_addrs: 抄送人地址（排除抄送人）
    """
    if not settings.COZE_API_TOKEN or not settings.COZE_BOT_ID:
        logger.warning("Coze API Token 或 Bot ID 未配置，使用默认分析")
        return _fallback_analysis(subject, body)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            headers = {
                "Authorization": f"Bearer {settings.COZE_API_TOKEN}",
                "Content-Type": "application/json",
            }
            base_url = settings.COZE_API_BASE.rstrip("/")

            # 1. 创建会话
            conv_resp = await client.post(
                f"{base_url}{_COZE_CONVERSATION_URL}",
                headers=headers,
                json={"messages": []},
            )
            conv_resp.raise_for_status()
            conv_data = conv_resp.json()
            conversation_id = conv_data["data"]["id"]

            # 2. 发送消息
            # 构建完整的邮件信息，包括收件人（用于责任人兜底）
            email_content = f"邮件主题：{subject}\n"
            if to_addrs:
                email_content += f"收件人：{to_addrs}\n"
            if cc_addrs:
                email_content += f"抄送人：{cc_addrs}\n"
            email_content += f"\n邮件内容：\n{body[:5000]}"  # 增加长度限制以支持转发邮件

            chat_resp = await client.post(
                f"{base_url}{_COZE_CHAT_URL}",
                headers=headers,
                json={
                    "bot_id": settings.COZE_BOT_ID,
                    "user_id": "gws-system",
                    "conversation_id": conversation_id,
                    "additional_messages": [
                        {"role": "user", "content": email_content}
                    ],
                    "stream": False,
                },
            )
            chat_resp.raise_for_status()
            chat_data = chat_resp.json()
            chat_id = chat_data["data"]["id"]

            # 3. 轮询等待完成
            for _ in range(30):  # 最多等 60 秒
                import asyncio
                await asyncio.sleep(2)

                retrieve_resp = await client.get(
                    f"{base_url}{_COZE_CHAT_RETRIEVE_URL}",
                    headers=headers,
                    params={"conversation_id": conversation_id, "chat_id": chat_id},
                )
                retrieve_resp.raise_for_status()
                status = retrieve_resp.json()["data"]["status"]

                if status == "completed":
                    break
                elif status == "failed":
                    logger.error(f"Coze Bot 处理失败: {retrieve_resp.json()}")
                    return _fallback_analysis(subject, body)

            # 4. 获取回复消息
            msg_resp = await client.get(
                f"{base_url}{_COZE_CHAT_MESSAGES_URL}",
                headers=headers,
                params={"conversation_id": conversation_id, "chat_id": chat_id},
            )
            msg_resp.raise_for_status()
            messages = msg_resp.json()["data"]

            # 找到 bot 的回复
            content = ""
            for msg in messages:
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    break

            if not content:
                logger.error("Coze Bot 返回空内容")
                return _fallback_analysis(subject, body)

            # 解析 JSON（处理可能的 markdown 代码块包裹）
            content = content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
                content = content.strip()

            result = json.loads(content)
            return result

    except json.JSONDecodeError as e:
        logger.error(f"Coze Bot 返回内容 JSON 解析失败: {e}")
        return _fallback_analysis(subject, body)
    except httpx.HTTPError as e:
        logger.error(f"Coze API 调用失败: {e}")
        return _fallback_analysis(subject, body)
    except Exception as e:
        logger.error(f"AI 分析异常: {e}")
        return _fallback_analysis(subject, body)


def _fallback_analysis(subject: str, body: str) -> Dict[str, Any]:
    """降级分析（当 AI 不可用时）"""
    is_cosign = any(kw in subject + body for kw in ["会签", "审批", "签批", "签署"])
    is_confidential = any(kw in subject + body for kw in ["机密", "保密", "内部", "战略", "并购"])

    return {
        "title": subject[:100] if subject else "未命名工作项",
        "summary": body[:200] if body else subject[:200],
        "type": "cosign" if is_cosign else "task",
        "department": "行政/产品部",
        "assignee_prefix": None,
        "due_date": None,
        "is_confidential": is_confidential,
    }
