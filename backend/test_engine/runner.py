"""Playwright + pytest 测试执行器 — 隔离子进程执行 + JSON 报告解析"""
import os
import sys
import json as json_lib
import asyncio
import subprocess
import re
import textwrap
from typing import Optional, Callable
from datetime import datetime, timezone
from loguru import logger

from backend.database import SessionLocal, TestRun, TestResult, TestCase
from backend.config import settings


class TestRunner:
    def __init__(self, progress_callback: Optional[Callable] = None):
        self.progress_callback = progress_callback
        self._running = False
        self._current_run_id: Optional[int] = None

    async def run_test_cases(self, run_id: int, test_cases: list, deploy_url: str,
                             login_info: dict = None, readonly_mode: bool = True,
                             headless: bool = None) -> dict:
        self._running = True
        self._current_run_id = run_id
        if headless is None:
            headless = settings.PLAYWRIGHT_HEADLESS

        db = SessionLocal()
        try:
            run = db.query(TestRun).filter(TestRun.id == run_id).first()
            if run:
                run.status = "running"
                run.started_at = datetime.now(timezone.utc)
                run.total_cases = len(test_cases)
                db.commit()
        finally:
            db.close()

        await self._push_progress("running", 0, f"开始执行 {len(test_cases)} 个测试用例")

        run_dir = os.path.abspath(os.path.join(settings.GENERATED_TEST_DIR, f"run_{run_id}"))
        os.makedirs(run_dir, exist_ok=True)

        test_file = os.path.join(run_dir, "test_suite.py")
        report_file = os.path.join(run_dir, ".report.json")

        test_code = build_test_file_content(test_cases, deploy_url, login_info, headless, readonly_mode)
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_code)

        import ast as _ast
        try:
            _ast.parse(test_code)
            logger.info(f"测试文件语法检查通过，共 {len(test_cases)} 个用例")
        except SyntaxError as e:
            logger.error(f"生成的测试文件语法错误: {e}\n文件内容:\n{test_code}")
            # 直接标记所有用例为error，不执行pytest
            db = SessionLocal()
            try:
                run = db.query(TestRun).filter(TestRun.id == run_id).first()
                if run:
                    run.status = "error"
                    run.completed_at = datetime.now(timezone.utc)
                    run.error_cases = len(test_cases)
                    run.total_cases = len(test_cases)
                    db.commit()
                for tc in test_cases:
                    result = TestResult(
                        test_run_id=run_id,
                        test_case_id=tc["id"],
                        name=tc.get("name", "unknown"),
                        status="error",
                        error_message=f"生成的测试文件语法错误(行{e.lineno}): {e.msg}",
                    )
                    db.add(result)
                db.commit()
            finally:
                db.close()
            self._running = False
            return {
                "status": "error", "total": len(test_cases),
                "passed": 0, "failed": 0, "errors": len(test_cases),
                "duration": 0, "results": [],
            }

        # 记录生成的测试文件内容便于调试
        logger.debug(f"生成测试文件:\n{test_code[:2000]}")

        timeout_seconds = settings.PLAYWRIGHT_TIMEOUT // 1000 + 600
        await self._run_pytest_suite(test_file, report_file, run_dir, timeout_seconds)

        # ← 注意：以下全部在 run_test_cases 方法内，缩进8格
        if not os.path.exists(report_file):
            logger.error(f"pytest json report 未生成: {report_file}，可能测试文件语法有误")
            parsed_results = [
                {
                    "test_case_id": tc["id"],
                    "name": tc.get("name", "unknown"),
                    "status": "error",
                    "duration": 0,
                    "error_message": "pytest 未生成报告文件，测试文件可能存在语法错误",
                    "error_traceback": "",
                    "screenshot_path": "",
                    "log_text": "",
                }
                for tc in test_cases
            ]
        else:
            parsed_results = parse_pytest_json(report_file, test_cases)

        passed, failed, errors = 0, 0, 0
        for pr in parsed_results:
            db = SessionLocal()
            try:
                test_result = TestResult(
                    test_run_id=run_id,
                    test_case_id=pr["test_case_id"],
                    name=pr["name"],
                    status=pr["status"],
                    duration_seconds=pr.get("duration", 0),
                    error_message=pr.get("error_message", ""),
                    error_traceback=pr.get("error_traceback", ""),
                    screenshot_path=pr.get("screenshot_path", ""),
                    log_text=pr.get("log_text", ""),
                )
                db.add(test_result)
                db.commit()
            finally:
                db.close()

            if pr["status"] == "passed":
                passed += 1
            elif pr["status"] == "failed":
                failed += 1
            else:
                errors += 1

        total_duration = sum(p.get("duration", 0) for p in parsed_results)
        db = SessionLocal()
        try:
            run = db.query(TestRun).filter(TestRun.id == run_id).first()
            if run:
                run.status = "passed" if errors == 0 and failed == 0 else "failed"
                run.completed_at = datetime.now(timezone.utc)
                run.passed_cases = passed
                run.failed_cases = failed
                run.error_cases = errors
                run.duration_seconds = total_duration
                db.commit()
        finally:
            db.close()

        await self._push_progress("completed", 100,
            f"测试完成: 通过{passed}, 失败{failed}, 错误{errors}")

        self._running = False
        return {
            "status": "passed" if errors == 0 and failed == 0 else "failed",
            "total": len(test_cases),
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "duration": total_duration,
            "results": parsed_results,
        }

    async def retry_single_case(self, run_id: int, test_case_id: int,
                                test_code: str, test_name: str,
                                deploy_url: str, headless: bool = True) -> dict:
        run_dir = os.path.abspath(os.path.join(settings.GENERATED_TEST_DIR, f"run_{run_id}"))
        os.makedirs(run_dir, exist_ok=True)

        retry_file = os.path.join(run_dir, f"retry_{test_case_id}.py")
        report_file = os.path.join(run_dir, f".retry_{test_case_id}.json")

        code = _build_single_test_file(test_code, test_name, deploy_url, headless)
        with open(retry_file, "w", encoding="utf-8") as f:
            f.write(code)

        await self._run_pytest_suite(retry_file, report_file, run_dir, 300)
        parsed = parse_pytest_json(report_file, [{"id": test_case_id, "name": test_name}])
        return parsed[0] if parsed else {
            "test_case_id": test_case_id,
            "status": "error",
            "error_message": "未找到测试结果",
        }

    def cancel(self):
        self._running = False

    async def _run_pytest_suite(self, test_file: str, report_file: str,
                                run_dir: str, timeout: int):
        cmd = [
            sys.executable, '-m', 'pytest',
            test_file,
            '--json-report',
            '--json-report-file=' + report_file,
            '-v',
            '--tb=short',
        ]
        logger.info(f"执行 pytest 子进程: {' '.join(cmd)}")
        await self._push_progress("running", 50, "pytest 子进程执行中...")

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, cwd=run_dir, timeout=timeout,
                capture_output=True, text=True
            )
            if result.returncode == 0:
                logger.info("pytest 子进程成功完成")
            else:
                logger.warning(f"pytest exited with code {result.returncode}")
                if result.stdout:
                    logger.info(f"pytest stdout:\n{result.stdout[:2000]}")
                if result.stderr:
                    logger.debug(f"pytest stderr:\n{result.stderr[:500]}")
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"pytest 子进程超时 ({timeout}s)")
            await self._push_progress("error", 50, f"测试执行超时 ({timeout}s)")
            _write_timeout_report(report_file, timeout)
            return None

    async def _push_progress(self, status: str, progress: int, message: str):
        if self.progress_callback:
            await self.progress_callback({
                "type": "progress",
                "run_id": self._current_run_id,
                "status": status,
                "progress": progress,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            })

    async def _save_run_error(self, run_id: int, error: str):
        db = SessionLocal()
        try:
            run = db.query(TestRun).filter(TestRun.id == run_id).first()
            if run:
                run.status = "error"
                run.completed_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()


