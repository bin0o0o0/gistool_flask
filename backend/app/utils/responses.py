"""统一 JSON 响应工具。

后端接口统一返回这种结构，Apifox 看起来会比较清楚：

成功：
    {"success": true, "data": {...}}

失败：
    {"success": false, "message": "..."}
"""

from __future__ import annotations

from flask import jsonify


def success_response(data: dict | list | None = None, message: str | None = None, status_code: int = 200):
    """构造成功响应。

    Args:
        data: 真正的业务数据，例如渲染结果。
        message: 可选的人类可读提示。
        status_code: HTTP 状态码，默认 200。
    """
    payload: dict = {"success": True}
    if data is not None:
        payload["data"] = data
    if message is not None:
        payload["message"] = message
    return jsonify(payload), status_code


def error_response(message: str, status_code: int = 400):
    """构造失败响应。"""
    return jsonify({"success": False, "message": message}), status_code
