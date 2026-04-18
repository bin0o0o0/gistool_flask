"""地图渲染 API。

主接口：

    POST /api/render

这个接口做的是“HTTP 层”的工作：

1. 接收 Apifox 或前端传来的 JSON。
2. 校验 JSON 必要字段是否齐全、枚举值是否合法。
3. 把 `output_dir` 和 `template_project` 从请求参数中拆出来。
4. 调用真正的渲染器 `ArcPyRenderer.render()`。
5. 把渲染结果包装成统一 JSON 响应。

这里有一个很重要的分层原则：

- `render.py` 只关心 HTTP、参数、返回值。
- `arcpy_renderer.py` 才关心 ArcPy、图层、符号、导出 PNG。

这样你学习时可以先看这个文件理解接口，再看 ArcPy 文件理解 GIS 细节。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, request

from app.core.constants import (
    BASemaps,
    LABEL_POSITIONS,
    STATION_SYMBOL_COLOR_PRESETS,
    STATION_SYMBOL_LEGACY_PRESETS,
    STATION_SYMBOL_SHAPES,
)
from app.utils.responses import error_response, success_response


render_bp = Blueprint("render", __name__)


class ValidationError(ValueError):
    """请求参数校验失败。

    单独定义这个异常，是为了和程序内部错误区分开：
    - ValidationError：调用方请求写错了，返回 400。
    - 其他 Exception：后端执行时出错，返回 500。
    """

    pass


@render_bp.post("")
def render_map():
    """执行一次同步地图渲染。

    当前版本没有数据库和异步任务，所以请求会一直等到 ArcPy 出图完成后再返回。
    对 Apifox 调试来说，这种同步方式最直观：发一个请求，立刻看到结果路径。
    """
    # 只接受 JSON 请求。Apifox 里 Body 类型请选择 raw JSON。
    if not request.is_json:
        return error_response("Expected JSON request body.", 400)

    payload = request.get_json() or {}
    try:
        # 把 HTTP 请求体转换为渲染器需要的三个参数：
        # - job_config：地图标题、输入文件、样式等业务配置
        # - output_dir：本次输出目录
        # - template_project：ArcGIS Pro 模板 aprx
        job_config, output_dir, template_project = _build_render_request(payload)
    except ValidationError as exc:
        return error_response(str(exc), 400)

    # 测试时会把 FakeRenderer 放进 app.extensions["renderer"]。
    # 真实运行时没有注入 renderer，就创建 ArcPyRenderer。
    renderer = current_app.extensions.get("renderer")
    if renderer is None:
        from app.gis.render import ArcPyRenderer

        renderer = ArcPyRenderer()

    try:
        # 真正耗时的出图动作在这里发生。
        # 如果 ArcPy 报错，ArcPyRenderer 通常会返回 failed result；
        # 这里的 except 兜底处理更上层的意外异常。
        result = renderer.render(
            job_config=job_config,
            output_dir=output_dir,
            template_project=template_project,
        )
    except Exception as exc:
        return error_response(str(exc), 500)

    return success_response(result)


def _build_render_request(payload: dict[str, Any]) -> tuple[dict[str, Any], Path, Path]:
    """把原始请求 JSON 转换成渲染器参数。

    为什么要拆出 `output_dir` 和 `template_project`？
        它们是“运行控制参数”，不是地图内容本身。
        ArcPyRenderer 关心输出到哪里、用哪个模板；
        而 `job_config` 只保留地图标题、图层、样式等业务配置。
    """
    _validate_render_payload(payload)
    config = current_app.extensions["app_config"]

    output_dir = _resolve_output_dir(payload["output_dir"], config.output_folder)
    template_project = _resolve_template_project(payload.get("template_project"), config.arcpy_template_project)

    job_config = {
        key: value
        for key, value in payload.items()
        # 这两个字段不传给 ArcPy 的地图配置，避免渲染层误以为它们是地图属性。
        if key not in {"output_dir", "template_project"}
    }
    return job_config, output_dir, template_project


def _resolve_output_dir(value: str, default_root: Path) -> Path:
    """解析本次输出目录。

    - 如果请求传绝对路径，例如 `D:/xxx/out1`，就直接使用。
    - 如果请求传相对路径，例如 `demo_001`，就放到默认 OUTPUT_FOLDER 下。
    """
    if not value:
        raise ValidationError("Missing output_dir.")
    path = Path(value)
    if not path.is_absolute():
        path = default_root / path
    return path.resolve()


def _resolve_template_project(value: str | None, default_template: Path | None) -> Path:
    """解析 ArcGIS Pro 模板工程路径。

    请求里的 `template_project` 优先级最高；如果没传，就用应用配置里的默认模板。
    """
    template_project = Path(value).resolve() if value else default_template
    if template_project is None:
        raise ValidationError("Missing template_project or ARCPY_TEMPLATE_PROJECT.")
    return template_project


def _validate_render_payload(payload: dict[str, Any]) -> None:
    """校验出图请求的整体结构。

    这里做“尽早失败”的校验：能在进入 ArcPy 前发现的问题，就不要拖到
    ArcPy 执行阶段才报错。ArcPy 的错误通常比较长、比较 GIS 化，
    对接口调用者不如这里的错误直观。
    """
    # 顶层字段代表一次出图请求的五大部分：
    # output_dir：输出路径
    # map_title：标题
    # output：尺寸/dpi
    # inputs：数据输入
    # layout：布局选项
    # style：样式选项
    required_top_level = {"output_dir", "map_title", "output", "inputs", "layout", "style"}
    missing = sorted(required_top_level - payload.keys())
    if missing:
        raise ValidationError(f"Missing required fields: {', '.join(missing)}")

    output = _require_dict(payload, "output")
    # width_px 和 height_px 当前主要是接口协议字段，真正导出尺寸更多由模板布局决定；
    # dpi 已经在 ArcPy exportToPNG 时使用。
    for field in ("width_px", "height_px", "dpi"):
        if field not in output:
            raise ValidationError(f"Missing output.{field}")

    inputs = _require_dict(payload, "inputs")
    # 本项目当前固定需要三个业务输入：
    # - basin_boundary：流域边界，面数据
    # - river_network：河流，线数据
    # - station_layers：站点 Excel，可以有多组
    for field in ("basin_boundary", "river_network", "station_layers"):
        if field not in inputs:
            raise ValidationError(f"Missing inputs.{field}")
    _require_path(inputs["basin_boundary"], "inputs.basin_boundary.path")
    _require_path(inputs["river_network"], "inputs.river_network.path")

    station_layers = inputs["station_layers"]
    # 至少需要一组站点图层，这样当前“4 个站点、两种样式”的用例能被保护。
    if not isinstance(station_layers, list) or not station_layers:
        raise ValidationError("inputs.station_layers must contain at least one item.")

    layout = _require_dict(payload, "layout")
    basemap = layout.get("basemap")
    # basemap 必须来自常量列表，避免前端或 Apifox 写错字符串。
    if basemap not in BASemaps:
        raise ValidationError("layout.basemap is not supported.")

    for index, layer in enumerate(station_layers):
        _validate_station_layer(layer, index)


def _validate_station_layer(layer: Any, index: int) -> None:
    """校验单个站点图层配置。

    一个 station_layer 对应一个 Excel 文件，会被 ArcPy 转成一个点图层。
    如果要两种站点样式，就传两个 station_layer：
    一个绿色圆形，一个红色三角形。
    """
    if not isinstance(layer, dict):
        raise ValidationError(f"inputs.station_layers[{index}] must be an object.")
    # 这些字段是 Excel 转点图层和标注必需的信息：
    # path：Excel 路径
    # sheet_name：工作表名称
    # x_field/y_field：经纬度字段
    # name_field：标注字段
    # layer_name：加入地图后的图层名
    # symbol/label：符号和标注样式
    for field in (
        "path",
        "sheet_name",
        "x_field",
        "y_field",
        "name_field",
        "layer_name",
        "symbol",
        "label",
    ):
        if field not in layer:
            raise ValidationError(f"Missing station layer field: {field}")

    _require_path(layer, f"inputs.station_layers[{index}].path")
    symbol = _require_dict(layer, "symbol")
    preset = symbol.get("preset")
    # 新版推荐用 shape/color_preset/color 分开描述站点符号；
    # preset 只作为旧版请求的兼容字段保留。
    if preset and preset not in STATION_SYMBOL_LEGACY_PRESETS:
        raise ValidationError(f"Unsupported station symbol preset: {preset}")

    shape = symbol.get("shape")
    if shape and shape not in STATION_SYMBOL_SHAPES:
        raise ValidationError(f"Unsupported station symbol shape: {shape}")

    color_preset = symbol.get("color_preset")
    if color_preset and color_preset not in STATION_SYMBOL_COLOR_PRESETS:
        raise ValidationError(f"Unsupported station symbol color preset: {color_preset}")

    label = _require_dict(layer, "label")
    position = label.get("position")
    # 先校验 position，后续即使增强标注偏移，也不会破坏接口协议。
    if position not in LABEL_POSITIONS:
        raise ValidationError(f"Unsupported label.position: {position}")


def _require_dict(payload: dict[str, Any], field: str) -> dict[str, Any]:
    """读取某个字段，并要求它必须是 JSON object。"""
    value = payload.get(field)
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be an object.")
    return value


def _require_path(payload: Any, field: str) -> None:
    """要求某个配置对象里必须有 path 字段。"""
    if not isinstance(payload, dict) or not payload.get("path"):
        raise ValidationError(f"Missing {field}.")
