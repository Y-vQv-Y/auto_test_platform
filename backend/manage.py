"""管理命令行工具"""
import os
import sys
import argparse
from cryptography.fernet import Fernet

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal, init_db
from backend.security.encryption import rotate_fernet_key
from loguru import logger


def cmd_generate_key():
    """生成新的 Fernet 密钥"""
    key = Fernet.generate_key().decode()
    print(f"\n新 Fernet 密钥 (请安全保存):\n\n{key}\n")
    print("将以下内容添加到 .env 文件:")
    print(f"FERNET_KEY={key}")
    print("\nwarning: 生成后请立即备份密钥。密钥丢失将导致所有已加密的 API Key 无法恢复。")


def cmd_rotate_key():
    """轮换 Fernet 加密密钥"""
    old_key = os.environ.get("FERNET_KEY", "")
    if not old_key:
        print("错误: FERNET_KEY 环境变量未设置。请在 .env 中设置当前使用的密钥。")
        sys.exit(1)

    print("此操作将使用新的 Fernet 密钥重新加密所有 AI API Key。")
    print(f"当前密钥: {old_key[:20]}...")
    print("\n请生成新密钥 (可使用 'python manage.py generate-fernet-key'):")
    new_key = input("粘贴新密钥: ").strip()

    if not new_key:
        print("错误: 未提供新密钥。")
        sys.exit(1)

    try:
        Fernet(new_key.encode())
    except Exception as e:
        print(f"错误: 新密钥格式无效: {e}")
        sys.exit(1)

    confirm = input(f"\n将使用新密钥重新加密所有 AI 配置。确认? (输入 yes 继续): ")
    if confirm.lower() != "yes":
        print("已取消。")
        sys.exit(0)

    init_db()
    db = SessionLocal()
    try:
        count = rotate_fernet_key(db, new_key)
        print(f"\n+ 密钥轮换完成: 共处理 {count} 条 AI 配置")
        print(f"+ 新密钥: {new_key}")
        print("\n下一步:")
        print("1. 将 .env 中的 FERNET_KEY 更新为新密钥")
        print("2. 安全保存旧密钥作为备份 (如不再需要可丢弃)")
        print("3. 重启服务")
    except Exception as e:
        print(f"\nX 密钥轮换失败: {e}")
        sys.exit(1)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="AI 自动测试平台 - 管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    subparsers.add_parser("generate-fernet-key", help="生成新的 Fernet 加密密钥")
    subparsers.add_parser("rotate-fernet-key", help="轮换 Fernet 加密密钥 (重新加密所有 API Key)")

    args = parser.parse_args()

    if args.command == "generate-fernet-key":
        cmd_generate_key()
    elif args.command == "rotate-fernet-key":
        cmd_rotate_key()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
