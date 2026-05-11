"""AI Factory - 根据配置创建对应的 AI Provider 实例"""
from typing import Optional
from loguru import logger

from .base import AIProvider
from .providers import PROVIDER_MAP


class AIFactory:
    """AI 工厂类"""

    @staticmethod
    def create_provider(config: dict, template_override: str = None) -> Optional[AIProvider]:
        """
        根据配置创建 AI Provider 实例

        Args:
            config: {
                "provider": "openai|anthropic|dashscope|deepseek|custom",
                "api_key": "...",
                "api_base_url": "...",
                "model": "...",
                "temperature": 0.3,
                "max_tokens": 4096,
            }
        Returns:
            AIProvider 实例或 None
        """
        provider_type = config.get("provider", "").lower()
        if provider_type not in PROVIDER_MAP:
            logger.error(f"不支持的AI提供商: {provider_type}，可选: {list(PROVIDER_MAP.keys())}")
            return None

        provider_class = PROVIDER_MAP[provider_type]
        try:
            instance = provider_class(config, template_override)
            logger.info(f"成功创建AI提供商: {provider_type}, 模型: {config.get('model', 'default')}")
            return instance
        except Exception as e:
            logger.error(f"创建AI提供商失败: {provider_type}, 错误: {e}")
            return None
