"""Jenkins 集成 API"""
import json
from fastapi import APIRouter, Depends, HTTPException as _HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from backend.database import get_db, JenkinsConfig, TestRun, Project, AIConfig
from backend.jenkins_integration import JenkinsIntegration
from backend.errors import ErrorCode, error_response

router = APIRouter(prefix="/api/v1/jenkins", tags=["Jenkins集成"])


class JenkinsConfigCreate(BaseModel):
    name: str
    url: str
    username: str = ""
    api_token: str = ""
    job_name: str = ""


class JenkinsConfigUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    username: Optional[str] = None
    api_token: Optional[str] = None
    job_name: Optional[str] = None
    enabled: Optional[bool] = None


@router.get("/configs")
def list_jenkins_configs(db: Session = Depends(get_db)):
    """获取 Jenkins 配置列表"""
    configs = db.query(JenkinsConfig).all()
    return {
        "items": [
            {
                "id": c.id,
                "name": c.name,
                "url": c.url,
                "username": c.username,
                "job_name": c.job_name,
                "enabled": c.enabled,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            }
            for c in configs
        ],
    }


@router.post("/configs")
def create_jenkins_config(data: JenkinsConfigCreate, db: Session = Depends(get_db)):
    """创建 Jenkins 配置"""
    config = JenkinsConfig(
        name=data.name,
        url=data.url,
        username=data.username,
        api_token=data.api_token,
        job_name=data.job_name,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return {"id": config.id, "name": config.name, "message": "Jenkins 配置创建成功"}


@router.put("/configs/{config_id}")
def update_jenkins_config(config_id: int, data: JenkinsConfigUpdate, db: Session = Depends(get_db)):
    """更新 Jenkins 配置"""
    config = db.query(JenkinsConfig).filter(JenkinsConfig.id == config_id).first()
    if not config:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "配置不存在", 404)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)
    db.commit()
    return {"message": "Jenkins 配置更新成功"}


@router.delete("/configs/{config_id}")
def delete_jenkins_config(config_id: int, db: Session = Depends(get_db)):
    """删除 Jenkins 配置"""
    config = db.query(JenkinsConfig).filter(JenkinsConfig.id == config_id).first()
    if not config:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "配置不存在", 404)
    db.delete(config)
    db.commit()
    return {"message": "Jenkins 配置已删除"}


@router.post("/configs/{config_id}/test")
async def test_jenkins_connection(config_id: int, db: Session = Depends(get_db)):
    """测试 Jenkins 连接"""
    config = db.query(JenkinsConfig).filter(JenkinsConfig.id == config_id).first()
    if not config:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "配置不存在", 404)

    jenkins = JenkinsIntegration(config.url, config.username, config.api_token)
    result = await jenkins.test_connection()
    return result


@router.post("/configs/{config_id}/trigger")
async def trigger_jenkins_job(
    config_id: int,
    params: dict = {},
    db: Session = Depends(get_db),
):
    """触发 Jenkins Job"""
    config = db.query(JenkinsConfig).filter(JenkinsConfig.id == config_id).first()
    if not config:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "配置不存在", 404)

    jenkins = JenkinsIntegration(config.url, config.username, config.api_token)
    result = await jenkins.trigger_test_job(config.job_name, params)
    return result


@router.post("/trigger")
async def jenkins_webhook_trigger(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Jenkins Webhook / CI/CD 触发接口
    此接口供 Jenkins pipeline 调用
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    project_name = body.get("projectName", body.get("project_name", ""))
    deploy_url = body.get("deployUrl", body.get("deploy_url", ""))
    source_code_path = body.get("sourceCodePath", body.get("source_code_path", ""))
    jenkins_job = body.get("jenkinsJobName", body.get("jenkins_job_name", ""))
    jenkins_build = body.get("jenkinsBuildNumber", body.get("jenkins_build_number", ""))

    # 查找或创建项目
    project = db.query(Project).filter(Project.name == project_name).first()
    if not project:
        project = Project(
            name=project_name,
            deploy_url=deploy_url,
            source_code_path=source_code_path,
            status="active",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

    # 查找默认 AI 配置
    ai_config = db.query(AIConfig).filter(AIConfig.is_default == True).first()

    # 创建测试运行
    run = TestRun(
        project_id=project.id,
        name=f"Jenkins触发 - {jenkins_job} #{jenkins_build}",
        status="generating",
        trigger_mode="jenkins",
        jenkins_job_name=jenkins_job,
        jenkins_build_number=jenkins_build,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return {
        "message": "测试已触发",
        "run_id": run.id,
        "project_id": project.id,
        "status": "pending",
    }

