"""Fernet 加密模块 — SQLAlchemy TypeDecorator + 迁移 + 密钥轮换"""
import os
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator
from loguru import logger

# Module-level singleton
_fernet = None


def get_fernet() -> Fernet:
    """Get or create the Fernet instance from FERNET_KEY env var.
    Returns None if FERNET_KEY is not configured — callers must handle gracefully."""
    global _fernet
    if _fernet is None:
        key = os.environ.get("FERNET_KEY", "")
        if not key:
            return None
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt an API key. Idempotent — already-encrypted values pass through.
    Returns plaintext as-is when encryption is not configured."""
    if not plaintext:
        return ""
    if plaintext.startswith("gAAAAA"):
        return plaintext
    fernet = get_fernet()
    if fernet is None:
        return plaintext
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_api_key(token: str) -> str:
    """Decrypt an API key. Legacy plaintext values pass through.
    Returns token as-is when encryption is not configured."""
    if not token:
        return ""
    if not token.startswith("gAAAAA"):
        return token
    fernet = get_fernet()
    if fernet is None:
        return token
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("无法解密 API Key: 加密令牌无效或密钥不匹配")
    except Exception as e:
        raise ValueError(f"解密 API Key 失败: {e}")


class EncryptedField(TypeDecorator):
    """SQLAlchemy TypeDecorator — transparent encrypt/decrypt at the ORM level."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_api_key(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_api_key(value)

    def copy(self, **kw):
        return EncryptedField()


def migrate_plaintext_keys(db_session) -> int:
    """Auto-migrate plaintext API keys to encrypted format. Idempotent.
    Returns the number of keys migrated."""
    from backend.database import AIConfig  # Lazy import to avoid circular deps

    count = 0
    configs = db_session.query(AIConfig).all()
    for cfg in configs:
        if cfg.api_key and not cfg.api_key.startswith("gAAAAA"):
            cfg.api_key = encrypt_api_key(cfg.api_key)
            logger.info(f"已加密 AI 配置 [{cfg.id}] {cfg.name} 的 API Key")
            count += 1

    if count > 0:
        db_session.commit()
    return count


def encrypt_data(plaintext: str) -> str:
    """通用数据加密（用于密码等敏感字段）。与 encrypt_api_key 行为相同。"""
    return encrypt_api_key(plaintext)


def decrypt_data(token: str) -> str:
    """通用数据解密（用于密码等敏感字段）。与 decrypt_api_key 行为相同。"""
    return decrypt_api_key(token)


def rotate_fernet_key(db_session, new_key_str: str) -> int:
    """Rotate Fernet encryption key using MultiFernet for zero-downtime.
    Returns the number of keys re-encrypted."""
    from backend.database import AIConfig  # Lazy import to avoid circular deps

    old_key_str = os.environ.get("FERNET_KEY", "")
    if not old_key_str:
        raise RuntimeError("FERNET_KEY 环境变量未设置，无法读取旧密钥进行轮换")

    old_fernet = Fernet(old_key_str.encode())
    new_fernet = Fernet(new_key_str.encode())
    multi = MultiFernet([new_fernet, old_fernet])

    configs = db_session.query(AIConfig).all()
    for cfg in configs:
        if cfg.api_key and cfg.api_key.startswith("gAAAAA"):
            plaintext = old_fernet.decrypt(cfg.api_key.encode()).decode()
            cfg.api_key = multi.encrypt(plaintext.encode()).decode()
            logger.info(f"已轮换 AI 配置 [{cfg.id}] {cfg.name} 的加密密钥")

    db_session.commit()
    logger.warning(f"密钥轮换完成: 共处理 {len(configs)} 条 AI 配置。请安全保存新密钥，丢弃旧密钥。")
    return len(configs)
