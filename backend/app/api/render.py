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

from flask import Blueprint, current_app, request, send_file

from app.core.constants import (
    BASemaps,
    LABEL_POSITIONS,
    STATION_SYMBOL_COLOR_PRESETS,
    STATION_SYMBOL_LEGACY_PRESETS,
    STATION_SYMBOL_SHAPES,
)
from app.utils.responses import error_response, success_response


render_bp = Blueprint("render", __name__)
LEGEND_NAME_OVERRIDE_SOURCE_TYPES = {"basin", "river", "station_layer", "station_group"}


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


@render_bp.get("/file")
def render_file():
    """把已生成的 PNG 作为浏览器可访问的文件返回。

    `/api/render` 返回的是服务器本地路径，例如 `D:\\...\\map.png`。
    浏览器不能直接读取这个路径，所以前端需要通过这个只读接口预览图片。
    """
    raw_path = request.args.get("path")
    if not raw_path:
        return error_response("Missing path.", 400)

    config = current_app.extensions["app_config"]
    file_path = Path(raw_path).resolve()
    output_root = config.output_folder.resolve()
    try:
        file_path.relative_to(output_root)
    except ValueError:
        return error_response("Requested file must stay under OUTPUT_FOLDER.", 400)

    if not file_path.exists() or not file_path.is_file():
        return error_response("Requested file does not exist.", 404)
    if file_path.suffix.lower() != ".png":
        return error_response("Only PNG render outputs can be previewed.", 400)

    return send_file(file_path, mimetype="image/png")


def _build_render_request(payload: dict[str, Any]) -> tuple[dict[str, Any], Path, Path]:
    """把原始请求 JSON 转换成渲染器参数。

    为什么要拆出 `output_dir` 和 `template_project`？
        它们是“运行控制参数”，不是地图内容本身。
        ArcPyRenderer 关心输出到哪里、用哪个模板；
        而 `job_config` 只保留地图标题、图层、样式等业务配置。
    """
    _validate_render_payload(payload)
    config = current_app.extensions["app_config"]

    output_dir = _resolve_output_dir(
        payload["output_dir"],
        config.output_folder,
        config.allow_absolute_output_dir,
    )
    template_project = _resolve_template_project(payload.get("template_project"), config.arcpy_template_project)

    job_config = {
        key: value
        for key, value in payload.items()
        # 这两个字段不传给 ArcPy 的地图配置，避免渲染层误以为它们是地图属性。
        if key not in {"output_dir", "template_project"}
    }
    return job_config, output_dir, template_project


def _resolve_output_dir(value: str, default_root: Path, allow_absolute: bool = False) -> Path:
    """解析本次输出目录。

    默认只允许相对路径，例如 `demo_001`，并统一放到 OUTPUT_FOLDER 下面。
    这样前端不能把结果写到服务器任意目录。

    如果本地调试确实需要绝对路径，可以显式开启 ALLOW_ABSOLUTE_OUTPUT_DIR。
    """
    if not value:
        raise ValidationError("Missing output_dir.")
    default_root = default_root.resolve()
    path = Path(value)
    if path.is_absolute() and not allow_absolute:
        raise ValidationError(
            "output_dir must be a relative path under OUTPUT_FOLDER. "
            "Set ALLOW_ABSOLUTE_OUTPUT_DIR=true only for local debugging."
        )
    if not path.is_absolute():
        path = default_root / path
    resolved = path.resolve()
    if not allow_absolute:
        try:
            resolved.relative_to(default_root)
        except ValueError as exc:
            raise ValidationError("output_dir must stay under OUTPUT_FOLDER.") from exc
    return resolved


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
    # width_px / height_px / dpi 会传给 ArcPyRenderer。
    # 渲染器会把像素尺寸换算成布局页面尺寸，再用 dpi 导出 PNG，
    # 因此这三个字段共同决定最终图片的像素宽高。
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
    legend_style = layout.get("legend_style")
    if legend_style is not None:
        if not isinstance(legend_style, dict):
            raise ValidationError("layout.legend_style must be an object.")
        _validate_legend_name_overrides(legend_style.get("name_overrides"))

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

    points = layer.get("points")
    if points is not None:
        if not isinstance(points, list):
            raise ValidationError(f"inputs.station_layers[{index}].points must be a list.")
        for point_index, point in enumerate(points):
            _validate_station_point(point, index, point_index)


def _validate_station_point(point: Any, layer_index: int, point_index: int) -> None:
    """Validate one optional per-point station style override."""
    if not isinstance(point, dict):
        raise ValidationError(f"inputs.station_layers[{layer_index}].points[{point_index}] must be an object.")

    row_number = point.get("row_number")
    if not isinstance(row_number, int) or row_number < 2:
        raise ValidationError(
            f"inputs.station_layers[{layer_index}].points[{point_index}].row_number must be an Excel data row number."
        )

    symbol = point.get("symbol")
    if symbol is not None:
        if not isinstance(symbol, dict):
            raise ValidationError(
                f"inputs.station_layers[{layer_index}].points[{point_index}].symbol must be an object."
            )
        shape = symbol.get("shape")
        if shape and shape not in STATION_SYMBOL_SHAPES:
            raise ValidationError(f"Unsupported station point symbol shape: {shape}")
        color_preset = symbol.get("color_preset")
        if color_preset and color_preset not in STATION_SYMBOL_COLOR_PRESETS:
            raise ValidationError(f"Unsupported station point symbol color preset: {color_preset}")

    label = point.get("label")
    if label is not None:
        if not isinstance(label, dict):
            raise ValidationError(
                f"inputs.station_layers[{layer_index}].points[{point_index}].label must be an object."
            )
        position = label.get("position")
        if position and position not in LABEL_POSITIONS:
            raise ValidationError(f"Unsupported station point label.position: {position}")


def _validate_legend_name_overrides(name_overrides: Any) -> None:
    """Validate optional centralized legend rename mappings."""
    if name_overrides is None:
        return
    if not isinstance(name_overrides, list):
        raise ValidationError("layout.legend_style.name_overrides must be a list.")
    for index, override in enumerate(name_overrides):
        if not isinstance(override, dict):
            raise ValidationError(f"layout.legend_style.name_overrides[{index}] must be an object.")
        source_type = override.get("source_type")
        if source_type not in LEGEND_NAME_OVERRIDE_SOURCE_TYPES:
            raise ValidationError(f"Unsupported legend name override source_type: {source_type}")
        source_key = override.get("source_key")
        if not isinstance(source_key, str) or not source_key.strip():
            raise ValidationError(f"layout.legend_style.name_overrides[{index}].source_key must be a non-empty string.")
        for field in ("default_name", "legend_name"):
            value = override.get(field)
            if value is not None and not isinstance(value, str):
                raise ValidationError(f"layout.legend_style.name_overrides[{index}].{field} must be a string.")


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
