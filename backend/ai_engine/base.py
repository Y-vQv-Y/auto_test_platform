"""AI 提供商基类"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, AsyncGenerator
from jinja2.sandbox import SandboxedEnvironment
from loguru import logger

# Shared Jinja2 sandbox — safe for user-editable templates
_jinja_env = SandboxedEnvironment()


def render_prompt_template(template_body: str, context: dict = None) -> str:
    """Render a Jinja2 prompt template with the given context variables.
    Uses SandboxedEnvironment to prevent code execution in user-editable templates."""
    if not template_body or not template_body.strip():
        return ""
    try:
        template = _jinja_env.from_string(template_body)
        return template.render(**(context or {}))
    except Exception as e:
        logger.error(f"Prompt 模板渲染失败: {e}")
        raise ValueError(f"Prompt 模板渲染失败: {e}")


class AIProvider(ABC):
    """AI 提供商抽象基类"""

    def __init__(self, config: dict, template_override: str = None):
        self.api_key = config.get("api_key", "")
        self.api_base_url = config.get("api_base_url", "")
        self.model = config.get("model", "")
        self.temperature = config.get("temperature", 0.3)
        self.max_tokens = config.get("max_tokens", 16384)
        self.extra_config = config.get("extra_config", {})
        self.template_override = template_override

    @abstractmethod
    async def chat(self, messages: List[Dict], stream: bool = False) -> str:
        """对话接口"""
        pass

    @abstractmethod
    async def chat_stream(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        """流式对话接口"""
        pass

    @abstractmethod
    async def generate_test_cases(
        self,
        source_code: str,
        test_type: str = "功能测试",
        additional_context: str = "",
    ) -> str:
        """生成测试用例代码"""
        pass

    @abstractmethod
    async def analyze_code(
        self,
        code: str,
        analysis_type: str = "功能分析",
    ) -> str:
        """分析源代码功能"""
        pass

    def _build_system_prompt(self, task_type: str = "default", context: dict = None) -> str:
        """构建系统提示词。优先使用数据库模板，回退到硬编码默认值。"""
        if self.template_override:
            return render_prompt_template(self.template_override, context)

        prompts = {
            "test_generation": """你是一个专业的自动化测试工程师。根据提供的源代码和页面路由信息，生成 Playwright + pytest 自动化测试代码。

【严格规则】
1. 函数签名: def test_xxx(page):
2. 导航必须使用: goto(page, BASE_URL + "/路径")
   goto 已预定义，自动等待SPA渲染，禁止直接用 page.goto
3. goto 后不要写 wait_for_load_state，已内置处理
4. 禁止定义辅助函数、类、fixture
5. 需要标准库时在函数内部 import（如: import time）
6. 每个函数完全独立，不依赖其他测试状态
7. 只输出Python代码，不要markdown标记
8. 生成exactly 8个测试函数
9. 【关键】路由必须来自 additional_context 中发现的真实路由，不要凭空猜测
10. goto后用 page.wait_for_selector('h1') 再做断言，确保页面渲染完成\n"
11. 断言页面标题时用 page.locator('h1').inner_text() 而不是直接比较\n"
12. 查找按钮/元素失败时先等待: page.wait_for_selector('button', timeout=5000)\n"

【可用变量和函数】
- page: Playwright Page对象
- BASE_URL: 部署根地址（如 http://192.168.1.1:8080）
- goto(page, url): 导航并等待渲染
- expect: playwright expect断言

【示例格式】
def test_home_page(page):
    goto(page, BASE_URL + "/")
    assert page.locator("h1").is_visible()

def test_list_page(page):
    goto(page, BASE_URL + "/list")
    page.wait_for_selector(".list-container")
    assert page.locator(".list-container").is_visible()
""",
        }
        return prompts.get(task_type, "你是一个专业的AI助手，请帮助完成测试相关任务。请用中文回复。")
