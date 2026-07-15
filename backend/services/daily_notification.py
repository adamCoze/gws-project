"""每日逾期工作通报邮件服务"""
import logging
import smtplib
import ssl
from collections import defaultdict
from datetime import datetime, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from urllib.parse import quote

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import WorkItem, Department, EmailConfig, StatusChangeLog

logger = logging.getLogger(__name__)

# 收件人 & 抄送人
TO_RECIPIENTS = ["leo.law@ntg.com.hk"]
CC_RECIPIENTS = [
    "xiangxin@ntg.com.hk",
    "vincent.xiang@ntg.com.hk",
    "thomas.tao@ntg.com.hk",
    "joanna.chen@ntg.com.hk",
    "leo.law@ntg.com.hk",
    "johnnie.wong@ntg.com.hk",
]
ALL_RECIPIENTS = list(set(TO_RECIPIENTS + CC_RECIPIENTS))

# 部门名称映射
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
        return department_obj.name.replace("/", "")
    return DEPT_NAMES.get(department_id, f"部门{department_id}")


def _build_search_url(email_subject: str) -> str:
    """构造阿里邮箱搜索URL"""
    keyword = email_subject or ""
    base = "https://mail.sg.aliyun.com/alimail/entries/v5.1/search"
    return f"{base}?keyword={quote(keyword)}"


def _build_edit_url(item_id: int) -> str:
    """构造工作项编辑页面URL"""
    return f"{GWS_BASE_URL}/admin/work-items?edit={item_id}"


def _format_due_date(due_date) -> str:
    """格式化截止日期"""
    if due_date is None:
        return "-"
    if isinstance(due_date, datetime):
        return due_date.strftime("%Y-%m-%d")
    if isinstance(due_date, date):
        return due_date.strftime("%Y-%m-%d")
    if isinstance(due_date, str):
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
        if isinstance(due_date, datetime):
            due = due_date.date()
        elif isinstance(due_date, date):
            due = due_date
        elif isinstance(due_date, str):
            due_str = str(due_date).split('.')[0].split(' ')[0]
            due = datetime.strptime(due_str, "%Y-%m-%d").date()
        else:
            return 0
        return (date.today() - due).days
    except (ValueError, TypeError) as e:
        logger.warning(f"计算逾期天数失败: {due_date}, error: {e}")
        return 0


def _get_month_key(dt) -> str:
    """获取月份键值 (YYYY-MM)"""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m")
    if isinstance(dt, date):
        return dt.strftime("%Y-%m")
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(str(dt).split('.')[0]).strftime("%Y-%m")
        except:
            return str(dt)[:7]
    return ""


def _month_display(month_key: str) -> str:
    """月份键值转中文显示，如 '2026-07' → '7月'"""
    try:
        parts = month_key.split("-")
        return f"{int(parts[1])}月"
    except:
        return month_key


async def _get_overdue_items_grouped(db: AsyncSession) -> dict:
    """
    查询所有逾期工作项，按部门+月份分组。
    返回: {dept_id: {month_key: [items]}}
    """
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
    items = result.scalars().all()

    grouped = defaultdict(lambda: defaultdict(list))
    for item in items:
        dept_id = item.department_id
        month_key = _get_month_key(item.due_date)
        grouped[dept_id][month_key].append(item)

    return grouped


async def _get_completed_items_grouped(db: AsyncSession) -> dict:
    """
    查询在指定月份内变为已完成的工作项，按部门+月份分组。
    月份 = 状态变更为 completed 的时间所在月份。
    返回: {dept_id: {month_key: [items]}}
    """
    # 查询 status_change_logs 中变为 completed 的记录
    result = await db.execute(
        select(StatusChangeLog, WorkItem)
        .join(WorkItem, StatusChangeLog.work_item_id == WorkItem.id)
        .options(selectinload(StatusChangeLog.work_item))
        .where(
            StatusChangeLog.new_status == "completed",
        )
        .order_by(StatusChangeLog.created_at.desc())
    )
    rows = result.all()

    grouped = defaultdict(lambda: defaultdict(list))
    for log, item in rows:
        dept_id = item.department_id
        month_key = _get_month_key(log.created_at)
        grouped[dept_id][month_key].append(item)

    return grouped


