"""每日工作通报邮件服务"""
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
TO_RECIPIENTS = ["adam.wang@ntg.com.hk"]
CC_RECIPIENTS = [
    "xiangxin@ntg.com.hk",
    "vincent.xiang@ntg.com.hk",
    "thomas.tao@ntg.com.hk",
    "joanna.chen@ntg.com.hk",
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


async def _get_pending_items_grouped(db: AsyncSession) -> dict:
    """
    查询所有待跟进工作项（status=pending），按部门+截止月份分组。
    返回: {dept_id: {month_key: [items]}}
    """
    result = await db.execute(
        select(WorkItem)
        .options(selectinload(WorkItem.department))
        .where(WorkItem.status == "pending")
        .order_by(WorkItem.department_id, WorkItem.due_date)
    )
    items = result.scalars().all()

    grouped = defaultdict(lambda: defaultdict(list))
    for item in items:
        dept_id = item.department_id
        month_key = _get_month_key(item.due_date) if item.due_date else "无截止日期"
        grouped[dept_id][month_key].append(item)

    return grouped


async def _get_overdue_items_grouped(db: AsyncSession) -> dict:
    """
    查询所有已逾时工作项（status=pending 且 due_date < today，动态计算），按部门+截止月份分组。
    返回: {dept_id: {month_key: [items]}}
    """
    today_str = date.today().strftime("%Y-%m-%d")
    result = await db.execute(
        select(WorkItem)
        .options(selectinload(WorkItem.department))
        .where(
            WorkItem.status == "pending",
            WorkItem.due_date < today_str,
        )
        .order_by(WorkItem.department_id, WorkItem.due_date)
    )
    items = result.scalars().all()

    grouped = defaultdict(lambda: defaultdict(list))
    for item in items:
        dept_id = item.department_id
        month_key = _get_month_key(item.due_date) if item.due_date else "无截止日期"
        grouped[dept_id][month_key].append(item)

    return grouped


async def _get_completed_count_grouped(db: AsyncSession) -> dict:
    """
    查询已完成工作项数量，按部门+月份分组（基于状态变更时间）。
    返回: {dept_id: {month_key: count}}
    """
    result = await db.execute(
        select(StatusChangeLog, WorkItem)
        .join(WorkItem, StatusChangeLog.work_item_id == WorkItem.id)
        .where(StatusChangeLog.new_status == "completed")
        .order_by(StatusChangeLog.created_at.desc())
    )
    rows = result.all()

    grouped = defaultdict(lambda: defaultdict(int))
    for log, item in rows:
        dept_id = item.department_id
        month_key = _get_month_key(log.created_at)
        grouped[dept_id][month_key] += 1

    return grouped


async def _get_all_departments(db: AsyncSession) -> list:
    """获取所有部门"""
    result = await db.execute(select(Department).order_by(Department.id))
    return result.scalars().all()


def _render_pending_row(item) -> str:
    """渲染待跟进工作项的HTML行"""
    search_url = _build_search_url(item.email_subject or item.title)
    gws_url = _build_edit_url(item.id)
    due_date_str = _format_due_date(item.due_date)

    content = item.content or "（无详细内容）"
    content_html = content.replace("\n", "<br>")

    return f"""
        <tr>
            <td style="border: 1px solid #ddd; padding: 8px; vertical-align: top;">
                <a href="{search_url}" target="_blank" style="color: #1a73e8; text-decoration: none; font-weight: 500;">
                    {item.email_subject or item.title}
                </a>
            </td>
            <td style="border: 1px solid #ddd; padding: 8px; font-size: 13px; line-height: 1.6;">{content_html}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center; white-space: nowrap;">{due_date_str}</td>
            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">
                <a href="{gws_url}" target="_blank" style="display: inline-block; padding: 5px 12px; background: #1677ff; color: white; border-radius: 4px; text-decoration: none; font-size: 12px;">
                    编辑此工作项
                </a>
            </td>
        </tr>"""


def _render_overdue_row(item) -> str:
    """渲染已逾时工作项的HTML行"""
    search_url = _build_search_url(item.email_subject or item.title)
    gws_url = _build_edit_url(item.id)
    due_date_str = _format_due_date(item.due_date)
    overdue_days = _calc_overdue_days(item.due_date)

    content = item.content or "（无详细内容）"
    content_html = content.replace("\n", "<br>")

    return f"""
        <tr>
            <td style="border: 1px solid #ddd; padding: 8px; vertical-align: top;">
                <a href="{search_url}" target="_blank" style="color: #d32f2f; text-decoration: none; font-weight: 500;">
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


def _render_item_table(items: list, table_type: str) -> str:
    """渲染工作项表格（pending 或 overdue）"""
    if not items:
        return ""

    if table_type == "pending":
        header_bg = "#e8f4fd"
        border_color = "#1677ff"
        rows = "\n".join(_render_pending_row(item) for item in items)
        return f"""
            <table style="border-collapse: collapse; width: 100%; margin-bottom: 10px;">
                <thead>
                    <tr>
                        <th style="border: 1px solid #ddd; padding: 8px; background: {header_bg}; text-align: left; font-size: 13px; min-width: 200px;">邮件标题</th>
                        <th style="border: 1px solid #ddd; padding: 8px; background: {header_bg}; text-align: left; font-size: 13px; min-width: 200px;">工作内容</th>
                        <th style="border: 1px solid #ddd; padding: 8px; background: {header_bg}; text-align: center; font-size: 13px; min-width: 80px;">截止日期</th>
                        <th style="border: 1px solid #ddd; padding: 8px; background: {header_bg}; text-align: center; font-size: 13px; min-width: 90px;">操作</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>"""
    else:  # overdue
        header_bg = "#fff5f5"
        border_color = "#d32f2f"
        rows = "\n".join(_render_overdue_row(item) for item in items)
        return f"""
            <table style="border-collapse: collapse; width: 100%; margin-bottom: 10px;">
                <thead>
                    <tr>
                        <th style="border: 1px solid #ddd; padding: 8px; background: {header_bg}; text-align: left; font-size: 13px; min-width: 200px;">邮件标题</th>
                        <th style="border: 1px solid #ddd; padding: 8px; background: {header_bg}; text-align: left; font-size: 13px; min-width: 200px;">工作内容</th>
                        <th style="border: 1px solid #ddd; padding: 8px; background: {header_bg}; text-align: center; font-size: 13px; min-width: 80px;">截止日期</th>
                        <th style="border: 1px solid #ddd; padding: 8px; background: {header_bg}; text-align: center; font-size: 13px; min-width: 60px;">逾期天数</th>
                        <th style="border: 1px solid #ddd; padding: 8px; background: {header_bg}; text-align: center; font-size: 13px; min-width: 90px;">操作</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>"""


def _build_html_email(pending_grouped: dict, overdue_grouped: dict, completed_counted: dict, all_depts: list) -> tuple:
    """构造HTML邮件内容"""
    today = date.today().strftime("%Y年%m月%d日")

    dept_sections = ""
    total_pending = 0
    total_overdue = 0
    total_completed = 0

    for dept in all_depts:
        dept_id = dept.id
        dept_name = _get_dept_name(dept.id, dept)
        dept_pending = pending_grouped.get(dept_id, {})
        dept_overdue = overdue_grouped.get(dept_id, {})
        dept_completed = completed_counted.get(dept_id, {})

        # 收集该部门所有有数据的月份（降序）
        all_months = set()
        all_months.update(dept_pending.keys())
        all_months.update(dept_overdue.keys())
        all_months.update(dept_completed.keys())

        # 分离"无截止日期"和正常月份
        has_no_due = "无截止日期" in all_months
        normal_months = sorted([m for m in all_months if m != "无截止日期"], reverse=True)
        ordered_months = normal_months + (["无截止日期"] if has_no_due else [])

        if not ordered_months:
            continue

        # 统计该部门总数（待跟进不含已逾时，避免重复计数）
        dept_overdue_count = sum(len(items) for items in dept_overdue.values())
        dept_overdue_ids = {item.id for dept_months in dept_overdue.values() for item in dept_months}
        dept_pending_count = sum(
            1 for items in dept_pending.values() for item in items if item.id not in dept_overdue_ids
        )
        dept_completed_count = sum(dept_completed.values())

        total_pending += dept_pending_count
        total_overdue += dept_overdue_count
        total_completed += dept_completed_count

        month_sections = ""
        for month_key in ordered_months:
            pending_items = dept_pending.get(month_key, [])
            overdue_items = dept_overdue.get(month_key, [])
            completed_count = dept_completed.get(month_key, 0)

            if not pending_items and not overdue_items and not completed_count:
                continue

            month_label = _month_display(month_key) if month_key != "无截止日期" else "无截止日期"
            # 待跟进 = pending 中排除已逾时的（避免重复计数）
            overdue_ids = {item.id for item in overdue_items}
            non_overdue_pending = [item for item in pending_items if item.id not in overdue_ids]
            pending_count = len(non_overdue_pending)
            overdue_count = len(overdue_items)

            # 月份标题
            month_sections += f"""
            <div style="margin: 15px 0 5px 0;">
                <h3 style="color: #333; font-size: 15px; margin: 0; padding: 8px 12px; background: #fafafa; border-left: 4px solid #1677ff; border-radius: 2px;">
                    ---- {month_label}：待跟进 {pending_count}项，已逾时 {overdue_count}项，已完成 {completed_count}项
                </h3>
            </div>"""

            # 待跟进表格（仅非逾期项）
            if non_overdue_pending:
                month_sections += _render_item_table(non_overdue_pending, "pending")

            # 已逾时表格
            if overdue_items:
                month_sections += _render_item_table(overdue_items, "overdue")

            # 已完成仅显示数量（如果有已完成但没有待跟进和逾时，也显示一行提示）
            if completed_count > 0 and not non_overdue_pending and not overdue_items:
                month_sections += f"""
                <p style="color: #52c41a; font-size: 13px; padding: 8px 12px; background: #f0f9eb; border-radius: 4px; margin: 5px 0;">
                    ✓ 当月已完成 {completed_count} 项
                </p>"""

        # 部门区块
        dept_sections += f"""
        <div style="margin-bottom: 25px; padding: 12px; border: 1px solid #e8e8e8; border-radius: 6px; background: #fff;">
            <h2 style="font-size: 16px; color: #333; margin: 0 0 5px 0; padding-bottom: 8px; border-bottom: 2px solid #1677ff;">
                {dept_name}
                <span style="font-size: 13px; color: #888; font-weight: normal; margin-left: 10px;">
                    待跟进 {dept_pending_count} · 已逾时 {dept_overdue_count} · 已完成 {dept_completed_count}
                </span>
            </h2>
            {month_sections}
        </div>"""

    # 邮件头部
    header_text = f"截至{today}，各部门工作跟进情况如下："
    subject = f"【工作跟进通报】待跟进{total_pending}项，已逾时{total_overdue}项，已完成{total_completed}项"

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
            <h2 style="color: #1a73e8; margin-bottom: 10px;">📋 工作跟进通报</h2>
            <p>{header_text}</p>
            <div style="background: #f0f7ff; border: 1px solid #d0e3f5; border-radius: 6px; padding: 12px 16px; margin-bottom: 20px;">
                <span style="font-size: 15px; font-weight: bold;">
                    📌 待跟进：<span style="color: #1677ff;">{total_pending}项</span>
                    &nbsp;&nbsp;|&nbsp;&nbsp;
                    🔴 已逾时：<span style="color: #d32f2f;">{total_overdue}项</span>
                    &nbsp;&nbsp;|&nbsp;&nbsp;
                    ✅ 已完成：<span style="color: #52c41a;">{total_completed}项</span>
                </span>
            </div>
            {dept_sections if dept_sections else '<p style="color: #888; font-style: italic;">各部门暂无工作数据。</p>'}
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
        # 查询待跟进工作项（按部门+月份分组）
        pending_grouped = await _get_pending_items_grouped(db)
        total_pending = sum(
            len(items)
            for dept_data in pending_grouped.values()
            for items in dept_data.values()
        )
        logger.info(f"查询到 {total_pending} 项待跟进工作")

        # 查询已逾时工作项（按部门+月份分组）
        overdue_grouped = await _get_overdue_items_grouped(db)
        total_overdue = sum(
            len(items)
            for dept_data in overdue_grouped.values()
            for items in dept_data.values()
        )
        logger.info(f"查询到 {total_overdue} 项已逾时工作")

        # 查询已完成数量（按部门+月份分组）
        completed_counted = await _get_completed_count_grouped(db)
        total_completed = sum(
            count
            for dept_data in completed_counted.values()
            for count in dept_data.values()
        )
        logger.info(f"查询到 {total_completed} 项已完成工作")

        # 查询所有部门
        all_depts = await _get_all_departments(db)

        # 构造邮件内容
        subject, html = _build_html_email(pending_grouped, overdue_grouped, completed_counted, all_depts)

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
