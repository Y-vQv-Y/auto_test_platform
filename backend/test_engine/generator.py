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
    """测试用例生成器"""

    def __init__(self, ai_config: dict, template_override: str = None):
        """
        Args:
            ai_config: AI 配置字典，包含 provider, api_key, model 等
            template_override: 可选的数据库 Prompt 模板（覆盖硬编码 prompt）
        """
        self.ai_config = ai_config
        self.template_override = template_override
        self.provider: Optional[AIProvider] = AIFactory.create_provider(ai_config, template_override)

        # 根据 AI 模型最大 tokens 动态计算源代码截断上限
        model_max_tokens = ai_config.get("max_tokens", 4096)
        # 每个 token 约对应 4 个字符，预留一半给对话和代码生成
        self.max_source_chars = min(model_max_tokens * 60, 2_000_000)
        self.max_source_chars = max(self.max_source_chars, 300_000)  # 保底 30 万


    # 新增方法到 TestGenerator 类
    async def _discover_routes(self, deploy_url: str) -> str:
        """爬取部署URL，提取页面路由和页面结构信息供AI参考"""
        if not deploy_url:
            return ""
        
        routes_info = []
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                # 获取首页HTML
                resp = await client.get(deploy_url)
                html = resp.text
                
                # 提取所有 href 路由（SPA路由）
                import re
                hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
                spa_routes = [h for h in hrefs if h.startswith('/') and not h.startswith('//')]
                spa_routes = list(dict.fromkeys(spa_routes))  # 去重保序
                
                # 提取页面title
                title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
                title = title_match.group(1) if title_match else ""
                
                routes_info.append(f"站点标题: {title}")
                routes_info.append(f"发现的路由: {spa_routes}")
                
                # 尝试获取 React Router 路由（从JS bundle中提取path）
                js_links = re.findall(r'src=["\']([^"\']+\.js)["\']', html)
                for js_url in js_links[:3]:  # 只取前3个JS文件
                    try:
                        full_js_url = js_url if js_url.startswith('http') else urljoin(deploy_url, js_url)
                        js_resp = await client.get(full_js_url, timeout=5.0)
                        js_content = js_resp.text[:50000]  # 只取前50K
                        # 提取 path: "/xxx" 或 to="/xxx" 模式
                        paths = re.findall(r'(?:path|to)[=:]["\s]*["\']([/][^"\'?\s]{1,50})["\']', js_content)
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
    # 修改 generate_test_cases 方法，在调用AI前注入路由信息
    async def generate_test_cases(self, project_id: int, source_path: str,
                                  test_type: str = "功能测试",
                                  additional_context: str = "") -> List[dict]:
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
    
        enforced_context = f"""{additional_context}
    
【动态发现的页面路由信息】
{route_info if route_info else "未能自动发现路由，请根据源代码分析页面路由"}

【强制要求】
- 生成exactly 8个独立的pytest测试函数
- 导航使用 goto(page, BASE_URL + "/路径")
- 根据上方发现的真实路由生成测试，不要假设路由
- 每个函数覆盖不同功能点
"""

    logger.info(f"开始生成测试用例，项目ID: {project_id}, 类型: {test_type}")
    raw_response = await self.provider.generate_test_cases(
        code_content, test_type, enforced_context
    )

    test_cases = self._parse_test_code(raw_response, test_type)
    # ... 后续保存逻辑不变

    async def analyze_project_source(self, source_path: str) -> str:
        """
        分析项目源代码结构
        """
        if not self.provider:
            raise ValueError("AI 提供商未配置")

        code_content = self._collect_source_code(source_path)
        analysis = await self.provider.analyze_code(code_content)
        return analysis

    async def generate_test_cases(self, project_id: int, source_path: str,
                                  test_type: str = "功能测试",
                                  additional_context: str = "") -> List[dict]:
        """
        根据源代码生成测试用例

        Returns:
            [{"name": "...", "description": "...", "code": "...", ...}]
        """
        if not self.provider:
            raise ValueError("AI 提供商未配置")

        code_content = self._collect_source_code(source_path)
        if not code_content.strip():
            raise ValueError("源代码为空，请检查源代码路径")

        logger.info(f"开始生成测试用例，项目ID: {project_id}, 类型: {test_type}")
        raw_response = await self.provider.generate_test_cases(
            code_content, test_type, additional_context
        )

        # 解析 AI 返回的测试代码
        test_cases = self._parse_test_code(raw_response, test_type)

        # 保存到数据库
        db = SessionLocal()
        try:
            saved_cases = []
            for tc in test_cases:
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
                })
            logger.info(f"成功生成 {len(saved_cases)} 个测试用例")
            return saved_cases
        finally:
            db.close()

    def _collect_source_code(self, source_path: str) -> str:
        """
        收集源代码，支持文件和目录
        """
        if not os.path.exists(source_path):
            logger.warning(f"源代码路径不存在: {source_path}")
            return ""

        code_parts = []
        if os.path.isfile(source_path):
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                code_parts.append(f"=== {os.path.basename(source_path)} ===\n{f.read()}")
        elif os.path.isdir(source_path):
            for root, dirs, files in os.walk(source_path):
                # 跳过 node_modules, .git, __pycache__ 等
                dirs[:] = [d for d in dirs if not d.startswith((".", "node_modules", "__pycache__", "venv", "dist", "build"))]
                for file in sorted(files):
                    if file.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".java", ".go", ".html", ".css")):
                        fpath = os.path.join(root, file)
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                                rel_path = os.path.relpath(fpath, source_path)
                                code_parts.append(f"=== {rel_path} ===\n{f.read()}")
                        except Exception:
                            pass

        result = "\n\n".join(code_parts)
        # 根据 AI 模型能力动态限制长度（默认 30 万字符）
        max_chars = self.max_source_chars
        if len(result) > max_chars:
            logger.warning(f"源代码过长({len(result)}字符)，截断至{max_chars}字符")
            result = result[:max_chars] + "\n\n# ... [代码截断]"
        else:
            logger.info(f"源代码长度: {len(result)}字符 (上限: {max_chars})")
        return result

    def _parse_test_code(self, raw: str, test_type: str) -> List[dict]:
        """
        解析 AI 返回的测试代码，分割成多个测试用例
        """
        test_cases = []

        # 尝试按测试函数分割
        pattern = r'(async\s+)?def\s+(test_\w+)\s*\('
        matches = list(re.finditer(pattern, raw))

        if len(matches) > 1:
            for i, match in enumerate(matches):
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
                fn_code = raw[start:end].strip()

                # 提取函数注释作为描述
                desc_pattern = r'"""(.*?)"""'
                desc_match = re.search(desc_pattern, fn_code, re.DOTALL)
                description = desc_match.group(1).strip() if desc_match else ""

                # Validate against raw code first
                valid, error = validate_test_code(fn_code)
                if not valid:
                    raise ValueError(f"AI 生成的测试代码验证失败 [{match.group(2)}]: {error}")
                # Store the sanitized version (dedented, self stripped, normalized)
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
            # 如果无法分割，整体作为一个测试用例
            name_match = re.search(r'(?:class\s+(\w+)|def\s+(test_\w+))', raw)
            name = name_match.group(1) or name_match.group(2) if name_match else f"test_{test_type}"
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
