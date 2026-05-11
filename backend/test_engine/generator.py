"""AI 测试用例生成器 - 分析源代码并生成 Playwright + pytest 测试代码"""
import os
import re
import ast
import json
import httpx
from typing import List, Optional
from loguru import logger
from urllib.parse import urljoin

from backend.ai_engine import AIFactory, AIProvider
from backend.database import SessionLocal, TestCase, Project
from backend.security.code_validator import validate_test_code, sanitize_test_code


class TestGenerator:

    def __init__(self, ai_config: dict, template_override: str = None):
        self.ai_config = ai_config
        self.template_override = template_override
        self.provider: Optional[AIProvider] = AIFactory.create_provider(ai_config, template_override)

        model_max_tokens = ai_config.get("max_tokens", 4096)
        self.max_source_chars = min(model_max_tokens * 60, 2_000_000)
        self.max_source_chars = max(self.max_source_chars, 300_000)

    async def _discover_routes(self, deploy_url: str) -> str:
        """爬取部署URL，提取页面路由信息供AI参考"""
        if not deploy_url:
            return ""

        routes_info = []
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(deploy_url)
                html = resp.text

                # 提取 href 路由
                hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
                spa_routes = [h for h in hrefs if h.startswith('/') and not h.startswith('//')]
                spa_routes = list(dict.fromkeys(spa_routes))

                # 提取页面 title
                title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
                title = title_match.group(1) if title_match else ""

                routes_info.append(f"站点标题: {title}")
                routes_info.append(f"HTML中发现的路由: {spa_routes}")

                # 从 JS bundle 提取路由
                js_links = re.findall(r'src=["\']([^"\']+\.js)["\']', html)
                for js_url in js_links[:3]:
                    try:
                        full_js_url = js_url if js_url.startswith('http') else urljoin(deploy_url, js_url)
                        js_resp = await client.get(full_js_url, timeout=5.0)
                        js_content = js_resp.text[:50000]
                        paths = re.findall(
                            r'(?:path|to)[=:]["\s]*["\']([/][^"\'?\s]{1,50})["\']',
                            js_content
                        )
                        paths = [p for p in paths if len(p) > 1 and not p.endswith('.')]
                        if paths:
                            routes_info.append(f"JS中发现路由: {list(dict.fromkeys(paths))[:20]}")
                        break
                    except Exception:
                        continue

        except Exception as e:
            logger.warning(f"路由发现失败: {e}")
            return ""

        return "\n".join(routes_info)

    async def analyze_project_source(self, source_path: str) -> str:
        """分析项目源代码结构"""
        if not self.provider:
            raise ValueError("AI 提供商未配置")
        code_content = self._collect_source_code(source_path)
        analysis = await self.provider.analyze_code(code_content)
        return analysis

    async def generate_test_cases(self, project_id: int, source_path: str,
                                  test_type: str = "功能测试",
                                  additional_context: str = "") -> List[dict]:
        """根据源代码生成测试用例"""
        if not self.provider:
            raise ValueError("AI 提供商未配置")

        code_content = self._collect_source_code(source_path)
        if not code_content.strip():
            raise ValueError("源代码为空，请检查源代码路径")

        # 获取项目部署URL
        db = SessionLocal()
        deploy_url = ""
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            deploy_url = project.deploy_url if project else ""
        finally:
            db.close()

        # 动态发现路由
        route_info = ""
        if deploy_url:
            logger.info(f"开始发现路由: {deploy_url}")
            route_info = await self._discover_routes(deploy_url)
            if route_info:
                logger.info(f"路由发现结果:\n{route_info}")

        enforced_context = (
            f"{additional_context}\n\n"
            f"【动态发现的页面路由信息】\n"
            f"{route_info if route_info else '未能自动发现路由，请根据源代码分析页面路由'}\n\n"
            f"【强制要求】\n"
            f"- 生成exactly 8个独立的pytest测试函数\n"
            f"- 导航使用 goto(page, BASE_URL + \"/路径\")\n"
            f"- 根据上方发现的真实路由生成测试，不要假设路由\n"
            f"- 每个函数覆盖不同功能点\n"
        )

        logger.info(f"开始生成测试用例，项目ID: {project_id}, 类型: {test_type}")
        raw_response = await self.provider.generate_test_cases(
            code_content, test_type, enforced_context
        )

        # 解析 AI 返回的测试代码
        test_cases = self._parse_test_code(raw_response, test_type)

        # 保存到数据库（同名用例替换）
        db = SessionLocal()
        try:
            saved_cases = []
            for tc in test_cases:
                existing = db.query(TestCase).filter(
                    TestCase.project_id == project_id,
                    TestCase.name == tc["name"],
                ).first()

                if existing:
                    existing.description = tc.get("description", "")
                    existing.code = tc.get("code", raw_response)
                    existing.category = test_type
                    existing.priority = tc.get("priority", "medium")
                    existing.tags = tc.get("tags", [])
                    existing.source = "ai_generated"
                    db.commit()
                    db.refresh(existing)
                    saved_cases.append({
                        "id": existing.id,
                        "name": existing.name,
                        "description": existing.description,
                        "priority": existing.priority,
                        "replaced": True,
                    })
                    logger.info(f"替换已有测试用例: {existing.name}")
                else:
                    test_case = TestCase(
                        project_id=project_id,
                        name=tc["name"],
                        description=tc.get("description", ""),
                        code=tc.get("code", raw_response),
                        category=test_type,
                        priority=tc.get("priority", "medium"),
                        source="ai_generated",
                        tags=tc.get("tags", []),
                    )
                    db.add(test_case)
                    db.commit()
                    db.refresh(test_case)
                    saved_cases.append({
                        "id": test_case.id,
                        "name": test_case.name,
                        "description": test_case.description,
                        "priority": test_case.priority,
                        "replaced": False,
                    })

            logger.info(f"成功生成/更新 {len(saved_cases)} 个测试用例")
            return saved_cases
        finally:
            db.close()

    def _collect_source_code(self, source_path: str) -> str:
        """收集源代码，支持文件和目录"""
        if not os.path.exists(source_path):
            logger.warning(f"源代码路径不存在: {source_path}")
            return ""

        code_parts = []
        if os.path.isfile(source_path):
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                code_parts.append(f"=== {os.path.basename(source_path)} ===\n{f.read()}")
        elif os.path.isdir(source_path):
            for root, dirs, files in os.walk(source_path):
                dirs[:] = [d for d in dirs if not d.startswith(
                    (".", "node_modules", "__pycache__", "venv", "dist", "build")
                )]
                for file in sorted(files):
                    if file.endswith((".py", ".js", ".jsx", ".ts", ".tsx",
                                      ".vue", ".java", ".go", ".html", ".css")):
                        fpath = os.path.join(root, file)
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                                rel_path = os.path.relpath(fpath, source_path)
                                code_parts.append(f"=== {rel_path} ===\n{f.read()}")
                        except Exception:
                            pass

        result = "\n\n".join(code_parts)
        max_chars = self.max_source_chars
        if len(result) > max_chars:
            logger.warning(f"源代码过长({len(result)}字符)，截断至{max_chars}字符")
            result = result[:max_chars] + "\n\n# ... [代码截断]"
        else:
            logger.info(f"源代码长度: {len(result)}字符 (上限: {max_chars})")
        return result

    def _parse_test_code(self, raw: str, test_type: str) -> List[dict]:
        """解析 AI 返回的测试代码，分割成多个测试用例"""
        test_cases = []

        pattern = r'(async\s+)?def\s+(test_\w+)\s*\('
        matches = list(re.finditer(pattern, raw))

        if len(matches) > 1:
            for i, match in enumerate(matches):
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
                fn_code = raw[start:end].strip()

                desc_pattern = r'"""(.*?)"""'
                desc_match = re.search(desc_pattern, fn_code, re.DOTALL)
                description = desc_match.group(1).strip() if desc_match else ""

                valid, error = validate_test_code(fn_code)
                if not valid:
                    raise ValueError(f"AI 生成的测试代码验证失败 [{match.group(2)}]: {error}")

                cleaned_code = sanitize_test_code(fn_code)
                tc = {
                    "name": match.group(2),
                    "description": description or f"{test_type} - {match.group(2)}",
                    "code": cleaned_code,
                    "priority": "high" if "critical" in fn_code.lower() or "核心" in fn_code else "medium",
                    "tags": [test_type],
                }
                test_cases.append(tc)

        if not test_cases:
            name_match = re.search(r'(?:class\s+(\w+)|def\s+(test_\w+))', raw)
            name = (name_match.group(1) or name_match.group(2)) if name_match else f"test_{test_type}"
            valid, error = validate_test_code(raw)
            if not valid:
                raise ValueError(f"AI 生成的测试代码验证失败 [{name}]: {error}")
            cleaned_code = sanitize_test_code(raw)
            tc = {
                "name": name,
                "description": f"{test_type} - 自动生成",
                "code": cleaned_code,
                "priority": "medium",
                "tags": [test_type],
            }
            test_cases.append(tc)

        return test_cases