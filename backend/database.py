"""数据库模型定义"""
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean,
    DateTime, Float, JSON, ForeignKey, Enum as SqlEnum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import StaticPool
import enum
import json
import os

from backend.config import settings
from backend.security.encryption import EncryptedField

# 确保数据目录存在
os.makedirs("./data", exist_ok=True)

DATABASE_URL = settings.DATABASE_URL
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _now():
    return datetime.now(timezone.utc)


# ---------- 枚举 ----------
class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DISABLED = "disabled"


class TestRunStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"


class AIConfigStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class AiProviderType(str, enum.Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DASHSCOPE = "dashscope"  # 阿里通义千问
    BAIDU = "baidu"  # 百度文心
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"  # 兼容OpenAI格式的自定义


# ---------- 模型 ----------
class Project(Base):
    """项目模型"""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, default="")
    source_code_path = Column(String(500), default="")  # 源代码路径
    deploy_url = Column(String(500), default="")  # 部署URL
    repo_url = Column(String(500), default="")  # 仓库地址
    repo_branch = Column(String(100), default="main")
    framework_type = Column(String(50), default="")  # 框架类型
    status = Column(String(20), default=ProjectStatus.ACTIVE.value)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    # 关联
    test_runs = relationship("TestRun", back_populates="project", cascade="all, delete-orphan")
    test_cases = relationship("TestCase", back_populates="project", cascade="all, delete-orphan")
    login_records = relationship("LoginRecord", back_populates="project", cascade="all, delete-orphan")
    prompt_templates = relationship("PromptTemplate", back_populates="project", cascade="all, delete-orphan")


class AIConfig(Base):
    """AI 配置"""
    __tablename__ = "ai_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    provider = Column(String(50), nullable=False)  # openai/anthropic/dashscope/baidu/custom
    api_key = Column(EncryptedField(), nullable=False)
    api_base_url = Column(String(500), default="")  # 自定义API地址
    model = Column(String(200), default="")  # 模型名称
    temperature = Column(Float, default=0.3)
    max_tokens = Column(Integer, default=4096)
    extra_config = Column(JSON, default=dict)
    status = Column(String(20), default=AIConfigStatus.ACTIVE.value)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class TestCase(Base):
    """AI 生成的测试用例"""
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, default="")
    code = Column(Text, default="")  # Playwright测试代码
    category = Column(String(50), default="")  # 功能/性能/安全/冒烟
    priority = Column(String(20), default="medium")  # high/medium/low
    source = Column(String(20), default="ai_generated")  # ai_generated/manual
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project", back_populates="test_cases")
    results = relationship("TestResult", back_populates="test_case", cascade="all, delete-orphan")


class TestRun(Base):
    """测试运行记录"""
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(300), default="")
    status = Column(String(20), default=TestRunStatus.PENDING.value)
    trigger_mode = Column(String(20), default="manual")  # manual / jenkins / scheduled

    # AI生成配置
    ai_config_id = Column(Integer, ForeignKey("ai_configs.id"), nullable=True)
    generate_prompt = Column(Text, default="")

    # 运行统计
    total_cases = Column(Integer, default=0)
    passed_cases = Column(Integer, default=0)
    failed_cases = Column(Integer, default=0)
    error_cases = Column(Integer, default=0)
    skipped_cases = Column(Integer, default=0)
    duration_seconds = Column(Float, default=0.0)

    # 安全模式
    readonly_mode = Column(Boolean, default=True)
    auto_rollback = Column(Boolean, default=True)

    # 报告
    report_path = Column(String(500), default="")
    report_html = Column(Text, default="")

    # Jenkins 信息
    jenkins_job_name = Column(String(200), default="")
    jenkins_build_number = Column(String(50), default="")

    created_at = Column(DateTime, default=_now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="test_runs")
    results = relationship("TestResult", back_populates="test_run", cascade="all, delete-orphan")


class TestResult(Base):
    """单个测试结果"""
    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    test_run_id = Column(Integer, ForeignKey("test_runs.id"), nullable=False, index=True)
    test_case_id = Column(Integer, ForeignKey("test_cases.id"), nullable=False, index=True)
    name = Column(String(300), default="")
    status = Column(String(20), default="pending")  # passed/failed/error/skipped
    duration_seconds = Column(Float, default=0.0)
    error_message = Column(Text, default="")
    error_traceback = Column(Text, default="")
    screenshot_path = Column(String(500), default="")
    video_path = Column(String(500), default="")
    log_text = Column(Text, default="")
    created_at = Column(DateTime, default=_now)

    test_run = relationship("TestRun", back_populates="results")
    test_case = relationship("TestCase", back_populates="results")


class LoginRecord(Base):
    """登录记录 - 用于验证码登录"""
    __tablename__ = "login_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    url = Column(String(500), nullable=False)
    username_selector = Column(String(200), default="")
    password_selector = Column(String(200), default="")
    login_button_selector = Column(String(200), default="")
    username = Column(String(200), default="")
    encrypted_password = Column(String(500), default="")
    cookies_data = Column(Text, default="")  # JSON 序列化的cookies
    local_storage = Column(Text, default="")  # JSON 序列化的localStorage
    session_valid = Column(Boolean, default=False)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project", back_populates="login_records")


class SecurityLog(Base):
    """安全日志"""
    __tablename__ = "security_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)  # url_check / tool_access / rollback
    target = Column(String(500), default="")
    action = Column(String(200), default="")
    result = Column(String(20), default="")  # allowed / blocked / rolled_back
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=_now)


class JenkinsConfig(Base):
    """Jenkins 集成配置"""
    __tablename__ = "jenkins_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    url = Column(String(500), nullable=False)
    username = Column(String(200), default="")
    api_token = Column(String(500), default="")
    job_name = Column(String(200), default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class PromptTemplate(Base):
    """Prompt 模板 — 按项目和 AI 提供商存储可定制的提示词"""
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    task_type = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    template_body = Column(Text, nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project", back_populates="prompt_templates")


DEFAULT_TEMPLATES = {
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
- 禁止断言 input.get_attribute("type") in ("text", "")
  原因: HTML input无type属性时get_attribute返回None不是""
- 正确: get_attribute("type") in ("text", "", None)
  更好: 直接断言 is_visible() 或 input_value() 即可，无需检查type

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
}


# ---------- 初始化数据库 ----------
def init_db():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
