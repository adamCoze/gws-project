# 集团工作跟进系统 - 阿里云部署指南

## 服务器配置
- **规格**: 2 vCPU, 2 GiB RAM, 40 GiB ESSD
- **地域**: 美国（弗吉尼亚）
- **系统**: Ubuntu 22.04

## 快速部署（Docker）

### 1. 服务器初始化

```bash
# SSH 登录服务器
ssh root@<服务器IP>

# 更新系统
apt update && apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker && systemctl start docker

# 安装 Docker Compose
apt install docker-compose-plugin -y
```

### 2. 上传项目代码

```bash
# 方式一：通过 scp 上传
# 在本地执行：
scp -r gws-project/ root@<服务器IP>:/opt/gws-project

# 方式二：通过 git clone（如果已推送到仓库）
cd /opt
git clone <仓库地址> gws-project
```

### 3. 配置环境变量

```bash
cd /opt/gws-project

# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填写实际配置
nano .env
```

**必须配置的项目：**
- `SECRET_KEY`：JWT 密钥，建议用 `openssl rand -base64 32` 生成
- `COZE_API_TOKEN`：Coze Personal Access Token（用于 AI 邮件分析）
- `COZE_BOT_ID`：Coze Bot ID（邮件分析助手）

### 4. 构建并启动

```bash
cd /opt/gws-project

# 构建镜像
docker compose build

# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f
```

### 5. 验证部署

```bash
# 检查服务状态
docker compose ps

# 测试 API 健康检查
curl http://localhost/api/health

# 测试前端页面
curl -I http://localhost
```

访问 `http://<服务器IP>` 即可打开系统。

**默认管理员账号：** `admin` / `admin123`

> ⚠️ 首次登录后请立即修改密码！

## 手动部署（不用 Docker）

### 1. 安装依赖

```bash
# Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# pnpm
corepack enable && corepack prepare pnpm@9.0.0 --activate

# Python 3.11
apt install -y python3 python3-pip python3-venv

# Nginx
apt install -y nginx
```

### 2. 构建项目

```bash
cd /opt/gws-project

# 安装前端依赖并构建
pnpm install
pnpm exec vite build
pnpm tsup server/server.ts --format esm --out-dir dist-server --external vite

# 安装后端依赖
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cd /opt/gws-project/backend
cp ../.env.example .env
nano .env  # 填写实际配置
```

### 4. 配置 Nginx

```bash
# 复制 nginx 配置
cp /opt/gws-project/deploy/nginx.conf /etc/nginx/sites-available/gws
ln -sf /etc/nginx/sites-available/gws /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 测试并重载 nginx
nginx -t && systemctl reload nginx
```

### 5. 使用 systemd 管理服务

创建后端服务：
```bash
cat > /etc/systemd/system/gws-backend.service << 'EOF'
[Unit]
Description=GWS FastAPI Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/gws-project/backend
ExecStart=/opt/gws-project/backend/venv/bin/python3 -c "import uvicorn; uvicorn.run('main:app', host='127.0.0.1', port=8000)"
Restart=always
RestartSec=5
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOF
```

创建前端服务：
```bash
cat > /etc/systemd/system/gws-frontend.service << 'EOF'
[Unit]
Description=GWS Frontend Server
After=network.target gws-backend.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/gws-project
ExecStart=/usr/bin/node dist-server/server.js
Restart=always
RestartSec=5
Environment=NODE_ENV=production
Environment=PORT=5000
Environment=BACKEND_PORT=8000

[Install]
WantedBy=multi-user.target
EOF
```

启动服务：
```bash
systemctl daemon-reload
systemctl enable gws-backend gws-frontend
systemctl start gws-backend gws-frontend

# 检查状态
systemctl status gws-backend
systemctl status gws-frontend
```

## 常用运维命令

```bash
# Docker 方式
docker compose logs -f              # 查看日志
docker compose restart              # 重启服务
docker compose down                 # 停止服务
docker compose build --no-cache     # 重新构建

# systemd 方式
journalctl -u gws-backend -f        # 查看后端日志
journalctl -u gws-frontend -f       # 查看前端日志
systemctl restart gws-backend       # 重启后端
systemctl restart gws-frontend      # 重启前端
```

## 数据备份

数据库文件位于 `/opt/gws-project/backend/data/gws.db`（手动部署）或 Docker volume `gws-data`（Docker 部署）。

```bash
# 备份数据库
cp backend/data/gws.db backend/data/gws.db.bak.$(date +%Y%m%d)

# Docker 方式备份
docker compose exec app cp /app/backend/data/gws.db /app/backend/data/gws.db.bak
docker compose cp app:/app/backend/data/gws.db.bak ./backup/
```

## 更新部署

```bash
cd /opt/gws-project

# 拉取最新代码
git pull

# Docker 方式更新
docker compose build
docker compose up -d

# systemd 方式更新
pnpm install && pnpm exec vite build && pnpm tsup server/server.ts --format esm --out-dir dist-server --external vite
systemctl restart gws-frontend
```

## 故障排查

| 问题 | 排查方法 |
|------|---------|
| 无法访问 | 检查安全组是否开放 80 端口 |
| 502 错误 | 检查后端是否启动：`curl localhost:8000/api/health` |
| 登录失败 | 检查 `.env` 中 SECRET_KEY 配置 |
| 邮件功能异常 | 检查邮箱配置的 IMAP/SMTP 设置 |
| AI 分析失败 | 检查 COZE_API_TOKEN 和 COZE_BOT_ID 是否有效 |
