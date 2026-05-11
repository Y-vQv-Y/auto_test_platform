#!/usr/bin/env python3
"""启动 AI 自动测试平台后端服务"""
import os
import sys
import uvicorn

# 将项目根目录添加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("=" * 60)
    print("  AI 自动测试平台 v1.0.0")
    print("  基于 Playwright + pytest 的自动化测试框架")
    print("=" * 60)
    print()
    print("  启动服务...")
    print("  API 文档: http://localhost:8000/docs")
    print("  前端地址: http://localhost:3000")
    print()

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
