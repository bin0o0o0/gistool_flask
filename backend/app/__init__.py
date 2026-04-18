"""Flask 应用工厂。

Gitee 参考项目采用的就是这种结构：`run.py` 只负责启动，
`app/__init__.py` 负责创建应用、加载配置、注册蓝图。

本项目暂时不接数据库、不做登录认证，所以这里没有 SQLAlchemy/JWT/Migrate。
我们只保留最核心的三件事：

1. 读取配置。
2. 注册 API 路由。
3. 注册统一错误处理。
"""

from __future__ import annotations


def create_app(config_overrides: dict | None = None):
    """创建并返回 Flask 应用实例。

    Args:
        config_overrides: 测试或临时运行时传入的配置覆盖项。
            例如测试中会传入一个假的 renderer，避免真的启动 ArcPy。

    Returns:
        配置完成、蓝图注册完成的 Flask app。
    """
    # ArcGIS Pro 的 propy 有时不会自动加载“当前用户”的 site-packages。
    # 如果某台电脑把 Flask 安装到了用户目录而不是 ArcGIS Pro 环境目录，
    # 这里会把那个用户目录补进 sys.path。路径由 Python 自动计算，不写死用户名。
    _ensure_user_site_packages()

    # 延迟导入 Flask：这样 `from app.gis.render import ArcPyRenderer`
    # 这种只想使用渲染核心的代码，不会因为环境里缺 Flask 而失败。
    from flask import Flask

    app = Flask(__name__)

    from app.core.config import get_config

    # 统一把配置对象保存到 Flask 的 extensions 里。
    # extensions 原本就是 Flask 推荐给扩展或应用组件保存共享对象的地方。
    config = get_config(config_overrides)
    app.config.from_mapping(config.to_flask_mapping())
    app.extensions["app_config"] = config

    # 测试时可以注入 FakeRenderer；真实运行时不注入，就在接口里创建 ArcPyRenderer。
    if config.renderer is not None:
        app.extensions["renderer"] = config.renderer

    # 保证默认输出目录存在，避免第一次请求时因为目录不存在而失败。
    config.ensure_directories()

    # flask-cors 是可选依赖。Apifox 调试不需要 CORS；以后接浏览器前端时，
    # 如果安装了 flask-cors，这里会自动启用跨域支持。
    try:
        from flask_cors import CORS
    except ImportError:  # pragma: no cover - optional local-development dependency
        CORS = None
    if CORS is not None:
        CORS(app, resources={r"/api/*": {"origins": config.frontend_url}})

    _register_blueprints(app)
    _register_error_handlers(app)
    return app


def _register_blueprints(app) -> None:
    """注册所有 API 模块。

    Blueprint 可以理解为“路由分组”。例如 health.py 只放健康检查，
    render.py 只放出图接口。这样文件会比所有接口都塞进一个 app.py 更好读。
    """
    from app.api.health import health_bp
    from app.api.options import options_bp
    from app.api.render import render_bp

    app.register_blueprint(health_bp, url_prefix="/api/health")
    app.register_blueprint(options_bp, url_prefix="/api/render-options")
    app.register_blueprint(render_bp, url_prefix="/api/render")


def _register_error_handlers(app) -> None:
    """注册全局错误处理。

    这里处理的是 Flask 层面的常见 HTTP 错误。
    业务校验错误一般在具体 API 中主动返回 `error_response()`。
    """
    from app.utils.responses import error_response

    @app.errorhandler(400)
    def bad_request(error):
        return error_response(getattr(error, "description", "Bad request."), 400)

    @app.errorhandler(404)
    def not_found(_error):
        return error_response("Resource not found.", 404)

    @app.errorhandler(500)
    def internal_error(_error):
        return error_response("Internal server error.", 500)


def _ensure_user_site_packages() -> None:
    """把当前用户的 Python site-packages 加入搜索路径。

    背景:
        ArcGIS Pro 的 `propy.bat` 会启动 `arcgispro-py3` 环境。
        在一些电脑上，`propy` 默认只加载 ArcGIS Pro 环境自己的
        site-packages，不会加载当前用户目录下的 site-packages。

    为什么需要这个函数:
        Flask 可以安装在两类位置：

        1. ArcGIS Pro Python 环境目录，例如
           `...\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\Lib\\site-packages`
        2. 当前用户目录，例如
           `C:\\Users\\<用户名>\\AppData\\Roaming\\Python\\Python39\\site-packages`

        如果 Flask 在第 1 类位置，通常不需要这个函数。
        如果 Flask 在第 2 类位置，这里主动调用 `site.addsitedir()`，
        让 `import flask` 能找到它。

    通用性:
        这里没有写死任何电脑用户名或固定路径。
        `site.getusersitepackages()` 会根据当前电脑、当前用户、当前 Python 版本
        自动计算用户 site-packages 路径。

    注意:
        这个函数只是兼容补丁，不会自动安装 Flask。
        换到新电脑部署时，仍然需要先确保 ArcGIS Pro Python 能访问 Flask。
    """
    import site
    import sys
    from pathlib import Path

    user_site = Path(site.getusersitepackages())
    if user_site.exists() and str(user_site) not in sys.path:
        site.addsitedir(str(user_site))