# =================================================================
# 模块级辅助函数
# =================================================================

def build_test_file_content(test_cases: list, deploy_url: str, login_info: dict,
                             headless: bool, readonly_mode: bool) -> str:
    # goto函数单独构建，避免f-string嵌套引号问题
    goto_func = '''
def goto(page, url, wait_for=None, timeout=15000):
    """导航并等待SPA页面渲染完成"""
    from urllib.parse import urlparse
    target_path = urlparse(url).path or "/"
    page.goto(url)
    # 等待网络空闲
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    # 等待URL路径切换到目标（SPA路由核心等待）
    try:
        page.wait_for_function(
            "(p => () => window.location.pathname === p)(" + repr(target_path) + ")",
            timeout=timeout
        )
    except Exception:
        pass
    # 等待h1出现（页面内容渲染标志）
    try:
        page.wait_for_selector("h1", timeout=timeout)
    except Exception:
        pass
    if wait_for:
        try:
            page.wait_for_selector(wait_for, timeout=timeout)
        except Exception:
            pass
    page.wait_for_timeout(800)
'''

    header = f'''import pytest
import re
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

DEPLOY_URL = {deploy_url!r}
BASE_URL = {deploy_url!r}
HEADLESS = {headless!r}
'''

    fixtures = '''
@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=HEADLESS, args=["--no-sandbox", "--disable-setuid-sandbox"])
        yield b
        b.close()

@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    p = context.new_page()
    p.set_default_timeout(15000)
    yield p
    context.close()
'''

    login_fixture = ""
    if login_info and login_info.get("cookies_data"):
        cookies_str = login_info["cookies_data"]
        login_fixture = f'''
@pytest.fixture(autouse=True)
def restore_login(page):
    import json
    _cookies = json.loads({cookies_str!r})
    page.context.add_cookies(_cookies)
'''

    # 拼接文件头部
    parts = [header, goto_func, fixtures, login_fixture]

    # 逐个用例生成函数
    for tc in test_cases:
        raw_code = tc.get("code", "").strip()
        tc_id = tc["id"]
        tc_name = tc.get("name", f"test_{tc_id}")

        cleaned = _clean_test_code_for_embed(raw_code)

        if not cleaned:
            func_body = f'    goto(page, BASE_URL + "/")\n    pass\n'
        else:
            # 替换 page.goto 为 goto helper
            cleaned = re.sub(
                r'page\.goto\(([^)]+)\)',
                lambda m: f"goto(page, {m.group(1)})",
                cleaned
            )
            # 去掉重复的 wait_for_load_state
            cleaned = re.sub(
                r'^\s*page\.wait_for_load_state\([^)]*\)\s*\n?',
                '',
                cleaned,
                flags=re.MULTILINE
            )
            # 缩进每一行
            indented = "\n".join(
                "    " + line if line.strip() else ""
                for line in cleaned.split("\n")
            )
            func_body = indented + "\n"

        func = f'\ndef test_{tc_id}(page):\n    """{tc_name}"""\n{func_body}\n'
        parts.append(func)

    result = "\n".join(parts)

    # 语法预检
    import ast as _ast
    try:
        _ast.parse(result)
        logger.info(f"测试文件语法检查通过，共 {len(test_cases)} 个用例")
    except SyntaxError as e:
        logger.error(f"生成测试文件语法错误(行{e.lineno}): {e.msg}\n{result[:3000]}")
        raise

    return result


