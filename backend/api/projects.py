"""项目管理 API"""
import os
import shutil
import zipfile
from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from loguru import logger

from backend.database import get_db, Project, ProjectStatus
from backend.config import settings
from backend.errors import ErrorCode, error_response
from backend.ai_engine.base import render_prompt_template

router = APIRouter(prefix="/api/v1/projects", tags=["项目管理"])


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    source_code_path: str = ""
    deploy_url: str = ""
    repo_url: str = ""
    repo_branch: str = "main"
    framework_type: str = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    source_code_path: Optional[str] = None
    deploy_url: Optional[str] = None
    repo_url: Optional[str] = None
    repo_branch: Optional[str] = None
    framework_type: Optional[str] = None
    status: Optional[str] = None


@router.get("")
def list_projects(
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """获取项目列表"""
    query = db.query(Project)
    if status:
        query = query.filter(Project.status == status)
    if search:
        query = query.filter(Project.name.contains(search))
    query = query.order_by(Project.updated_at.desc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "source_code_path": p.source_code_path,
                "deploy_url": p.deploy_url,
                "framework_type": p.framework_type,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else "",
                "updated_at": p.updated_at.isoformat() if p.updated_at else "",
            }
            for p in items
        ],
    }


@router.post("")
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    """创建项目"""
    project = Project(
        name=data.name,
        description=data.description,
        source_code_path=data.source_code_path,
        deploy_url=data.deploy_url,
        repo_url=data.repo_url,
        repo_branch=data.repo_branch,
        framework_type=data.framework_type,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Auto-create default prompt templates for this project
    from backend.database import PromptTemplate, DEFAULT_TEMPLATES
    for task_type, body in DEFAULT_TEMPLATES.items():
        template = PromptTemplate(
            project_id=project.id,
            provider="",
            task_type=task_type,
            name=f"默认{task_type}模板",
            template_body=body,
            is_default=True,
        )
        db.add(template)
    db.commit()

    return {
        "id": project.id,
        "name": project.name,
        "message": "项目创建成功",
    }


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    """获取项目详情"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "项目不存在", 404)

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "source_code_path": project.source_code_path,
        "deploy_url": project.deploy_url,
        "repo_url": project.repo_url,
        "repo_branch": project.repo_branch,
        "framework_type": project.framework_type,
        "status": project.status,
        "created_at": project.created_at.isoformat() if project.created_at else "",
        "updated_at": project.updated_at.isoformat() if project.updated_at else "",
        "test_count": len(project.test_runs) if project.test_runs else 0,
        "case_count": len(project.test_cases) if project.test_cases else 0,
    }


@router.put("/{project_id}")
def update_project(project_id: int, data: ProjectUpdate, db: Session = Depends(get_db)):
    """更新项目"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "项目不存在", 404)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "项目更新成功", "id": project_id}


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """删除项目"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "项目不存在", 404)

    db.delete(project)
    db.commit()
    return {"message": "项目已删除"}


@router.post("/{project_id}/upload")
async def upload_project_source(project_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """上传项目源代码（Zip 压缩包），自动解压并设置源码路径"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "项目不存在", 404)

    # 验证文件格式
    if not file.filename or not file.filename.endswith(".zip"):
        raise error_response(ErrorCode.INVALID_FORMAT, "仅支持 .zip 格式", 400)

    # 创建上传目录
    upload_dir = os.path.join(settings.GENERATED_TEST_DIR, "..", "uploaded_source", str(project_id))
    upload_dir = os.path.abspath(upload_dir)
    os.makedirs(upload_dir, exist_ok=True)

    # 清空旧文件
    for item in os.listdir(upload_dir):
        item_path = os.path.join(upload_dir, item)
        try:
            if os.path.isfile(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        except Exception as e:
            logger.warning(f"清理旧文件失败: {e}")

    # 保存上传的 zip
    zip_path = os.path.join(upload_dir, "source.zip")
    content = await file.read()
    with open(zip_path, "wb") as f:
        f.write(content)

    # 解压
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(upload_dir)
        os.remove(zip_path)  # 删除 zip 包
        logger.info(f"源码已解压到: {upload_dir}")
    except zipfile.BadZipFile:
        os.remove(zip_path)
        raise error_response(ErrorCode.INVALID_FORMAT, "无效的 Zip 文件", 400)

    # 更新项目的源码路径
    project.source_code_path = upload_dir
    project.updated_at = datetime.now(timezone.utc)
    db.commit()

    # 统计文件数
    file_count = 0
    for root, dirs, files in os.walk(upload_dir):
        dirs[:] = [d for d in dirs if not d.startswith((".", "__pycache__", "node_modules"))]
        file_count += len(files)

    logger.info(f"项目 {project_id} 源代码上传完成，共 {file_count} 个文件")
    return {
        "message": f"源码上传成功，共 {file_count} 个文件",
        "source_code_path": upload_dir,
        "file_count": file_count,
    }


# ========== Prompt 模板 API ==========

class TemplateCreate(BaseModel):
    provider: str = ""
    task_type: str
    name: str
    template_body: str
    is_default: bool = False


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    template_body: Optional[str] = None
    provider: Optional[str] = None
    is_default: Optional[bool] = None


@router.get("/{project_id}/templates")
def list_templates(project_id: int, db: Session = Depends(get_db)):
    """获取项目的 Prompt 模板列表"""
    from backend.database import PromptTemplate
    templates = db.query(PromptTemplate).filter(
        PromptTemplate.project_id == project_id
    ).all()
    return {
        "items": [
            {
                "id": t.id, "project_id": t.project_id, "provider": t.provider,
                "task_type": t.task_type, "name": t.name,
                "template_body": t.template_body, "is_default": t.is_default,
                "created_at": t.created_at.isoformat() if t.created_at else "",
                "updated_at": t.updated_at.isoformat() if t.updated_at else "",
            }
            for t in templates
        ],
    }


@router.post("/{project_id}/templates")
def create_template(project_id: int, data: TemplateCreate, db: Session = Depends(get_db)):
    """创建 Prompt 模板（含 Jinja2 语法校验）"""
    from backend.database import PromptTemplate
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "项目不存在", 404)
    try:
        render_prompt_template(data.template_body)
    except Exception as e:
        raise error_response(ErrorCode.INVALID_FORMAT, f"模板语法错误: {e}", 400)

    template = PromptTemplate(
        project_id=project_id, provider=data.provider, task_type=data.task_type,
        name=data.name, template_body=data.template_body, is_default=data.is_default,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return {"id": template.id, "message": "模板创建成功"}


@router.put("/{project_id}/templates/{template_id}")
def update_template(project_id: int, template_id: int, data: TemplateUpdate, db: Session = Depends(get_db)):
    """更新 Prompt 模板"""
    from backend.database import PromptTemplate
    template = db.query(PromptTemplate).filter(
        PromptTemplate.id == template_id, PromptTemplate.project_id == project_id,
    ).first()
    if not template:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "模板不存在", 404)
    if data.template_body is not None:
        try:
            render_prompt_template(data.template_body)
        except Exception as e:
            raise error_response(ErrorCode.INVALID_FORMAT, f"模板语法错误: {e}", 400)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)
    db.commit()
    return {"message": "模板更新成功"}


@router.delete("/{project_id}/templates/{template_id}")
def delete_template(project_id: int, template_id: int, db: Session = Depends(get_db)):
    """删除 Prompt 模板"""
    from backend.database import PromptTemplate
    template = db.query(PromptTemplate).filter(
        PromptTemplate.id == template_id, PromptTemplate.project_id == project_id,
    ).first()
    if not template:
        raise error_response(ErrorCode.RESOURCE_NOT_FOUND, "模板不存在", 404)
    db.delete(template)
    db.commit()
    return {"message": "模板已删除"}