async def _get_all_departments(db: AsyncSession) -> list:
    """获取所有部门"""
    result = await db.execute(select(Department).order_by(Department.id))
    return result.scalars().all()


def _render_item_row(item, show_overdue: bool = True) -> str:
    """渲染单个工作项的HTML行"""
    search_url = _build_search_url(item.email_subject or item.title)
    gws_url = _build_edit_url(item.id)
    due_date_str = _format_due_date(item.due_date)

    content = item.content or "（无详细内容）"
    content_html = content.replace("\n", "<br>")

    if show_overdue:
        overdue_days = _calc_overdue_days(item.due_date)
        return f"""
        <tr>
            <td style="border: 1px solid #ddd; padding: 8px; vertical-align: top;">
                <a href="{search_url}" target="_blank" style="color: #1a73e8; text-decoration: none; font-weight: 500;">
                    {item.email_subject or item.title}
                </a>
            </td>
            <td style="border: 1px solid #ddd; padding: 8px; font-size: 13px; line-height: 1.6;">{content_html}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center; white-space: nowrap;">{due_date_str}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center; white-space: nowrap; color: #d32f2f; font-weight: bold;">{overdue_days}天</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">
                <a href="{gws_url}" target="_blank" style="display: inline-block; padding: 5px 12px; background: #1677ff; color: white; border-radius: 4px; text-decoration: none; font-size: 12px;">
                    编辑此工作项
                </a>
            </td>
        </tr>"""
    else:
        # 已完成项
        return f"""
        <tr style="background: #f9f9f9;">
            <td style="border: 1px solid #ddd; padding: 8px; vertical-align: top;">
                <a href="{search_url}" target="_blank" style="color: #52c41a; text-decoration: none;">
                    {item.email_subject or item.title}
                </a>
            </td>
            <td style="border: 1px solid #ddd; padding: 8px; font-size: 13px; line-height: 1.6;">{content_html}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center; white-space: nowrap; color: #52c41a;">✓ 已完成</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">
                <a href="{gws_url}" target="_blank" style="display: inline-block; padding: 5px 12px; background: #52c41a; color: white; border-radius: 4px; text-decoration: none; font-size: 12px;">
                    查看
                </a>
            </td>
        </tr>"""


