"""Unit tests for code_validator — indentation normalization and syntax validation."""
import pytest
from backend.security.code_validator import CodeValidator, validate_test_code


class TestNormalizeIndentation:
    def test_basic_function(self):
        code = "async def test_foo(page):\n    pass\n"
        validator = CodeValidator()
        valid, err = validator.validate(code)
        assert valid, f"Basic function should pass: {err}"

    def test_class_wrapped_code(self):
        code = (
            "class TestFoo:\n"
            "    async def test_bar(self, page: Page):\n"
            '        """Docstring"""\n'
            "        page.goto('/')\n"
            "        assert page.locator('h1').is_visible()\n"
        )
        valid, err = validate_test_code(code)
        assert valid, f"Class-wrapped code should pass: {err}"

    def test_mixed_2_space_indent(self):
        code = (
            "async def test_baz(page: Page):\n"
            '  """Docstring"""\n'
            "  page.goto('/login')\n"
            "  page.locator('button').click()\n"
        )
        valid, err = validate_test_code(code)
        assert valid, f"2-space indent should pass: {err}"

    def test_tab_indentation(self):
        code = (
            "async def test_tabs(page: Page):\n"
            '\t"""Docstring"""\n'
            '\tpage.goto("/")\n'
            '\tassert page.locator("h1").is_visible()\n'
        )
        valid, err = validate_test_code(code)
        assert valid, f"Tab indent should pass: {err}"

    def test_multi_method_class(self):
        code = (
            "class TestSuite:\n"
            "    async def test_a(self, page: Page):\n"
            '        """Test A"""\n'
            "        page.goto('/a')\n"
            "        assert page.locator('h1').is_visible()\n"
            "\n"
            "    async def test_b(self, page: Page):\n"
            '        """Test B"""\n'
            "        page.goto('/b')\n"
            "        assert page.locator('h2').is_visible()\n"
        )
        valid, err = validate_test_code(code)
        assert valid, f"Multi-method class should pass: {err}"

    def test_double_indented_body(self):
        code = (
            "async def test_double(page: Page):\n"
            "        page.goto('/')\n"
            "        assert True\n"
        )
        valid, err = validate_test_code(code)
        assert valid, f"Double-indented body should pass: {err}"


class TestSanitizeCode:
    def test_class_stripped(self):
        code = (
            "class TestFoo:\n"
            "    async def test_bar(self, page: Page):\n"
            '        """Doc"""\n'
            "        pass\n"
        )
        result = CodeValidator._sanitize_code(code)
        assert "class TestFoo" not in result
        assert "self" not in result
        assert "async def test_bar(page: Page):" in result
        assert "    pass" in result

    def test_self_stripped_from_signature(self):
        code = "async def test_x(self, page: Page, fixture):\n    pass\n"
        result = CodeValidator._sanitize_code(code)
        assert "self" not in result
        assert "async def test_x(page: Page, fixture):" in result

    def test_self_attribute_stripped(self):
        code = "self.page.goto('/')\nself.driver.quit()\n"
        result = CodeValidator._sanitize_code(code)
        assert "self." not in result
        assert "page.goto('/')" in result
        assert "driver.quit()" in result


class TestEdgeCases:
    def test_empty_code(self):
        valid, err = validate_test_code("")
        assert not valid

    def test_too_short_code(self):
        valid, err = validate_test_code("x = 1")
        assert not valid
        assert "过短" in err

    def test_dangerous_builtin(self):
        code = "async def test_eval(page: Page):\n    eval('print(1)')\n"
        valid, err = validate_test_code(code)
        assert not valid
        assert "eval" in err
