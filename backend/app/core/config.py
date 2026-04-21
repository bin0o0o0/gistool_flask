"""应用配置集中管理。

这个文件解决一个很实际的问题：路径和环境变量不要散落在各个接口里。
后端启动时统一读取配置，后续 API 和渲染器都从同一个配置对象取值。

当前项目没有数据库，所以配置项很少：

- 输出目录：渲染结果写到哪里。
- ArcGIS Pro 模板工程：使用哪个 `.aprx`。
- 上传目录：前端上传的模板、边界、河流和站点 Excel 保存到哪里。
- 前端地址：以后接浏览器前端时给 CORS 使用。
- renderer：测试专用，可注入假的渲染器。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _is_truthy(value: Any) -> bool:
    """把配置值转换成布尔值。

    环境变量都是字符串，所以这里统一支持常见写法：
    true/1/yes/on 表示开启，其余值都按关闭处理。
    """
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    """应用运行配置。

    `frozen=True` 表示对象创建后不应该再被修改。这样配置会更可预测：
    启动时确定一次，运行过程中只读取，不到处改。
    """

    # 所有出图结果的默认根目录。默认情况下，前端只能把结果写到这个目录下面。
    output_folder: Path

    # 前端上传文件的根目录。上传接口会按日期和 uuid 再建子目录，避免文件互相覆盖。
    upload_folder: Path

    # ArcGIS Pro 模板工程路径。渲染时会复制一份到 output_dir，避免改坏原模板。
    arcpy_template_project: Path | None

    # ArcGIS Pro Python 启动脚本路径。后续前端配置页可以读取/填写这个路径。
    arcgis_propy_path: Path | None

    # 是否允许请求体传绝对 output_dir。默认关闭，只建议本地调试时临时开启。
    allow_absolute_output_dir: bool

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
            3. 如果没有配置模板，则保持 None，由 `/api/render` 在缺少 template_project 时返回 400。

        注意：
            不要在代码里写死某台电脑上的 `.aprx` 路径。
            换电脑、部署服务器或交给前端调用时，模板路径应来自请求体 `template_project`
            或环境变量 `ARCPY_TEMPLATE_PROJECT`。
        """
        values = mapping or {}

        # 默认输出到项目根目录的 output 文件夹。
        # `.resolve()` 会把相对路径变成绝对路径，后续日志和接口返回更清楚。
        output_folder = Path(
            values.get("OUTPUT_FOLDER")
            or os.getenv("OUTPUT_FOLDER")
            or Path.cwd() / "output"
        ).resolve()
        upload_folder = Path(
            values.get("UPLOAD_FOLDER")
            or os.getenv("UPLOAD_FOLDER")
            or Path.cwd() / "uploads"
        ).resolve()

        # 模板工程可以由单次测试覆盖，也可以由环境变量覆盖。
        # 这里不设置代码默认值，是为了避免把开发电脑上的绝对路径带到其他部署环境。
        template_value = (
            values.get("ARCPY_TEMPLATE_PROJECT")
            or os.getenv("ARCPY_TEMPLATE_PROJECT")
        )
        template_project = Path(template_value).resolve() if template_value else None
        propy_value = values.get("ARCGIS_PROPY") or os.getenv("ARCGIS_PROPY")
        propy_path = Path(propy_value).resolve() if propy_value else None

        return cls(
            output_folder=output_folder,
            upload_folder=upload_folder,
            arcpy_template_project=template_project,
            arcgis_propy_path=propy_path,
            allow_absolute_output_dir=_is_truthy(
                values.get("ALLOW_ABSOLUTE_OUTPUT_DIR")
                or os.getenv("ALLOW_ABSOLUTE_OUTPUT_DIR")
            ),
            frontend_url=values.get("FRONTEND_URL") or os.getenv("FRONTEND_URL", "*"),
            renderer=values.get("RENDERER"),
        )

    def ensure_directories(self) -> None:
        """创建运行所需目录。

        output_folder 用于保存出图结果，upload_folder 用于保存前端上传的数据。
        两个目录都在启动时创建，避免第一次请求时才因为目录不存在而失败。
        """
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self.upload_folder.mkdir(parents=True, exist_ok=True)

    def to_flask_mapping(self) -> dict[str, Any]:
        """转换成 Flask app.config 可直接加载的字典。
            self.output_folder 在 AppConfig 里是 Path 类型，
            但 Flask 的 app.config 更适合存普通字符串，而不是 Path 对象。
        """
        return {
            "OUTPUT_FOLDER": str(self.output_folder),
            "UPLOAD_FOLDER": str(self.upload_folder),
            "ARCPY_TEMPLATE_PROJECT": (
                str(self.arcpy_template_project) if self.arcpy_template_project else None
            ),
            "ARCGIS_PROPY": str(self.arcgis_propy_path) if self.arcgis_propy_path else None,
            "ALLOW_ABSOLUTE_OUTPUT_DIR": self.allow_absolute_output_dir,
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
            "upload_folder": str(self.upload_folder),
            "arcpy_template_project": (
                str(self.arcpy_template_project) if self.arcpy_template_project else None
            ),
            "arcgis_propy_path": (
                str(self.arcgis_propy_path) if self.arcgis_propy_path else None
            ),
            "allow_absolute_output_dir": self.allow_absolute_output_dir,
            "runtime": "ArcPy in-process",
        }


def get_config(mapping: dict[str, Any] | None = None) -> AppConfig:
    """配置工厂函数。

    单独包一层函数，是为了让 `app/__init__.py` 不关心 AppConfig 的创建细节。
    AppConfig.from_mapping(...)这样写也行，但是写get_config(...)更规范
    """
    return AppConfig.from_mapping(mapping)
