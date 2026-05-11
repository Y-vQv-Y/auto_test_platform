"""AI 提供商实现 - 支持 OpenAI / Anthropic / 阿里通义千问 / DeepSeek / 自定义"""
import json
from typing import List, Dict, AsyncGenerator
from loguru import logger

from .base import AIProvider


class OpenAIProvider(AIProvider):
    """OpenAI 兼容接口（也支持 DeepSeek 等兼容 OpenAI 格式的接口）"""

    def __init__(self, config: dict, template_override: str = None):
        super().__init__(config, template_override)
        # 自动补全 API 路径：DeepSeek 等需要以 /v1 结尾
        if self.api_base_url:
            if "deepseek" in self.api_base_url.lower() and not self.api_base_url.rstrip("/").endswith("/v1"):
                self.api_base_url = self.api_base_url.rstrip("/") + "/v1"
                logger.info(f"自动补全 API 路径 → {self.api_base_url}")

    async def chat(self, messages: List[Dict], stream: bool = False) -> str:
        import openai
        try:
            base_url = self.api_base_url or "https://api.openai.com/v1"
            logger.info(f"AI请求: provider=openai, model={self.model}, base_url={base_url}")

            # 构建请求参数
            kwargs = dict(
                model=self.model or "gpt-4",
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=False,
            )

            # 支持 DeepSeek V4 等思考模型的 extra_body 参数
            # 通过 AI 配置的 extra_config JSON 字段传入
            if self.extra_config:
                if "thinking" in self.extra_config:
                    kwargs["extra_body"] = {"thinking": self.extra_config["thinking"]}
                if "reasoning_effort" in self.extra_config:
                    kwargs["reasoning_effort"] = self.extra_config["reasoning_effort"]

            client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=base_url,
                timeout=openai.Timeout(120.0, connect=30.0),
            )
            resp = await client.chat.completions.create(**kwargs)

            # 提取响应内容（兼容 DeepSeek V4 思考模型）
            message = resp.choices[0].message
            content = message.content or ""
            if not content.strip():
                reasoning = getattr(message, "reasoning_content", None)
                if reasoning:
                    content = f"[思考过程]\n{reasoning}"
                else:
                    content = str(message.model_dump() if hasattr(message, 'model_dump') else message)[:200]

            return content
        except openai.APIConnectionError as e:
            logger.error(f"AI连接失败: 无法连接到 {base_url} - {e}")
            raise Exception(f"无法连接到AI服务({base_url})，请检查API地址和网络连接: {e}")
        except openai.AuthenticationError as e:
            logger.error(f"AI认证失败: API Key 无效 - {e}")
            raise Exception("AI API Key 认证失败，请检查 API Key 是否正确")
        except openai.RateLimitError as e:
            logger.error(f"AI速率限制: {e}")
            raise Exception("AI 接口请求频率过高，请稍后再试")
        except openai.APIStatusError as e:
            logger.error(f"AI服务错误: status={e.status_code} - {e}")
            raise Exception(f"AI服务返回错误(status={e.status_code}): {e.message}")
        except Exception as e:
            logger.error(f"AI请求未知错误: {type(e).__name__}: {e}")
            raise Exception(f"AI请求失败: {type(e).__name__}: {e}")

    async def chat_stream(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        import openai
        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base_url or "https://api.openai.com/v1",
        )
        stream = await client.chat.completions.create(
            model=self.model or "gpt-4",
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_test_cases(self, source_code: str, test_type: str = "功能测试",
                                  additional_context: str = "") -> str:
        messages = [
            {"role": "system", "content": self._build_system_prompt("test_generation")},
            {"role": "user", "content": f"测试类型: {test_type}\n\n源代码:\n```\n{source_code}\n```\n\n{additional_context}\n\n请根据以上源代码生成完整的 Playwright + pytest 测试代码。"}
        ]
        return await self.chat(messages)

    async def analyze_code(self, code: str, analysis_type: str = "功能分析") -> str:
        messages = [
            {"role": "system", "content": self._build_system_prompt("code_analysis")},
            {"role": "user", "content": f"分析类型: {analysis_type}\n\n源代码:\n```\n{code}\n```\n\n请分析以上代码的功能和测试要点。"}
        ]
        return await self.chat(messages)


class AnthropicProvider(AIProvider):
    """Anthropic Claude 接口"""

    async def chat(self, messages: List[Dict], stream: bool = False) -> str:
        import anthropic
        from anthropic import APIConnectionError, APIStatusError, APITimeoutError
        try:
            logger.info(f"AI请求: provider=anthropic, model={self.model}")
            client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                timeout=120.0,  # 增加超时
            )
            system_msg = ""
            chat_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_msg += msg["content"] + "\n"
                else:
                    chat_messages.append({"role": msg["role"], "content": msg["content"]})

            resp = await client.messages.create(
                model=self.model or "claude-3-sonnet-20241022",
                system=system_msg.strip() or None,
                messages=chat_messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            return resp.content[0].text if resp.content else ""
        except APIConnectionError as e:
            logger.error(f"Anthropic连接失败: {e}")
            raise Exception(f"无法连接到Anthropic服务，请检查网络: {e}")
        except APITimeoutError as e:
            logger.error(f"Anthropic超时: {e}")
            raise Exception("Anthropic请求超时，请稍后再试")
        except APIStatusError as e:
            logger.error(f"Anthropic服务错误: status={e.status_code} - {e}")
            raise Exception(f"Anthropic服务错误(status={e.status_code}): {e.response}")
        except Exception as e:
            logger.error(f"Anthropic请求未知错误: {type(e).__name__}: {e}")
            raise Exception(f"AI请求失败: {type(e).__name__}: {e}")

    async def chat_stream(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg += msg["content"] + "\n"
            else:
                chat_messages.append({"role": msg["role"], "content": msg["content"]})

        async with client.messages.stream(
            model=self.model or "claude-3-sonnet-20241022",
            system=system_msg.strip() or None,
            messages=chat_messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def generate_test_cases(self, source_code: str, test_type: str = "功能测试",
                                  additional_context: str = "") -> str:
        messages = [
            {"role": "user", "content": f"{self._build_system_prompt('test_generation')}\n\n测试类型: {test_type}\n\n源代码:\n```\n{source_code}\n```\n\n{additional_context}\n\n请根据以上源代码生成完整的 Playwright + pytest 测试代码。"}
        ]
        return await self.chat(messages)

    async def analyze_code(self, code: str, analysis_type: str = "功能分析") -> str:
        messages = [
            {"role": "user", "content": f"{self._build_system_prompt('code_analysis')}\n\n分析类型: {analysis_type}\n\n源代码:\n```\n{code}\n```\n\n请分析以上代码。"}
        ]
        return await self.chat(messages)


class DashScopeProvider(AIProvider):
    """阿里云通义千问"""

    async def _call_dashscope(self, messages: List[Dict], stream: bool = False) -> str:
        import openai
        try:
            logger.info(f"AI请求: provider=dashscope, model={self.model}")
            client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                timeout=openai.Timeout(120.0, connect=30.0),
            )
            resp = await client.chat.completions.create(
                model=self.model or "qwen-turbo",
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=False,
            )
            return resp.choices[0].message.content or ""
        except openai.APIConnectionError as e:
            raise Exception(f"无法连接到通义千问服务，请检查网络: {e}")
        except openai.AuthenticationError as e:
            raise Exception("通义千问 API Key 认证失败")
        except Exception as e:
            logger.error(f"通义千问请求失败: {type(e).__name__}: {e}")
            raise Exception(f"AI请求失败: {type(e).__name__}: {e}")

    async def chat(self, messages: List[Dict], stream: bool = False) -> str:
        return await self._call_dashscope(messages, stream)

    async def chat_stream(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        import openai
        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        stream_resp = await client.chat.completions.create(
            model=self.model or "qwen-turbo",
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        async for chunk in stream_resp:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_test_cases(self, source_code: str, test_type: str = "功能测试",
                                  additional_context: str = "") -> str:
        messages = [
            {"role": "system", "content": self._build_system_prompt("test_generation")},
            {"role": "user", "content": f"测试类型: {test_type}\n\n源代码:\n```\n{source_code}\n```\n\n{additional_context}\n\n生成测试代码。"}
        ]
        return await self.chat(messages)

    async def analyze_code(self, code: str, analysis_type: str = "功能分析") -> str:
        messages = [
            {"role": "system", "content": self._build_system_prompt("code_analysis")},
            {"role": "user", "content": f"分析类型: {analysis_type}\n\n代码:\n```\n{code}\n```\n\n分析代码。"}
        ]
        return await self.chat(messages)


class DeepSeekProvider(AIProvider):
    """DeepSeek API (兼容 OpenAI 格式)"""

    def __init__(self, config: dict, template_override: str = None):
        super().__init__(config, template_override)
        if not self.api_base_url:
            self.api_base_url = "https://api.deepseek.com"

    async def chat(self, messages: List[Dict], stream: bool = False) -> str:
        import openai
        try:
            base_url = self.api_base_url or "https://api.deepseek.com"
            logger.info(f"AI请求: provider=deepseek, model={self.model}, base_url={base_url}")
            client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=base_url,
                timeout=openai.Timeout(120.0, connect=30.0),
            )
            resp = await client.chat.completions.create(
                model=self.model or "deepseek-chat",
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=False,
            )
            return resp.choices[0].message.content or ""
        except openai.APIConnectionError as e:
            logger.error(f"DeepSeek连接失败: {e}")
            raise Exception(f"无法连接到DeepSeek服务({base_url})，请检查API地址和网络: {e}")
        except openai.AuthenticationError as e:
            logger.error(f"DeepSeek认证失败: {e}")
            raise Exception("DeepSeek API Key 认证失败")
        except openai.RateLimitError as e:
            raise Exception("DeepSeek请求频率过高，请稍后再试")
        except openai.APIStatusError as e:
            raise Exception(f"DeepSeek服务错误(status={e.status_code})")
        except Exception as e:
            logger.error(f"DeepSeek请求未知错误: {type(e).__name__}: {e}")
            raise Exception(f"AI请求失败: {type(e).__name__}: {e}")

    async def chat_stream(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        import openai
        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base_url,
        )
        stream_resp = await client.chat.completions.create(
            model=self.model or "deepseek-chat",
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        async for chunk in stream_resp:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_test_cases(self, source_code: str, test_type: str = "功能测试",
                                  additional_context: str = "") -> str:
        messages = [
            {"role": "system", "content": self._build_system_prompt("test_generation")},
            {"role": "user", "content": f"测试类型: {test_type}\n\n源代码:\n```\n{source_code}\n```\n\n{additional_context}\n\n生成测试代码。"}
        ]
        return await self.chat(messages)

    async def analyze_code(self, code: str, analysis_type: str = "功能分析") -> str:
        messages = [
            {"role": "system", "content": self._build_system_prompt("code_analysis")},
            {"role": "user", "content": f"分析类型: {analysis_type}\n\n代码:\n```\n{code}\n```\n\n分析代码。"}
        ]
        return await self.chat(messages)


class CustomProvider(AIProvider):
    """自定义 OpenAI 兼容接口"""

    async def chat(self, messages: List[Dict], stream: bool = False) -> str:
        import openai
        try:
            logger.info(f"AI请求: provider=custom, model={self.model}, base_url={self.api_base_url}")
            client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_base_url,
                timeout=openai.Timeout(120.0, connect=30.0),
            )
            resp = await client.chat.completions.create(
                model=self.model or "gpt-3.5-turbo",
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=False,
            )
            return resp.choices[0].message.content or ""
        except openai.APIConnectionError as e:
            raise Exception(f"无法连接到自定义AI服务({self.api_base_url})，请检查地址和网络: {e}")
        except openai.AuthenticationError as e:
            raise Exception("自定义AI API Key 认证失败")
        except Exception as e:
            logger.error(f"自定义AI请求失败: {type(e).__name__}: {e}")
            raise Exception(f"AI请求失败: {type(e).__name__}: {e}")

    async def chat_stream(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        import openai
        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base_url,
        )
        stream_resp = await client.chat.completions.create(
            model=self.model or "gpt-3.5-turbo",
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        async for chunk in stream_resp:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_test_cases(self, source_code: str, test_type: str = "功能测试",
                                  additional_context: str = "") -> str:
        messages = [
            {"role": "system", "content": self._build_system_prompt("test_generation")},
            {"role": "user", "content": f"测试类型: {test_type}\n\n源代码:\n```\n{source_code}\n```\n\n{additional_context}\n\n生成测试代码。"}
        ]
        return await self.chat(messages)

    async def analyze_code(self, code: str, analysis_type: str = "功能分析") -> str:
        messages = [
            {"role": "system", "content": self._build_system_prompt("code_analysis")},
            {"role": "user", "content": f"分析类型: {analysis_type}\n\n代码:\n```\n{code}\n```\n\n分析代码。"}
        ]
        return await self.chat(messages)


PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "dashscope": DashScopeProvider,
    "deepseek": DeepSeekProvider,
    "custom": CustomProvider,
}