def _build_html_email(overdue_grouped: dict, completed_grouped: dict, all_depts: list) -> tuple:
    """构造HTML邮件内容"""
    today = date.today().strftime("%Y年%m月%d日")

    dept_sections = ""
    total_overdue = 0

    for dept in all_depts:
        dept_id = dept.id
        dept_name = _get_dept_name(dept.id, dept)
        dept_overdue = overdue_grouped.get(dept_id, {})
        dept_completed = completed_grouped.get(dept_id, {})

        # 获取该部门有逾期数据的月份列表（降序）
        overdue_months = sorted(dept_overdue.keys(), reverse=True)

        if not overdue_months:
            continue  # 该部门没有逾期数据，跳过

        month_sections = ""
        for month_key in overdue_months:
            overdue_items = dept_overdue[month_key]
            completed_items = dept_completed.get(month_key, [])
            month_label = _month_display(month_key)

            overdue_count = len(overdue_items)
            completed_count = len(completed_items)
            total_overdue += overdue_count

            # 月份头部
            month_sections += f"""
            <div style="margin: 15px 0 5px 0;">
                <h3 style="color: #333; font-size: 15px; margin: 0; padding: 8px 12px; background: #fafafa; border-left: 4px solid #d32f2f; border-radius: 2px;">
                    ----{month_label} 逾期工作：{overdue_count}项，已完成：{completed_count}项
                </h3>
            </div>
            <table style="border-collapse: collapse; width: 100%; margin-bottom: 10px;">
                <thead>
                    <tr>
                        <th style="border: 1px solid #ddd; padding: 8px; background: #fff5f5; text-align: left; font-size: 13px; min-width: 200px;">邮件标题</th>
                        <th style="border: 1px solid #ddd; padding: 8px; background: #fff5f5; text-align: left; font-size: 13px; min-width: 200px;">工作内容</th>
                        <th style="border: 1px solid #ddd; padding: 8px; background: #fff5f5; text-align: center; font-size: 13px; min-width: 80px;">截止日期</th>
                        <th style="border: 1px solid #ddd; padding: 8px; background: #fff5f5; text-align: center; font-size: 13px; min-width: 60px;">逾期天数</th>
                        <th style="border: 1px solid #ddd; padding: 8px; background: #fff5f5; text-align: center; font-size: 13px; min-width: 90px;">操作</th>
                    </tr>
                </thead>
                <tbody>"""

            # 逾期工作项
            for item in overdue_items:
                month_sections += _render_item_row(item, show_overdue=True)

            # 已完成工作项（同月）
            if completed_items:
                month_sections += f"""
                    <tr>
                        <td colspan="5" style="border: 1px solid #ddd; padding: 6px 8px; background: #f0f9eb; font-size: 13px; color: #52c41a; font-weight: 500;">
                            ✓ 当月已完成（{completed_count}项）
                        </td>
                    </tr>"""
                # 已完成表头
                month_sections += """
                    <tr>
                        <th style="border: 1px solid #ddd; padding: 6px; background: #f6ffed; text-align: left; font-size: 12px; color: #52c41a;">邮件标题</th>
                        <th style="border: 1px solid #ddd; padding: 6px; background: #f6ffed; text-align: left; font-size: 12px; color: #52c41a;">工作内容</th>
                        <th style="border: 1px solid #ddd; padding: 6px; background: #f6ffed; text-align: center; font-size: 12px; color: #52c41a;" colspan="2">状态</th>
                        <th style="border: 1px solid #ddd; padding: 6px; background: #f6ffed; text-align: center; font-size: 12px; color: #52c41a;">操作</th>
                    </tr>"""
                for item in completed_items:
                    month_sections += _render_item_row(item, show_overdue=False)

            month_sections += "</tbody></table>"

        # 部门区块
        dept_sections += f"""
        <div style="margin-bottom: 25px; padding: 12px; border: 1px solid #e8e8e8; border-radius: 6px; background: #fff;">
            <h2 style="font-size: 16px; color: #333; margin: 0 0 5px 0; padding-bottom: 8px; border-bottom: 2px solid #1677ff;">
                {dept_name}
            </h2>
            {month_sections}
        </div>"""

    # 邮件头部
    if total_overdue > 0:
        header_text = f"截至{today}，以下工作已逾期，请关注推进："
    else:
        header_text = f"截至{today}，暂无逾期事项。"

    subject = f"【工作跟进通报】截至{today}，共{total_overdue}项逾期"

    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Microsoft YaHei', 'PingFang SC', Arial, sans-serif; color: #333; line-height: 1.6; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .footer {{ margin-top: 20px; color: #999; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2 style="color: #d32f2f; margin-bottom: 10px;">📋 工作跟进通报</h2>
            <p>{header_text}</p>
            {dept_sections if dept_sections else '<p style="color: #888; font-style: italic;">各部门暂无逾期事项。</p>'}
            <div class="footer">
                <p>此邮件由集团工作跟进系统（GWS）自动发送，请勿直接回复。</p>
            </div>
        </div>
    </body>
    </html>
    """
    return subject, html


async def send_daily_overdue_notification():
    """发送每日工作跟进通报邮件"""
    logger.info("开始生成每日工作跟进通报邮件...")

    from database import async_session

    async with async_session() as db:
        # 查询逾期工作项（按部门+月份分组）
        overdue_grouped = await _get_overdue_items_grouped(db)
        total_overdue = sum(
            len(items)
            for dept_data in overdue_grouped.values()
            for items in dept_data.values()
        )
        logger.info(f"查询到 {total_overdue} 项逾期工作")

        # 查询已完成工作项（按部门+月份分组）
        completed_grouped = await _get_completed_items_grouped(db)

        # 查询所有部门
        all_depts = await _get_all_departments(db)

        # 构造邮件内容
        subject, html = _build_html_email(overdue_grouped, completed_grouped, all_depts)

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
        msg["To"] = ", ".join(TO_RECIPIENTS)
        msg["Cc"] = ", ".join(CC_RECIPIENTS)
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()

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
                ALL_RECIPIENTS,
                msg.as_string(),
            )

        logger.info(f"每日工作跟进通报邮件已发送，收件人: {TO_RECIPIENTS}，抄送: {CC_RECIPIENTS}")
        return True

    except Exception as e:
        logger.error(f"发送每日工作跟进通报邮件失败: {e}", exc_info=True)
        return False
