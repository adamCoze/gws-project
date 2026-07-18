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
    "is_confidential": false,
    "cosign_status": [],
    "completion_assessment": "in_progress"
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

type（必填，三选一）
- "task"：普通工作任务（默认值）
- "cosign"：会签/审批类任务
- "report"：报告/周报/月报/汇总类（仅需知会备查，无需执行行动）
- 判断依据：
  - 邮件中包含"会签"、"审批"、"签批"、"签署"、"批复"、"征求意见"等关键词时，type 为 "cosign"
  - 邮件中包含"报告"、"周报"、"月报"、"汇总"、"报表"、"简报"、"情况说明"、"查收"、"报送"、"提交"（后接报告类名词）等关键词，且邮件性质为信息通报而非需要执行的任务时，type 为 "report"
  - 如果邮件内容仅展示信息、同步进展、通报情况，没有具体的请示内容、没有指派特定人员执行具体任务，则 type 为 "report"（不限于转发邮件，所有邮件均适用此规则）

department（必填，从以下4个部门中选择1个）
可选值：
- 人事/商务部
- 财审/投资部
- 行政/产品部
- 法务/媒体部
判断规则：
1. 涉及招聘、薪酬、薪资、工资、强积金、MPF、社保、公积金、五险一金、绩效考核、人事变动、员工福利、薪酬调整、薪资及社保公积金会签、商务合同、客户合作、商品/产品上架会签、例会纪要/纲要、内训总结、企业文化活动、员工健康安全 → 人事/商务部
2. 涉及财务审计、预算、资金、投资、融资、股权、财务报表、费用支付申请、银行开户、印花税缴纳 → 财审/投资部
3. 涉及行政管理、办公用品、产品规划、产品设计、日常运营、物业维修/养护、物业包销/销售运营、车辆维护、行政部日常开支（速递/宽带/电话/停车/物业费）、办公绿植养护、资产明细/周报 → 行政/产品部
4. 涉及法律事务、合规、合同审核、媒体公关、品牌宣传、诉讼/仲裁/法庭命令、董事辞任/任命、授权书/法律函件、公司治理文件 → 法务/媒体部
5. 重要：以邮件实际内容和业务性质为判断依据，不要被邮件路径中的部门名称误导（例如路径含"法务部"但内容是财务报表，应归财审/投资部）
6. 无法判断时，默认返回 "行政/产品部"

assignee_prefix（可选）
- 如果邮件中明确指定了责任人，提取其邮箱前缀
- 会签类邮件：提取当前待会签人的邮箱前缀（多个用逗号分隔）
- 如果无法确定，返回 null

责任人提取规则：
1. 优先从邮件正文中提取明确指定的责任人
2. 会签类邮件：提取所有需要会签的人（包括已会签和待会签）
3. 转发邮件：转发人不作为责任人，从转发体中找到实际执行人/会签人

due_date（可选）
- 如果邮件中有明确的截止日期，提取为 YYYY-MM-DD 格式
- 如果没有明确截止日期：
  - 会签类（type=cosign）：默认为当前日期 + 3个工作日
  - 普通任务（type=task）：默认为当前日期 + 7个工作日
- 返回格式：YYYY-MM-DD

is_confidential（必填，布尔值）
- true：邮件涉及敏感内容（机密、保密、并购、重组、高管人事变动、敏感财务数据）
- false：普通邮件

cosign_status（会签类必填，任务类返回空数组）
- 分析每个会签人的状态
- 格式：[{"name": "邮箱前缀", "status": "approved/pending/rejected", "remark": "简短备注"}]
- status 判断规则：
  - "approved"：回复中包含"同意"、"无异议"、"确认"、"赞成"等肯定表述
  - "rejected"：回复中包含"反对"、"不同意"、"驳回"等否定表述
  - "pending"：尚未回复或无法判断
- 例如：[{"name": "thomas.tao", "status": "approved", "remark": "无异议"}, {"name": "johnnie.wong", "status": "pending"}]

completion_assessment（必填）
- AI 对工作完成状态的判断
- 可选值："completed" | "in_progress" | "uncertain"
- 判断规则：
  - "completed"：邮件明确表示工作已完成（如"已完成"、"已支付"、"已发出"、"已收到"、"已获批"等）
  - "in_progress"：工作正在进行中，尚未完成
  - "uncertain"：无法明确判断（保持保守，让人工确认）
