"""AI 生成代码安全校验器 — 在保存到数据库前验证代码语法和安全性"""
import ast
import re
from loguru import logger


class CodeValidator:
    """AI-generated code validator — AST syntax check + refusal detection + dangerous pattern detection"""

    # Refusal patterns (case-insensitive regex)
    REFUSAL_PATTERNS = [
        r"I (cannot|can't|am unable to|am not able to) (generate|create|write|produce|provide)",
        r"I (don't|do not) feel comfortable",
        r"I apologize.*(cannot|can't|unable)",
        r"(against|violates) my (guidelines|policy|ethical)",
        r"(cannot|can't|unable to) (generate|create|provide) (test|code)",
        r"instead.*(I|you|we) (suggest|recommend)",
    ]

    # Dangerous import modules
    DANGEROUS_IMPORTS = {"subprocess", "shutil", "socket", "ctypes"}

    # Dangerous builtin function names (checked via ast.Call)
    DANGEROUS_BUILTINS = {"eval", "exec", "compile", "__import__"}

    # Dangerous os sub-functions
    DANGEROUS_OS_CALLS = {"os.system", "os.popen"}

    MIN_CODE_LENGTH = 30

    def validate_syntax(self, code: str) -> tuple:
        """Check if code is valid Python syntax. Returns (is_valid: bool, error: str)."""
        try:
            cleaned = self._sanitize_code(code)
            ast.parse(cleaned)
            return True, ""
        except IndentationError as e:
            return False, f"Python 缩进错误 (行 {e.lineno}): {e.msg}。请检查代码缩进是否一致（使用4个空格，不要混用Tab）"
        except SyntaxError as e:
            return False, f"Python 语法错误 (行 {e.lineno}): {e.msg}"

    def detect_refusal(self, code: str) -> tuple:
        """Check if AI response contains refusal language. Returns (is_clean: bool, error: str)."""
        for pattern in self.REFUSAL_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                logger.warning(f"检测到 AI 拒绝生成: 匹配模式 '{pattern}'")
                return False, "AI 响应包含拒绝生成代码的内容（检测到 AI 安全拒绝）"
        return True, ""

    def detect_dangerous_patterns(self, code: str) -> tuple:
        """AST-walk to detect dangerous imports, builtin calls, and os sub-functions.
        Returns (is_clean: bool, error: str)."""
        try:
            cleaned = self._sanitize_code(code)
            tree = ast.parse(cleaned)
        except SyntaxError:
            return True, ""  # Already caught by validate_syntax, don't double-report

        found = []

        for node in ast.walk(tree):
            # Dangerous imports: import subprocess, import shutil, etc.
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in self.DANGEROUS_IMPORTS:
                        found.append(f"import {alias.name}")

            # Dangerous from-imports: from subprocess import ...
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in self.DANGEROUS_IMPORTS:
                    names = [a.name for a in node.names] if node.names else ["*"]
                    found.append(f"from {node.module} import {', '.join(names)}")

            # Dangerous builtins: eval(), exec(), compile(), __import__()
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in self.DANGEROUS_BUILTINS:
                    found.append(node.func.id)

                # Dangerous os usage: os.system(), os.popen()
                elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    full_name = f"{node.func.value.id}.{node.func.attr}"
                    if full_name in self.DANGEROUS_OS_CALLS:
                        found.append(full_name)

        if found:
            return False, f"检测到危险代码模式: {', '.join(sorted(set(found)))}"
        return True, ""

    def validate(self, code: str) -> tuple:
        """Full validation pipeline. Returns (is_valid: bool, error: str)."""
        if not code or not code.strip():
            return False, "代码为空"

        if len(code.strip()) < self.MIN_CODE_LENGTH:
            return False, f"生成的代码过短（少于{self.MIN_CODE_LENGTH}字符），可能无效"

        valid, error = self.validate_syntax(code)
        if not valid:
            logger.warning(f"代码语法验证失败: {error} [代码片段: {code.strip()[:100]}]")
            return False, error

        valid, error = self.detect_refusal(code)
        if not valid:
            logger.warning(f"代码拒绝检测失败: {error}")
            return False, error

        valid, error = self.detect_dangerous_patterns(code)
        if not valid:
            logger.warning(f"代码危险模式检测失败: {error}")
            return False, error

        logger.debug("代码验证通过")
        return True, ""

    @staticmethod
    def _normalize_indentation(code: str) -> str:
        lines = code.split('\n')
        indent_counts: dict[int, int] = {}
        for line in lines:
            stripped = line.lstrip(' ')
            if not stripped:
                continue
            # Skip function/class definition lines themselves
            if re.match(r'^(async\s+def|def|class)\s', stripped):
                continue
            indent = len(line) - len(stripped)
            if indent > 0:
                indent_counts[indent] = indent_counts.get(indent, 0) + 1

        if not indent_counts:
            return code

        # Use the most common body indentation level as the reference.
        # After _sanitize_code's dedent step, function defs are at column 0
        # and body lines are at consistent, valid indentation levels.
        # Mapping body_indent to one level of 4-space indentation gives
        # correct results for well-formed code without introducing orphan
        # blocks that GCD-based approaches can trigger on outlier lines.
        body_indent = max(indent_counts, key=indent_counts.get)
        if body_indent < 2:
            body_indent = 4

        target_unit = 4
        out: list[str] = []
        for line in lines:
            stripped = line.lstrip(' ')
            if not stripped:
                out.append('')
                continue
            indent = len(line) - len(stripped)
            if indent == 0:
                out.append(stripped)
            else:
                level = max(1, round(indent / body_indent))
                out.append(' ' * (level * target_unit) + stripped)
        return '\n'.join(out)

    @staticmethod
    def _sanitize_code(code: str) -> str:
        """Remove markdown fences, self params, and normalize AI-generated code."""
        cleaned = code.strip()
        # Normalize tabs to 4 spaces
        cleaned = cleaned.expandtabs(4)
        # Remove opening fence
        cleaned = re.sub(r'^```(?:python|py|javascript|js|typescript|ts)?\s*\n', '', cleaned)
        # Remove closing fence
        cleaned = re.sub(r'\n```\s*$', '', cleaned)

        # Strip class wrappers FIRST, before any other processing
        class_pattern = re.compile(r'^class\s+\w+.*?:\s*\n', re.MULTILINE)
        while True:
            class_match = class_pattern.search(cleaned)
            if not class_match:
                break
            cleaned = cleaned.replace(class_match.group(), '', 1)
            # Find indentation of the first non-empty line after class removal
            method_indent = 0
            for line in cleaned.split('\n'):
                stripped = line.lstrip(' ')
                if stripped:
                    method_indent = len(line) - len(stripped)
                    break
            if method_indent > 0:
                lines = cleaned.split('\n')
                new_lines = []
                for line in lines:
                    if line.strip():
                        leading = len(line) - len(line.lstrip(' '))
                        remove = min(leading, method_indent)
                        new_lines.append(line[remove:])
                    else:
                        new_lines.append(line)
                cleaned = '\n'.join(new_lines)

        # If no class wrapper was found, the code may have been extracted
        # from inside a class by _parse_test_code (which splits on def
        # lines and excludes the class header). In that case the function
        # definition and its body retain the class-level indentation,
        # causing indentation errors after normalization. Detect and
        # dedent by the def line's indent.
        if not re.search(r'^class\s+\w+', cleaned, re.MULTILINE):
            lines = cleaned.split('\n')
            def_indent = 0
            for line in lines:
                stripped = line.lstrip()
                if stripped and re.match(r'^(async\s+)?(def|class)\s', stripped):
                    def_indent = len(line) - len(stripped)
                    break
            if def_indent > 0:
                dedented = []
                for line in lines:
                    if line.strip():
                        leading = len(line) - len(line.lstrip(' '))
                        remove = min(leading, def_indent)
                        dedented.append(line[remove:])
                    else:
                        dedented.append(line)
                cleaned = '\n'.join(dedented)

        # Strip 'self' parameter from function signatures AFTER class unwrapping
        def strip_self_in_sig(m):
            before = m.group(1)
            params = m.group(2)
            params = re.sub(r'\bself\s*,\s*', '', params)
            params = re.sub(r',\s*\bself\b', '', params)
            params = re.sub(r'\bself\b', '', params)
            params = params.strip()
            return f'{before}{params})'
        cleaned = re.sub(
            r'((?:async\s+)?def\s+\w+\s*\()([^)]*)\)',
            strip_self_in_sig,
            cleaned
        )

        # Strip 'self.' from attribute access
        cleaned = re.sub(r'\bself\.', '', cleaned)

        # Re-indent to consistent 4-space increments LAST
        cleaned = cleaned.expandtabs(4)
        cleaned = CodeValidator._normalize_indentation(cleaned)

        return cleaned


def validate_test_code(code: str) -> tuple:
    """Convenience function: validate a single AI-generated test code string.
    Returns (is_valid: bool, error: str)."""
    validator = CodeValidator()
    return validator.validate(code)


def sanitize_test_code(code: str) -> str:
    """Sanitize and normalize AI-generated test code for storage/execution.
    Applies all cleaning steps: dedent, strip self, normalize indentation.
    This is the same transform that validate_syntax uses internally, exposed
    so callers can persist the cleaned version rather than the raw AI output."""
    validator = CodeValidator()
    return validator._sanitize_code(code)