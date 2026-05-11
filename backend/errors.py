"""结构化错误码 — 所有 API 错误响应使用数值错误码"""
from enum import IntEnum
from typing import Optional
from fastapi import HTTPException


class ErrorCode(IntEnum):
    """API 错误码枚举 — 按范围分类"""

    # === 1xxx: 验证错误 ===
    VALIDATION_ERROR = 1000
    MISSING_FIELD = 1001
    INVALID_FORMAT = 1002
    RESOURCE_NOT_FOUND = 1003
    RESOURCE_ALREADY_EXISTS = 1004
    INVALID_STATE = 1005

    # === 2xxx: AI 引擎错误 ===
    AI_PROVIDER_ERROR = 2000
    AI_PROVIDER_UNAVAILABLE = 2001
    AI_RATE_LIMITED = 2002
    AI_RESPONSE_MALFORMED = 2003
    AI_CODE_VALIDATION_FAILED = 2004
    AI_CONFIG_INVALID = 2005

    # === 3xxx: 测试执行错误 ===
    TEST_EXECUTION_ERROR = 3000
    TEST_EXECUTION_FAILED = 3001
    TEST_TIMEOUT = 3002
    TEST_BROWSER_CRASH = 3003
    TEST_NO_CASES = 3004

    # === 4xxx: 安全错误 ===
    SECURITY_ERROR = 4000
    URL_NOT_WHITELISTED = 4001
    TOOL_BLOCKED = 4002
    READONLY_VIOLATION = 4003
    ENCRYPTION_ERROR = 4004

    # === 5xxx: 系统错误 ===
    SYSTEM_ERROR = 5000
    INTERNAL_ERROR = 5001
    DATABASE_ERROR = 5002
    CONFIG_ERROR = 5003
    EXTERNAL_SERVICE_ERROR = 5004


def error_response(code: ErrorCode, detail: str, status_code: int = 400) -> HTTPException:
    """Create a structured HTTPException with numeric error code."""
    return HTTPException(
        status_code=status_code,
        detail={
            "detail": detail,
            "code": code.value,
        },
    )