- 会签类特殊规则：如果所有会签人都是 approved，则判定为 "completed"

转发邮件处理规则：
- 必须解析转发体，提取完整原始邮件内容
- 转发人不是责任人，要从转发体中找到实际执行人"""

_COZE_CHAT_URL = "/v3/chat"


async def analyze_email_with_ai(subject: str, body: str, to_addrs: str = "", cc_addrs: str = "") -> Optional[Dict[str, Any]]:
    """使用 Coze Bot API 分析邮件内容。
    
    返回 None 表示 AI 分析失败（Token 过期、API 错误等），
    调用方应停止创建低质量工作项，改为记录日志并发送告警。
    """
    if not settings.COZE_API_TOKEN or not settings.COZE_BOT_ID:
        logger.error("Coze API Token 或 Bot ID 未配置，无法分析邮件")
        return None

    bot_content = ""
    try:
        email_content = f"邮件主题：{subject}\n"
        if to_addrs:
            email_content += f"收件人：{to_addrs}\n"
        if cc_addrs:
            email_content += f"抄送人：{cc_addrs}\n"
        email_content += f"\n邮件内容：\n{body[:5000]}"

        headers = {
            "Authorization": f"Bearer {settings.COZE_API_TOKEN}",
            "Content-Type": "application/json",
        }
        base_url = settings.COZE_API_BASE.rstrip("/")

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{base_url}{_COZE_CHAT_URL}",
                headers=headers,
                json={
                    "bot_id": settings.COZE_BOT_ID,
                    "user_id": "gws-system",
                    "additional_messages": [
                        {"role": "user", "content": email_content, "content_type": "text"}
                    ],
                    "stream": True,
                },
            )
            resp.raise_for_status()

            chat_status = ""
            current_event = ""
            delta_accumulator = ""

            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue

                if line.startswith("event:"):
                    current_event = line[6:]
                    continue

                if line.startswith("data:"):
                    data_str = line[5:]
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if "status" in data:
                        chat_status = data["status"]

                    if current_event == "conversation.message.delta" and "content" in data:
                        delta_accumulator += data["content"]

                    if current_event == "conversation.message.completed" and "content" in data:
                        content_val = data["content"]
                        if content_val.startswith("{") and not bot_content:
                            bot_content = content_val

            if not bot_content and delta_accumulator.startswith("{"):
                bot_content = delta_accumulator

            if not bot_content:
                logger.error("Coze Bot 返回空内容, chat_status=%s", chat_status)
                return None

            content = bot_content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
                content = content.strip()

            result = json.loads(content)
            logger.info("AI 分析成功: title=%s, department=%s, completion=%s",
                       result.get("title", "?"), result.get("department", "?"),
                       result.get("completion_assessment", "?"))
            return result

    except json.JSONDecodeError as e:
        logger.error("Coze Bot 返回内容 JSON 解析失败: %s, content=%s", e, bot_content[:200])
        return None
    except httpx.HTTPError as e:
        logger.error("Coze API 调用失败: %s", e)
        return None
    except Exception as e:
        logger.error("Coze AI 分析异常: %s", e, exc_info=True)
        return None


def _fallback_analysis(subject: str, body: str) -> Dict[str, Any]:
    """降级分析（已弃用 - 仅保留供手动调用场景使用）。
    
    注意：analyze_email_with_ai() 不再自动调用此函数。
    AI 分析失败时应返回 None，由调用方决定是否创建低质量工作项。
    """
    is_cosign = any(kw in subject + body for kw in ["会签", "审批", "签批", "签署"])
    report_keywords = ["报告", "周报", "月报", "汇总", "报表", "简报", "情况说明", "查收", "报送", "每日电邮", "例会纪要", "例会纲要", "信息汇总", "工作总结"]
    is_report = not is_cosign and any(kw in subject + body for kw in report_keywords)
    is_confidential = any(kw in subject + body for kw in ["机密", "保密", "内部", "战略", "并购"])

    if is_cosign:
        item_type = "cosign"
    elif is_report:
        item_type = "report"
    else:
        item_type = "task"

    return {
        "title": subject[:100] if subject else "未命名工作项",
        "summary": body[:200] if body else subject[:200],
        "type": item_type,
        "department": "行政/产品部",
        "assignee_prefix": None,
        "due_date": None,
        "is_confidential": is_confidential,
        "cosign_status": [],
        "completion_assessment": "completed" if is_report else "uncertain",
    }
