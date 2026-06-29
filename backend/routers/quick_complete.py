"""快捷完成工作项 - 无需登录的页面和API"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import WorkItem, Department, StatusChangeLog, User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["quick-complete"])

QUICK_COMPLETE_TOKEN = "gws-qc-2026-secret"


def _verify_token(token: str):
    """验证快捷完成token"""
    if token != QUICK_COMPLETE_TOKEN:
        raise HTTPException(status_code=403, detail="无效的访问令牌")


@router.get("/quick-complete/{item_id}", response_class=HTMLResponse)
async def quick_complete_page(
    item_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """快捷完成页面 - 显示工作项信息和确认按钮"""
    _verify_token(token)
    
    result = await db.execute(
        select(WorkItem)
        .options(selectinload(WorkItem.department))
        .where(WorkItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    
    if not item:
        return HTMLResponse(content="<h2>工作项不存在</h2>", status_code=404)
    
    if item.status == "completed":
        return HTMLResponse(content=f"""
        <html>
        <head><meta charset="utf-8"><title>已完成</title></head>
        <body style="font-family: 'Microsoft YaHei', Arial; text-align: center; padding: 50px;">
            <h1 style="color: #4caf50;">✅ 已完成</h1>
            <p style="font-size: 18px; color: #666;">该工作项已标记为已完成。</p>
            <p style="color: #999;">标题：{item.title}</p>
        </body>
        </html>
        """)
    
    dept_name = item.department.name.replace("/", "") if item.department else "未知部门"
    content = item.content or "（无详细内容）"
    content_html = content.replace("\n", "<br>")
    
    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>快捷完成 - {item.title}</title>
        <style>
            body {{ font-family: 'Microsoft YaHei', 'PingFang SC', Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
            .card {{ max-width: 600px; margin: 30px auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 30px; }}
            h2 {{ color: #333; margin-bottom: 20px; }}
            .info {{ margin: 15px 0; padding: 12px; background: #f9f9f9; border-radius: 4px; }}
            .info-label {{ color: #888; font-size: 13px; }}
            .info-value {{ color: #333; font-size: 15px; margin-top: 4px; }}
            .btn {{ display: inline-block; padding: 12px 40px; background: #4caf50; color: white; border: none; border-radius: 6px; font-size: 16px; cursor: pointer; margin-top: 20px; }}
            .btn:hover {{ background: #43a047; }}
            .btn:disabled {{ background: #ccc; cursor: not-allowed; }}
            .cancel-btn {{ display: inline-block; padding: 12px 30px; background: #fff; color: #666; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; cursor: pointer; margin-top: 20px; margin-left: 10px; text-decoration: none; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>📋 确认完成工作</h2>
            <div class="info">
                <div class="info-label">邮件标题</div>
                <div class="info-value">{item.email_subject or item.title}</div>
            </div>
            <div class="info">
                <div class="info-label">所属部门</div>
                <div class="info-value">{dept_name}</div>
            </div>
            <div class="info">
                <div class="info-label">工作内容</div>
                <div class="info-value" style="line-height: 1.8;">{content_html}</div>
            </div>
            <div class="info">
                <div class="info-label">截止日期</div>
                <div class="info-value">{item.due_date or '未设置'}</div>
            </div>
            <div class="info">
                <div class="info-label">当前状态</div>
                <div class="info-value" style="color: #d32f2f; font-weight: bold;">
                    {'已逾期' if item.status == 'overdue' else item.status}
                </div>
            </div>
            <div style="text-align: center; margin-top: 30px;">
                <button class="btn" id="completeBtn" onclick="markComplete()">✅ 确认设为已完成</button>
                <a href="http://47.253.159.101" class="cancel-btn">返回系统</a>
            </div>
            <div id="result" style="text-align: center; margin-top: 20px; display: none;"></div>
        </div>
        <script>
            async function markComplete() {{
                const btn = document.getElementById('completeBtn');
                const result = document.getElementById('result');
                btn.disabled = true;
                btn.textContent = '处理中...';
                result.style.display = 'none';
                
                try {{
                    const resp = await fetch('/api/quick-complete/{item_id}?token={token}', {{
                        method: 'POST',
                    }});
                    const data = await resp.json();
                    
                    if (resp.ok) {{
                        btn.style.display = 'none';
                        result.innerHTML = '<h2 style="color: #4caf50;">✅ 已完成</h2><p style="color: #666;">该工作项已成功标记为已完成。</p>';
                        result.style.display = 'block';
                    }} else {{
                        throw new Error(data.detail || '操作失败');
                    }}
                }} catch (e) {{
                    btn.disabled = false;
                    btn.textContent = '✅ 确认设为已完成';
                    result.innerHTML = '<p style="color: #d32f2f;">❌ ' + e.message + '</p>';
                    result.style.display = 'block';
                }}
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.post("/api/quick-complete/{item_id}")
async def quick_complete_api(
    item_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """快捷完成API - 将工作项状态设为completed"""
    _verify_token(token)
    
    result = await db.execute(
        select(WorkItem)
        .options(selectinload(WorkItem.department))
        .where(WorkItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="工作项不存在")
    
    if item.status == "completed":
        return {"message": "该工作项已完成", "status": "completed"}
    
    old_status = item.status
    item.status = "completed"
    item.updated_at = datetime.utcnow()
    
    # 记录状态变更日志
    log = StatusChangeLog(
        work_item_id=item.id,
        old_status=old_status,
        new_status="completed",
        operator_id=None,  # 系统操作，无操作人
        remark="通过每日通报邮件快捷完成",
    )
    db.add(log)
    
    await db.commit()
    
    logger.info(f"工作项 #{item_id} 已通过邮件快捷完成 (原状态: {old_status})")
    return {"message": "已完成", "status": "completed", "item_id": item_id}
