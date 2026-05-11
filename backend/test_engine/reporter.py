"""测试报告生成器"""
import os
import json
from datetime import datetime
from typing import Optional
from jinja2 import Template
from loguru import logger

from backend.database import SessionLocal, TestRun, TestResult
from backend.config import settings


REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>测试报告 - {{ run.name }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #0a0e1a; color: #e0e0e0; min-height: 100vh; }
        .header { background: linear-gradient(135deg, #0f1923 0%, #1a1a2e 100%);
                  border-bottom: 1px solid rgba(0, 255, 255, 0.1);
                  padding: 30px 40px; position: relative; overflow: hidden; }
        .header::before { content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0;
                          background: radial-gradient(ellipse at 30% 50%, rgba(0,255,255,0.05) 0%, transparent 60%); }
        .header h1 { font-size: 28px; color: #00e5ff; margin-bottom: 8px; position: relative; }
        .header .meta { color: #8899aa; font-size: 14px; position: relative; }
        .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                   gap: 16px; padding: 30px 40px; }
        .stat-card { background: linear-gradient(135deg, rgba(15,25,35,0.9), rgba(26,26,46,0.9));
                     border: 1px solid rgba(0,255,255,0.1); border-radius: 12px;
                     padding: 20px; text-align: center; }
        .stat-card .value { font-size: 36px; font-weight: bold; }
        .stat-card .label { font-size: 12px; color: #8899aa; margin-top: 4px; text-transform: uppercase; }
        .stat-card.passed .value { color: #00e676; }
        .stat-card.failed .value { color: #ff1744; }
        .stat-card.error .value { color: #ff9100; }
        .stat-card.total .value { color: #448aff; }
        .stat-card.duration .value { color: #e040fb; font-size: 24px; }
        .results { padding: 0 40px 40px; }
        .result-item { background: rgba(15,25,35,0.8); border: 1px solid rgba(0,255,255,0.08);
                       border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
        .result-header { display: flex; justify-content: space-between; align-items: center;
                         padding: 16px 20px; cursor: pointer; }
        .result-header .name { font-size: 14px; font-weight: 500; }
        .result-header .status { padding: 4px 12px; border-radius: 12px; font-size: 12px; }
        .status-passed { background: rgba(0,230,118,0.15); color: #00e676; }
        .status-failed { background: rgba(255,23,68,0.15); color: #ff1744; }
        .status-error { background: rgba(255,145,0,0.15); color: #ff9100; }
        .result-detail { padding: 0 20px 20px; display: none; }
        .result-detail.open { display: block; }
        .result-detail pre { background: rgba(0,0,0,0.3); padding: 16px; border-radius: 8px;
                             font-size: 12px; overflow-x: auto; margin-top: 8px; }
        .footer { text-align: center; padding: 20px; color: #556677; font-size: 12px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔬 {{ run.name }}</h1>
        <div class="meta">
            项目ID: {{ run.project_id }} |
            触发方式: {{ run.trigger_mode }} |
            执行时间: {{ run.created_at }} |
            耗时: {{ "%.2f"|format(run.duration_seconds or 0) }}秒
        </div>
    </div>
    <div class="summary">
        <div class="stat-card total"><div class="value">{{ run.total_cases or 0 }}</div><div class="label">总用例</div></div>
        <div class="stat-card passed"><div class="value">{{ run.passed_cases or 0 }}</div><div class="label">通过</div></div>
        <div class="stat-card failed"><div class="value">{{ run.failed_cases or 0 }}</div><div class="label">失败</div></div>
        <div class="stat-card error"><div class="value">{{ run.error_cases or 0 }}</div><div class="label">错误</div></div>
        <div class="stat-card duration"><div class="value">{{ "%.1f"|format(run.duration_seconds or 0) }}s</div><div class="label">总耗时</div></div>
    </div>
    <div class="results">
        <h3 style="margin-bottom:16px;color:#00e5ff;">测试结果明细</h3>
        {% for result in results %}
        <div class="result-item">
            <div class="result-header" onclick="this.nextElementSibling.classList.toggle('open')">
                <span class="name">{{ result.name }}</span>
                <span class="status status-{{ result.status }}">{{ result.status }}</span>
            </div>
            <div class="result-detail">
                <div>耗时: {{ "%.2f"|format(result.duration_seconds or 0) }}s</div>
                {% if result.error_message %}
                <pre>{{ result.error_message }}</pre>
                {% endif %}
                {% if result.error_traceback %}
                <pre>{{ result.error_traceback }}</pre>
                {% endif %}
                {% if result.log_text %}
                <pre>{{ result.log_text }}</pre>
                {% endif %}
            </div>
        </div>
        {% endfor %}
    </div>
    <div class="footer">AI 自动测试平台 - {{ now }}</div>
    <script>
        document.querySelectorAll('.result-header').forEach(function(h) {
            h.addEventListener('click', function() {
                var detail = this.nextElementSibling;
                if (detail) {
                    detail.classList.toggle('open');
                }
            });
        });
    </script>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            document.querySelectorAll('.result-header').forEach(function(h) {
                h.addEventListener('click', function() {
                    var detail = this.nextElementSibling;
                    if (detail) detail.classList.toggle('open');
                });
            });
        });
    </script>
</body>
</html>
"""


class TestReporter:
    """测试报告生成器"""

    @staticmethod
    def generate_html_report(run_id: int) -> Optional[str]:
        """生成 HTML 测试报告"""
        db = SessionLocal()
        try:
            run = db.query(TestRun).filter(TestRun.id == run_id).first()
            if not run:
                logger.error(f"测试运行记录不存在: {run_id}")
                return None

            results = db.query(TestResult).filter(
                TestResult.test_run_id == run_id
            ).all()

            template = Template(REPORT_TEMPLATE)
            html = template.render(
                run=run,
                results=results,
                now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

            # 保存报告
            report_dir = os.path.join(settings.REPORT_DIR, f"run_{run_id}")
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, "report.html")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html)

            # 更新数据库中的报告路径
            run.report_path = report_path
            run.report_html = html
            db.commit()

            logger.info(f"报告已生成: {report_path}")
            return report_path

        except Exception as e:
            logger.error(f"生成报告失败: {e}")
            return None
        finally:
            db.close()

    @staticmethod
    def get_report_data(run_id: int) -> dict:
        """获取报告数据"""
        db = SessionLocal()
        try:
            run = db.query(TestRun).filter(TestRun.id == run_id).first()
            if not run:
                return {}

            results = db.query(TestResult).filter(
                TestResult.test_run_id == run_id
            ).all()

            return {
                "run": {
                    "id": run.id,
                    "name": run.name,
                    "project_id": run.project_id,
                    "status": run.status,
                    "trigger_mode": run.trigger_mode,
                    "total_cases": run.total_cases,
                    "passed_cases": run.passed_cases,
                    "failed_cases": run.failed_cases,
                    "error_cases": run.error_cases,
                    "duration_seconds": run.duration_seconds,
                    "created_at": run.created_at.isoformat() if run.created_at else "",
                    "started_at": run.started_at.isoformat() if run.started_at else "",
                    "completed_at": run.completed_at.isoformat() if run.completed_at else "",
                },
                "results": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "status": r.status,
                        "duration_seconds": r.duration_seconds,
                        "error_message": r.error_message,
                        "log_text": r.log_text,
                    }
                    for r in results
                ],
            }
        finally:
            db.close()
