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
1. 函数签名必须是: def test_xxx(page):
2. 【禁止】直接使用 page.goto()，必须使用 goto(page, url)
   正确: goto(page, BASE_URL + "/ai-config")
   错误: page.goto(BASE_URL + "/ai-config")
3. goto已内置等待SPA渲染，调用后无需再等待，直接断言
4. 禁止定义辅助函数、类、fixture、conftest
5. 需要标准库时在函数内部import（如: import time）
6. 每个函数完全独立，不依赖其他测试的状态
7. 只输出Python代码，不要markdown代码块标记
8. 根据页面数量生成对应数量的测试函数，每页至少2个
9. 路由必须来自additional_context中发现的真实路由，不要假设

【选择器规则 - 必须遵守】
- 禁止: page.locator("text=测试运行").is_visible()
  原因: text=选择器可能匹配多个元素导致strict mode报错
- 正确-断言标题: h1 = page.locator("h1").first.inner_text(); assert "目标文字" in h1
- 正确-查找按钮: page.locator("button").filter(has_text="新建项目").first.click()
- 正确-查找文字: page.get_by_text("目标文字", exact=True).first.is_visible()
- 正确-等待元素: page.wait_for_selector(".cyber-card", timeout=5000)
- 所有多元素选择器必须加.first或.filter()缩小范围

【可用变量和函数】
- page: Playwright Page对象（已打开浏览器）
- BASE_URL: 部署根地址（末尾无斜杠，如 http://192.168.1.1:3000）
  ★ 拼接路径直接写：goto(page, BASE_URL + "/ai-config")
  ★ 根路径写：goto(page, BASE_URL + "/")
- goto(page, url): 导航并自动等待SPA渲染完成，必须用这个
- expect: playwright的expect断言对象
- pytest: pytest模块

【正确示例】
def test_dashboard(page):
    goto(page, BASE_URL + "/")
    h1 = page.locator("h1").first.inner_text()
    assert "控制台" in h1
    card = page.locator(".cyber-card").first
    assert card.is_visible()

def test_projects_page(page):
    goto(page, BASE_URL + "/projects")
    h1 = page.locator("h1").first.inner_text()
    assert "项目管理" in h1
    btn = page.locator("button").filter(has_text="新建项目").first
    assert btn.is_visible()

【错误示例（禁止）】
def test_bad(page):
    page.goto(BASE_URL + "/projects")        # 禁止
    page.wait_for_load_state("networkidle")  # 禁止，goto已处理
    page.locator("text=项目管理").is_visible() # 禁止，可能strict mode报错
""",

    "code_analysis": """你是一个资深的全栈工程师。请分析提供的源代码，识别出：
1. 主要功能模块
2. 路由/端点
3. 关键业务逻辑
4. 数据流
5. 需要测试的核心功能点
6. 潜在的边界条件和异常情况

{% if user_context %}额外上下文: {{ user_context }}{% endif %}

请用中文回复。""",

    "page_analysis": """你是一个专业的Web测试专家。请分析提供的页面，生成对应的测试用例设计：
1. 功能测试点
2. 交互测试点
3. 边界条件
4. 异常场景
5. 安全测试点
6. 性能关注点

{% if page_url %}页面URL: {{ page_url }}{% endif %}
{% if page_title %}页面标题: {{ page_title }}{% endif %}

请用中文回复。
""",
        }
        return prompts.get(task_type, "你是一个专业的AI助手，请帮助完成测试相关任务。请用中文回复。")
