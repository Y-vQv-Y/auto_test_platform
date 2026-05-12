import sqlite3
import os

db_path = "./data/test_platform.db"

def fix_database():
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查 login_records 表的列
        cursor.execute("PRAGMA table_info(login_records)")
        columns = [column[1] for column in cursor.fetchall()]
        
        print(f"当前 login_records 表的列: {columns}")

        # 需要添加的列及其类型
        required_columns = {
            "login_button_selector": "VARCHAR(200)",
            "username_selector": "VARCHAR(200)",
            "password_selector": "VARCHAR(200)",
            "username": "VARCHAR(200)",
            "encrypted_password": "VARCHAR(500)",
            "session_valid": "BOOLEAN DEFAULT 0"
        }

        for col_name, col_type in required_columns.items():
            if col_name not in columns:
                print(f"正在添加缺失的列: {col_name}")
                cursor.execute(f"ALTER TABLE login_records ADD COLUMN {col_name} {col_type}")
            else:
                print(f"列已存在: {col_name}")

        conn.commit()
        print("数据库修复完成！")
        
    except Exception as e:
        print(f"修复数据库时出错: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    fix_database()
