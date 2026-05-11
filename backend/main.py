"""AI 自动测试平台 - FastAPI 主入口"""
import os
import sys
import json
from contextlib import asynccontextmanager
from pathlib import Path
from loguru import logger
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import init_db, SessionLocal
from backend.security.encryption import migrate_plaintext_keys

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:7}</level> | {message}")
logger.add("./logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG", encoding="utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    logger.info(f"{settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    # 初始化数据库
    init_db()
    # 自动迁移明文 API Key 到加密格式
    try:
        db = SessionLocal()
        try:
            migrated = migrate_plaintext_keys(db)
            if migrated > 0:
                logger.warning(f"已自动加密 {migrated} 条旧 API Key（从明文迁移到加密存储）")
            else:
                logger.info("API Key 加密状态正常，无需迁移")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"API Key 迁移失败: {e}")
    os.makedirs(settings.REPORT_DIR, exist_ok=True)
    os.makedirs(settings.GENERATED_TEST_DIR, exist_ok=True)
    os.makedirs("./logs", exist_ok=True)
    os.makedirs("./data", exist_ok=True)
    logger.info("数据库初始化完成")
    yield
    logger.info("应用关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI自动测试平台 - Playwright + pytest 自动化测试框架",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 注册路由 ----------
from backend.api.projects import router as projects_router
from backend.api.test_runs import router as test_runs_router
from backend.api.ai_configs import router as ai_configs_router
from backend.api.jenkins import router as jenkins_router
from backend.api.settings_api import router as settings_router

app.include_router(projects_router)
app.include_router(test_runs_router)
app.include_router(ai_configs_router)
app.include_router(jenkins_router)
app.include_router(settings_router)


# ---------- 静态文件服务 ----------
FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """提供前端静态文件"""
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return JSONResponse({"error": "前端未构建"}, status_code=404)
else:
    @app.get("/")
    async def root():
        return {
            "message": f"{settings.APP_NAME} v{settings.APP_VERSION}",
            "status": "running",
            "docs": "/docs",
        }


# ---------- 全局异常处理 ----------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from backend.errors import ErrorCode
    from fastapi import HTTPException as _FastAPIHTTPException
    if isinstance(exc, _FastAPIHTTPException):
        raise exc
    logger.error(f"全局异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误: {str(exc)}", "code": ErrorCode.INTERNAL_ERROR.value},
    )


# ---------- 健康检查 ----------
@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": __import__("datetime").datetime.now().isoformat()}


# ---------- 启动入口 ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
    )
