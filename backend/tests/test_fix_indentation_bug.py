"""Test: AI-generated code extracted from inside a class without class header.
This reproduces the exact scenario reported in the bug — _parse_test_code splits
on def lines and the extracted code retains class-level indentation."""
import pytest
import ast
from backend.security.code_validator import CodeValidator, validate_test_code

validator = CodeValidator()


def test_sanitize_dedents_class_method_without_class_header():
    """Simulate code extracted from inside a class (no class line)."""
    code = (
        '    async def test_connection(self, config_name: str):\n'
        '        """测试指定配置的连接"""\n'
        '        self.page.goto("/login")\n'
        '        self.page.fill("#username", "admin")\n'
        '        self.page.fill("#password", "****")\n'
        '        self.page.click("#login-btn")\n'
        '        assert self.page.locator(".welcome").is_visible()\n'
    )
    cleaned = validator._sanitize_code(code)
    # Verify it parses as valid Python
    tree = ast.parse(cleaned)
    assert tree is not None
    # Verify the function def is at module level (0 indent)
    first_line = cleaned.lstrip('\n').split('\n')[0]
    assert not first_line.startswith(' '), f"Function def should not be indented, got: {repr(first_line)}"
    # Verify body is properly indented (4 spaces)
    lines = cleaned.split('\n')
    body_line = lines[1]
    assert body_line.startswith('    '), f"Body should be indented with 4 spaces, got: {repr(body_line)}"
    # Verify no 'self.' references remain
    assert 'self.' not in cleaned, f"self. references should be stripped"


def test_validate_passes_for_class_method_without_class_header():
    """Full validation must pass for code extracted from inside a class."""
    code = (
        '    async def test_connection(self, config_name: str):\n'
        '        """测试指定配置的连接"""\n'
        '        page = self.page\n'
        '        page.goto("/login")\n'
        '        assert page.locator("h1").is_visible()\n'
    )
    valid, error = validate_test_code(code)
    assert valid, f"Validation should pass, got error: {error}"


def test_validate_passes_for_normally_indented_code():
    """Regular code at column 0 should still pass."""
    code = (
        'async def test_login(page):\n'
        '    """测试登录"""\n'
        '    page.goto("/login")\n'
        '    page.fill("#username", "admin")\n'
        '    assert page.locator(".welcome").is_visible()\n'
    )
    valid, error = validate_test_code(code)
    assert valid, f"Validation should pass, got error: {error}"


def test_validate_passes_for_class_wrapped_code():
    """Code with a class wrapper should still be handled correctly."""
    code = (
        'class TestLogin:\n'
        '    async def test_connection(self, config_name: str):\n'
        '        """测试指定配置的连接"""\n'
        '        self.page.goto("/login")\n'
        '        self.page.fill("#username", "admin")\n'
        '        self.page.click("#login-btn")\n'
        '        assert self.page.locator(".welcome").is_visible()\n'
        '\n'
        '    async def test_logout(self, page):\n'
        '        """测试指定配置的连接"""\n'
        '        page.click(".logout")\n'
        '        assert page.locator("#login-btn").is_visible()\n'
    )
    valid, error = validate_test_code(code)
    assert valid, f"Validation should pass, got error: {error}"


def test_validate_fails_for_invalid_syntax():
    """Genuinely broken code must still fail."""
    code = (
        'async def test_broken(self):\n'
        'print("this is not indented")\n'
    )
    valid, error = validate_test_code(code)
    assert not valid, "Broken code should fail validation"


def test_sanitize_dedent_twice_nested():
    """Code with 8-space def indent (double-nested) should be dedented."""
    code = (
        '        async def test_deeply_nested(self):\n'
        '            """Deep nesting"""\n'
        '            self.page.goto("/")\n'
    )
    cleaned = validator._sanitize_code(code)
    tree = ast.parse(cleaned)
    assert tree is not None
    # Verify the def is at column 0
    first_line = cleaned.lstrip('\n').split('\n')[0]
    assert not first_line.startswith(' '), f"Def should start at column 0, got: {repr(first_line)}"
    # Verify body is indented
    lines = [l for l in cleaned.split('\n') if l.strip()]
    assert len(lines) >= 3
    assert lines[1].startswith('    '), f"Body line 1 should be indented: {repr(lines[1])}"
