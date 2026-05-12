import sys
import os

# 将项目根目录添加到 sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal, LoginRecord, Project

client = TestClient(app)

def verify():
    db = SessionLocal()
    try:
        # 1. 确保有一个测试项目
        project = db.query(Project).first()
        if not project:
            project = Project(name="Test Project", deploy_url="http://example.com")
            db.add(project)
            db.commit()
            db.refresh(project)
        
        project_id = project.id
        print(f"验证项目 ID: {project_id}")

        # 2. 测试获取自动登录配置接口
        response = client.get(f"/api/v1/captcha/auto_login_config/{project_id}")
        print(f"GET /api/v1/captcha/auto_login_config/{project_id} 状态码: {response.status_code}")
        
        if response.status_code == 200:
            print("API 响应成功！")
            print(f"响应内容: {response.json()}")
        else:
            print(f"API 响应失败: {response.text}")
            
    except Exception as e:
        print(f"验证过程中出错: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify()
