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
    # ArcGIS Pro 的 propy 有时不会自动加载项目虚拟环境或当前用户的 site-packages。
    # 这里先补项目 .venv，再补用户目录。这样 Flask 可以固定安装在项目 .venv 中，
    # 但进程仍然由 propy 启动，ArcPy 仍然来自 ArcGIS Pro Python。
    _ensure_runtime_site_packages()

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
    from app.api.uploads import uploads_bp

    app.register_blueprint(health_bp, url_prefix="/api/health")
    app.register_blueprint(options_bp, url_prefix="/api/render-options")
    app.register_blueprint(render_bp, url_prefix="/api/render")
    app.register_blueprint(uploads_bp, url_prefix="/api/uploads")


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


def _ensure_runtime_site_packages() -> None:
    """把项目和用户级 Python site-packages 加入搜索路径。

    背景:
        ArcGIS Pro 的 `propy.bat` 会启动 `arcgispro-py3` 环境。
        在一些电脑上，`propy` 默认只加载 ArcGIS Pro 环境自己的
        site-packages，不会加载项目 `.venv` 或当前用户目录下的 site-packages。

    为什么需要这个函数:
        Flask 可以安装在三类位置：

        1. 项目虚拟环境目录，例如
           `<项目根目录>\\.venv\\Lib\\site-packages`
        2. ArcGIS Pro Python 环境目录，例如
           `...\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\Lib\\site-packages`
        3. 当前用户目录，例如
           `C:\\Users\\<用户名>\\AppData\\Roaming\\Python\\Python39\\site-packages`

        如果 Flask 在 ArcGIS Pro 环境目录，通常不需要这个函数。
        如果 Flask 在项目 `.venv` 或用户目录，这里主动调用 `site.addsitedir()`，
        让 `import flask` 能找到它。

    通用性:
        项目 `.venv` 路径根据当前文件位置自动向上推导，不写死盘符。
        用户 site-packages 由 `site.getusersitepackages()` 自动计算，不写死用户名。

    注意:
        这个函数只是“让 propy 能找到项目 .venv 里的 Flask”，不会自动安装 Flask。
        新电脑部署时仍然要先运行安装脚本，把 Flask 安装进项目 `.venv`。
    """
    import site
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    candidates = [
        _project_venv_site_packages(project_root),
        Path(site.getusersitepackages()),
    ]
    _add_existing_site_package_dirs(candidates)


def _project_venv_site_packages(project_root) -> "Path":
    """计算项目 `.venv` 的 site-packages 路径。

    当前项目主要面向 Windows + ArcGIS Pro，所以优先使用 Windows venv 路径：
    `.venv\\Lib\\site-packages`。
    """
    from pathlib import Path

    return Path(project_root) / ".venv" / "Lib" / "site-packages"


def _add_existing_site_package_dirs(candidates) -> None:
    """把存在的 site-packages 目录加入 sys.path。

    使用 `site.addsitedir()` 而不是简单 `sys.path.append()`，是因为
    addsitedir 会处理 `.pth` 文件，更接近 Python 正常加载 site-packages 的行为。

    这里还有一个很重要的小细节：项目 `.venv` 必须排在用户 site-packages 前面。
    如果某台电脑用户目录里也装过 Flask，我们仍然希望优先使用项目内固定的 Flask，
    这样部署结果更稳定，不会被用户以前装过的包版本影响。
    """
    import site
    import sys
    from pathlib import Path

    existing_paths = []
    for candidate in candidates:
        candidate_path = Path(candidate)
        candidate_text = str(candidate_path)
        if candidate_path.exists():
            site.addsitedir(candidate_text)

            # 先记录，稍后统一调整顺序，保证传入 candidates 的顺序就是最终优先级。
            existing_paths.append(candidate_text)

    for candidate_text in reversed(existing_paths):
        while candidate_text in sys.path:
            sys.path.remove(candidate_text)
        sys.path.insert(0, candidate_text)


def _ensure_user_site_packages() -> None:
    """兼容旧名称：只补当前用户的 site-packages。

    现在 `create_app()` 已经改用 `_ensure_runtime_site_packages()`。
    这个函数保留给旧测试或外部临时脚本，避免私有函数名变化导致导入失败。
    """
    import site
    from pathlib import Path

    user_site = Path(site.getusersitepackages())
    _add_existing_site_package_dirs([user_site])
