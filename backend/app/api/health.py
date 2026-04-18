"""健康检查接口。

这个接口通常是调试后端时第一个访问的地址：

    GET /api/health

如果它能返回 200，说明 Flask 服务至少已经启动成功；
返回体里的路径还能帮助确认当前后端使用的 output 目录和 aprx 模板。
"""

from __future__ import annotations

from flask import Blueprint, current_app

from app.utils.responses import success_response


health_bp = Blueprint("health", __name__)


@health_bp.get("")
def healthcheck():
    """返回服务运行状态和关键配置。"""
    # app_config 是在 create_app() 中放进 current_app.extensions 的配置对象。
    config = current_app.extensions["app_config"]
    return success_response(config.to_health_payload())
