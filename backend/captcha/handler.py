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
                            const body = document.body.textContent || '';
                            // 检查常见登录成功标志
                            const hasText = body.includes('登录成功') || 
                                           body.includes('欢迎回来') || 
                                           body.includes('个人中心') || 
                                           body.includes('退出登录') ||
                                           body.includes('Logout') ||
                                           body.includes('Settings');
                            
                            const hasElement = !!document.querySelector('.user-info, .avatar, [data-testid="user-menu"], .logout-btn, #logout');
                            
                            // 检查 URL 是否还在登录页
                            const isLoginPage = window.location.href.toLowerCase().includes('login');
                            
                            return (hasText || hasElement) && !isLoginPage;
                        }
                    """)
                    
                    # 更新数据库状态
                    record.session_valid = is_valid
                    if is_valid:
                        record.last_login_at = datetime.now(timezone.utc)
                    db.commit()
                    
                    logger.info(f"项目 {project_id} 登录态校验结果: {'有效' if is_valid else '失效'}")
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
