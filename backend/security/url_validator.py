"""URL 校验器 - 确保测试目标 URL 在允许范围内"""
import re
from urllib.parse import urlparse
from typing import List, Optional
from datetime import datetime
from loguru import logger


class URLValidator:
    """URL 安全校验器（仅在白名单模式下启用严格校验）"""

    def __init__(self):
        self.blocked_schemes = {"file:", "ftp:", "data:", "javascript:"}

    def validate(self, url: str, whitelist: Optional[List[str]] = None) -> bool:
        """
        验证 URL 是否安全

        Args:
            url: 待验证的 URL
            whitelist: 允许的 URL 白名单列表。传 None 或空列表 = 放通所有合法 URL

        Returns:
            bool: 是否安全
        """
        try:
            parsed = urlparse(url)
            scheme = parsed.scheme.lower()

            # 检查协议（始终拦截危险协议）
            if scheme in self.blocked_schemes:
                self._log("url_check", url, "blocked", f"禁止的协议: {scheme}")
                return False

            # 只允许 http/https
            if scheme not in ("http", "https"):
                self._log("url_check", url, "blocked", f"不支持的协议: {scheme}")
                return False

            # 如果传入了白名单且非空，进行白名单匹配
            if whitelist:
                host = parsed.hostname.lower() if parsed.hostname else ""
                allowed = False
                for allowed_url in whitelist:
                    allowed_parsed = urlparse(allowed_url)
                    allowed_host = allowed_parsed.hostname.lower() if allowed_parsed.hostname else ""
                    if host == allowed_host or host.endswith("." + allowed_host):
                        allowed = True
                        break
                if not allowed:
                    self._log("url_check", url, "blocked", f"不在白名单中: {host}")
                    return False

            self._log("url_check", url, "allowed", "URL验证通过")
            return True

        except Exception as e:
            logger.error(f"URL验证异常: {e}")
            self._log("url_check", url, "error", str(e))
            return False

    def sanitize_url(self, url: str) -> str:
        """清理 URL，移除敏感信息"""
        try:
            parsed = urlparse(url)
            clean = parsed._replace(params="", fragment="")
            return clean.geturl()
        except Exception:
            return url

    def _log(self, event_type: str, target: str, result: str, detail: str):
        """记录安全日志"""
        from backend.database import SessionLocal, SecurityLog  # Lazy import — avoid circular dependency
        try:
            db = SessionLocal()
            log = SecurityLog(
                event_type=event_type,
                target=target[:500],
                action="validate",
                result=result,
                detail=detail[:1000],
            )
            db.add(log)
            db.commit()
        except Exception as e:
            logger.warning(f"记录安全日志失败: {e}")
        finally:
            db.close()
