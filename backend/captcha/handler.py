"""验证码处理 - 支持滑块验证码弹出浏览器手动处理并记录登录信息"""
import os
import json
import time
import base64
from typing import Optional
from loguru import logger
from datetime import datetime, timezone

from backend.database import SessionLocal, LoginRecord, Project


class CaptchaHandler:
    """验证码处理器 - 弹出浏览器让用户手动完成滑块验证"""

    SESSION_TTL_SECONDS = 1800  # 登录态默认有效期 30 分钟

    def __init__(self):
        self._browser = None
        self._context = None

    async def handle_slider_captcha(self, project_id: int, url: str,
                                    headless: bool = False,
                                    timeout: int = 120) -> Optional[dict]:
        """
        处理滑块验证码 - 弹出浏览器让用户手动完成验证
        Docker 环境（无 DISPLAY）自动使用无头模式

        Args:
            project_id: 项目ID
            url: 登录页面URL
            headless: 是否无头模式
            timeout: 等待超时时间（秒）

        Returns:
            dict: 登录信息（cookies, localStorage等）
        """
        from playwright.async_api import async_playwright

        # Docker 环境没有显示器，强制使用无头模式
        if 'DISPLAY' not in os.environ:
            headless = True
            logger.info("Docker 环境: 使用无头模式处理验证码")

        logger.info(f"开始处理验证码: {url}, headless={headless}")

        async with async_playwright() as pw:
            self._browser = await pw.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )

            # 创建上下文
            self._context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
            )

            page = await self._context.new_page()
            await page.goto(url, wait_until="networkidle")

            logger.info("浏览器已打开，等待用户完成滑块验证...")

            # 等待用户完成登录（检测到URL变化或特定元素）
            original_url = page.url
            logged_in = False
            start_time = time.time()

            while time.time() - start_time < timeout:
                await page.wait_for_timeout(1000)
                current_url = page.url

                # 检测URL变化（登录后通常会跳转）
                if current_url != original_url and "login" not in current_url.lower():
                    logged_in = True
                    break

                # 检测是否存在特定登录成功后的元素
                try:
                    is_logged_in = await page.evaluate("""
                        () => {
                            // 检查常见登录成功标志
                            const body = document.body.textContent || '';
                            return body.includes('登录成功') ||
                                   body.includes('欢迎回来') ||
                                   !!document.querySelector('.user-info, .avatar, [data-testid="user-menu"]');
                        }
                    """)
                    if is_logged_in:
                        logged_in = True
                        break
                except Exception:
                    pass

            if not logged_in:
                logger.warning("用户未在超时时间内完成验证")
                await self._cleanup()
                return None

            logger.info("用户已成功登录，正在获取会话信息...")

            # 获取 cookies
            cookies = await self._context.cookies()
            cookies_json = json.dumps(cookies, ensure_ascii=False)

            # 获取 localStorage
            local_storage = {}
            try:
                local_storage = await page.evaluate("() => JSON.stringify(window.localStorage)")
                local_storage = json.loads(local_storage)
            except Exception:
                pass

            # 保存登录记录
            login_info = {
                "url": url,
                "cookies_data": cookies_json,
                "local_storage": json.dumps(local_storage, ensure_ascii=False) if local_storage else "",
                "logged_in": True,
                "timestamp": time.time(),
            }

            # 保存到数据库
            db = SessionLocal()
            try:
                record = db.query(LoginRecord).filter(
                    LoginRecord.project_id == project_id,
                ).first()

                if not record:
                    record = LoginRecord(
                        project_id=project_id,
                        url=url,
                        cookies_data=cookies_json,
                        local_storage=json.dumps(local_storage, ensure_ascii=False) if local_storage else "",
                        session_valid=True,
                        last_login_at=datetime.now(timezone.utc),
                    )
                    db.add(record)
                else:
                    record.cookies_data = cookies_json
                    record.local_storage = json.dumps(local_storage, ensure_ascii=False) if local_storage else ""
                    record.session_valid = True
                    record.last_login_at = datetime.now(timezone.utc)

                db.commit()
                logger.info(f"登录信息已保存，项目ID: {project_id}")
            except Exception as e:
                logger.error(f"保存登录信息失败: {e}")
            finally:
                db.close()

            await self._cleanup()
            return login_info

    async def auto_fill_and_captcha(self, project_id: int, url: str,
                                     username_selector: str, password_selector: str,
                                     login_button_selector: str, username: str, password: str,
                                     headless: bool = False, timeout: int = 120) -> Optional[dict]:
        """
        混合模式：自动填写用户名密码 + 等待用户手动完成拖动验证码。
        适用于点击登录后弹出滑块/图形验证码的系统。

        Docker 环境（无 DISPLAY）自动使用无头模式 + 返回手动 Cookie 粘贴指引。
        """
        from playwright.async_api import async_playwright
        from backend.security.encryption import decrypt_data

        # Docker 环境没有显示器
        is_docker = 'DISPLAY' not in os.environ
        if is_docker:
            headless = True
            logger.info("Docker 环境: 自动填充后将截图供参考，请使用粘贴 Cookie 方式")

        logger.info(f"混合模式登录: 自动填表 + 手动验证码, url={url}")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)

                # ★ 自动填写用户名和密码
                try:
                    await page.wait_for_selector(username_selector, timeout=5000)
                    await page.fill(username_selector, username)
                    logger.info(f"已自动填写用户名: {username}")
                except Exception as e:
                    logger.warning(f"自动填写用户名失败: {e}，请手动填写")

                try:
                    await page.wait_for_selector(password_selector, timeout=5000)
                    # 密码可能需要解密
                    actual_password = password
                    if password.startswith("gAAAAA"):
                        try:
                            actual_password = decrypt_data(password)
                        except Exception:
                            pass
                    await page.fill(password_selector, actual_password)
                    logger.info("已自动填写密码")
                except Exception as e:
                    logger.warning(f"自动填写密码失败: {e}，请手动填写")

                # ★ 自动点击登录按钮（触发验证码）
                try:
                    await page.wait_for_selector(login_button_selector, timeout=5000)
                    await page.click(login_button_selector)
                    logger.info("已自动点击登录按钮，等待验证码处理...")
                except Exception as e:
                    logger.warning(f"点击登录按钮失败: {e}")

                if is_docker:
                    # Docker 模式：等待一段时间后截取页面状态
                    await page.wait_for_timeout(3000)
                    logger.info("Docker 环境：请在浏览器中手动完成验证码登录，然后粘贴 Cookie")
                    # 不等了，直接返回，让用户走粘贴 Cookie 流程
                    return None

                # 非 Docker 模式：等待用户完成验证码
                original_url = page.url
                logged_in = False
                start_time = time.time()

                logger.info("请在弹出的浏览器窗口中完成拖动验证码...")

                while time.time() - start_time < timeout:
                    await page.wait_for_timeout(1000)
                    current_url = page.url

                    # 检测URL变化
                    if current_url != original_url and "login" not in current_url.lower():
                        logged_in = True
                        break

                    # 检测页面内容变化
                    try:
                        is_logged = await page.evaluate("""() => {
                            const body = document.body.textContent || '';
                            const hasNav = !!document.querySelector(
                                '.sidebar, .navbar, .header, .el-menu, ' +
                                '.user-info, .avatar, .logout-btn, #logout'
                            );
                            const hasText = body.includes('主页') || body.includes('首页') ||
                                           body.includes('Dashboard') || body.includes('退出登录') ||
                                           body.includes('欢迎');
                            return hasNav || hasText;
                        }""")
                        if is_logged:
                            logged_in = True
                            break
                    except Exception:
                        pass

                if not logged_in:
                    logger.warning("用户未在超时时间内完成验证码")
                    return None

                logger.info("验证码处理完成，登录成功！正在保存会话...")

                # 保存 cookies 和 localStorage
                cookies = await context.cookies()
                cookies_json = json.dumps(cookies, ensure_ascii=False)

                local_storage = {}
                try:
                    ls_raw = await page.evaluate("() => JSON.stringify(window.localStorage)")
                    local_storage = json.loads(ls_raw)
                except Exception:
                    pass

                self._save_login_record(project_id, url, cookies_json,
                                        json.dumps(local_storage, ensure_ascii=False) if local_storage else "",
                                        username_selector, password_selector, login_button_selector,
                                        username, password)

                return {
                    "url": url,
                    "cookies_data": cookies_json,
                    "local_storage": json.dumps(local_storage, ensure_ascii=False) if local_storage else "",
                    "logged_in": True,
                    "timestamp": time.time(),
                }

            except Exception as e:
                logger.error(f"混合模式登录失败: {e}")
                return None
            finally:
                await context.close()
                await browser.close()

    def _save_login_record(self, project_id, url, cookies_json, local_storage_json,
                           username_selector, password_selector, login_button_selector,
                           username, encrypted_password):
        """保存或更新登录记录"""
        db = SessionLocal()
        try:
            record = db.query(LoginRecord).filter(
                LoginRecord.project_id == project_id,
            ).first()
            now = datetime.now(timezone.utc)
            if not record:
                record = LoginRecord(
                    project_id=project_id, url=url,
                    username_selector=username_selector,
                    password_selector=password_selector,
                    login_button_selector=login_button_selector,
                    username=username,
                    encrypted_password=encrypted_password,
                    cookies_data=cookies_json,
                    local_storage=local_storage_json,
                    session_valid=True,
                    last_login_at=now,
                )
                db.add(record)
            else:
                record.cookies_data = cookies_json
                record.local_storage = local_storage_json
                record.session_valid = True
                record.last_login_at = now
            db.commit()
            logger.info(f"登录信息已保存，项目ID: {project_id}")
        except Exception as e:
            logger.error(f"保存登录记录失败: {e}")
        finally:
            db.close()

    def is_session_fresh(self, project_id: int) -> bool:
        """
        基于 TTL 快速判断登录态是否仍在有效窗口内（不发起网络请求）。
        返回 True 表示 last_login_at 在 SESSION_TTL_SECONDS 内且 session_valid=True。
        """
        db = SessionLocal()
        try:
            record = db.query(LoginRecord).filter(
                LoginRecord.project_id == project_id
            ).first()
            if not record or not record.session_valid or not record.last_login_at:
                return False
            elapsed = (datetime.now(timezone.utc) - record.last_login_at).total_seconds()
            return elapsed <= self.SESSION_TTL_SECONDS
        except Exception:
            return False
        finally:
            db.close()

    async def get_login_info(self, project_id: int) -> Optional[dict]:
        """获取已保存的登录信息"""
        db = SessionLocal()
        try:
            record = db.query(LoginRecord).filter(
                LoginRecord.project_id == project_id,
            ).first()

            if not record:
                return None

            return {
                "url": record.url,
                "cookies_data": record.cookies_data,
                "local_storage": record.local_storage,
                "session_valid": record.session_valid,
                "last_login_at": record.last_login_at.isoformat() if record.last_login_at else "",
                "has_login": bool(record.cookies_data),
            }
        finally:
            db.close()

    async def auto_login(self, project_id: int, url: str, username_selector: str, password_selector: str, login_button_selector: str, username: str, password: str, headless: bool = True, timeout: int = 60) -> Optional[dict]:
        """
        执行自动登录，通过用户名、密码和选择器进行登录。
        兼容 SPA（Element UI / Vue / React）登录页和传统表单登录。
        """
        from playwright.async_api import async_playwright
        from backend.security.encryption import decrypt_data

        logger.info(f"开始自动登录项目 {project_id}: {url}")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-setuid-sandbox"])
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                original_url = page.url  # 记录登录前 URL

                # 填写用户名和密码
                await page.wait_for_selector(username_selector, timeout=5000)
                await page.fill(username_selector, username)
                await page.fill(password_selector, password)

                # 点击登录按钮
                await page.wait_for_selector(login_button_selector, timeout=5000)
                await page.click(login_button_selector)

                # ★ 自动检测并破解滑块验证码
                from backend.captcha.slider_solver import SliderSolver
                captcha_solved = await SliderSolver.wait_for_captcha_gone(page, timeout=120)
                if captcha_solved:
                    logger.info("验证码已自动处理（或无需验证码）")

                # ★ 等待登录 AJAX 完成 + 页面跳转（验证码后需要更长时间）
                await page.wait_for_timeout(4000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass

                # ★ 额外等待 SPA 路由跳转完成
                await page.wait_for_timeout(2000)

                # 检测登录是否成功（兼容 SPA 无跳转和传统跳转两种模式）
                is_logged_in = await page.evaluate("""
                    (originalUrl) => {
                        const currentUrl = window.location.href;

                        // 1. URL 完全变了（不是 hash 变化）且不在登录页 → 肯定登录成功
                        const origPath = new URL(originalUrl).pathname;
                        const curPath = new URL(currentUrl).pathname;
                        if (curPath !== origPath && !currentUrl.toLowerCase().includes('login')) {
                            return true;
                        }

                        // 2. 检查登录表单是否消失了
                        const loginFormEls = document.querySelectorAll(
                            'input[placeholder*="用户名"], input[placeholder*="密码"], ' +
                            'input[name="username"], input[name="password"]'
                        );
                        const loginFormVisible = loginFormEls.length > 0 &&
                            Array.from(loginFormEls).some(el => el.offsetParent !== null);

                        // 3. 检查导航/菜单元素是否出现了
                        const navSelectors = [
                            '.el-menu', '.sidebar', '.navbar', '.el-header',
                            '.el-aside', '.main-container', '.dashboard',
                            '.user-info', '.avatar', '.logout-btn', '#logout',
                            '.el-dropdown', '.navbar-user', '.header-user',
                            '.layout', '.app-wrapper', '.home', '.index',
                            'nav', 'header', 'aside', '[class*="sidebar"]',
                            '[class*="navbar"]', '[class*="nav-menu"]',
                            '[class*="layout"]', '[class*="wrapper"]',
                        ];
                        const hasNav = navSelectors.some(sel => {
                            try { return !!document.querySelector(sel); } catch(e) { return false; }
                        });

                        // 4. 检查页面标题
                        const title = document.title || '';
                        const isLoginTitle = title.includes('登录') || title.includes('Login');

                        // 5. 页面文本内容检测
                        const body = document.body.textContent || '';
                        const hasContent = body.length > 100;  // 登录页通常文字较少
                        const hasLoginWords = body.includes('登录') || body.includes('Login');

                        // 综合判断：
                        // a. 登录表单消失 + 有导航元素 = 登录成功
                        if (!loginFormVisible && hasNav) return true;
                        // b. URL变了 + 有导航元素 = 登录成功
                        if (curPath !== origPath && hasNav) return true;
                        // c. 导航元素存在 + 页面内容多 + 不是登录页标题 = 成功
                        if (hasNav && hasContent && !isLoginTitle) return true;

                        return false;
                    }
                """, original_url)

                if not is_logged_in:
                    # 截图调试
                    try:
                        screenshot_path = f"/app/logs/auto_login_{project_id}_{int(time.time())}.png"
                        await page.screenshot(path=screenshot_path, full_page=False)
                        current_url = page.url
                        page_title = await page.title()
                        logger.warning(
                            f"项目 {project_id} 自动登录失败：未检测到登录成功标志\n"
                            f"  当前URL: {current_url}\n"
                            f"  页面标题: {page_title}\n"
                            f"  截图: {screenshot_path}"
                        )
                    except Exception:
                        logger.warning(f"项目 {project_id} 自动登录失败：未检测到登录成功标志")
                    return None

                logger.info(f"项目 {project_id} 自动登录成功，正在获取会话信息...")

                cookies = await context.cookies()
                cookies_json = json.dumps(cookies, ensure_ascii=False)

                local_storage = {}
                try:
                    local_storage = await page.evaluate("() => JSON.stringify(window.localStorage)")
                    local_storage = json.loads(local_storage)
                except Exception:
                    pass

                login_info = {
                    "url": url,
                    "cookies_data": cookies_json,
                    "local_storage": json.dumps(local_storage, ensure_ascii=False) if local_storage else "",
                    "logged_in": True,
                    "timestamp": time.time(),
                }

                db = SessionLocal()
                try:
                    record = db.query(LoginRecord).filter(
                        LoginRecord.project_id == project_id,
                    ).first()

                    if not record:
                        record = LoginRecord(
                            project_id=project_id,
                            url=url,
                            username_selector=username_selector,
                            password_selector=password_selector,
                            login_button_selector=login_button_selector,
                            username=username,
                            encrypted_password=password, # 密码已加密，直接存储
                            cookies_data=cookies_json,
                            local_storage=json.dumps(local_storage, ensure_ascii=False) if local_storage else "",
                            session_valid=True,
                            last_login_at=datetime.now(timezone.utc),
                        )
                        db.add(record)
                    else:
                        record.url = url
                        record.username_selector = username_selector
                        record.password_selector = password_selector
                        record.login_button_selector = login_button_selector
                        record.username = username
                        record.encrypted_password = password
                        record.cookies_data = cookies_json
                        record.local_storage = json.dumps(local_storage, ensure_ascii=False) if local_storage else ""
                        record.session_valid = True
                        record.last_login_at = datetime.now(timezone.utc)

                    db.commit()
                    logger.info(f"自动登录信息已保存，项目ID: {project_id}")
                except Exception as e:
                    logger.error(f"保存自动登录信息失败: {e}")
                finally:
                    db.close()

                return login_info

            except Exception as e:
                logger.error(f"自动登录过程中发生错误: {e}")
                return None
            finally:
                await context.close()
                await browser.close()

    async def check_session_validity(self, project_id: int) -> bool:
        """
        检查指定项目的登录会话是否仍然有效
        通过访问项目 URL 并检查页面上是否存在登录成功的标志性元素
        """
        from playwright.async_api import async_playwright
        
        db = SessionLocal()
        try:
            record = db.query(LoginRecord).filter(LoginRecord.project_id == project_id).first()
            if not record or not record.cookies_data:
                logger.warning(f"项目 {project_id} 没有保存的登录信息")
                return False
            
            project = db.query(Project).filter(Project.id == project_id).first()
            url = project.deploy_url if project else record.url
            if not url:
                logger.warning(f"项目 {project_id} 没有配置部署地址")
                return False

            cookies = json.loads(record.cookies_data)
            local_storage = json.loads(record.local_storage) if record.local_storage else {}

            logger.info(f"正在校验项目 {project_id} 的登录态有效性: {url}")
            
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
                context = await browser.new_context(viewport={"width": 1280, "height": 720})
                
                # 注入 Cookie
                await context.add_cookies(cookies)
                
                page = await context.new_page()
                
                # 注入 LocalStorage (如果存在)
                if local_storage:
                    await page.add_init_script(f"""
                        () => {{
                            const storage = {json.dumps(local_storage)};
                            for (const [key, value] of Object.entries(storage)) {{
                                window.localStorage.setItem(key, value);
                            }}
                        }}
                    """)

                try:
                    # 访问页面
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    
                    # 检查登录成功标志
                    is_valid = await page.evaluate("""
                        () => {
                            const url = window.location.href.toLowerCase();

                            // 1. URL 不在登录页 + 有实质内容 = 登录成功
                            const isLoginPage = url.includes('login') || url.includes('signin') || url.includes('auth');
                            const body = document.body.textContent || '';
                            const hasSubstantialContent = body.length > 200;

                            // 2. 检查登录表单是否还在
                            const loginInputs = document.querySelectorAll(
                                'input[placeholder*="用户名"], input[placeholder*="密码"], ' +
                                'input[name="username"], input[name="password"]'
                            );
                            const hasLoginForm = loginInputs.length > 0 &&
                                Array.from(loginInputs).some(el => {
                                    try { return el.offsetParent !== null; } catch(e) { return false; }
                                });

                            // 3. 检查导航结构
                            const navEls = document.querySelectorAll(
                                '.el-menu, .sidebar, .navbar, .el-header, .el-aside, ' +
                                '.main-container, .layout, nav, header, aside, ' +
                                '.app-wrapper, [class*="sidebar"], [class*="nav"], ' +
                                '[class*="menu"], [class*="layout"]'
                            );

                            // 4. 放宽判断：URL不在登录页 || 有导航结构 || 无登录表单
                            if (!isLoginPage && hasSubstantialContent) return true;
                            if (navEls.length >= 2) return true;
                            if (!hasLoginForm && hasSubstantialContent) return true;

                            return false;
                        }
                    """)
                    
                    # 更新数据库状态
                    record.session_valid = is_valid
                    if is_valid:
                        record.last_login_at = datetime.now(timezone.utc)
                    db.commit()

                    if not is_valid:
                        current_url = page.url
                        page_title = await page.title()
                        screenshot_path = f"/app/logs/session_check_{project_id}_{int(time.time())}.png"
                        await page.screenshot(path=screenshot_path, full_page=False)
                        logger.warning(
                            f"项目 {project_id} 登录态校验结果: 失效\n"
                            f"  访问URL: {url}\n"
                            f"  当前URL: {current_url}\n"
                            f"  页面标题: {page_title}\n"
                            f"  截图: {screenshot_path}"
                        )
                    else:
                        logger.info(f"项目 {project_id} 登录态校验结果: 有效")

                    return is_valid
                except Exception as e:
                    logger.error(f"校验过程中发生错误: {e}")
                    return False
                finally:
                    await context.close()
                    await browser.close()
        finally:
            db.close()

    async def clear_login(self, project_id: int) -> bool:
        """清除登录信息"""
        db = SessionLocal()
        try:
            record = db.query(LoginRecord).filter(
                LoginRecord.project_id == project_id,
            ).first()
            if record:
                record.session_valid = False
                record.cookies_data = ""
                record.local_storage = ""
                db.commit()
                return True
            return False
        finally:
            db.close()

    async def _cleanup(self):
        """清理浏览器资源"""
        try:
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
        except Exception as e:
            logger.warning(f"清理浏览器资源失败: {e}")
