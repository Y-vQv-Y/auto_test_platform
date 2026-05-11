"""自动回滚 - 当测试异常时自动恢复环境到初始状态"""
import os
import json
import shutil
import tempfile
from datetime import datetime
from typing import Optional
from loguru import logger


class AutoRollback:
    """自动回滚管理器"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._snapshots = {}

    def create_snapshot(self, snapshot_id: str, target_dir: str) -> bool:
        """
        创建目录快照，用于回滚

        Args:
            snapshot_id: 快照标识
            target_dir: 目标目录

        Returns:
            bool: 是否成功
        """
        if not self.enabled:
            logger.info("回滚功能未启用，跳过快照创建")
            return True

        if not os.path.exists(target_dir):
            logger.warning(f"快照目录不存在: {target_dir}")
            return False

        try:
            snapshot_dir = os.path.join(tempfile.gettempdir(), "snapshots", snapshot_id)
            os.makedirs(snapshot_dir, exist_ok=True)

            # 复制目录到快照
            shutil.copytree(target_dir, f"{snapshot_dir}/data", dirs_exist_ok=True)

            # 记录文件列表和校验信息
            manifest = self._build_manifest(target_dir)
            with open(f"{snapshot_dir}/manifest.json", "w") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            self._snapshots[snapshot_id] = {
                "id": snapshot_id,
                "target": target_dir,
                "created_at": datetime.now().isoformat(),
                "manifest": manifest,
            }

            self._log("rollback", target_dir, "snapshot_created", f"快照创建成功: {snapshot_id}")
            logger.info(f"快照创建成功: {snapshot_id}")
            return True

        except Exception as e:
            logger.error(f"创建快照失败: {e}")
            self._log("rollback", target_dir, "snapshot_failed", str(e))
            return False

    def rollback(self, snapshot_id: str) -> bool:
        """
        回滚到快照状态

        Args:
            snapshot_id: 快照标识

        Returns:
            bool: 是否成功
        """
        if not self.enabled:
            return True

        snapshot_info = self._snapshots.get(snapshot_id)
        if not snapshot_info:
            logger.warning(f"快照不存在: {snapshot_id}")
            return False

        try:
            target_dir = snapshot_info["target"]
            snapshot_dir = os.path.join(tempfile.gettempdir(), "snapshots", snapshot_id)

            # 移除当前目录
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)

            # 恢复快照
            shutil.copytree(f"{snapshot_dir}/data", target_dir)

            self._log("rollback", target_dir, "rolled_back", f"回滚成功: {snapshot_id}")
            logger.info(f"回滚成功: {snapshot_id}")
            return True

        except Exception as e:
            logger.error(f"回滚失败: {e}")
            self._log("rollback", snapshot_id, "rollback_failed", str(e))
            return False

    def _build_manifest(self, directory: str) -> dict:
        """构建目录清单"""
        manifest = {
            "files": [],
            "total_size": 0,
        }
        for root, dirs, files in os.walk(directory):
            for f in files:
                try:
                    fpath = os.path.join(root, f)
                    stat = os.stat(fpath)
                    manifest["files"].append({
                        "path": os.path.relpath(fpath, directory),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    })
                    manifest["total_size"] += stat.st_size
                except Exception:
                    pass
        return manifest

    def _log(self, event_type: str, target: str, result: str, detail: str):
        from backend.database import SessionLocal, SecurityLog
        db = None
        try:
            db = SessionLocal()
            log = SecurityLog(
                event_type=event_type,
                target=target[:500],
                action="rollback",
                result=result,
                detail=detail[:1000],
            )
            db.add(log)
            db.commit()
        except Exception:
            pass
        finally:
            if db:
                db.close()