"""每日逾期工作通报邮件服务"""
import logging
import smtplib
import ssl
from datetime import datetime, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import WorkItem, Department, EmailConfig

logger = logging.getLogger(__name__)

# 测试阶段先发给 adam.wang，上线后再改为正式收件人
RECIPIENTS = ["adam.wang@ntg.com.hk"]
# RECIPIENTS = [
#     "adam.wang@ntg.com.hk",
#     # TODO: 添加 4 位部门总监 + 总裁邮箱
# ]

# 部门名称映射（确保显示"部"字）
DEPT_NAMES = {
    1: "人事商务部",
    2: "财审投资部",
    3: "行政产品部",
    4: "法务媒体部",
}

GWS_BASE_URL = "http://47.253.159.101"


def _get_dept_name(department_id: int, department_obj=None) -> str:
    """获取部门名称"""
    if department_obj and department_obj.name:
        # 去掉斜杠，如 "人事/商务部" → "人事商务部"
        return department_obj.name.replace("/", "")
    return DEPT_NAMES.get(department_id, f"部门{department_id}")


def _build_search_url(email_subject: str) -> str:
    """构造阿里邮箱搜索URL"""
    keyword = email_subject or ""
    base = "https://mail.sg.aliyun.com/alimail/entries/v5.1/search"
    return f"{base}?keyword={quote(keyword)}"


def _build_gws_login_url() -> str:
    """构造GWS系统登录页面URL"""
    return f"{GWS_BASE_URL}/login"


def _format_due_date(due_date) -> str:
    """格式化截止日期，只显示日期部分"""
    if due_date is None:
        return "-"
    if isinstance(due_date, datetime):
        return due_date.strftime("%Y-%m-%d")
    if isinstance(due_date, date):
        return due_date.strftime("%Y-%m-%d")
    if isinstance(due_date, str):
        # 处理 "2026-06-24 03:32:25.889034" 或 "2026-06-24" 格式
        try:
            dt = datetime.fromisoformat(str(due_date).split('.')[0])
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return str(due_date)[:10]
    return str(due_date)[:10]


def _calc_overdue_days(due_date) -> int:
    """计算逾期天数"""
    try:
        if due_date is None:
            return 0
        
        # 处理 datetime 对象
        if isinstance(due_date, datetime):
            due = due_date.date()
        elif isinstance(due_date, date):
            due = due_date
        elif isinstance(due_date, str):
            # 处理字符串格式
            due_str = str(due_date).split('.')[0].split(' ')[0]  # 取日期部分
            due = datetime.strptime(due_str, "%Y-%m-%d").date()
        else:
            return 0
        
        return (date.today() - due).days
    except (ValueError, TypeError) as e:
        logger.warning(f"计算逾期天数失败: {due_date}, error: {e}")
        return 0


async def _get_overdue_items(db: AsyncSession) -> list:
    """查询所有逾期工作项"""
    today_str = date.today().strftime("%Y-%m-%d")
    result = await db.execute(
        select(WorkItem)
        .options(selectinload(WorkItem.department))
        .where(
            WorkItem.due_date < today_str,
            WorkItem.status.notin_(["completed", "cancelled"]),
        )
        .order_by(WorkItem.department_id, WorkItem.due_date)
    )
    return result.scalars().all()


async def _get_all_departments(db: AsyncSession) -> list:
    """获取所有部门"""
    result = await db.execute(select(Department).order_by(Department.id))
    return result.scalars().all()


