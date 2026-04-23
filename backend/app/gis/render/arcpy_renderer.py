"""ArcPy 地图渲染器。

这个文件是整个项目里最核心的 GIS 逻辑。它不关心 HTTP、不关心 Flask，
只负责一件事：

    根据 job_config，把流域、河流、站点数据加载到 ArcGIS Pro 模板工程里，
    设置样式和标注，然后导出 PNG。

整体流程可以按下面顺序理解：

1. `ArcPyRenderer.render()` 是对外入口。
2. 复制模板 `.aprx` 到本次输出目录，避免修改原始模板。
3. 打开复制后的工程，找到固定名称的地图、布局、地图框。
4. 清空旧业务图层，保留底图。
5. 把 GeoJSON 转成 shapefile，把站点 Excel 转成点图层。
6. 给流域、河流、站点设置符号和标注。
7. 根据流域边界设置地图框范围。
8. 导出 `map.png`，同时写 `result.json`。

ArcPy 的对象模型比较深，尤其是 CIM 符号部分第一次看会有点绕。
代码里把相关操作拆成小函数，就是为了方便逐段理解。
"""

from __future__ import annotations

import csv
import json
import shutil
import time
from pathlib import Path
from typing import Any

from app.core.constants import STATION_SYMBOL_COLOR_PRESETS, STATION_SYMBOL_LEGACY_PRESETS


class ArcPyRenderer:
    """基于 ArcPy 的同步地图渲染器。

    这个类没有保存状态，每次调用 `render()` 都是一轮完整出图。
    因此它可以被 Flask 接口直接创建和调用，也方便单元测试用假 ArcPy 替代。
    """

    def render(self, *, job_config: dict[str, Any], output_dir: Path, template_project: Path) -> dict[str, Any]:
        """执行一次地图渲染。

        Args:
            job_config: 地图业务配置，包括输入文件、样式、布局选项等。
            output_dir: 本次出图目录。函数会在里面生成 map.png/result.json/aprx 副本。
            template_project: ArcGIS Pro 模板工程 `.aprx`。

        Returns:
            结构化结果字典，同时也会写入 `output_dir/result.json`。
        """
        # 每次请求使用独立目录，避免不同请求之间的临时 shp/dbf/aprx 相互覆盖。
        output_dir.mkdir(parents=True, exist_ok=True)
        output_png = output_dir / "map.png"
        result_json = output_dir / "result.json"
        start = time.perf_counter()

        try:
            # ArcPy 只能在 ArcGIS Pro Python 环境中导入。
            # 如果你用普通 Python 运行真实渲染，这里会失败并写出 failed result。
            import arcpy  # type: ignore
        except Exception as exc:  # pragma: no cover - only happens outside ArcGIS Pro Python
            return _write_failure(
                result_json=result_json,
                output_png=output_png,
                error=f"arcpy import failed: {exc}",
                elapsed_seconds=round(time.perf_counter() - start, 3),
                extra={"requested_title": job_config.get("map_title")},
            )

        if not template_project.exists():
            # 模板不存在是配置错误，直接返回结构化失败，方便 Apifox 看到明确原因。
            return _write_failure(
                result_json=result_json,
                output_png=output_png,
                error=f"ArcPy template project does not exist: {template_project}",
                elapsed_seconds=round(time.perf_counter() - start, 3),
                extra={"requested_title": job_config.get("map_title")},
            )

        try:
            # 真正的 ArcPy 操作都放到内部函数中，render() 只负责入口、计时和结果包装。
            extra = _export_template_render(
                arcpy=arcpy,
                job_config=job_config,
                output_png=output_png,
                template_project=template_project,
            )
        except Exception as exc:
            return _write_failure(
                result_json=result_json,
                output_png=output_png,
                error=str(exc),
                elapsed_seconds=round(time.perf_counter() - start, 3),
                extra={"requested_title": job_config.get("map_title")},
            )

        warnings = extra.pop("warnings", [])
        # ArcPy 操作成功后，把输出路径、警告、耗时等信息写入 result.json。
        return _write_success(
            result_json=result_json,
            output_png=output_png,
            job_config=job_config,
            elapsed_seconds=round(time.perf_counter() - start, 3),
            warnings=warnings,
            extra=extra,
        )


