"""工具白名单管理 - 控制哪些操作可以被测试脚本执行"""
import re
from typing import List, Set
from datetime import datetime
from loguru import logger


class ToolWhitelist:
    """工具白名单管理器"""

    # 默认允许的操作
    DEFAULT_ALLOWED = {
        # 页面导航与读取
        "page.goto", "page.reload", "page.go_back", "page.go_forward",
        "page.title", "page.url", "page.content", "page.text_content",
        "page.inner_text", "page.inner_html", "page.get_attribute",
        "page.screenshot", "page.pdf",
        "page.query_selector", "page.query_selector_all",
        "page.wait_for_selector", "page.wait_for_load_state",
        "page.wait_for_url", "page.wait_for_timeout",
        "page.is_visible", "page.is_hidden", "page.is_enabled",
        "page.is_disabled", "page.is_checked",

        # 元素操作（安全）
        "locator.click", "locator.dblclick", "locator.hover",
        "locator.focus", "locator.tab_index",
        "locator.text_content", "locator.inner_text",
        "locator.get_attribute", "locator.is_visible",
        "locator.is_hidden", "locator.is_enabled",
        "locator.is_disabled", "locator.is_checked",
        "locator.count", "locator.all_text_contents",
        "locator.all_inner_texts",
        "locator.input_value", "locator.press",

        # 键盘
        "page.keyboard", "keyboard.press", "keyboard.type",
        "keyboard.insert_text",

        # 截图
        "page.screenshot",

        # 断言
        "expect", "assert",
    }

    # 默认禁止的操作
    DEFAULT_BLOCKED = {
        # 危险的页面操作
        "page.evaluate", "page.eval_on_selector",
        "page.evaluate_handle", "page.add_init_script",
        "page.set_content", "page.set_input_files",
        "page.dispatch_event", "page.add_script_tag",
        "page.add_style_tag",

        # 网络
        "page.route", "page.unroute",
        "context.route", "context.unroute",
        "page.set_extra_http_headers",

        # 文件
        "page.set_input_files",
        "locator.set_input_files",
        "locator.upload_file",

        # 下载
        "page.expect_download",
        "page.expect_file_chooser",
        "context.expect_event",
    }

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.allowed: Set[str] = set(self.DEFAULT_ALLOWED)
        self.blocked: Set[str] = set(self.DEFAULT_BLOCKED)

    def check(self, tool_name: str, detail: str = "") -> bool:
        """
        检查工具是否在白名单中

        Args:
            tool_name: 工具/操作名称
            detail: 操作详情

        Returns:
            bool: 是否允许
        """
        if not self.enabled:
            return True

        # 检查是否在禁止列表
        for blocked in self.blocked:
            if tool_name.startswith(blocked):
                self._log("tool_access", tool_name, "blocked", f"禁止的操作: {detail}")
                return False

        # 检查是否在允许列表
        for allowed in self.allowed:
            if tool_name.startswith(allowed):
                return True

        # 未明确允许的操作，默认禁止
        self._log("tool_access", tool_name, "blocked", f"未授权的操作: {detail}")
        return False

    def add_allowed(self, tool_name: str):
        """添加允许的操作"""
        self.allowed.add(tool_name)
        if tool_name in self.blocked:
            self.blocked.remove(tool_name)

    def add_blocked(self, tool_name: str):
        """添加禁止的操作"""
        self.blocked.add(tool_name)
        if tool_name in self.allowed:
            self.allowed.remove(tool_name)

    def get_allowed_list(self) -> List[str]:
        """获取允许的操作列表"""
        return sorted(self.allowed)

    def get_blocked_list(self) -> List[str]:
        """获取禁止的操作列表"""
        return sorted(self.blocked)

    def _log(self, event_type: str, target: str, result: str, detail: str):
        """记录安全日志"""
        from backend.database import SessionLocal, SecurityLog
        try:
            db = SessionLocal()
            log = SecurityLog(
                event_type=event_type,
                target=target[:500],
                action="whitelist_check",
                result=result,
                detail=detail[:1000],
            )
            db.add(log)
            db.commit()
        except Exception as e:
            logger.warning(f"记录安全日志失败: {e}")
        finally:
            db.close()