def _clean_test_code_for_embed(code: str) -> str:
    """清理 AI 生成代码，提取函数体内容用于嵌入 fixture 包装函数。"""
    # 去除 markdown fence
    code = re.sub(r'^```(?:python|py)?\s*\n', '', code.strip())
    code = re.sub(r'\n```\s*$', '', code)
    code = code.strip()

    # 仅去除【顶层】import 行（缩进为0的import），保留函数体内部的import
    top_level_cleaned = []
    for line in code.split("\n"):
        stripped = line.strip()
        is_top_import = (
            not line.startswith(" ") and not line.startswith("\t")
            and (stripped.startswith("import ") or stripped.startswith("from "))
        )
        if is_top_import:
            continue
        top_level_cleaned.append(line)
    code = "\n".join(top_level_cleaned).strip()

    # 去除 self. 引用（兼容旧数据库中带 self 的代码）
    code = re.sub(r'\bself\.', '', code)

    # 提取第一个 def test_ 函数体
    func_pattern = re.compile(
        r'^(?:async\s+)?def\s+\w+\s*\([^)]*\)\s*:\s*\n(.*)',
        re.MULTILINE | re.DOTALL
    )
    match = func_pattern.search(code)
    if match:
        body = match.group(1)

        # dedent 消除公共缩进
        body = textwrap.dedent(body)

        # 去掉首行 docstring（单行或多行）
        body = body.lstrip("\n")
        body = re.sub(r'^[ \t]*""".*?"""\s*\n?', '', body, flags=re.DOTALL)
        body = re.sub(r"^[ \t]*'''.*?'''\s*\n?", '', body, flags=re.DOTALL)
        body = body.strip()

        # 修正缩进：标准化为4空格单位，但保留相对层级
        body = _fix_indentation(body)
        return body

    # 没有函数定义：直接返回裸逻辑，dedent + 修正缩进
    code = textwrap.dedent(code).strip()
    return _fix_indentation(code)


