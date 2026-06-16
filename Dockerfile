# 集团工作跟进系统 - 生产环境 Docker 镜像
FROM node:20-slim AS frontend-builder

RUN corepack enable && corepack prepare pnpm@9.0.0 --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile 2>/dev/null || pnpm install

COPY . .
RUN pnpm exec vite build
RUN pnpm tsup server/server.ts --format esm --out-dir dist-server --external vite

# --- Python backend ---
FROM python:3.11-slim AS backend

WORKDIR /app

COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/

# --- 最终运行镜像 ---
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl nginx supervisor \
    && rm -rf /var/lib/apt/lists/*

RUN corepack enable 2>/dev/null || true

# 安装 Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制后端
COPY --from=backend /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=backend /app/backend ./backend

# 复制前端构建产物
COPY --from=frontend-builder /app/dist ./dist
COPY --from=frontend-builder /app/dist-server ./dist-server
COPY --from=frontend-builder /app/node_modules ./node_modules
COPY --from=frontend-builder /app/package.json ./

# 配置
COPY deploy/nginx.conf /etc/nginx/sites-available/default
COPY deploy/supervisord.conf /etc/supervisor/conf.d/app.conf
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80

ENV NODE_ENV=production
ENV BACKEND_PORT=8000
ENV FRONTEND_PORT=5000

ENTRYPOINT ["/entrypoint.sh"]
