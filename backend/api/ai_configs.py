"""AI 配置管理 API"""
import asyncio
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from loguru import logger

from backend.database import get_db, AIConfig, AIConfigStatus
from backend.ai_engine import AIFactory
from backend.errors import ErrorCode, error_response

router = APIRouter(prefix="/api/v1/ai-configs", tags=["AI配置"])


class AIConfigCreate(BaseModel):
    name: str
    provider: str  # openai/anthropic/dashscope/deepseek/custom
    api_key: str
    api_base_url: str = ""
    model: str = ""
    temperature: float = 0.3
    max_tokens: int = 4096
    is_default: bool = False


class AIConfigUpdate(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    status: Optional[str] = None
    is_default: Optional[bool] = None


@router.get("")
def list_ai_configs(
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """获取 AI 配置列表"""
    query = db.query(AIConfig)
    if provider:
        query = query.filter(AIConfig.provider == provider)
    query = query.order_by(AIConfig.is_default.desc(), AIConfig.updated_at.desc())

    return {
        "items": [
            {
                "id": c.id,
                "name": c.name,
                "provider": c.provider,
                "api_base_url": c.api_base_url,
                "model": c.model,
                "temperature": c.temperature,
                "max_tokens": c.max_tokens,
                "status": c.status,
                "is_default": c.is_default,
                "created_at": c.created_at.isoformat() if c.created_at else "",
                "updated_at": c.updated_at.isoformat() if c.updated_at else "",
                # API Key 只返回前8位
                "api_key_preview": "••••••••" if c.api_key else "",
            }
            for c in query.all()
        ],
    }


@router.post("")
def create_ai_config(data: AIConfigCreate, db: Session = Depends(get_db)):
    """创建 AI 配置"""
    if data.is_default:
        # 取消其他默认配置
        db.query(AIConfig).filter(AIConfig.is_default == True).update(
            {"is_default": False}
        )

    config = AIConfig(
        name=data.name,
        provider=data.provider,
        api_key=data.api_key,
        api_base_url=data.api_base_url,
        model=data.model,
        temperature=data.temperature,
        max_tokens=data.max_tokens,
        is_default=data.is_default,
        status=AIConfigStatus.ACTIVE.value,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    return {
        "id": config.id,
        "name": config.name,
        "message": "AI 配置创建成功",
    }


@router.get("/{config_id}")
def get_ai_config(config_id: int, db: Session = Depends(get_db)):
    """获取 AI 配置详情"""
    config = db.query(AIConfig).filter(AIConfig.id == config_id).first()
    if not config:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "配置不存在", 404)

    return {
        "id": config.id,
        "name": config.name,
        "provider": config.provider,
        "api_base_url": config.api_base_url,
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "status": config.status,
        "is_default": config.is_default,
        "api_key_preview": config.api_key[:8] + "..." if config.api_key else "",
    }


@router.put("/{config_id}")
def update_ai_config(config_id: int, data: AIConfigUpdate, db: Session = Depends(get_db)):
    """更新 AI 配置"""
    config = db.query(AIConfig).filter(AIConfig.id == config_id).first()
    if not config:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "配置不存在", 404)

    if data.is_default:
        db.query(AIConfig).filter(AIConfig.is_default == True).update(
            {"is_default": False}
        )

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)
    db.commit()

    return {"message": "AI 配置更新成功"}


@router.delete("/{config_id}")
def delete_ai_config(config_id: int, db: Session = Depends(get_db)):
    """删除 AI 配置"""
    config = db.query(AIConfig).filter(AIConfig.id == config_id).first()
    if not config:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "配置不存在", 404)

    db.delete(config)
    db.commit()
    return {"message": "AI 配置已删除"}


@router.post("/{config_id}/test")
async def test_ai_connection(config_id: int, db: Session = Depends(get_db)):
    """测试 AI 连接（发送一条简单消息验证连通性）"""
    config = db.query(AIConfig).filter(AIConfig.id == config_id).first()
    if not config:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "配置不存在", 404)

    # 自动补全 API 地址路径（DeepSeek 需要 /v1）
    api_base_url = config.api_base_url
    if "deepseek" in (api_base_url or "").lower() and not api_base_url.rstrip("/").endswith("/v1"):
        api_base_url = api_base_url.rstrip("/") + "/v1"
        logger.info(f"自动补全 API 路径: {config.api_base_url} → {api_base_url}")

    provider = AIFactory.create_provider({
        "provider": config.provider,
        "api_key": config.api_key,
        "api_base_url": api_base_url,
        "model": config.model,
        "temperature": 0.1,
        "max_tokens": 4096,   # 思考模型需要更多 token 才能输出文字
        "extra_config": config.extra_config or {},
    })

    if not provider:
        raise error_response(ErrorCode.AI_CONFIG_INVALID, f"不支持的 AI 提供商: {config.provider}", 400)

    try:
        # 发送一条简单测试消息
        result = await asyncio.wait_for(
            provider.chat([{"role": "user", "content": "请回复 OK 表示连接正常。"}]),
            timeout=30.0,
        )
        return {
            "success": True,
            "message": "AI 连接测试成功",
            "response": result[:200] if result else "（空响应）",
        }
    except asyncio.TimeoutError:
        logger.error(f"AI连接测试超时: config_id={config_id}")
        raise error_response(ErrorCode.AI_PROVIDER_UNAVAILABLE, "AI 连接超时（超过30秒），请检查网络和API地址", 504)
    except Exception as e:
        logger.error(f"AI连接测试失败: config_id={config_id}, error={e}")
        raise error_response(ErrorCode.AI_PROVIDER_ERROR, str(e), 502)
