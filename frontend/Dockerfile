# ============================================
# AI 自动测试平台 - 前端 Dockerfile
# 多阶段构建：Node.js 构建 → Nginx 运行
#
# 构建时传入后端地址（前后端分离部署）：
#   docker build \
#     --build-arg VITE_API_BASE_URL=https://api.example.com \
#     -t auto-test-frontend:latest \
#     -f frontend/Dockerfile .
#
# 使用 Nginx 反向代理（同源部署）：
#   docker build -t auto-test-frontend:latest -f frontend/Dockerfile .
# ============================================
# ---- 阶段一：构建 ----
FROM docker.1ms.run/library/node:20-alpine AS builder

WORKDIR /app

# 参数：后端 API 地址，默认空字符串（同源访问）
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# 安装依赖（利用 Docker 缓存）
COPY frontend/package.json frontend/package-lock.json* ./


RUN npm config set registry https://registry.npmmirror.com && npm install

# 复制源码并构建
COPY frontend/ .
RUN npm run build

# ---- 阶段二：运行 ----
FROM docker.1ms.run/library/nginx:stable-alpine AS runtime

# 从构建阶段复制产物
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx 配置：SPA 路由回退 + API 代理（可选）
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
