# ============================================
# AI 自动测试平台 - 后端 Dockerfile
# 基于 Python 3.11 + Playwright
# ============================================
FROM docker.1ms.run/library/python:3.11-slim AS builder

WORKDIR /app

# 安装编译依赖
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# ============================================
FROM docker.1ms.run/library/python:3.11-slim AS runtime

WORKDIR /app

# 安装 Playwright 运行时系统依赖（仅 Chromium）+ xvfb（虚拟显示，支持有头模式）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 从前一阶段复制已安装的 Python 包
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制项目代码
COPY backend/ ./backend/
COPY run_backend.py .

# 创建必要的数据目录
RUN mkdir -p ./data ./logs ./test_reports ./generated_tests

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# 切换到 appuser 后安装 Playwright 浏览器（确保浏览器在 appuser 的 home 下）
USER appuser
ENV PLAYWRIGHT_BROWSERS_PATH=/home/appuser/.cache/ms-playwright
RUN playwright install chromium && \
    playwright install-deps chromium 2>/dev/null || true

# 健康检查（端口从环境变量 PORT 读取，默认 8000）
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import os, urllib.request; port=os.environ.get('PORT','8000'); urllib.request.urlopen(f'http://localhost:{port}/health')" || exit 1

EXPOSE 8000

# 使用 python -m 启动，自动读取 settings.HOST 和 settings.PORT（支持环境变量覆盖）
CMD ["python", "-m", "backend.main"]