def _fix_indentation(code: str) -> str:
    """将代码缩进标准化为4空格单位，保留相对层级结构。"""
    lines = code.split('\n')
    if not lines:
        return code

    # 找出最小非零缩进作为基准单位
    indent_sizes = set()
    for line in lines:
        stripped = line.lstrip(' ')
        if stripped and not stripped.startswith('#'):
            indent = len(line) - len(stripped)
            if indent > 0:
                indent_sizes.add(indent)

    # 基准缩进单位：取最小值，若异常则默认4
    base_unit = min(indent_sizes) if indent_sizes else 4
    if base_unit < 1:
        base_unit = 4

    result = []
    for line in lines:
        if not line.strip():
            result.append('')
            continue
        stripped = line.lstrip(' ')
        raw_indent = len(line) - len(stripped)
        # 计算层级（四舍五入避免轻微偏差）
        level = round(raw_indent / base_unit)
        result.append('    ' * level + stripped)

    return '\n'.join(result)


def _build_single_test_file(test_code: str, test_name: str,
                             deploy_url: str, headless: bool) -> str:
    cleaned = _clean_test_code_for_embed(test_code)
    return f'''import pytest
from playwright.sync_api import sync_playwright, expect

DEPLOY_URL = {deploy_url!r}
BASE_URL = DEPLOY_URL
HEADLESS = {headless!r}

@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=HEADLESS, args=["--no-sandbox"])
        yield b
        b.close()

@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={{"width": 1920, "height": 1080}})
    p = context.new_page()
    yield p
    context.close()

def test_retry(page):
    """{test_name}"""
    page.goto(DEPLOY_URL)
{_indent_code(cleaned, 4)}
'''


def _indent_code(code: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line for line in code.strip().split("\n"))


def parse_pytest_json(report_file: str, test_cases: list) -> list:
    try:
        with open(report_file, 'r', encoding='utf-8') as f:
            report = json_lib.load(f)
    except (FileNotFoundError, json_lib.JSONDecodeError):
        return [
            {
                "test_case_id": tc["id"],
                "name": tc.get("name", "unknown"),
                "status": "error",
                "duration": 0,
                "error_message": "无法读取测试报告文件",
            }
            for tc in test_cases
        ]

    tc_map = {}
    for tc in test_cases:
        tc_map[tc.get("name", "")] = tc["id"]
        tc_map[f'test_{tc["id"]}'] = tc["id"]

    results = []
    for test in report.get("tests", []):
        nodeid = test.get("nodeid", "")
        outcome = test.get("outcome", "error")
        status_map = {"passed": "passed", "failed": "failed", "error": "error", "skipped": "skipped"}
        status = status_map.get(outcome, "error")

        tc_id = None
        nodeid_lower = nodeid.lower()
        for key, tid in tc_map.items():
            if key.lower() in nodeid_lower:
                tc_id = tid
                break
        if tc_id is None:
            tc_id = test_cases[0]["id"] if test_cases else 0

        error_msg = ""
        error_tb = ""
        call_data = test.get("call", {}) or {}
        if call_data.get("longrepr"):
            error_msg = str(call_data["longrepr"])[:500]
        if call_data.get("traceback"):
            error_tb = "\n".join(str(t) for t in call_data["traceback"])

        results.append({
            "test_case_id": tc_id,
            "name": nodeid.split("::")[-1] if "::" in nodeid else nodeid,
            "status": status,
            "duration": test.get("duration", 0),
            "error_message": error_msg,
            "error_traceback": error_tb,
            "screenshot_path": "",
            "log_text": "",
        })

    return results


def _write_timeout_report(report_file: str, timeout_seconds: int):
    report = {
        "created": datetime.now(timezone.utc).isoformat(),
        "exitcode": -1,
        "tests": [{
            "nodeid": "test_suite.py::test_timeout",
            "outcome": "error",
            "duration": timeout_seconds,
            "call": {
                "longrepr": f"测试执行超时 ({timeout_seconds}s)，子进程已被强制终止",
            }
        }]
    }
    with open(report_file, 'w', encoding='utf-8') as f:
        json_lib.dump(report, f)


# 兼容旧引用
_active_runners: dict = {}