def _write_result(result_json: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """把结果字典写入 result.json，并原样返回。

    这样 API 可以直接把返回值发给调用方，同时磁盘上也留下可追踪记录。
    """
    result_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _write_failure(
    *,
    result_json: Path,
    output_png: Path,
    error: str,
    elapsed_seconds: float = 0,
    warnings: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """写入失败结果。

    ArcPy 报错时不要只抛异常给 Flask；写 result.json 的好处是：
    即使 HTTP 请求中断，也能在输出目录里找到失败原因。
    """
    payload: dict[str, Any] = {
        "status": "failed",
        "output_png": str(output_png),
        "feature_counts": {},
        "warnings": warnings or [],
        "elapsed_seconds": elapsed_seconds,
        "error": error,
    }
    if extra:
        payload.update(extra)
    return _write_result(result_json, payload)


def _write_success(
    *,
    result_json: Path,
    output_png: Path,
    job_config: dict[str, Any],
    elapsed_seconds: float,
    warnings: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """写入成功结果。"""
    payload: dict[str, Any] = {
        "status": "succeeded",
        "output_png": str(output_png),
        "result_json": str(result_json),
        "feature_counts": {
            "station_layers": len(job_config.get("inputs", {}).get("station_layers", [])),
        },
        "warnings": warnings or [],
        "elapsed_seconds": elapsed_seconds,
    }
    if extra:
        payload.update(extra)
    return _write_result(result_json, payload)


def _hex_to_rgb(color: str) -> list[int]:
    """把网页常用的 `#RRGGBB` 颜色转换成 `[R, G, B]`。

    请求 JSON 里用 `#ff0000` 这种格式最直观；
    ArcGIS 符号对象需要 RGB 数组，所以这里做一次转换。
    """
    normalized = color.strip().lstrip("#")
    if len(normalized) != 6:
        raise ValueError(f"Expected #RRGGBB color, got {color!r}")
    return [int(normalized[index : index + 2], 16) for index in (0, 2, 4)]


def _arcgis_rgb(color: str, alpha_percent: int = 100) -> dict[str, list[int]]:
    """转换成 ArcPy 符号属性常用的颜色格式。

    ArcPy 简单符号经常接受：
        {"RGB": [red, green, blue, alpha]}

    alpha_percent 是透明度百分比，100 表示完全不透明。
    """
    red, green, blue = _hex_to_rgb(color)
    return {"RGB": [red, green, blue, alpha_percent]}


def _supports(layer, capability: str) -> bool:
    """安全检查图层是否支持某项能力。

    ArcGIS Pro 里不同图层类型支持的属性不一样。
    例如有些图层不能设置 SYMBOLOGY，有些图层不能 SHOWLABELS。
    先检查再操作，可以减少 ArcPy 抛出的底层异常。
    """
    if not hasattr(layer, "supports"):
        return hasattr(layer, capability.lower())
    try:
        return bool(layer.supports(capability))
    except Exception:
        return False


def _require_single(items, label: str):
    """要求模板里某个对象必须且只能找到一个。

    例如本项目约定模板中有且只有一个名为“地图”的 Map。
    如果没有找到或找到多个，继续渲染都会变得不可预测，所以直接失败。
    """
    if len(items) != 1:
        raise RuntimeError(f"Template must contain exactly one {label}.")
    return items[0]


def _clear_business_layers(map_obj) -> None:
    """清空业务图层，只保留底图。

    模板工程里通常已经有底图。每次渲染前先移除旧的流域、河流、站点图层，
    可以避免重复请求后地图里堆积多份旧数据。
    """
    for layer in list(map_obj.listLayers()):
        if getattr(layer, "isBasemapLayer", False):
            continue
        map_obj.removeLayer(layer)


def _remove_existing_dataset(path: Path) -> None:
    """删除已存在的临时输出数据。

    Shapefile 不是单个文件，而是一组同名不同扩展名文件：
    `.shp/.shx/.dbf/.prj/...`。所以删除 shp 时要按 stem 删除整组文件。
    """
    if path.suffix.lower() in {".shp", ".dbf"}:
        for candidate in path.parent.glob(f"{path.stem}.*"):
            if candidate.is_file():
                candidate.unlink()
        return
    if path.exists() and path.is_file():
        path.unlink()


def _apply_polygon_style(layer, job_config: dict[str, Any], layer_config: dict[str, Any] | None = None) -> None:
    """设置流域边界面图层样式。

    对应请求 JSON：

        style.basin_fill.color / opacity
        style.basin_boundary.color / width_pt

    面图层通常有填充色和外轮廓线两个部分，所以这里分别设置。
    """
    if not _supports(layer, "SYMBOLOGY"):
        return
    style = (layer_config or {}).get("style") or job_config.get("style", {})
    boundary_style = style.get("basin_boundary", {})
    fill_style = style.get("basin_fill", {})
    try:
        symbology = layer.symbology
        symbol = symbology.renderer.symbol
        # 填充色支持 opacity，例如 0.45 会转成 ArcGIS 的 alpha=45。
        if fill_style.get("color"):
            opacity = fill_style.get("opacity", 1)
            symbol.color = _arcgis_rgb(fill_style["color"], int(float(opacity) * 100))
        # 外边界用 outlineColor/outlineWidth 控制。
        if boundary_style.get("color"):
            symbol.outlineColor = _arcgis_rgb(boundary_style["color"])
        if boundary_style.get("width_pt") is not None:
            symbol.outlineWidth = float(boundary_style["width_pt"])
        layer.symbology = symbology
    except Exception:
        # 样式设置失败不应该阻断整个出图。
        # 有些模板图层符号结构不同，ArcPy 可能不支持这些属性。
        return


def _apply_line_style(layer, job_config: dict[str, Any], layer_config: dict[str, Any] | None = None) -> None:
    """设置河流线图层样式。

    对应请求 JSON：

        style.river_network.color
        style.river_network.width_pt

    之前输出图里河流看不见，核心原因之一就是线数据和线样式没有正确处理。
    这里固定把河流 GeoJSON 按 POLYLINE 转换，并设置线色和线宽。
    """
    if not _supports(layer, "SYMBOLOGY"):
        return
    style = ((layer_config or {}).get("style") or job_config.get("style", {})).get("river_network", {})
    try:
        symbology = layer.symbology
        symbol = symbology.renderer.symbol
        color = _arcgis_rgb(style.get("color", "#2f80ed"))
        width = float(style.get("width_pt", 1.0))
        # ArcPy 简单线符号常用 color/size 表示颜色和宽度。
        symbol.color = color
        symbol.size = width
        # 某些符号对象还暴露 outlineColor/outlineWidth，也顺手设置，兼容更多模板。
        if hasattr(symbol, "outlineColor"):
            symbol.outlineColor = color
        if hasattr(symbol, "outlineWidth"):
            symbol.outlineWidth = width
        layer.symbology = symbology
    except Exception:
        return


def _station_color(preset: str | None) -> str:
    """根据站点预设返回默认颜色。

    如果请求里同时传了 `symbol.color`，会优先使用请求里的颜色；
    这个函数只负责 preset 的默认兜底值。
    """
    if preset and preset in STATION_SYMBOL_LEGACY_PRESETS:
        color_preset = STATION_SYMBOL_LEGACY_PRESETS[preset]["color_preset"]
        return STATION_SYMBOL_COLOR_PRESETS[color_preset]
    return STATION_SYMBOL_COLOR_PRESETS["blue"]


def _station_shape(symbol_config: dict[str, Any]) -> str:
    """解析站点形状。

    新请求优先使用 `symbol.shape`；
    旧请求如果只传 `symbol.preset`，就从兼容表里推导形状。
    """
    if symbol_config.get("shape"):
        return symbol_config["shape"]
    preset = symbol_config.get("preset")
    if preset in STATION_SYMBOL_LEGACY_PRESETS:
        return STATION_SYMBOL_LEGACY_PRESETS[preset]["shape"]
    return "circle"


def _station_symbol_color(symbol_config: dict[str, Any]) -> str:
    """解析站点颜色。

    优先级：
    1. `symbol.color`：完全自定义颜色。
    2. `symbol.color_preset`：从颜色预设中选。
    3. `symbol.preset`：兼容旧版组合预设。
    4. 默认蓝色。
    """
    if symbol_config.get("color"):
        return symbol_config["color"]
    color_preset = symbol_config.get("color_preset")
    if color_preset in STATION_SYMBOL_COLOR_PRESETS:
        return STATION_SYMBOL_COLOR_PRESETS[color_preset]
    return _station_color(symbol_config.get("preset"))


def _marker_geometry(shape: str, size: float = 2.0) -> dict[str, list[list[list[float]]]]:
    """根据站点形状构造 CIM marker 几何。

    ArcPy 的普通 `symbol.shape` 并不能稳定把点符号改成三角形。
    所以这里用 CIM：直接把 markerGraphic 的 geometry 改成目标形状的面。

    这里的 size 是几何模板大小，不是最终屏幕字号；
    真正的符号大小仍然由 CIM marker_layer.size 控制。
    """
    if shape == "square":
        return {
            "rings": [
                [
                    [-size, size],
                    [size, size],
                    [size, -size],
                    [-size, -size],
                    [-size, size],
                ]
            ]
        }
    if shape == "diamond":
        return {
            "rings": [
                [
                    [0, size],
                    [size, 0],
                    [0, -size],
                    [-size, 0],
                    [0, size],
                ]
            ]
        }
    if shape == "rectangle":
        return {
            "rings": [
                [
                    [-size * 1.5, size * 0.75],
                    [size * 1.5, size * 0.75],
                    [size * 1.5, -size * 0.75],
                    [-size * 1.5, -size * 0.75],
                    [-size * 1.5, size * 0.75],
                ]
            ]
        }
    return {
        "rings": [
            [
                [0, size],
                [size * 0.866, -size * 0.5],
                [-size * 0.866, -size * 0.5],
                [0, size],
            ]
        ]
    }


def _apply_marker_shape_cim(layer, shape: str, color: str, size: float, rotation: float = 0.0) -> None:
    """用 CIM 把站点点符号改成指定形状。

    CIM 是 Cartographic Information Model，比普通 symbology API 更底层。
    它的路径很深：

        layer definition
        -> renderer
        -> symbol
        -> symbolLayers[0]
        -> markerGraphics[0]

    这也是为什么函数里有一串 `.symbol.symbol.symbolLayers`。
    """
    if shape == "circle":
        return
    try:
        definition = layer.getDefinition("V2")
        marker_layer = definition.renderer.symbol.symbol.symbolLayers[0]
        marker_layer.size = size
        marker_layer.angle = rotation
        marker_graphic = marker_layer.markerGraphics[0]
        marker_graphic.geometry = _marker_geometry(shape)
        rgb = [*_hex_to_rgb(color), 100]
        # CIM 里的颜色对象通常是 `color.values = [R, G, B, A]`。
        for symbol_layer in getattr(marker_graphic.symbol, "symbolLayers", []) or []:
            layer_color = getattr(symbol_layer, "color", None)
            if layer_color is not None and hasattr(layer_color, "values"):
                layer_color.values = rgb
        layer.setDefinition(definition)
    except Exception:
        # 如果某个 ArcGIS 版本或模板符号结构不同，形状设置失败时不阻断出图。
        return


def _apply_station_symbol(layer, station_layer: dict[str, Any]) -> None:
    """设置单个站点图层的符号。

    一个 station_layer 对应一个 Excel 文件转出来的点图层。
    这里负责：

    - 设置图层名称。
    - 设置颜色。
    - 设置点大小。
    - 如果不是 circle，则额外用 CIM 设置对应形状。
    """
    if station_layer.get("layer_name") and hasattr(layer, "name"):
        try:
            layer.name = station_layer["layer_name"]
        except Exception:
            pass
    if not _supports(layer, "SYMBOLOGY"):
        return
    symbol_config = station_layer.get("symbol", {})
    try:
        symbology = layer.symbology
        symbol = symbology.renderer.symbol
        # 颜色和形状已经拆开：颜色可来自自定义 color、color_preset 或旧 preset。
        color = _station_symbol_color(symbol_config)
        symbol.color = _arcgis_rgb(color)
        if symbol_config.get("size_pt") is not None:
            symbol.size = float(symbol_config["size_pt"])
        rotation = float(symbol_config.get("rotation_deg", 0) or 0)
        if hasattr(symbol, "angle"):
            symbol.angle = rotation
        layer.symbology = symbology
        # 非圆形站点需要 CIM，因为普通符号 API 不够稳定。
        shape = _station_shape(symbol_config)
        _apply_marker_shape_cim(layer, shape, color, float(symbol_config.get("size_pt", 10)), rotation)
    except Exception:
        return


def _set_label_cim_style(layer, label_config: dict[str, Any]) -> None:
    """设置标注文字的 CIM 样式。

    普通 labelClass 可以设置表达式和可见性；
    字号、颜色这种文字符号细节更适合通过 CIM 修改。
    """
    try:
        definition = layer.getDefinition("V2")
        if not getattr(definition, "labelClasses", None):
            return
        text_symbol = definition.labelClasses[0].textSymbol.symbol
        # 字号：你要求站点标注 font_size_pt=20，这里会写到 textSymbol.height。
        if label_config.get("font_size_pt") is not None:
            text_symbol.height = float(label_config["font_size_pt"])
        # 字体颜色：当前需求是黑色，所以请求里传 "#000000"。
        if label_config.get("color"):
            rgb = _hex_to_rgb(label_config["color"])
            for symbol_layer in getattr(text_symbol.symbol, "symbolLayers", []) or []:
                color = getattr(symbol_layer, "color", None)
                if color is not None and hasattr(color, "values"):
                    color.values = [*rgb, 100]
        layer.setDefinition(definition)
    except Exception:
        return


def _apply_station_labels(layer, station_layer: dict[str, Any]) -> None:
    """开启并配置站点标注。

    标注文本来自 `name_field`，例如 name 字段。
    ArcGIS Arcade 表达式写法是 `$feature.name`。
    """
    label_config = station_layer.get("label", {})
    enabled = bool(label_config.get("enabled"))
    if not _supports(layer, "SHOWLABELS"):
        return
    try:
        layer.showLabels = enabled
        label_classes = layer.listLabelClasses()
        if not label_classes:
            return
        label_class = label_classes[0]
        label_class.visible = enabled
        if enabled:
            field = station_layer.get("name_field")
            if field:
                label_class.expression = f"$feature.{field}"
            _set_label_cim_style(layer, label_config)
    except Exception:
        return


def _first_layout_element(layout, element_type: str, names: list[str]):
    """按名称顺序查找布局元素，返回第一个匹配项。"""
    for name in names:
        try:
            elements = layout.listElements(element_type, name)
        except Exception:
            elements = []
        if elements:
            return elements[0], name
    return None, names[0]


def _set_layout_element_visible(element, enabled: bool, warnings: list[str], label: str) -> None:
    """安全设置布局元素显隐。"""
    try:
        element.visible = enabled
    except Exception:
        warnings.append(f"layout element {label!r} visibility could not be changed.")


_LAYOUT_ELEMENT_BOXES = {
    "title": {"x": 0.36, "y": 0.86, "width": 0.28, "height": 0.055, "text_size": 18},
    "legend": {"x": 0.045, "y": 0.42, "width": 0.22, "height": 0.38},
    "scale_bar": {"x": 0.31, "y": 0.055, "width": 0.34, "height": 0.035},
    "north_arrow": {"x": 0.92, "y": 0.78, "width": 0.035, "height": 0.08},
}

_LEGEND_PATCH_HEIGHT = 6
_LEGEND_PATCH_WIDTH = 12
_LEGEND_LEFT_RESERVE_RATIO = 0.25
_LEGEND_BOTTOM_RESERVE_RATIO = 1 / 3
_DEFAULT_MAP_VIEW_PADDING = {"left": 0.2408, "right": 0.1808, "top": 0.14, "bottom": 0.14}


def _manual_layout_element_config(layout_config: dict[str, Any], box_key: str) -> dict[str, Any] | None:
    """Return a manual element config when the request opts into manual layout."""
    if layout_config.get("mode") != "manual":
        return None
    elements = layout_config.get("elements")
    if not isinstance(elements, dict):
        return None
    element_config = elements.get(box_key)
    return element_config if isinstance(element_config, dict) else None


def _layout_element_enabled(layout_config: dict[str, Any], box_key: str) -> bool:
    """Read enabled from manual elements first, then from the legacy element switch."""
    manual_config = _manual_layout_element_config(layout_config, box_key)
    if manual_config is not None and "enabled" in manual_config:
        return bool(manual_config.get("enabled"))
    return bool(layout_config.get(box_key, {}).get("enabled", True))


def _float_config(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _apply_absolute_layout_element_box(element, config: dict[str, Any], warnings: list[str]) -> None:
    """Apply x/y/width/height values already expressed in layout page units."""
    try:
        element.elementPositionX = float(config["x"])
        element.elementPositionY = float(config["y"])
        element.elementWidth = float(config["width"])
        element.elementHeight = float(config["height"])
        if "font_size" in config and hasattr(element, "textSize"):
            element.textSize = float(config["font_size"])
    except Exception:
        warnings.append(f"layout element {getattr(element, 'name', 'manual')!r} manual size or position could not be applied.")


def _apply_layout_element_box(
    layout,
    element,
    box_key: str,
    warnings: list[str],
    layout_config: dict[str, Any] | None = None,
) -> None:
    """按页面比例设置布局元素的位置和大小。"""
    if layout_config is not None:
        manual_config = _manual_layout_element_config(layout_config, box_key)
        if manual_config is not None:
            _apply_absolute_layout_element_box(element, manual_config, warnings)
            return
    box = _LAYOUT_ELEMENT_BOXES[box_key]
    try:
        page_width = float(getattr(layout, "pageWidth"))
        page_height = float(getattr(layout, "pageHeight"))
        element.elementPositionX = page_width * box["x"]
        element.elementPositionY = page_height * box["y"]
        element.elementWidth = page_width * box["width"]
        element.elementHeight = page_height * box["height"]
        if "text_size" in box and hasattr(element, "textSize"):
            element.textSize = box["text_size"]
    except Exception:
        warnings.append(f"layout element {getattr(element, 'name', box_key)!r} size or position could not be adjusted.")


def _apply_manual_map_frame_box(map_frame, job_config: dict[str, Any], warnings: list[str]) -> None:
    """Apply a user-defined map frame position when layout.mode is manual."""
    layout_config = job_config.get("layout", {})
    manual_config = _manual_layout_element_config(layout_config, "map_frame")
    if manual_config is None:
        return
    _apply_absolute_layout_element_box(map_frame, manual_config, warnings)


def _mark_direct_white_background(element) -> None:
    """Set direct background attributes when the ArcPy element exposes them."""
    if hasattr(element, "background_color"):
        try:
            element.background_color = "#ffffff"
        except Exception:
            return


def _tune_direct_legend_element(element) -> None:
    """Apply direct LegendElement options exposed by ArcPy."""
    if hasattr(element, "fittingStrategy"):
        try:
            element.fittingStrategy = "AdjustColumnsAndFont"
        except Exception:
            return


def _legend_style_config(layout_config: dict[str, Any]) -> dict[str, Any]:
    style_config = layout_config.get("legend_style")
    return style_config if isinstance(style_config, dict) else {}


def _tune_cim_legend_element(element, style_config: dict[str, Any] | None = None) -> None:
    """Keep legend symbols compact and consistent across polygon/line/point layers."""
    style_config = style_config or {}
    patch_width = _float_config(style_config.get("patch_width"), _LEGEND_PATCH_WIDTH)
    patch_height = _float_config(style_config.get("patch_height"), _LEGEND_PATCH_HEIGHT)
    if hasattr(element, "fittingStrategy"):
        element.fittingStrategy = "AdjustColumnsAndFont"
    if hasattr(element, "scaleSymbols"):
        element.scaleSymbols = bool(style_config.get("scale_symbols", False))
    if hasattr(element, "autoFonts"):
        element.autoFonts = bool(style_config.get("auto_fonts", True))
    if hasattr(element, "minFontSize"):
        element.minFontSize = _float_config(style_config.get("min_font_size"), 5)
    if hasattr(element, "defaultPatchHeight"):
        element.defaultPatchHeight = patch_height
    if hasattr(element, "defaultPatchWidth"):
        element.defaultPatchWidth = patch_width
    for gap_name in ("itemGap", "classGap", "layerNameGap", "patchGap", "textGap"):
        if hasattr(element, gap_name):
            api_name = {
                "itemGap": "item_gap",
                "classGap": "class_gap",
                "layerNameGap": "layer_name_gap",
                "patchGap": "patch_gap",
                "textGap": "text_gap",
            }[gap_name]
            setattr(element, gap_name, _float_config(style_config.get(api_name), 2))
    for item in getattr(element, "items", []) or []:
        if hasattr(item, "patchHeight"):
            item.patchHeight = patch_height
        if hasattr(item, "patchWidth"):
            item.patchWidth = patch_width
        if hasattr(item, "scaleToPatch"):
            item.scaleToPatch = bool(style_config.get("scale_to_patch", True))


def _make_white_cim_fill(cim_module):
    """Create an opaque white CIM polygon fill symbol reference."""
    color = cim_module.CreateCIMObjectFromClassName("CIMRGBColor", "V2")
    color.values = [255, 255, 255, 100]
    fill = cim_module.CreateCIMObjectFromClassName("CIMSolidFill", "V2")
    fill.enable = True
    fill.color = color
    polygon = cim_module.CreateCIMObjectFromClassName("CIMPolygonSymbol", "V2")
    polygon.symbolLayers = [fill]
    symbol_ref = cim_module.CreateCIMObjectFromClassName("CIMSymbolReference", "V2")
    symbol_ref.symbol = polygon
    return symbol_ref


def _set_cim_layout_white_backgrounds(
    layout,
    element_names: set[str],
    warnings: list[str],
    layout_config: dict[str, Any] | None = None,
) -> None:
    """通过 CIM 给标题和图例设置白底。"""
    try:
        import arcpy.cim as cim_module  # type: ignore

        definition = layout.getDefinition("V2")
        elements = getattr(definition, "elements", []) or []
    except Exception:
        return

    layout_config = layout_config or {}
    legend_style = _legend_style_config(layout_config)
    changed = False
    for element in elements:
        if getattr(element, "name", None) not in element_names:
            continue
        frame = getattr(element, "graphicFrame", None)
        if frame is None:
            graphic = getattr(element, "graphic", None)
            frame = getattr(graphic, "frame", None)
        if frame is None:
            warnings.append(f"layout element {getattr(element, 'name', 'unnamed')!r} background could not be set.")
            continue
        try:
            frame.backgroundSymbol = _make_white_cim_fill(cim_module)
            if hasattr(frame, "backgroundGapX"):
                frame.backgroundGapX = 1
            if hasattr(frame, "backgroundGapY"):
                frame.backgroundGapY = 1
            if getattr(element, "name", None) == "图例":
                _tune_cim_legend_element(element, legend_style)
            changed = True
        except Exception:
            warnings.append(f"layout element {getattr(element, 'name', 'unnamed')!r} background could not be set.")

    if changed:
        try:
            layout.setDefinition(definition)
        except Exception:
            warnings.append("layout element white backgrounds could not be saved.")


def _apply_layout_elements(layout, job_config: dict[str, Any], warnings: list[str]) -> None:
    """应用布局元素配置。

    当前模板里的标题、图例、比例尺还没有完全整理好，所以这里采用“软失败”：
    - 找得到元素就设置。
    - 找不到元素就写 warning。
    - 不因为缺少布局元素而阻止出图。

    这样你可以先稳定生成地图主体，后续再完善标题、图例、比例尺、指北针。
    """
    layout_config = job_config.get("layout", {})
    title_enabled = _layout_element_enabled(layout_config, "title")
    title_element, title_name = _first_layout_element(layout, "TEXT_ELEMENT", ["标题", "文本"])
    if title_element is None:
        warnings.append("layout title element named '标题' or '文本' was not found; map_title was not applied.")
    else:
        _set_layout_element_visible(title_element, title_enabled, warnings, title_name)
        if title_enabled and job_config.get("map_title"):
            try:
                title_element.text = job_config["map_title"]
            except Exception:
                warnings.append(f"layout title element named {title_name!r} text could not be changed.")
        if title_enabled:
            _apply_layout_element_box(layout, title_element, "title", warnings, layout_config)
            _mark_direct_white_background(title_element)

    layout_elements = [
        ("legend", "LEGEND_ELEMENT", ["图例"], "legend"),
        ("scale_bar", "MAPSURROUND_ELEMENT", ["比例尺"], "scale bar"),
        ("north_arrow", "MAPSURROUND_ELEMENT", ["指北针"], "north arrow"),
    ]
    for config_key, element_type, names, warning_label in layout_elements:
        enabled = _layout_element_enabled(layout_config, config_key)
        element, matched_name = _first_layout_element(layout, element_type, names)
        if element is None:
            if enabled:
                warnings.append(f"{warning_label} is enabled, but no layout element named {names[0]!r} exists.")
            continue
        _set_layout_element_visible(element, enabled, warnings, matched_name)
        if enabled:
            _apply_layout_element_box(layout, element, config_key, warnings, layout_config)
            if config_key == "legend":
                _tune_direct_legend_element(element)
                _mark_direct_white_background(element)

    background_names = set()
    if title_enabled and title_element is not None:
        background_names.add(title_name)
    legend_enabled = _layout_element_enabled(layout_config, "legend")
    if legend_enabled:
        background_names.add("图例")
    if background_names:
        _set_cim_layout_white_backgrounds(layout, background_names, warnings, layout_config)


def _snapshot_layout_elements(layout, map_frame) -> list[tuple[Any, float, float, float, float]]:
    """记录页面尺寸改变前的布局元素位置和大小。"""
    try:
        elements = list(layout.listElements())
    except Exception:
        elements = []
    if map_frame not in elements:
        elements.append(map_frame)
    snapshots = []
    for element in elements:
        try:
            snapshots.append(
                (
                    element,
                    float(element.elementPositionX),
                    float(element.elementPositionY),
                    float(element.elementWidth),
                    float(element.elementHeight),
                )
            )
        except (AttributeError, TypeError, ValueError):
            continue
    return snapshots


def _scale_layout_elements(
    snapshots: list[tuple[Any, float, float, float, float]],
    *,
    scale_x: float,
    scale_y: float,
    warnings: list[str],
) -> None:
    """按页面尺寸变化比例缩放布局元素，保留模板版式。"""
    for element, x, y, width, height in snapshots:
        try:
            element.elementPositionX = x * scale_x
            element.elementPositionY = y * scale_y
            element.elementWidth = width * scale_x
            element.elementHeight = height * scale_y
        except Exception:
            name = getattr(element, "name", "unnamed")
            warnings.append(f"layout element {name!r} size or position could not be scaled.")


def _positive_int(value: Any, default: int) -> int:
    """把请求值转换成正整数，转换失败时使用默认值。

    API 层已经会校验 output 字段是否存在，但渲染器也可能被脚本直接调用。
    这里再兜底一次，避免 ArcPy 阶段因为 `0 dpi` 或非数字宽高抛出晦涩异常。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _layout_units_per_inch(layout) -> tuple[str, float]:
    """读取布局页面单位，并返回“一英寸等于多少布局单位”。

    ArcGIS Pro 的 `layout.pageWidth/pageHeight` 使用模板自己的页面单位。
    例如当前测试模板是 `MILLIMETER`，如果仍按英寸直接写 10.67，
    ArcGIS 会理解成 10.67 毫米，最终图片就会非常小。
    """
    page_units = str(getattr(layout, "pageUnits", "INCH") or "INCH").upper()
    units_per_inch = {
        "INCH": 1.0,
        "INCHES": 1.0,
        "MILLIMETER": 25.4,
        "MILLIMETERS": 25.4,
        "CENTIMETER": 2.54,
        "CENTIMETERS": 2.54,
        "POINT": 72.0,
        "POINTS": 72.0,
    }.get(page_units, 1.0)
    return page_units, units_per_inch


def _apply_requested_output_size(layout, map_frame, job_config: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    """把请求里的像素尺寸真正应用到 ArcGIS Pro 布局。

    ArcGIS Pro 的 Layout 导出 PNG 时，最终像素尺寸主要由两件事决定：
    - 布局页面尺寸，单位通常是英寸；
    - `exportToPNG(..., resolution=dpi)` 里的 dpi。

    因此要得到 `width_px x height_px` 的图片，就需要把页面尺寸设置成：
    - pageWidth = width_px / dpi
    - pageHeight = height_px / dpi

    同时把地图框铺满页面，避免只改页面尺寸后，地图内容仍停留在旧模板的小框里。
    """
    output_config = job_config.get("output", {})
    width_px = _positive_int(output_config.get("width_px"), 1600)
    height_px = _positive_int(output_config.get("height_px"), 1200)
    dpi = _positive_int(output_config.get("dpi"), 96)
    page_width_in = width_px / dpi
    page_height_in = height_px / dpi
    page_units, units_per_inch = _layout_units_per_inch(layout)
    page_width = page_width_in * units_per_inch
    page_height = page_height_in * units_per_inch

    original_page_width = float(getattr(layout, "pageWidth", 0) or 0)
    original_page_height = float(getattr(layout, "pageHeight", 0) or 0)
    element_snapshots = _snapshot_layout_elements(layout, map_frame)

    try:
        layout.pageWidth = page_width
        layout.pageHeight = page_height
    except Exception:
        warnings.append("layout page size could not be changed; template page size was kept.")

    if original_page_width > 0 and original_page_height > 0:
        _scale_layout_elements(
            element_snapshots,
            scale_x=page_width / original_page_width,
            scale_y=page_height / original_page_height,
            warnings=warnings,
        )
    else:
        warnings.append("layout element positions were not scaled because template page size could not be read.")

    return {
        "width_px": width_px,
        "height_px": height_px,
        "dpi": dpi,
        "page_width_in": round(page_width_in, 6),
        "page_height_in": round(page_height_in, 6),
        "layout_page_width": round(page_width, 6),
        "layout_page_height": round(page_height, 6),
        "layout_page_units": page_units,
    }


def _prepare_vector_dataset(
    arcpy,
    input_path: str,
    work_dir: Path,
    stem: str,
    geometry_type: str,
) -> Path:
    """准备面/线数据集。

    ArcGIS Pro 的 `map.addDataFromPath()` 可以直接加载 shp，
    但对 GeoJSON 的符号和图层类型识别不一定稳定。
    所以这里遇到 `.geojson/.json` 时，先用 `JSONToFeatures` 转成 shapefile。

    geometry_type 非常关键：
    - 流域边界必须传 POLYGON。
    - 河流网络必须传 POLYLINE。
    """
    source_path = Path(input_path)
    if source_path.suffix.lower() not in {".geojson", ".json"}:
        return source_path

    feature_path = work_dir / f"{stem}.shp"
    _remove_existing_dataset(feature_path)
    # ArcPy 会在同目录下生成 shp/shx/dbf/prj 等一组文件。
    arcpy.conversion.JSONToFeatures(str(source_path), str(feature_path), geometry_type)
    return feature_path


def _create_station_feature_class(arcpy, station_layer: dict[str, Any], work_dir: Path, index: int) -> Path:
    """把站点 Excel 转成点 shapefile。

    ArcPy 处理 Excel 点位通常分两步：

    1. `ExcelToTable`：Excel -> dbf/table
    2. `XYTableToPoint`：table + x/y 字段 -> point feature class

    当前坐标系固定使用 WGS84/EPSG:4326，因为请求里的 lon/lat 是经纬度。
    """
    table_path = work_dir / f"station_table_{index}.dbf"
    point_path = work_dir / f"station_layer_{index}.shp"
    # 每次重跑前先删除旧临时文件，避免 ArcPy 因输出已存在而报错。
    _remove_existing_dataset(table_path)
    _remove_existing_dataset(point_path)
    arcpy.conversion.ExcelToTable(
        station_layer["path"],
        str(table_path),
        station_layer["sheet_name"],
    )
    arcpy.management.XYTableToPoint(
        str(table_path),
        str(point_path),
        station_layer["x_field"],
        station_layer["y_field"],
        None,
        arcpy.SpatialReference(4326),
    )
    return point_path


def _create_station_table(arcpy, station_layer: dict[str, Any], work_dir: Path, index: int) -> Path:
    """Convert one station Excel file into an ArcPy table."""
    table_path = work_dir / f"station_table_{index}.dbf"
    _remove_existing_dataset(table_path)
    arcpy.conversion.ExcelToTable(
        station_layer["path"],
        str(table_path),
        station_layer["sheet_name"],
    )
    return table_path


def _xy_table_to_station_points(arcpy, table_path: Path, point_path: Path, station_layer: dict[str, Any]) -> Path:
    """Convert a table containing x/y columns to a point feature class."""
    _remove_existing_dataset(point_path)
    arcpy.management.XYTableToPoint(
        str(table_path),
        str(point_path),
        station_layer["x_field"],
        station_layer["y_field"],
        None,
        arcpy.SpatialReference(4326),
    )
    return point_path


def _manual_extent(arcpy, map_view_config: dict[str, Any]) -> Any | None:
    extent_config = map_view_config.get("extent")
    if not isinstance(extent_config, dict):
        return None
    try:
        return arcpy.Extent(
            float(extent_config["xmin"]),
            float(extent_config["ymin"]),
            float(extent_config["xmax"]),
            float(extent_config["ymax"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _map_view_padding(map_view_config: dict[str, Any]) -> dict[str, float]:
    padding = map_view_config.get("padding")
    if not isinstance(padding, dict):
        return dict(_DEFAULT_MAP_VIEW_PADDING)
    return {
        "left": _float_config(padding.get("left"), _DEFAULT_MAP_VIEW_PADDING["left"]),
        "right": _float_config(padding.get("right"), _DEFAULT_MAP_VIEW_PADDING["right"]),
        "top": _float_config(padding.get("top"), _DEFAULT_MAP_VIEW_PADDING["top"]),
        "bottom": _float_config(padding.get("bottom"), _DEFAULT_MAP_VIEW_PADDING["bottom"]),
    }


def _combine_extents(arcpy, extents: list[Any], map_view_config: dict[str, Any] | None = None) -> Any | None:
    """Combine ArcPy extent objects when coordinate bounds are available."""
    if not extents:
        return None
    bounds = []
    for extent in extents:
        try:
            bounds.append(
                (
                    float(extent.XMin),
                    float(extent.YMin),
                    float(extent.XMax),
                    float(extent.YMax),
                )
            )
        except (AttributeError, TypeError, ValueError):
            return extents[0]
    try:
        xmin = min(item[0] for item in bounds)
        ymin = min(item[1] for item in bounds)
        xmax = max(item[2] for item in bounds)
        ymax = max(item[3] for item in bounds)
        width = xmax - xmin
        height = ymax - ymin
        fallback_span = max(abs(xmin), abs(ymin), abs(xmax), abs(ymax), 1.0) * 0.01
        map_view_config = map_view_config or {}
        mode = map_view_config.get("mode", "auto_padding")
        if mode == "auto":
            padding = {"left": 0, "right": 0, "top": 0, "bottom": 0}
        else:
            padding = _map_view_padding(map_view_config)
        span_x = width if width > 0 else fallback_span
        span_y = height if height > 0 else fallback_span
        return arcpy.Extent(
            xmin - span_x * padding["left"],
            ymin - span_y * padding["bottom"],
            xmax + span_x * padding["right"],
            ymax + span_y * padding["top"],
        )
    except Exception:
        return extents[0]


def _set_map_extent_to_layers(
    arcpy,
    map_frame,
    layers: list[Any],
    warnings: list[str],
    map_view_config: dict[str, Any] | None = None,
) -> None:
    """Zoom the map frame to all business layers, including per-point station sublayers."""
    map_view_config = map_view_config or {}
    if map_view_config.get("mode") == "manual_extent":
        extent = _manual_extent(arcpy, map_view_config)
        if extent is None:
            warnings.append("map_view.manual_extent is invalid; automatic extent was used.")
        else:
            map_frame.camera.setExtent(extent)
            return

    extents = []
    for layer in layers:
        try:
            extent = map_frame.getLayerExtent(layer, False, True)
        except Exception:
            warnings.append(f"layer extent could not be read for {getattr(layer, 'name', 'unnamed layer')}.")
            continue
        if extent is not None:
            extents.append(extent)
    combined_extent = _combine_extents(arcpy, extents, map_view_config)
    if combined_extent is not None:
        map_frame.camera.setExtent(combined_extent)


def _station_style_key(station_layer: dict[str, Any]) -> str:
    """Build a stable key for grouping points that share the same visual style."""
    return json.dumps(
        {
            "symbol": station_layer.get("symbol", {}),
            "label": station_layer.get("label", {}),
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def _station_point_layer_config(station_layer: dict[str, Any], point_config: dict[str, Any] | None) -> dict[str, Any]:
    """Merge layer defaults with one optional per-point override."""
    merged = dict(station_layer)
    merged["symbol"] = {
        **(station_layer.get("symbol") or {}),
        **((point_config or {}).get("symbol") or {}),
    }
    merged["label"] = {
        **(station_layer.get("label") or {}),
        **((point_config or {}).get("label") or {}),
    }
    return merged


def _station_csv_fields(station_layer: dict[str, Any]) -> list[str]:
    """Return the minimal table fields needed for points and labels."""
    fields: list[str] = []
    for field in (station_layer.get("x_field"), station_layer.get("y_field"), station_layer.get("name_field")):
        if field and field not in fields:
            fields.append(field)
    return fields


def _write_station_group_table(
    work_dir: Path,
    layer_index: int,
    group_index: int,
    fields: list[str],
    rows: list[dict[str, Any]],
) -> Path:
    """Write one style group to a temporary CSV table for XYTableToPoint."""
    table_path = work_dir / f"station_group_table_{layer_index}_{group_index}.csv"
    _remove_existing_dataset(table_path)
    with table_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    return table_path


def _add_per_point_station_layers(
    arcpy,
    map_obj,
    station_layer: dict[str, Any],
    work_dir: Path,
    index: int,
    warnings: list[str],
) -> list[Any]:
    """Render one Excel station layer as internal sublayers grouped by per-point styles."""
    table_path = _create_station_table(arcpy, station_layer, work_dir, index)
    fields = _station_csv_fields(station_layer)
    point_configs = {
        int(point["row_number"]): point
        for point in station_layer.get("points", [])
        if isinstance(point, dict) and isinstance(point.get("row_number"), int)
    }
    seen_rows: set[int] = set()
    groups: dict[str, dict[str, Any]] = {}

    with arcpy.da.SearchCursor(str(table_path), fields) as cursor:
        for zero_index, row_values in enumerate(cursor):
            row_number = zero_index + 2
            values = dict(zip(fields, row_values))
            point_config = point_configs.get(row_number)
            if point_config is None:
                warnings.append(
                    f"station layer {station_layer.get('layer_name', index)} row {row_number} used layer default style."
                )
            else:
                seen_rows.add(row_number)
            style_config = _station_point_layer_config(station_layer, point_config)
            key = _station_style_key(style_config)
            if key not in groups:
                groups[key] = {"config": style_config, "rows": []}
            groups[key]["rows"].append(values)

    for row_number in sorted(set(point_configs) - seen_rows):
        warnings.append(
            f"station layer {station_layer.get('layer_name', index)} point row {row_number} was not found in Excel data."
        )

    base_layer_name = station_layer.get("layer_name") or f"StationLayer{index + 1}"
    added_layers: list[Any] = []
    for group_index, group in enumerate(groups.values()):
        group_config = dict(group["config"])
        group_config["layer_name"] = f"{base_layer_name} - {group_index + 1}"
        group_table = _write_station_group_table(work_dir, index, group_index, fields, group["rows"])
        point_path = work_dir / f"station_layer_{index}_group_{group_index}.shp"
        _xy_table_to_station_points(arcpy, group_table, point_path, station_layer)
        added_layer = map_obj.addDataFromPath(str(point_path))
        _apply_station_symbol(added_layer, group_config)
        _apply_station_labels(added_layer, group_config)
        added_layers.append(added_layer)
    return added_layers


def _add_station_layers(arcpy, map_obj, station_layers: list[dict[str, Any]], work_dir: Path, warnings: list[str]) -> list[Any]:
    """Add station layers to the map and apply layer or per-point styles."""
    added_layers: list[Any] = []
    for index, station_layer in enumerate(station_layers):
        if station_layer.get("points"):
            added_layers.extend(_add_per_point_station_layers(arcpy, map_obj, station_layer, work_dir, index, warnings))
            continue
        point_path = _create_station_feature_class(arcpy, station_layer, work_dir, index)
        added_layer = map_obj.addDataFromPath(str(point_path))
        _apply_station_symbol(added_layer, station_layer)
        _apply_station_labels(added_layer, station_layer)
        added_layers.append(added_layer)
    return added_layers


def _basin_layer_configs(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """兼容新旧流域面输入结构。"""
    layers = inputs.get("basin_boundaries")
    if isinstance(layers, list) and layers:
        return [layer for layer in layers if isinstance(layer, dict) and layer.get("path")]
    return [inputs["basin_boundary"]]


def _river_layer_configs(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """兼容新旧河流水系输入结构。"""
    layers = inputs.get("river_networks")
    if isinstance(layers, list) and layers:
        return [layer for layer in layers if isinstance(layer, dict) and layer.get("path")]
    return [inputs["river_network"]]


def _rename_layer(layer, layer_name: str | None) -> None:
    """给新增图层设置用户可读名称；失败时不阻断出图。"""
    if not layer_name or not hasattr(layer, "name"):
        return
    try:
        layer.name = layer_name
    except Exception:
        return


def _export_template_render(
    *,
    arcpy,
    job_config: dict[str, Any],
    output_png: Path,
    template_project: Path,
) -> dict[str, Any]:
    """基于模板工程完成一次 ArcPy 出图。

    这是 ArcPy 主流程函数。你可以把它看成一条流水线：

    模板 aprx -> 打开地图/布局/地图框 -> 加载数据 -> 设置样式 -> 缩放范围 -> 导出 PNG。
    """
    # 不直接打开原始 template_project，而是复制到 output_dir。
    # 这样 ArcPy 对工程的保存、图层增删都发生在副本上，不会污染模板。
    copied_project = output_png.parent / template_project.name
    if copied_project.resolve() == template_project.resolve():
        # 如果用户把 output_dir 设成模板所在目录，为了避免源文件覆盖自己，
        # 副本改名为 xxx.jobcopy.aprx。
        copied_project = output_png.parent / f"{template_project.stem}.jobcopy{template_project.suffix}"
    shutil.copy2(template_project, copied_project)

    # 打开复制后的 ArcGIS Pro 工程。
    project = arcpy.mp.ArcGISProject(str(copied_project))

    # 这些名称必须和模板中的对象名称一致。
    # 如果你的 ArcGIS Pro 里改了 Map/Layout/Map Frame 名称，这里也要同步改。
    map_obj = _require_single(project.listMaps("地图"), "map named 地图")
    layout = _require_single(project.listLayouts("布局"), "layout named 布局")
    map_frame = _require_single(
        layout.listElements("MAPFRAME_ELEMENT", "地图框"),
        "map frame named 地图框",
    )
    warnings: list[str] = []
    requested_output = _apply_requested_output_size(layout, map_frame, job_config, warnings)
    _apply_manual_map_frame_box(map_frame, job_config, warnings)

    # 清掉上次请求留下的业务图层，保留模板自带底图。
    _clear_business_layers(map_obj)
    _apply_layout_elements(layout, job_config, warnings)

    inputs = job_config.get("inputs", {})
    # 先加全部流域，再加全部河流，再加站点。图层顺序通常会影响地图显示效果。
    basin_layers = []
    for index, basin_config in enumerate(_basin_layer_configs(inputs)):
        basin_path = _prepare_vector_dataset(
            arcpy,
            basin_config["path"],
            output_png.parent,
            f"basin_boundary_{index + 1}",
            "POLYGON",
        )
        basin_layer = map_obj.addDataFromPath(str(basin_path))
        _rename_layer(basin_layer, basin_config.get("layer_name"))
        _apply_polygon_style(basin_layer, job_config, basin_config)
        basin_layers.append(basin_layer)

    river_layers = []
    for index, river_config in enumerate(_river_layer_configs(inputs)):
        river_path = _prepare_vector_dataset(
            arcpy,
            river_config["path"],
            output_png.parent,
            f"river_network_{index + 1}",
            "POLYLINE",
        )
        river_layer = map_obj.addDataFromPath(str(river_path))
        _rename_layer(river_layer, river_config.get("layer_name"))
        _apply_line_style(river_layer, job_config, river_config)
        river_layers.append(river_layer)

    station_layers = _add_station_layers(arcpy, map_obj, inputs.get("station_layers", []), output_png.parent, warnings)

    # Zoom to all business layers. Stations can sit outside the basin boundary,
    # especially while users are testing coordinates, so include them here too.
    _set_map_extent_to_layers(
        arcpy,
        map_frame,
        basin_layers + river_layers + station_layers,
        warnings,
        job_config.get("map_view", {}),
    )
    # ArcGIS populates legend items after layers are added, so tune the legend a second time
    # right before export to keep point symbols compact in the legend.
    _apply_layout_elements(layout, job_config, warnings)

    # DPI 和上面设置过的页面尺寸共同决定最终导出像素：
    # width_px = pageWidth * dpi, height_px = pageHeight * dpi。
    dpi = int(requested_output["dpi"])
    layout.exportToPNG(str(output_png), resolution=dpi)

    # 保存 aprx 副本，方便你打开输出目录里的工程检查图层和样式。
    if hasattr(project, "save"):
        project.save()

    return {
        "copied_project": str(copied_project),
        "requested_title": job_config.get("map_title"),
        "requested_output": requested_output,
        "warnings": warnings,
    }
