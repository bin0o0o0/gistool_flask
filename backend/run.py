"""Flask 后端启动入口。

这个文件故意保持很薄：真正的应用创建逻辑在 `app/__init__.py`
的 `create_app()` 里。这样做有两个好处：

1. Apifox / 浏览器调试时，可以直接运行这个文件启动服务。
2. 单元测试时，可以绕过真实端口，直接导入 `create_app()` 创建测试 app。

注意：本项目的方案 A 是“Flask 进程内直接调用 ArcPy”，所以生产调试时
不要用普通 Python 启动，而要用 ArcGIS Pro 自带的 `propy.bat`。
"""

from __future__ import annotations

import os

from app import create_app


# 创建 Flask app 实例。Flask 的命令行工具或 WSGI 服务器也可以复用这个变量。
app = create_app()


if __name__ == "__main__":
    # 这三个环境变量用于临时切换监听地址、端口和 debug 模式。
    # 例如：
    #   $env:FLASK_PORT="5050"
    #   propy.bat backend\run.py
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)
