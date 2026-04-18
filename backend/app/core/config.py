"""应用配置集中管理。

这个文件解决一个很实际的问题：路径和环境变量不要散落在各个接口里。
后端启动时统一读取配置，后续 API 和渲染器都从同一个配置对象取值。

当前项目没有数据库，所以配置项很少：

- 输出目录：渲染结果写到哪里。
- ArcGIS Pro 模板工程：使用哪个 `.aprx`。
- 前端地址：以后接浏览器前端时给 CORS 使用。
- renderer：测试专用，可注入假的渲染器。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# 默认使用你已经准备好的 ArcGIS Pro 工程。
# 如果以后要换模板，不需要改代码，设置环境变量 ARCPY_TEMPLATE_PROJECT 即可。
DEFAULT_TEMPLATE_PROJECT = r"D:\work\2026\arcgis_file\gistool_test\gistool_test.aprx"


@dataclass(frozen=True)
class AppConfig:
    """应用运行配置。

    `frozen=True` 表示对象创建后不应该再被修改。这样配置会更可预测：
    启动时确定一次，运行过程中只读取，不到处改。
    """

    # 所有出图结果的默认根目录。请求里也可以传绝对 output_dir 覆盖。
    output_folder: Path

    # ArcGIS Pro 模板工程路径。渲染时会复制一份到 output_dir，避免改坏原模板。
    arcpy_template_project: Path | None

    # 预留给浏览器前端跨域使用。Apifox 调接口不依赖它。
    frontend_url: str

    # 测试钩子：单元测试传 FakeRenderer，真实运行保持 None。
    renderer: Any | None = None

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any] | None = None) -> "AppConfig":
        """从 Flask 配置覆盖项和环境变量创建配置对象。

        优先级：
            1. `mapping` 中显式传入的值，主要给测试用。
            2. 环境变量，主要给本地/服务器部署用。
            3. 代码里的默认值。
        """
        values = mapping or {}

        # 默认输出到项目根目录的 output 文件夹。
        # `.resolve()` 会把相对路径变成绝对路径，后续日志和接口返回更清楚。
        output_folder = Path(
            values.get("OUTPUT_FOLDER")
            or os.getenv("OUTPUT_FOLDER")
            or Path.cwd() / "output"
        ).resolve()

        # 模板工程可以由单次测试覆盖，也可以由环境变量覆盖。
        template_value = (
            values.get("ARCPY_TEMPLATE_PROJECT")
            or os.getenv("ARCPY_TEMPLATE_PROJECT")
            or DEFAULT_TEMPLATE_PROJECT
        )
        template_project = Path(template_value).resolve() if template_value else None

        return cls(
            output_folder=output_folder,
            arcpy_template_project=template_project,
            frontend_url=values.get("FRONTEND_URL") or os.getenv("FRONTEND_URL", "*"),
            renderer=values.get("RENDERER"),
        )

    def ensure_directories(self) -> None:
        """创建运行所需目录。

        这里目前只需要 output_folder。以后如果增加 uploads/tmp，也应在这里集中创建。
        """
        self.output_folder.mkdir(parents=True, exist_ok=True)

    def to_flask_mapping(self) -> dict[str, Any]:
        """转换成 Flask app.config 可直接加载的字典。
            self.output_folder 在 AppConfig 里是 Path 类型，
            但 Flask 的 app.config 更适合存普通字符串，而不是 Path 对象。
        """
        return {
            "OUTPUT_FOLDER": str(self.output_folder),
            "ARCPY_TEMPLATE_PROJECT": (
                str(self.arcpy_template_project) if self.arcpy_template_project else None
            ),
            "FRONTEND_URL": self.frontend_url,
        }

    def to_health_payload(self) -> dict[str, Any]:
        """健康检查接口返回的数据。

        这些信息方便你在 Apifox 里确认：
        - 后端是否启动成功。
        - 当前使用哪个 output 目录。
        - 当前使用哪个 aprx 模板。
        """
        return {
            "service": "gis-flask-study-backend",
            "status": "ok",
            "output_folder": str(self.output_folder),
            "arcpy_template_project": (
                str(self.arcpy_template_project) if self.arcpy_template_project else None
            ),
            "runtime": "ArcPy in-process",
        }


def get_config(mapping: dict[str, Any] | None = None) -> AppConfig:
    """配置工厂函数。

    单独包一层函数，是为了让 `app/__init__.py` 不关心 AppConfig 的创建细节。
    AppConfig.from_mapping(...)这样写也行，但是写get_config(...)更规范
    """
    return AppConfig.from_mapping(mapping)
