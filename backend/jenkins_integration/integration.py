"""Jenkins 集成 - 支持 CI/CD 阶段自动触发测试"""
import json
import hmac
import hashlib
from typing import Optional, Callable
from datetime import datetime
from loguru import logger
import httpx


class JenkinsIntegration:
    """Jenkins 集成"""

    def __init__(self, base_url: str = "", username: str = "", api_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.api_token = api_token

    async def test_connection(self) -> dict:
        """测试 Jenkins 连接"""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/api/json",
                    auth=(self.username, self.api_token),
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "connected": True,
                        "version": data.get("nodeDescription", ""),
                        "jobs": len(data.get("jobs", [])),
                    }
                return {"connected": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def trigger_test_job(self, job_name: str, params: dict = None) -> dict:
        """
        触发 Jenkins Job 执行测试

        Args:
            job_name: Jenkins Job 名称
            params: 构建参数

        Returns:
            dict: 触发结果
        """
        try:
            async with httpx.AsyncClient() as client:
                if params:
                    # 带参数的构建
                    resp = await client.post(
                        f"{self.base_url}/job/{job_name}/buildWithParameters",
                        auth=(self.username, self.api_token),
                        params=params,
                        timeout=10,
                    )
                else:
                    resp = await client.post(
                        f"{self.base_url}/job/{job_name}/build",
                        auth=(self.username, self.api_token),
                        timeout=10,
                    )

                if resp.status_code in (200, 201, 302):
                    # 获取队列位置
                    queue_location = resp.headers.get("Location", "")
                    return {
                        "success": True,
                        "queue_location": queue_location,
                        "build_number": self._extract_build_number(queue_location),
                    }
                return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_build_status(self, job_name: str, build_number: str) -> dict:
        """获取构建状态"""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/job/{job_name}/{build_number}/api/json",
                    auth=(self.username, self.api_token),
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "building": data.get("building", False),
                        "result": data.get("result", "PENDING"),
                        "duration": data.get("duration", 0),
                        "timestamp": data.get("timestamp", 0),
                        "url": data.get("url", ""),
                    }
                return {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    async def get_job_info(self, job_name: str) -> dict:
        """获取 Job 信息"""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/job/{job_name}/api/json",
                    auth=(self.username, self.api_token),
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "name": data.get("name", job_name),
                        "url": data.get("url", ""),
                        "description": data.get("description", ""),
                        "last_build": data.get("lastBuild", {}).get("number") if data.get("lastBuild") else None,
                        "last_successful": data.get("lastSuccessfulBuild", {}).get("number") if data.get("lastSuccessfulBuild") else None,
                        "last_failed": data.get("lastFailedBuild", {}).get("number") if data.get("lastFailedBuild") else None,
                        "health": data.get("healthReport", [{}])[0].get("score", 100) if data.get("healthReport") else 100,
                    }
                return {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def validate_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        if not secret:
            return True
        mac = hmac.new(secret.encode(), payload, hashlib.sha256)
        expected = mac.hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)


    def parse_webhook_payload(self, payload: dict) -> dict:
        """解析 Jenkins webhook 回调"""
        return {
            "job_name": payload.get("job", {}).get("name", ""),
            "build_number": str(payload.get("build", {}).get("number", "")),
            "build_status": payload.get("build", {}).get("status", ""),
            "build_phase": payload.get("build", {}).get("phase", ""),
            "scm_url": payload.get("job", {}).get("scm", {}).get("url", ""),
            "scm_branch": payload.get("job", {}).get("scm", {}).get("branch", ""),
        }

    def build_jenkinsfile_template(self, project_name: str, test_platform_url: str) -> str:
        """生成 Jenkinsfile 模板"""
        return f"""pipeline {{
    agent any

    environment {{
        TEST_PLATFORM_URL = '{test_platform_url}'
        PROJECT_NAME = '{project_name}'
    }}

    stages {{
        stage('Build') {{
            steps {{
                echo '构建项目...'
                // 在这里添加你的构建步骤
            }}
        }}

        stage('Deploy') {{
            steps {{
                echo '部署项目...'
                // 在这里添加你的部署步骤
            }}
        }}

        stage('Auto Test') {{
            steps {{
                script {{
                    // 调用 AI 自动测试平台
                    def response = httpRequest(
                        url: "${{TEST_PLATFORM_URL}}/api/v1/jenkins/trigger",
                        httpMode: 'POST',
                        contentType: 'APPLICATION_JSON',
                        requestBody: json(
                            projectName: "${{PROJECT_NAME}}",
                            jenkinsJobName: env.JOB_NAME,
                            jenkinsBuildNumber: env.BUILD_NUMBER,
                            deployUrl: '', // 请填写部署URL
                            sourceCodePath: '', // 请填写源码路径
                        )
                    )
                    echo "测试结果: ${{response}}"
                }}
            }}
        }}

        stage('Report') {{
            steps {{
                echo '生成测试报告...'
            }}
        }}
    }}

    post {{
        always {{
            cleanWs()
        }}
        failure {{
            // 测试失败通知
            echo '测试失败，请检查报告'
        }}
    }}
}}
"""

    def _extract_build_number(self, queue_location: str) -> str:
        """从队列 URL 提取构建编号"""
        try:
            # /queue/item/123/ 格式
            parts = queue_location.rstrip("/").split("/")
            return parts[-1] if parts else ""
        except Exception:
            return ""
