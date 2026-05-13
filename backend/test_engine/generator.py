"""AI 测试用例生成器 - 分析源代码并生成 Playwright + pytest 测试代码"""
import os
import re
import ast
import json
import httpx
from typing import List, Optional, Dict
from loguru import logger
from urllib.parse import urljoin, urlparse

from backend.ai_engine import AIFactory, AIProvider
from backend.database import SessionLocal, TestCase, Project, LoginRecord
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
                hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
                spa_routes = [h for h in hrefs if h.startswith('/') and not h.startswith('//')]
                spa_routes = list(dict.fromkeys(spa_routes))
                title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
                title = title_match.group(1) if title_match else ""
                routes_info.append(f"站点标题: {title}")
                routes_info.append(f"HTML中发现的路由: {spa_routes}")
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

    async def _deep_scan_pages(self, deploy_url: str, cookies: list = None, storage: dict = None) -> List[Dict]:
        """
        深度扫描所有页面，获取每个页面的元素结构
        cookies: Playwright 格式的 cookie 列表 [{"name":"x","value":"y","domain":"..."}]
        storage: localStorage 键值对 {"key": "value"}
        返回: [{"path": "/xxx", "title": "...", "elements": {...}}]
        """
        if not deploy_url:
            return []

        # 第一步：从 HTML + JS Bundle 分析路由
        all_routes = set()

        # 将 Playwright cookie 格式转为 httpx 格式
        httpx_cookies = {}
        if cookies:
            for c in cookies:
                httpx_cookies[c.get("name", "")] = c.get("value", "")

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, cookies=httpx_cookies) as client:
                resp = await client.get(deploy_url)
                html = resp.text

                # 从HTML提取路由（过滤资源文件）
                hrefs = re.findall(r'href=["\']([^"\'?\#]+)["\']', html)
                for h in hrefs:
                    if (h.startswith('/') and not h.startswith('//')
                            and not re.search(r'\.(js|css|png|jpg|jpeg|svg|ico|woff2?|ttf|eot|map|json|xml|txt)([?#]|$)', h)):
                        all_routes.add(h)

                # 从JS bundle深度提取路由
                js_links = re.findall(r'src=["\']([^"\']+\.js)["\']', html)
                js_links += re.findall(r'href=["\']([^"\']+\.js)["\']', html)
                js_links = list(dict.fromkeys(js_links))

                found_routes = 0
                for js_url in js_links[:10]:
                    if found_routes >= 30:
                        break
                    try:
                        full_js_url = js_url if js_url.startswith('http') else urljoin(deploy_url, js_url)
                        js_resp = await client.get(full_js_url, timeout=10.0)
                        js_content = js_resp.text[:300000]

                        # Vue Router / React Router / 手动 push 等多种模式
                        patterns = [
                            r'path\s*:\s*["\']([/][^"\'?\s*]{1,80})["\']',
                            r"'path'\s*:\s*'([/][^'?\s]{1,80})'",
                            r'router\.(?:push|replace)\s*\(\s*["\']([/][^"\'?\s]{1,80})["\']',
                            r'\$router\.(?:push|replace)\s*\(\s*["\']([/][^"\'?\s]{1,80})["\']',
                            r'navigate\(["\']([/][^"\'?\s]{1,80})["\']',
                            r'\{\s*path\s*:\s*["\']([/][^"\'?\s]{1,80})["\']',
                            r'to\s*=\s*["\']([/][^"\'?\s]{1,80})["\']',
                            r'to\s*:\s*["\']([/][^"\'?\s]{1,80})["\']',
                            r'redirect\s*:\s*["\']([/][^"\'?\s]{1,80})["\']',
                            r'index\s*=\s*["\']([/][^"\'?\s]{1,80})["\']',
                            r'index\s*:\s*["\']([/][^"\'?\s]{1,80})["\']',
                            r'component\s*:\s*\(\)\s*=>\s*import\s*\(\s*["\'](?:\.\.?)?(/[^"\'?\s]{1,80})["\']',
                        ]
                        for pattern in patterns:
                            found = re.findall(pattern, js_content)
                            for p in found:
                                if (len(p) > 1 and p.startswith('/')
                                        and not p.startswith('//')
                                        and not re.search(r'\.(js|css|png|jpg|jpeg|svg|ico|woff2?|ttf|eot|map|json|xml|txt|git|env|lock|md)($|[?#])', p)
                                        and '/' not in p.split('/')[-1]
                                        and not re.search(r'[/\\]node_modules[/\\]', p)
                                        and '*' not in p
                                        and '{' not in p
                                        and ':' not in p
                                        and ' ' not in p):
                                    all_routes.add(p)
                                    found_routes += 1
                    except Exception:
                        continue

        except Exception as e:
            logger.warning(f"深度扫描(httpx)失败: {e}")

        # 确保首页在内
        all_routes.add('/')

        # 过滤资源文件路径
        is_asset = re.compile(r'\.(js|css|png|jpg|jpeg|svg|ico|woff2?|ttf|eot|map|json|xml|txt|git|env|lock|md)($|[?#])')
        all_routes = {
            r for r in all_routes
            if not is_asset.search(r)
            and not r.startswith('/assets/')
            and not r.startswith('/static/')
            and not r.startswith('/node_modules/')
            and not r.startswith('/favicon')
        }

        routes_list = sorted(all_routes)
        logger.info(f"HTML/JS 分析发现 {len(routes_list)} 个路由: {routes_list}")

        # 第二步：用 Playwright 从运行中页面提取真实路由（更可靠）
        if len(routes_list) <= 1:
            logger.info("HTML/JS 分析路由不足，尝试从运行中页面提取...")
            try:
                from playwright.async_api import async_playwright
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(headless=True, args=['--no-sandbox'])
                    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
                    if cookies:
                        await context.add_cookies(cookies)

                    page = await context.new_page()

                    # ★ 先注入 localStorage init_script（页面加载前生效）
                    if storage:
                        await page.add_init_script(f"""
                            () => {{
                                const storage = {json.dumps(storage, ensure_ascii=False)};
                                for (const [k, v] of Object.entries(storage)) {{
                                    try {{ window.localStorage.setItem(k, v); }} catch(e) {{}}
                                }}
                            }}
                        """)

                    await page.goto(deploy_url, wait_until='networkidle', timeout=30000)
                    await page.wait_for_timeout(3000)

                    # 从运行中的 Vue/React 应用提取路由
                    runtime_routes = await page.evaluate("""() => {
                        const routes = new Set();
                        routes.add('/');

                        // 方法1: 从 Vue Router 提取
                        try {
                            const app = document.querySelector('#app');
                            if (app && app.__vue_app__) {
                                const router = app.__vue_app__.config.globalProperties.$router;
                                if (router && router.options && router.options.routes) {
                                    function extractPaths(routeList, prefix) {
                                        for (const r of routeList) {
                                            if (r.path && typeof r.path === 'string' && r.path !== '*' && !r.path.startsWith(':')) {
                                                const fullPath = (prefix + '/' + r.path).replace(/\\/+/g, '/');
                                                routes.add(fullPath);
                                            }
                                            if (r.children) {
                                                const childPrefix = r.path && typeof r.path === 'string'
                                                    ? (prefix + '/' + r.path).replace(/\\/+/g, '/')
                                                    : prefix;
                                                extractPaths(r.children, childPrefix);
                                            }
                                        }
                                    }
                                    extractPaths(router.options.routes, '');
                                }
                                // 也尝试从 $router.getRoutes() 提取
                                if (router && router.getRoutes) {
                                    try {
                                        const allRoutes = router.getRoutes();
                                        allRoutes.forEach(r => {
                                            if (r.path && r.path !== '*' && !r.path.startsWith(':')) {
                                                routes.add(r.path.startsWith('/') ? r.path : '/' + r.path);
                                            }
                                        });
                                    } catch(e2) {}
                                }
                            }
                        } catch(e) {}

                        // 方法2: 从 DOM 链接提取
                        document.querySelectorAll('a[href^="/"]').forEach(a => {
                            const href = a.getAttribute('href');
                            if (href && href.length > 1 && !href.includes('.')) {
                                routes.add(href.split('?')[0].split('#')[0]);
                            }
                        });

                        // 方法3: 从 el-menu（Element UI 菜单）提取
                        document.querySelectorAll(
                            '.el-menu-item, .el-sub-menu, [class*="menu-item"], [class*="nav-item"]'
                        ).forEach(el => {
                            const index = el.getAttribute('index');
                            if (index && index.startsWith('/')) {
                                routes.add(index.split('?')[0]);
                            }
                            // 也检查 data-index
                            const dataIdx = el.getAttribute('data-index');
                            if (dataIdx && dataIdx.startsWith('/')) {
                                routes.add(dataIdx.split('?')[0]);
                            }
                        });

                        // 方法4: 从 sidebar/nav 所有链接提取
                        document.querySelectorAll(
                            '.sidebar a, nav a, .el-aside a, .menu a, ' +
                            '[class*="sidebar"] a, [class*="nav"] a, [class*="menu"] a'
                        ).forEach(a => {
                            const href = a.getAttribute('href');
                            if (href && href.startsWith('/') && !href.includes('.') && href.length > 1) {
                                routes.add(href.split('?')[0].split('#')[0]);
                            }
                        });

                        // 方法5: 从 router-link 提取（Vue Router 组件）
                        document.querySelectorAll('[to]').forEach(el => {
                            const to = el.getAttribute('to');
                            if (to && to.startsWith('/') && !to.includes('.')) {
                                routes.add(to.split('?')[0]);
                            }
                        });

                        return Array.from(routes);
                    }""")

                    logger.info(f"运行中页面提取到 {len(runtime_routes)} 个路由: {runtime_routes}")
                    for r in runtime_routes:
                        if not is_asset.search(r) and r != '/':
                            all_routes.add(r)

                    await browser.close()
            except Exception as e:
                logger.warning(f"运行中页面路由提取失败: {e}")

        routes_list = sorted(all_routes)
        logger.info(f"最终发现 {len(routes_list)} 个路由: {routes_list}")

        # 第二步：逐页访问，获取页面元素结构
        page_infos = []
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True, args=['--no-sandbox'])
                context = await browser.new_context(viewport={"width": 1920, "height": 1080})

                # ★ 注入登录态：Cookie + LocalStorage
                if cookies:
                    try:
                        await context.add_cookies(cookies)
                        logger.info(f"已注入 {len(cookies)} 个 Cookie 用于页面爬取")
                    except Exception as e:
                        logger.warning(f"注入 Cookie 失败: {e}")

                for route in routes_list[:20]:  # 最多扫描20个页面
                    url = urljoin(deploy_url, route)
                    try:
                        page = await context.new_page()
                        await page.goto(url, wait_until='networkidle', timeout=15000)

                        # ★ 注入 LocalStorage（每页都需要，因为 localStorage 是 per-origin）
                        if storage:
                            try:
                                for k, v in storage.items():
                                    await page.evaluate(
                                        f"window.localStorage.setItem({json.dumps(k)}, {json.dumps(v)})"
                                    )
                            except Exception:
                                pass

                        await page.wait_for_timeout(1000)

                        # 提取页面结构
                        page_info = await page.evaluate("""() => {
                            const info = {
                                title: document.title,
                                h1: Array.from(document.querySelectorAll('h1')).map(e => e.innerText.trim()).filter(Boolean),
                                h2: Array.from(document.querySelectorAll('h2')).map(e => e.innerText.trim()).filter(Boolean).slice(0, 5),
                                buttons: Array.from(document.querySelectorAll('button')).map(e => e.innerText.trim()).filter(Boolean).slice(0, 10),
                                links: Array.from(document.querySelectorAll('a[href]')).map(e => ({text: e.innerText.trim(), href: e.getAttribute('href')})).filter(e => e.text).slice(0, 10),
                                inputs: Array.from(document.querySelectorAll('input,textarea,select')).map(e => ({type: e.type || e.tagName, placeholder: e.placeholder, name: e.name})).slice(0, 10),
                                tables: document.querySelectorAll('table,tbody').length,
                                forms: document.querySelectorAll('form').length,
                                modals: document.querySelectorAll('[class*="modal"],[class*="dialog"]').length,
                                text_content: document.body.innerText.slice(0, 500),
                            };
                            return info;
                        }""")

                        page_info['path'] = route
                        page_info['url'] = url
                        page_infos.append(page_info)
                        logger.info(f"扫描页面: {route} -> {page_info.get('h1', '')}")
                        await page.close()

                    except Exception as e:
                        logger.warning(f"扫描页面 {route} 失败: {e}")
                        page_infos.append({
                            'path': route,
                            'url': url,
                            'title': route,
                            'error': str(e),
                        })

                await context.close()
                await browser.close()

        except Exception as e:
            logger.warning(f"Playwright页面扫描失败，使用基础路由信息: {e}")
            # 降级：只用路由列表
            for route in routes_list:
                page_infos.append({'path': route, 'url': urljoin(deploy_url, route), 'title': route})

        return page_infos

    async def analyze_project_source(self, source_path: str) -> str:
        if not self.provider:
            raise ValueError("AI 提供商未配置")
        code_content = self._collect_source_code(source_path)
        return await self.provider.analyze_code(code_content)

    async def generate_test_cases(self, project_id: int, source_path: str,
                                  test_type: str = "功能测试",
                                  additional_context: str = "") -> List[dict]:
        if not self.provider:
            raise ValueError("AI 提供商未配置")

        code_content = self._collect_source_code(source_path)
        if not code_content.strip():
            raise ValueError("源代码为空，请检查源代码路径")

        # 获取项目部署URL + 登录态
        db = SessionLocal()
        deploy_url = ""
        login_cookies = None
        login_storage = None
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            deploy_url = project.deploy_url if project else ""

            # 查询已保存的登录记录
            login_record = db.query(LoginRecord).filter(
                LoginRecord.project_id == project_id
            ).first()

            session_ok = login_record and login_record.session_valid

            if login_record and login_record.cookies_data:
                try:
                    login_cookies = json.loads(login_record.cookies_data)
                    if session_ok:
                        logger.info(f"已加载 {len(login_cookies)} 个登录 Cookie")
                    else:
                        logger.warning(
                            f"登录态可能已失效 (session_valid={login_record.session_valid})，"
                            f"但仍加载了 {len(login_cookies)} 个 Cookie"
                        )
                except Exception as e:
                    logger.warning(f"解析登录 Cookie 失败: {e}")
            elif not login_record:
                logger.warning(f"项目 {project_id} 无登录记录，深度扫描将不携带登录态")

            if login_record and login_record.local_storage:
                try:
                    login_storage = json.loads(login_record.local_storage)
                    logger.info(f"已加载 {len(login_storage)} 个 localStorage 条目")
                except Exception as e:
                    logger.warning(f"解析 localStorage 失败: {e}")
        finally:
            db.close()

        # 深度扫描所有页面（携带登录态）
        page_infos = []
        if deploy_url:
            logger.info(f"开始深度扫描页面: {deploy_url} (登录态: {'有' if login_cookies else '无'})")
            page_infos = await self._deep_scan_pages(deploy_url, login_cookies, login_storage)
            logger.info(f"共扫描到 {len(page_infos)} 个页面")

        # 构建页面信息摘要
        pages_summary = self._build_pages_summary(page_infos, deploy_url)

        # 根据页面数量动态决定生成数量：每页至少2个用例
        page_count = len(page_infos) if page_infos else 4
        target_count = max(8, page_count * 2)
        target_count = min(target_count, 30)  # 上限30个，避免token超限

        logger.info(f"目标生成测试用例数量: {target_count} (页面数: {page_count})")

        all_saved_cases = []

        # 分批生成：每批覆盖3-4个页面，避免单次token超限
        batch_size = 3
        page_batches = [page_infos[i:i+batch_size] for i in range(0, len(page_infos), batch_size)] if page_infos else [[]]

        for batch_idx, batch_pages in enumerate(page_batches):
            batch_summary = self._build_pages_summary(batch_pages, deploy_url)
            batch_target = max(3, len(batch_pages) * 2)

            enforced_context = (
                f"{additional_context}\n\n"
                f"【完整站点页面信息】\n{pages_summary}\n\n"
                f"【本批次重点测试页面】\n{batch_summary}\n\n"
                f"【强制要求】\n"
                f"- 生成exactly {batch_target}个独立的pytest测试函数\n"
                f"- 专注测试本批次页面的功能\n"
                f"- 导航使用 goto(page, BASE_URL + \"/路径\")\n"
                f"- 使用上方扫描到的真实页面元素（按钮文本、输入框等）\n"
                f"- 每个函数完全独立，函数名不能重复\n"
                f"- 批次编号{batch_idx+1}，函数名加后缀避免重复，如 test_xxx_b{batch_idx+1}\n"
            )

            logger.info(f"生成第 {batch_idx+1}/{len(page_batches)} 批测试用例，目标 {batch_target} 个")

            try:
                raw_response = await self.provider.generate_test_cases(
                    code_content, test_type, enforced_context
                )
                batch_cases = self._parse_test_code(raw_response, test_type)
                saved = await self._save_test_cases(project_id, batch_cases, raw_response, test_type)
                all_saved_cases.extend(saved)
                logger.info(f"第 {batch_idx+1} 批生成 {len(saved)} 个用例")
            except Exception as e:
                logger.error(f"第 {batch_idx+1} 批生成失败: {e}")
                continue

        logger.info(f"全部生成完成，共 {len(all_saved_cases)} 个测试用例")
        return all_saved_cases

    def _build_pages_summary(self, page_infos: List[Dict], deploy_url: str) -> str:
        """将页面扫描结果格式化为AI可读的摘要"""
        if not page_infos:
            return "未能扫描到页面信息"

        lines = []
        for p in page_infos:
            path = p.get('path', '/')
            lines.append(f"\n--- 页面: {path} ---")
            lines.append(f"URL: {deploy_url.rstrip('/')}{path}")

            if p.get('error'):
                lines.append(f"[扫描失败: {p['error']}]")
                continue

            if p.get('h1'):
                lines.append(f"标题(h1): {p['h1']}")
            if p.get('h2'):
                lines.append(f"子标题(h2): {p['h2']}")
            if p.get('buttons'):
                lines.append(f"按钮: {p['buttons']}")
            if p.get('inputs'):
                inputs_desc = [f"{i.get('type','input')}[{i.get('placeholder') or i.get('name','')}]"
                               for i in p.get('inputs', [])]
                lines.append(f"输入框: {inputs_desc}")
            if p.get('forms', 0) > 0:
                lines.append(f"表单数量: {p['forms']}")
            if p.get('tables', 0) > 0:
                lines.append(f"表格/列表: {p['tables']}")
            if p.get('modals', 0) > 0:
                lines.append(f"弹窗组件: {p['modals']}")
            if p.get('text_content'):
                # 只取前200字作为页面内容摘要
                lines.append(f"页面文字摘要: {p['text_content'][:200]}")

        return "\n".join(lines)

    async def _save_test_cases(self, project_id: int, test_cases: List[dict],
                                raw_response: str, test_type: str) -> List[dict]:
        """保存测试用例到数据库，同名替换"""
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
            return saved_cases
        finally:
            db.close()

    def _collect_source_code(self, source_path: str) -> str:
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
                    logger.warning(f"跳过验证失败的用例 [{match.group(2)}]: {error}")
                    continue  # 跳过单个失败用例，不终止整批

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
            test_cases.append({
                "name": name,
                "description": f"{test_type} - 自动生成",
                "code": cleaned_code,
                "priority": "medium",
                "tags": [test_type],
            })

        return test_cases