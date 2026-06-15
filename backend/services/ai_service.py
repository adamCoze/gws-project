"""DeepSeek AI 邮件分析服务"""
import json
import logging
from typing import Optional, Dict, Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业的工作邮件分析助手。你的任务是分析邮件内容，提取关键工作信息。

请严格按照以下JSON格式返回分析结果（不要包含任何其他文字）：
{
    "title": "工作项标题（简明扼要，不超过50字）",
    "summary": "工作项摘要（100字以内）",
    "type": "task或cosign（任务或会签）",
    "department": "部门名称（从以下选择：总裁办、规划管理部、区域一部、区域二部、运营部、财务部、人力资源部）",
    "assignee_prefix": "责任人邮箱前缀（如zhangsan，如果无法确定则返回null）",
    "due_date": "截止日期YYYY-MM-DD格式（如果无法确定则返回null）",
    "is_confidential": false
}

分析规则：
1. 如果邮件涉及财务数据、战略规划、人事变动等敏感内容，is_confidential设为true
2. 如果邮件中有明确的截止时间，提取为due_date
3. 如果邮件中@某人或指定某人负责，提取其邮箱前缀（通常是拼音）
4. 会签类邮件通常包含"会签"、"审批"、"签批"等关键词
5. 部门判断基于邮件内容和发件人信息"""


async def analyze_email_with_ai(subject: str, body: str) -> Optional[Dict[str, Any]]:
    """使用 DeepSeek AI 分析邮件内容"""
    if not settings.DEEPSEEK_API_KEY:
        logger.warning("DeepSeek API Key 未配置，使用默认分析")
        return _fallback_analysis(subject, body)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                settings.DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"邮件主题：{subject}\n\n邮件内容：\n{body[:2000]}"},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # 解析 JSON
            result = json.loads(content)
            return result

    except json.JSONDecodeError as e:
        logger.error(f"AI返回内容JSON解析失败: {e}")
        return _fallback_analysis(subject, body)
    except httpx.HTTPError as e:
        logger.error(f"DeepSeek API 调用失败: {e}")
        return _fallback_analysis(subject, body)
    except Exception as e:
        logger.error(f"AI分析异常: {e}")
        return _fallback_analysis(subject, body)


def _fallback_analysis(subject: str, body: str) -> Dict[str, Any]:
    """降级分析（当AI不可用时）"""
    # 简单的关键词匹配
    is_cosign = any(kw in subject + body for kw in ["会签", "审批", "签批", "签署"])
    is_confidential = any(kw in subject + body for kw in ["机密", "保密", "内部", "战略", "并购"])

    return {
        "title": subject[:100] if subject else "未命名工作项",
        "summary": body[:200] if body else subject[:200],
        "type": "cosign" if is_cosign else "task",
        "department": "运营部",
        "assignee_prefix": None,
        "due_date": None,
        "is_confidential": is_confidential,
    }
