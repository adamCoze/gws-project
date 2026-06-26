#!/bin/bash
set -e

# 生成 .env 文件（如果不存在）
if [ ! -f /app/backend/.env ]; then
    cat > /app/backend/.env << EOF
DATABASE_URL=sqlite+aiosqlite:///./data/gws.db
SECRET_KEY=${SECRET_KEY:-$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")}
COZE_API_TOKEN=${COZE_API_TOKEN:-}
COZE_BOT_ID=${COZE_BOT_ID:-}
COZE_API_BASE=${COZE_API_BASE:-https://api.coze.cn}
ALIMAIL_APP_ID=${ALIMAIL_APP_ID:-}
ALIMAIL_APP_SECRET=${ALIMAIL_APP_SECRET:-}
ALIMAIL_API_BASE=${ALIMAIL_API_BASE:-https://alimail-sg.aliyuncs.com}
ALIMAIL_WEBMAIL_BASE=${ALIMAIL_WEBMAIL_BASE:-https://mail.sg.aliyun.com/alimail/entries/v5.1/mail/inbox/all/}
EOF
    echo "已生成 /app/backend/.env"
fi

# 确保数据目录存在
mkdir -p /app/backend/data

exec supervisord -c /etc/supervisor/conf.d/app.conf
