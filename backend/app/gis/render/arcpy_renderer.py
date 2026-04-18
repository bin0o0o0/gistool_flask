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


def _apply_polygon_style(layer, job_config: dict[str, Any]) -> None:
    """设置流域边界面图层样式。

    对应请求 JSON：

        style.basin_fill.color / opacity
        style.basin_boundary.color / width_pt

    面图层通常有填充色和外轮廓线两个部分，所以这里分别设置。
    """
    if not _supports(layer, "SYMBOLOGY"):
        return
    style = job_config.get("style", {})
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


def _apply_line_style(layer, job_config: dict[str, Any]) -> None:
    """设置河流线图层样式。

    对应请求 JSON：

        style.river_network.color
        style.river_network.width_pt

    之前输出图里河流看不见，核心原因之一就是线数据和线样式没有正确处理。
    这里固定把河流 GeoJSON 按 POLYLINE 转换，并设置线色和线宽。
    """
    if not _supports(layer, "SYMBOLOGY"):
        return
    style = job_config.get("style", {}).get("river_network", {})
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


def _apply_marker_shape_cim(layer, shape: str, color: str, size: float) -> None:
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
        layer.symbology = symbology
        # 非圆形站点需要 CIM，因为普通符号 API 不够稳定。
        shape = _station_shape(symbol_config)
        _apply_marker_shape_cim(layer, shape, color, float(symbol_config.get("size_pt", 10)))
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


def _apply_layout_elements(layout, job_config: dict[str, Any], warnings: list[str]) -> None:
    """应用布局元素配置。

    当前模板里的标题、图例、比例尺还没有完全整理好，所以这里采用“软失败”：
    - 找得到元素就设置。
    - 找不到元素就写 warning。
    - 不因为缺少布局元素而阻止出图。

    这样你可以先稳定生成地图主体，后续再完善标题、图例、比例尺、指北针。
    """
    title = job_config.get("map_title")
    if title:
        # 模板里如果有名为“标题”的 TEXT_ELEMENT，就把请求的 map_title 写进去。
        title_elements = layout.listElements("TEXT_ELEMENT", "标题")
        if title_elements:
            title_elements[0].text = title
        else:
            warnings.append("layout title element named '标题' was not found; map_title was not applied.")

    layout_config = job_config.get("layout", {})
    # 当前只是检查是否存在图例元素；后续可以继续扩展图例位置、字体、大小等。
    if layout_config.get("legend", {}).get("enabled"):
        legends = layout.listElements("LEGEND_ELEMENT")
        if not legends:
            warnings.append("legend is enabled, but no legend element exists in the template layout.")
    # 比例尺和指北针在 ArcGIS Pro 中都属于 mapsurround 类元素，
    # 这里先做存在性检查，缺失则提示。
    if layout_config.get("scale_bar", {}).get("enabled"):
        scale_bars = layout.listElements("MAPSURROUND_ELEMENT")
        if not scale_bars:
            warnings.append("scale bar is enabled, but no scale bar element exists in the template layout.")


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


def _add_station_layers(arcpy, map_obj, station_layers: list[dict[str, Any]], work_dir: Path) -> None:
    """把所有站点图层加入地图并设置样式/标注。"""
    for index, station_layer in enumerate(station_layers):
        point_path = _create_station_feature_class(arcpy, station_layer, work_dir, index)
        added_layer = map_obj.addDataFromPath(str(point_path))
        _apply_station_symbol(added_layer, station_layer)
        _apply_station_labels(added_layer, station_layer)


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

    # 清掉上次请求留下的业务图层，保留模板自带底图。
    _clear_business_layers(map_obj)
    _apply_layout_elements(layout, job_config, warnings)

    inputs = job_config.get("inputs", {})
    # 流域边界按面数据处理。
    basin_path = _prepare_vector_dataset(
        arcpy,
        inputs["basin_boundary"]["path"],
        output_png.parent,
        "basin_boundary",
        "POLYGON",
    )
    # 河流网络按线数据处理。这一点对河流能否显示非常关键。
    river_path = _prepare_vector_dataset(
        arcpy,
        inputs["river_network"]["path"],
        output_png.parent,
        "river_network",
        "POLYLINE",
    )
    # 先加流域，再加河流，再加站点。图层顺序通常会影响地图显示效果。
    basin_layer = map_obj.addDataFromPath(str(basin_path))
    _apply_polygon_style(basin_layer, job_config)
    river_layer = map_obj.addDataFromPath(str(river_path))
    _apply_line_style(river_layer, job_config)
    _add_station_layers(arcpy, map_obj, inputs.get("station_layers", []), output_png.parent)

    # 根据流域边界缩放地图框，让导出的图片聚焦到本次数据范围。
    extent = map_frame.getLayerExtent(basin_layer, False, True)
    map_frame.camera.setExtent(extent)

    # DPI 控制导出图片清晰度。宽高目前主要由模板布局页面决定。
    dpi = int(job_config.get("output", {}).get("dpi", 96))
    layout.exportToPNG(str(output_png), resolution=dpi)

    # 保存 aprx 副本，方便你打开输出目录里的工程检查图层和样式。
    if hasattr(project, "save"):
        project.save()

    return {
        "copied_project": str(copied_project),
        "requested_title": job_config.get("map_title"),
        "warnings": warnings,
    }