def _build_html_email(items: list, all_depts: list) -> str:
    """构造HTML邮件内容"""
    today = date.today().strftime("%Y年%m月%d日")
    
    # 按部门分组
    dept_items = {}
    for item in items:
        dept_id = item.department_id
        if dept_id not in dept_items:
            dept_items[dept_id] = []
        dept_items[dept_id].append(item)
    
    # 构造表格行
    rows_html = ""
    has_any_overdue = False
    
    for dept in all_depts:
        dept_name = _get_dept_name(dept.id, dept)
        dept_overdue = dept_items.get(dept.id, [])
        
        if dept_overdue:
            has_any_overdue = True
            for item in dept_overdue:
                overdue_days = _calc_overdue_days(item.due_date)
                search_url = _build_search_url(item.email_subject or item.title)
                gws_url = _build_gws_login_url()
                due_date_formatted = _format_due_date(item.due_date)
                
                # 工作内容换行处理
                content = item.content or "（无详细内容）"
                content_html = content.replace("\n", "<br>")
                
                rows_html += f"""
                <tr>
                    <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top;">
                        <a href="{search_url}" target="_blank" style="color: #1a73e8; text-decoration: none; font-weight: 500;">
                            {item.email_subject or item.title}
                        </a>
                    </td>
                    <td style="border: 1px solid #ddd; padding: 10px; text-align: center; white-space: nowrap;">{dept_name}</td>
                    <td style="border: 1px solid #ddd; padding: 10px; font-size: 13px; line-height: 1.6;">{content_html}</td>
                    <td style="border: 1px solid #ddd; padding: 10px; text-align: center; white-space: nowrap;">{due_date_formatted}</td>
                    <td style="border: 1px solid #ddd; padding: 10px; text-align: center; white-space: nowrap; color: #d32f2f; font-weight: bold;">{overdue_days}天</td>
                    <td style="border: 1px solid #ddd; padding: 10px; text-align: center;">
                        <a href="{gws_url}" target="_blank" style="display: inline-block; padding: 6px 16px; background: #1677ff; color: white; border-radius: 4px; text-decoration: none; font-size: 13px;">
                            登录工作跟进系统
                        </a>
                    </td>
                </tr>"""
        else:
            # 无逾期的部门
            rows_html += f"""
                <tr>
                    <td colspan="6" style="border: 1px solid #ddd; padding: 10px; color: #888; font-style: italic;">
                        {dept_name}根据邮件分析暂无逾期事项
                    </td>
                </tr>"""
    
    if has_any_overdue:
        header_text = f"截至{today}，以下工作已逾期，请关注推进："
    else:
        header_text = f"截至{today}，各部门暂无逾期事项。"
    
    overdue_count = len(items)
    subject = f"【逾期工作通报】截至{today}，共{overdue_count}项逾期"
    
    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Microsoft YaHei', 'PingFang SC', Arial, sans-serif; color: #333; line-height: 1.6; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            h2 {{ color: #d32f2f; margin-bottom: 10px; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 15px; }}
            th {{ background: #f5f5f5; border: 1px solid #ddd; padding: 10px; text-align: center; font-weight: 600; }}
            .footer {{ margin-top: 20px; color: #999; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>📋 逾期工作通报</h2>
            <p>{header_text}</p>
            <table>
                <thead>
                    <tr>
                        <th style="min-width: 200px;">邮件标题</th>
                        <th style="min-width: 80px;">所属部门</th>
                        <th style="min-width: 250px;">工作内容</th>
                        <th style="min-width: 80px;">截止日期</th>
                        <th style="min-width: 60px;">逾期天数</th>
                        <th style="min-width: 100px;">操作</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
            <div class="footer">
                <p>此邮件由集团工作跟进系统（GWS）自动发送，请勿直接回复。</p>
            </div>
        </div>
    </body>
    </html>
    """
    return subject, html


async def send_daily_overdue_notification():
    """发送每日逾期工作通报邮件"""
    logger.info("开始生成每日逾期通报邮件...")
    
    from database import async_session
    
    async with async_session() as db:
        # 查询逾期工作项
        items = await _get_overdue_items(db)
        logger.info(f"查询到 {len(items)} 项逾期工作")
        
        # 查询所有部门
        all_depts = await _get_all_departments(db)
        
        # 构造邮件内容
        subject, html = _build_html_email(items, all_depts)
        
        # 获取 SMTP 配置
        result = await db.execute(
            select(EmailConfig).where(EmailConfig.is_active == True)
        )
        email_config = result.scalar_one_or_none()
        
        if not email_config:
            logger.error("未找到活跃的邮件配置，无法发送通报邮件")
            return False
    
    # 发送邮件
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = email_config.email_address
        msg["To"] = ", ".join(RECIPIENTS)
        
        msg.attach(MIMEText(html, "html", "utf-8"))
        
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            email_config.smtp_host,
            email_config.smtp_port,
            context=context,
        ) as server:
            server.login(email_config.username, email_config.password)
            server.sendmail(
                email_config.email_address,
                RECIPIENTS,
                msg.as_string(),
            )
        
        logger.info(f"每日逾期通报邮件已发送，收件人: {RECIPIENTS}")
        return True
        
    except Exception as e:
        logger.error(f"发送每日逾期通报邮件失败: {e}", exc_info=True)
        return False
