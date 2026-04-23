"""ArcPyRenderer 单元测试。

这个文件测试的是 GIS 渲染核心，但不依赖真实 ArcGIS Pro。

做法是：
    1. 构造一组 FakeArcPy 对象。
    2. 用 monkeypatch 把 `import arcpy` 替换成 fake_module。
    3. 调用 ArcPyRenderer。
    4. 检查它是否正确调用了 JSONToFeatures、ExcelToTable、XYTableToPoint、
       是否设置了符号、标注、输出结果等。

真实 ArcPy smoke 已经在手工验证里跑过；单元测试用 fake 的好处是快、稳定、
不要求每次 CI 或普通开发环境都安装 ArcGIS Pro。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class _FakeExtent:
    def __init__(self, xmin: float, ymin: float, xmax: float, ymax: float) -> None:
        self.XMin = xmin
        self.YMin = ymin
        self.XMax = xmax
        self.YMax = ymax


class _FakeLayer:
    """模拟 ArcPy 图层对象。

    ArcPy 的真实 layer 有很多属性。测试只实现当前渲染器会用到的那一小部分：
    - name
    - symbology
    - supports()
    - labelClasses/CIM definition
    """

    def __init__(self, name: str, *, is_basemap: bool = False, extent=None) -> None:
        self.name = name
        self.isBasemapLayer = is_basemap
        self.extent = extent or _FakeExtent(0, 0, 10, 10)
        self.symbology = _FakeSymbology()
        self.showLabels = False
        self._label_classes = [_FakeLabelClass()]
        self.definition = _FakeLayerDefinition()

    def supports(self, capability: str) -> bool:
        # 渲染器会先问图层是否支持 SYMBOLOGY/SHOWLABELS，再设置样式和标注。
        return capability in {"SYMBOLOGY", "SHOWLABELS"}

    def listLabelClasses(self):
        return self._label_classes

    def getDefinition(self, _version):
        return self.definition

    def setDefinition(self, definition):
        self.definition = definition


class _FakeSymbol:
    """模拟 ArcPy 符号对象。

    这里的属性会被渲染器写入，测试再读取它们进行断言。
    """

    def __init__(self) -> None:
        self.color = None
        self.outlineColor = None
        self.outlineWidth = None
        self.size = None


class _FakeRenderer:
    """模拟 symbology.renderer。"""

    def __init__(self) -> None:
        self.symbol = _FakeSymbol()


class _FakeSymbology:
    """模拟 layer.symbology。"""

    def __init__(self) -> None:
        self.renderer = _FakeRenderer()


class _FakeLabelClass:
    """模拟 ArcPy 标注类。

    expression 例如 `$feature.name`，visible 表示标注是否开启。
    """

    def __init__(self) -> None:
        self.expression = ""
        self.visible = False


class _FakeColor:
    """模拟 CIM 颜色对象，CIM 颜色通常写在 values 数组里。"""

    def __init__(self) -> None:
        self.values = None


class _FakeTextSymbolLayer:
    """模拟文字符号里的颜色层。"""

    def __init__(self) -> None:
        self.color = _FakeColor()


class _FakeTextPolygonSymbol:
    """模拟 CIM textSymbol.symbol。"""

    def __init__(self) -> None:
        self.symbolLayers = [_FakeTextSymbolLayer()]


class _FakeCimTextSymbol:
    """模拟 CIM 文字符号，height 对应字体大小。"""

    def __init__(self) -> None:
        self.height = None
        self.symbol = _FakeTextPolygonSymbol()


class _FakeCimLabelClass:
    """模拟 CIM label class。"""

    def __init__(self) -> None:
        self.textSymbol = SimpleNamespace(symbol=_FakeCimTextSymbol())


class _FakeLayerDefinition:
    """模拟 layer.getDefinition('V2') 返回的 CIM definition。

    红色三角形和标注字号都通过这个对象修改，所以 fake 结构要和渲染器访问路径一致。
    """

    def __init__(self) -> None:
        self.labelClasses = [_FakeCimLabelClass()]
        self.renderer = SimpleNamespace(
            symbol=SimpleNamespace(
                symbol=SimpleNamespace(
                    symbolLayers=[
                        SimpleNamespace(
                            size=None,
                            markerGraphics=[
                                SimpleNamespace(
                                    geometry=None,
                                    symbol=SimpleNamespace(
                                        symbolLayers=[
                                            SimpleNamespace(color=SimpleNamespace(values=None)),
                                            SimpleNamespace(color=SimpleNamespace(values=None)),
                                        ]
                                    ),
                                )
                            ],
                        )
                    ]
                )
            )
        )


class _FakeMap:
    """模拟 ArcGIS Pro Map 对象。"""

    def __init__(self) -> None:
        # 初始包含一个底图和一个旧业务图层，用来测试渲染前是否清理旧业务图层。
        self._layers = [_FakeLayer("world topo", is_basemap=True), _FakeLayer("old business")]
        self.added_paths: list[str] = []
        self.removed_layers: list[str] = []

    def listLayers(self):
        return list(self._layers)

    def removeLayer(self, layer):
        # 记录被删除的图层名，方便必要时断言。
        self.removed_layers.append(layer.name)
        self._layers = [candidate for candidate in self._layers if candidate is not layer]

    def addDataFromPath(self, path: str):
        # ArcPy addDataFromPath 会返回新增图层。这里用文件名 stem 当默认图层名。
        self.added_paths.append(path)
        layer = _FakeLayer(Path(path).stem)
        self._layers.append(layer)
        return layer


class _FakeCamera:
    """模拟地图框 camera，用于记录 setExtent 调用。"""

    def __init__(self) -> None:
        self.extents: list[str] = []

    def setExtent(self, extent):
        self.extents.append(extent)


class _FakeMapFrame:
    """模拟布局里的地图框。"""

    def __init__(self, fake_map: _FakeMap) -> None:
        self.type = "MAPFRAME_ELEMENT"
        self.name = "地图框"
        self.visible = True
        self.camera = _FakeCamera()
        self.requested_extent_layers: list[str] = []
        self.elementPositionX = 1
        self.elementPositionY = 1
        self.elementWidth = 9
        self.elementHeight = 6

    def getLayerExtent(self, layer, *_args):
        # 真实 ArcPy 会计算图层范围；fake 直接返回 layer.extent。
        self.requested_extent_layers.append(layer.name)
        return layer.extent


class _FakeLayoutElement:
    """模拟布局里的标题、图例、比例尺、指北针。"""

    def __init__(
        self,
        element_type: str,
        name: str,
        *,
        text: str | None = None,
        x: float = 0,
        y: float = 0,
        width: float = 1,
        height: float = 1,
    ) -> None:
        self.type = element_type
        self.name = name
        self.text = text
        self.visible = True
        self.elementPositionX = x
        self.elementPositionY = y
        self.elementWidth = width
        self.elementHeight = height
        self.textSize = 10
        self.background_color = None
        self.fittingStrategy = None


class _FakeLayout:
    """模拟 Layout 对象。"""

    def __init__(self, map_frame: _FakeMapFrame | None, elements: list[_FakeLayoutElement] | None = None) -> None:
        self._map_frame = map_frame
        self._elements = elements or []
        self.exported_png: str | None = None
        self.exported_resolution: int | None = None
        self.pageWidth = 11
        self.pageHeight = 8.5
        self.pageUnits = "INCH"

    def listElements(self, element_type=None, wildcard=None):
        elements = []
        if element_type == "MAPFRAME_ELEMENT":
            elements = [] if self._map_frame is None else [self._map_frame]
        elif element_type is None:
            elements = ([] if self._map_frame is None else [self._map_frame]) + list(self._elements)
        else:
            elements = [element for element in self._elements if element.type == element_type]
        if wildcard:
            elements = [element for element in elements if element.name == wildcard]
        return elements

    def exportToPNG(self, path: str, resolution: int = 96):
        # 真实 ArcPy 会导出图片；fake 只写一个字节文件表示“导出发生了”。
        self.exported_png = path
        self.exported_resolution = resolution
        Path(path).write_bytes(b"fake-png")


class _FakeProject:
    """模拟 arcpy.mp.ArcGISProject。"""

    def __init__(
        self,
        opened_path: str,
        *,
        include_map_frame: bool = True,
        layout_elements: list[_FakeLayoutElement] | None = None,
    ) -> None:
        self.opened_path = opened_path
        self._map = _FakeMap()
        self._map_frame = _FakeMapFrame(self._map) if include_map_frame else None
        self._layout = _FakeLayout(self._map_frame, layout_elements)

    def listMaps(self, wildcard=None):
        # 只有名称匹配“地图”时才返回 fake map，模拟模板名称约束。
        if wildcard and wildcard != "地图":
            return []
        return [self._map]

    def listLayouts(self, wildcard=None):
        # 只有名称匹配“布局”时才返回 fake layout。
        if wildcard and wildcard != "布局":
            return []
        return [self._layout]

    def save(self):
        return None


def _install_fake_arcpy(monkeypatch, fake_project_factory, *, fail_on_existing_outputs: bool = False):
    """把假的 arcpy 模块安装到 sys.modules。

    渲染器内部会执行 `import arcpy`。Python 导入模块时会先查 sys.modules，
    所以测试可以把 fake_module 放进去，让渲染器以为自己拿到了真实 ArcPy。

    Args:
        monkeypatch: pytest 的猴子补丁工具，测试结束会自动还原。
        fake_project_factory: 每次打开 ArcGISProject 时创建 fake project 的函数。
        fail_on_existing_outputs: 用来模拟 ArcPy 对“输出已存在”的严格行为。
    """
    excel_calls = []
    xy_calls = []
    json_to_features_calls = []
    table_rows = {}

    def _excel_to_table(input_excel, output_table, sheet_name):
        # 记录调用参数，测试可以检查 Excel 是否真的被转换。
        if fail_on_existing_outputs and Path(output_table).exists():
            raise RuntimeError(f"already exists: {output_table}")
        excel_calls.append((input_excel, output_table, sheet_name))
        table_rows[output_table] = [
            {"lon": 100, "lat": 30, "name": "Station A"},
            {"lon": 101, "lat": 31, "name": "Station B"},
        ]
        Path(output_table).write_text("table", encoding="utf-8")
        return output_table

    def _xy_table_to_point(input_table, output_fc, x_field, y_field, z_field=None, coordinate_system=None):
        # 记录 x/y 字段和坐标系，证明站点 Excel 被转成点图层。
        if fail_on_existing_outputs and Path(output_fc).exists():
            raise RuntimeError(f"already exists: {output_fc}")
        if not Path(input_table).exists():
            raise RuntimeError(f"input table does not exist: {input_table}")
        xy_calls.append((input_table, output_fc, x_field, y_field, z_field, coordinate_system))
        Path(output_fc).write_text("points", encoding="utf-8")
        return output_fc

    class _SearchCursor:
        """Small fake for arcpy.da.SearchCursor over ExcelToTable output rows."""

        def __init__(self, table, field_names):
            self._rows = table_rows.get(str(table), [])
            self._field_names = list(field_names)
            self._index = 0

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            return False

        def __iter__(self):
            return self

        def __next__(self):
            if self._index >= len(self._rows):
                raise StopIteration
            row = self._rows[self._index]
            self._index += 1
            return tuple(row.get(field) for field in self._field_names)

    def _json_to_features(input_json, output_features, geometry_type=None):
        # 记录 geometry_type，测试会断言流域是 POLYGON、河流是 POLYLINE。
        if fail_on_existing_outputs and Path(output_features).exists():
            raise RuntimeError(f"already exists: {output_features}")
        json_to_features_calls.append((input_json, output_features, geometry_type))
        Path(output_features).write_text("features", encoding="utf-8")
        return output_features

    class _FakeArcGISProject:
        """模拟 arcpy.mp.ArcGISProject 构造器。"""

        def __init__(self, opened_path: str) -> None:
            self._project = fake_project_factory(opened_path)

        def __getattr__(self, name):
            # 把未定义属性转发给内部 fake project，减少重复样板代码。
            return getattr(self._project, name)

    # 这个 SimpleNamespace 就是假的 arcpy 模块。
    # 只实现当前渲染器使用到的 mp/conversion/management/SpatialReference。
    fake_module = SimpleNamespace(
        mp=SimpleNamespace(ArcGISProject=_FakeArcGISProject),
        conversion=SimpleNamespace(
            ExcelToTable=_excel_to_table,
            JSONToFeatures=_json_to_features,
        ),
        management=SimpleNamespace(XYTableToPoint=_xy_table_to_point),
        da=SimpleNamespace(SearchCursor=_SearchCursor),
        SpatialReference=lambda wkid: f"sr:{wkid}",
        Extent=_FakeExtent,
        _excel_calls=excel_calls,
        _xy_calls=xy_calls,
        _json_to_features_calls=json_to_features_calls,
    )
    monkeypatch.setitem(sys.modules, "arcpy", fake_module)
    return fake_module


def _job_config(tmp_path: Path) -> dict:
    """构造一份渲染器可直接消费的 job_config。

    注意它和 API 请求体相比少了 `output_dir`：
    API 层会把 output_dir 拆出来，ArcPyRenderer 只接收地图业务配置。
    """
    basin = tmp_path / "basin.geojson"
    rivers = tmp_path / "rivers.geojson"
    green = tmp_path / "green.xlsx"
    red = tmp_path / "red.xlsx"
    for path in (basin, rivers, green, red):
        # FakeArcPy 不读取真实内容，但路径需要存在，更贴近真实调用。
        path.write_text("sample", encoding="utf-8")
    return {
        "map_title": "styled map",
        "output": {"width_px": 1200, "height_px": 800, "dpi": 144},
        "inputs": {
            "basin_boundary": {"path": str(basin)},
            "river_network": {"path": str(rivers)},
            "station_layers": [
                {
                    "path": str(green),
                    "sheet_name": "Sheet1",
                    "x_field": "lon",
                    "y_field": "lat",
                    "name_field": "name",
                    "layer_name": "GreenCircleStations",
                    "symbol": {
                        "preset": "circle_green",
                        "shape": "circle",
                        "color": "#00a651",
                        "size_pt": 20,
                    },
                    "label": {
                        "enabled": True,
                        "color": "#000000",
                        "font_size_pt": 20,
                        "position": "top_right",
                        "rotation_deg": 0,
                    },
                },
                {
                    "path": str(red),
                    "sheet_name": "Sheet1",
                    "x_field": "lon",
                    "y_field": "lat",
                    "name_field": "name",
                    "layer_name": "RedTriangleStations",
                    "symbol": {
                        "preset": "triangle_red",
                        "shape": "triangle",
                        "color": "#ff0000",
                        "size_pt": 20,
                    },
                    "label": {
                        "enabled": True,
                        "color": "#000000",
                        "font_size_pt": 20,
                        "position": "top_right",
                        "rotation_deg": 0,
                    },
                },
            ],
        },
        "layout": {
            "title": {"enabled": True},
            "legend": {"enabled": True},
            "scale_bar": {"enabled": True},
            "north_arrow": {"enabled": True},
        },
        "style": {
            "basin_boundary": {"color": "#222222", "width_pt": 1.2},
            "basin_fill": {"color": "#e6f0d4", "opacity": 0.45},
            "river_network": {"color": "#2f80ed", "width_pt": 2.5},
        },
    }


def test_arcpy_renderer_copies_template_and_exports_png(tmp_path, monkeypatch):
    """渲染器应该复制模板工程，并导出 map.png/result.json。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    output_dir = tmp_path / "outputs"
    opened_paths: list[str] = []

    def build_project(opened_path: str):
        # 记录 ArcPy 打开的工程路径，用来确认打开的是副本，不是原模板。
        opened_paths.append(opened_path)
        return _FakeProject(opened_path)

    _install_fake_arcpy(monkeypatch, build_project)

    result = ArcPyRenderer().render(
        job_config=_job_config(tmp_path),
        output_dir=output_dir,
        template_project=template_project,
    )

    copied_project = output_dir / template_project.name
    assert copied_project.exists()
    assert opened_paths == [str(copied_project)]
    assert result["status"] == "succeeded"
    assert result["feature_counts"]["station_layers"] == 2
    assert (output_dir / "map.png").exists()
    assert (output_dir / "result.json").exists()


def test_arcpy_renderer_applies_requested_output_pixel_size_and_scales_layout_elements(tmp_path, monkeypatch):
    """width_px/height_px/dpi 应转换页面尺寸，并保留模板地图框的大区域。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_projects = []

    def build_project(opened_path: str):
        project = _FakeProject(opened_path)
        fake_projects.append(project)
        return project

    _install_fake_arcpy(monkeypatch, build_project)

    result = ArcPyRenderer().render(
        job_config=_job_config(tmp_path),
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    layout = fake_projects[0]._layout
    map_frame = fake_projects[0]._map_frame
    assert round(layout.pageWidth, 3) == round(1200 / 144, 3)
    assert round(layout.pageHeight, 3) == round(800 / 144, 3)
    assert round(map_frame.elementPositionX, 3) == round(1 * (layout.pageWidth / 11), 3)
    assert round(map_frame.elementPositionY, 3) == round(1 * (layout.pageHeight / 8.5), 3)
    assert round(map_frame.elementWidth, 3) == round(9 * (layout.pageWidth / 11), 3)
    assert round(map_frame.elementHeight, 3) == round(6 * (layout.pageHeight / 8.5), 3)
    assert layout.exported_resolution == 144
    assert result["requested_output"]["width_px"] == 1200
    assert result["requested_output"]["height_px"] == 800
    assert result["requested_output"]["dpi"] == 144


def test_arcpy_renderer_tunes_legend_items_to_uniform_small_patches():
    """图例里的站点大符号应缩进统一 patch，避免比流域和河流图样大很多。"""
    from types import SimpleNamespace

    from app.gis.render import arcpy_renderer

    legend = SimpleNamespace(
        scaleSymbols=True,
        autoFonts=False,
        minFontSize=6,
        defaultPatchHeight=12,
        defaultPatchWidth=24,
        itemGap=5,
        classGap=5,
        layerNameGap=5,
        patchGap=5,
        textGap=5,
        items=[
            SimpleNamespace(patchHeight=0, patchWidth=0, scaleToPatch=False),
            SimpleNamespace(patchHeight=0, patchWidth=0, scaleToPatch=False),
            SimpleNamespace(patchHeight=0, patchWidth=0, scaleToPatch=False),
        ],
    )

    arcpy_renderer._tune_cim_legend_element(legend)

    assert legend.scaleSymbols is False
    assert legend.defaultPatchHeight == 6
    assert legend.defaultPatchWidth == 12
    assert all(item.scaleToPatch is True for item in legend.items)
    assert all(item.patchHeight == 6 for item in legend.items)
    assert all(item.patchWidth == 12 for item in legend.items)


def test_arcpy_renderer_converts_requested_output_size_when_layout_uses_millimeters(tmp_path, monkeypatch):
    """模板布局单位是毫米时，像素尺寸也应按 dpi 正确换算。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_projects = []

    def build_project(opened_path: str):
        project = _FakeProject(opened_path)
        project._layout.pageUnits = "MILLIMETER"
        fake_projects.append(project)
        return project

    _install_fake_arcpy(monkeypatch, build_project)

    result = ArcPyRenderer().render(
        job_config=_job_config(tmp_path),
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    layout = fake_projects[0]._layout
    map_frame = fake_projects[0]._map_frame
    assert round(layout.pageWidth, 3) == round(1200 / 144 * 25.4, 3)
    assert round(layout.pageHeight, 3) == round(800 / 144 * 25.4, 3)
    assert round(map_frame.elementWidth, 3) == round(9 * (layout.pageWidth / 11), 3)
    assert round(map_frame.elementHeight, 3) == round(6 * (layout.pageHeight / 8.5), 3)
    assert result["requested_output"]["layout_page_units"] == "MILLIMETER"


def test_arcpy_renderer_updates_template_layout_elements_and_title_fallback(tmp_path, monkeypatch):
    """模板中已有的标题/图例/比例尺/指北针元素应被按请求更新。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_projects = []
    title = _FakeLayoutElement("TEXT_ELEMENT", "文本", text="图名", x=2, y=7, width=4, height=0.5)
    legend = _FakeLayoutElement("LEGEND_ELEMENT", "图例", x=8, y=1, width=2, height=3)
    scale_bar = _FakeLayoutElement("MAPSURROUND_ELEMENT", "比例尺", x=1, y=0.3, width=2, height=0.4)
    north_arrow = _FakeLayoutElement("MAPSURROUND_ELEMENT", "指北针", x=7, y=6, width=0.5, height=1)

    def build_project(opened_path: str):
        project = _FakeProject(opened_path, layout_elements=[title, legend, scale_bar, north_arrow])
        fake_projects.append(project)
        return project

    _install_fake_arcpy(monkeypatch, build_project)

    ArcPyRenderer().render(
        job_config=_job_config(tmp_path),
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    layout = fake_projects[0]._layout
    assert title.text == "styled map"
    assert title.visible is True
    assert legend.visible is True
    assert scale_bar.visible is True
    assert north_arrow.visible is True
    assert round(title.elementPositionX, 3) == round(layout.pageWidth * 0.36, 3)
    assert round(title.elementPositionY, 3) == round(layout.pageHeight * 0.86, 3)
    assert round(title.elementWidth, 3) == round(layout.pageWidth * 0.28, 3)
    assert round(title.elementHeight, 3) == round(layout.pageHeight * 0.055, 3)
    assert title.textSize == 18
    assert title.background_color == "#ffffff"
    assert round(legend.elementPositionX, 3) == round(layout.pageWidth * 0.045, 3)
    assert round(legend.elementPositionY, 3) == round(layout.pageHeight * 0.42, 3)
    assert round(legend.elementWidth, 3) == round(layout.pageWidth * 0.22, 3)
    assert round(legend.elementHeight, 3) == round(layout.pageHeight * 0.38, 3)
    assert legend.fittingStrategy == "AdjustColumnsAndFont"
    assert legend.background_color == "#ffffff"
    assert round(scale_bar.elementPositionX, 3) == round(layout.pageWidth * 0.31, 3)
    assert round(scale_bar.elementPositionY, 3) == round(layout.pageHeight * 0.055, 3)
    assert round(scale_bar.elementWidth, 3) == round(layout.pageWidth * 0.34, 3)
    assert round(scale_bar.elementHeight, 3) == round(layout.pageHeight * 0.035, 3)
    assert round(north_arrow.elementPositionX, 3) == round(layout.pageWidth * 0.92, 3)
    assert round(north_arrow.elementPositionY, 3) == round(layout.pageHeight * 0.78, 3)
    assert round(north_arrow.elementWidth, 3) == round(layout.pageWidth * 0.035, 3)
    assert round(north_arrow.elementHeight, 3) == round(layout.pageHeight * 0.08, 3)


def test_arcpy_renderer_applies_manual_layout_element_positions(tmp_path, monkeypatch):
    """manual 布局应按请求里的绝对布局单位设置元素位置和大小。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_projects = []
    title = _FakeLayoutElement("TEXT_ELEMENT", "文本", text="图名")
    legend = _FakeLayoutElement("LEGEND_ELEMENT", "图例")
    scale_bar = _FakeLayoutElement("MAPSURROUND_ELEMENT", "比例尺")
    north_arrow = _FakeLayoutElement("MAPSURROUND_ELEMENT", "指北针")

    def build_project(opened_path: str):
        project = _FakeProject(opened_path, layout_elements=[title, legend, scale_bar, north_arrow])
        fake_projects.append(project)
        return project

    _install_fake_arcpy(monkeypatch, build_project)
    job_config = _job_config(tmp_path)
    job_config["layout"] = {
        "basemap": "Topographic",
        "mode": "manual",
        "elements": {
            "map_frame": {"x": 10, "y": 11, "width": 120, "height": 80},
            "title": {
                "enabled": True,
                "x": 20,
                "y": 170,
                "width": 80,
                "height": 12,
                "font_size": 16,
                "background": True,
            },
            "legend": {"enabled": True, "x": 12, "y": 90, "width": 60, "height": 70, "background": True},
            "scale_bar": {"enabled": True, "x": 85, "y": 12, "width": 90, "height": 8},
            "north_arrow": {"enabled": True, "x": 240, "y": 160, "width": 8, "height": 18},
        },
    }

    ArcPyRenderer().render(
        job_config=job_config,
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    map_frame = fake_projects[0]._map_frame
    assert (map_frame.elementPositionX, map_frame.elementPositionY) == (10, 11)
    assert (map_frame.elementWidth, map_frame.elementHeight) == (120, 80)
    assert (title.elementPositionX, title.elementPositionY) == (20, 170)
    assert (title.elementWidth, title.elementHeight) == (80, 12)
    assert title.textSize == 16
    assert (legend.elementPositionX, legend.elementPositionY) == (12, 90)
    assert (scale_bar.elementWidth, scale_bar.elementHeight) == (90, 8)
    assert (north_arrow.elementPositionX, north_arrow.elementPositionY) == (240, 160)


def test_arcpy_renderer_hides_disabled_layout_elements(tmp_path, monkeypatch):
    """关闭布局元素开关时，应隐藏模板中对应元素。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    title = _FakeLayoutElement("TEXT_ELEMENT", "标题", text="图名")
    legend = _FakeLayoutElement("LEGEND_ELEMENT", "图例")
    scale_bar = _FakeLayoutElement("MAPSURROUND_ELEMENT", "比例尺")
    north_arrow = _FakeLayoutElement("MAPSURROUND_ELEMENT", "指北针")

    def build_project(opened_path: str):
        return _FakeProject(opened_path, layout_elements=[title, legend, scale_bar, north_arrow])

    _install_fake_arcpy(monkeypatch, build_project)
    job_config = _job_config(tmp_path)
    job_config["layout"] = {
        "title": {"enabled": False},
        "legend": {"enabled": False},
        "scale_bar": {"enabled": False},
        "north_arrow": {"enabled": False},
    }

    ArcPyRenderer().render(
        job_config=job_config,
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    assert title.visible is False
    assert legend.visible is False
    assert scale_bar.visible is False
    assert north_arrow.visible is False


def test_arcpy_renderer_converts_geojson_and_station_excel(tmp_path, monkeypatch):
    """GeoJSON 和 Excel 应转换成 ArcGIS 可加载的临时要素类。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_arcpy = _install_fake_arcpy(monkeypatch, lambda opened_path: _FakeProject(opened_path))

    ArcPyRenderer().render(
        job_config=_job_config(tmp_path),
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    assert [call[2] for call in fake_arcpy._json_to_features_calls] == ["POLYGON", "POLYLINE"]
    # 两组站点图层，所以 ExcelToTable 和 XYTableToPoint 都应调用两次。
    assert len(fake_arcpy._excel_calls) == 2
    assert len(fake_arcpy._xy_calls) == 2
    assert fake_arcpy._xy_calls[0][2:4] == ("lon", "lat")


def test_arcpy_renderer_applies_station_styles_and_black_large_labels(tmp_path, monkeypatch):
    """站点样式应保留：绿色圆形、红色三角形、黑色 20 号标注。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_projects = []

    def build_project(opened_path: str):
        project = _FakeProject(opened_path)
        fake_projects.append(project)
        return project

    _install_fake_arcpy(monkeypatch, build_project)

    ArcPyRenderer().render(
        job_config=_job_config(tmp_path),
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    layers = {layer.name: layer for layer in fake_projects[0]._map.listLayers()}
    green_layer = layers["GreenCircleStations"]
    red_layer = layers["RedTriangleStations"]
    # 绿色圆形站点：颜色和大小来自请求里的 symbol。
    assert green_layer.symbology.renderer.symbol.color == {"RGB": [0, 166, 81, 100]}
    assert green_layer.symbology.renderer.symbol.size == 20
    assert green_layer.definition.labelClasses[0].textSymbol.symbol.height == 20
    # 标注颜色仍然是黑色，不跟着红色三角形变红。
    assert green_layer.definition.labelClasses[0].textSymbol.symbol.symbol.symbolLayers[0].color.values == [
        0,
        0,
        0,
        100,
    ]
    # 红色三角形站点：普通 symbology 设置红色，CIM geometry 设置三角形。
    assert red_layer.symbology.renderer.symbol.color == {"RGB": [255, 0, 0, 100]}
    assert red_layer.definition.renderer.symbol.symbol.symbolLayers[0].markerGraphics[0].geometry is not None
    assert red_layer.definition.labelClasses[0].textSymbol.symbol.height == 20


def test_arcpy_renderer_applies_split_square_and_diamond_shapes(tmp_path, monkeypatch):
    """shape 和 color_preset 分开传入时，方形/菱形也应真正写入 CIM 几何。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_projects = []

    def build_project(opened_path: str):
        project = _FakeProject(opened_path)
        fake_projects.append(project)
        return project

    _install_fake_arcpy(monkeypatch, build_project)
    job_config = _job_config(tmp_path)
    job_config["inputs"]["station_layers"][0]["symbol"] = {
        "shape": "square",
        "color_preset": "green",
        "size_pt": 18,
    }
    job_config["inputs"]["station_layers"][1]["symbol"] = {
        "shape": "diamond",
        "color_preset": "red",
        "size_pt": 18,
    }

    ArcPyRenderer().render(
        job_config=job_config,
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    layers = {layer.name: layer for layer in fake_projects[0]._map.listLayers()}
    square_geometry = layers["GreenCircleStations"].definition.renderer.symbol.symbol.symbolLayers[0].markerGraphics[0].geometry
    diamond_geometry = layers["RedTriangleStations"].definition.renderer.symbol.symbol.symbolLayers[0].markerGraphics[0].geometry
    assert square_geometry["rings"][0] == [[-2.0, 2.0], [2.0, 2.0], [2.0, -2.0], [-2.0, -2.0], [-2.0, 2.0]]
    assert diamond_geometry["rings"][0] == [[0, 2.0], [2.0, 0], [0, -2.0], [-2.0, 0], [0, 2.0]]


def test_arcpy_renderer_applies_rectangle_marker_shape(tmp_path, monkeypatch):
    """rectangle 站点形状应写入比正方形更宽的 CIM 几何。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_projects = []

    def build_project(opened_path: str):
        project = _FakeProject(opened_path)
        fake_projects.append(project)
        return project

    _install_fake_arcpy(monkeypatch, build_project)
    job_config = _job_config(tmp_path)
    job_config["inputs"]["station_layers"][0]["symbol"] = {
        "shape": "rectangle",
        "color_preset": "green",
        "size_pt": 18,
    }

    ArcPyRenderer().render(
        job_config=job_config,
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    layers = {layer.name: layer for layer in fake_projects[0]._map.listLayers()}
    rectangle_geometry = layers["GreenCircleStations"].definition.renderer.symbol.symbol.symbolLayers[0].markerGraphics[0].geometry
    assert rectangle_geometry["rings"][0] == [[-3.0, 1.5], [3.0, 1.5], [3.0, -1.5], [-3.0, -1.5], [-3.0, 1.5]]


def test_arcpy_renderer_applies_station_marker_rotation(tmp_path, monkeypatch):
    """站点符号旋转应写到 symbol.rotation_deg，而不是标注文字配置。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_projects = []

    def build_project(opened_path: str):
        project = _FakeProject(opened_path)
        fake_projects.append(project)
        return project

    _install_fake_arcpy(monkeypatch, build_project)
    job_config = _job_config(tmp_path)
    job_config["inputs"]["station_layers"][0]["symbol"] = {
        "shape": "triangle",
        "color_preset": "red",
        "size_pt": 18,
        "rotation_deg": 35,
    }

    ArcPyRenderer().render(
        job_config=job_config,
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    layers = {layer.name: layer for layer in fake_projects[0]._map.listLayers()}
    marker_layer = layers["GreenCircleStations"].definition.renderer.symbol.symbol.symbolLayers[0]
    assert marker_layer.angle == 35


def test_arcpy_renderer_splits_one_station_excel_by_per_point_styles(tmp_path, monkeypatch):
    """One station Excel should render separate internal layers for differently styled rows."""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_projects = []

    def build_project(opened_path: str):
        project = _FakeProject(opened_path)
        fake_projects.append(project)
        return project

    fake_arcpy = _install_fake_arcpy(monkeypatch, build_project)
    job_config = _job_config(tmp_path)
    job_config["inputs"]["station_layers"] = [job_config["inputs"]["station_layers"][0]]
    job_config["inputs"]["station_layers"][0]["layer_name"] = "MixedStations"
    job_config["inputs"]["station_layers"][0]["points"] = [
        {
            "row_number": 2,
            "name": "Station A",
            "symbol": {
                "shape": "circle",
                "color_preset": "green",
                "color": "#00a651",
                "size_pt": 20,
                "rotation_deg": 0,
            },
            "label": {
                "enabled": True,
                "color": "#000000",
                "font_size_pt": 20,
                "position": "top_right",
            },
        },
        {
            "row_number": 3,
            "name": "Station B",
            "symbol": {
                "shape": "triangle",
                "color_preset": "red",
                "color": "#ff0000",
                "size_pt": 22,
                "rotation_deg": 0,
            },
            "label": {
                "enabled": True,
                "color": "#111111",
                "font_size_pt": 18,
                "position": "left",
            },
        },
    ]

    result = ArcPyRenderer().render(
        job_config=job_config,
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    assert result["status"] == "succeeded"
    assert len(fake_arcpy._excel_calls) == 1
    assert len(fake_arcpy._xy_calls) == 2
    layers = [layer for layer in fake_projects[0]._map.listLayers() if layer.name.startswith("MixedStations")]
    assert len(layers) == 2
    assert layers[0].symbology.renderer.symbol.color == {"RGB": [0, 166, 81, 100]}
    assert layers[1].symbology.renderer.symbol.color == {"RGB": [255, 0, 0, 100]}
    assert layers[1].definition.renderer.symbol.symbol.symbolLayers[0].markerGraphics[0].geometry is not None
    assert layers[1].definition.labelClasses[0].textSymbol.symbol.height == 18
    assert "MixedStations - 1" in fake_projects[0]._map_frame.requested_extent_layers
    assert "MixedStations - 2" in fake_projects[0]._map_frame.requested_extent_layers


def test_arcpy_renderer_adds_padding_to_combined_map_extent(tmp_path, monkeypatch):
    """Final map extent should use the approved balanced default padding."""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_projects = []

    def build_project(opened_path: str):
        project = _FakeProject(opened_path)
        fake_projects.append(project)
        return project

    _install_fake_arcpy(monkeypatch, build_project)

    ArcPyRenderer().render(
        job_config=_job_config(tmp_path),
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    extent = fake_projects[0]._map_frame.camera.extents[-1]
    assert round(extent.XMin, 3) == -2.408
    assert round(extent.YMin, 3) == -1.4
    assert round(extent.XMax, 3) == 11.808
    assert round(extent.YMax, 3) == 11.4


def test_arcpy_renderer_uses_manual_map_extent(tmp_path, monkeypatch):
    """map_view.manual_extent 应完全覆盖自动图层范围。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    fake_projects = []

    def build_project(opened_path: str):
        project = _FakeProject(opened_path)
        fake_projects.append(project)
        return project

    _install_fake_arcpy(monkeypatch, build_project)
    job_config = _job_config(tmp_path)
    job_config["map_view"] = {
        "mode": "manual_extent",
        "extent": {"xmin": 90.5, "ymin": 30.25, "xmax": 110.75, "ymax": 45.5},
    }

    ArcPyRenderer().render(
        job_config=job_config,
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    extent = fake_projects[0]._map_frame.camera.extents[-1]
    assert (extent.XMin, extent.YMin, extent.XMax, extent.YMax) == (90.5, 30.25, 110.75, 45.5)


def test_arcpy_renderer_adds_multiple_basin_and_river_layers_with_independent_styles(tmp_path, monkeypatch):
    """多流域和多河流配置应分别加载，并应用各自图层样式。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    second_basin = tmp_path / "basin_2.geojson"
    second_river = tmp_path / "rivers_2.geojson"
    second_basin.write_text("{}", encoding="utf-8")
    second_river.write_text("{}", encoding="utf-8")
    fake_projects = []

    def build_project(opened_path: str):
        project = _FakeProject(opened_path)
        fake_projects.append(project)
        return project

    _install_fake_arcpy(monkeypatch, build_project)
    job_config = _job_config(tmp_path)
    job_config["inputs"]["basin_boundaries"] = [
        {
            "path": job_config["inputs"]["basin_boundary"]["path"],
            "layer_name": "上游流域",
            "style": {
                "basin_boundary": {"color": "#111111", "width_pt": 1.1},
                "basin_fill": {"color": "#e6f0d4", "opacity": 0.45},
            },
        },
        {
            "path": str(second_basin),
            "layer_name": "下游流域",
            "style": {
                "basin_boundary": {"color": "#7a4f2a", "width_pt": 0.8},
                "basin_fill": {"color": "#f6d7a7", "opacity": 0.35},
            },
        },
    ]
    job_config["inputs"]["river_networks"] = [
        {
            "path": job_config["inputs"]["river_network"]["path"],
            "layer_name": "主干河流",
            "style": {"river_network": {"color": "#2f80ed", "width_pt": 2.5}},
        },
        {
            "path": str(second_river),
            "layer_name": "支流",
            "style": {"river_network": {"color": "#00a6c8", "width_pt": 1.2}},
        },
    ]

    ArcPyRenderer().render(
        job_config=job_config,
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    layers = {layer.name: layer for layer in fake_projects[0]._map.listLayers()}
    assert "上游流域" in layers
    assert "下游流域" in layers
    assert "主干河流" in layers
    assert "支流" in layers
    assert layers["下游流域"].symbology.renderer.symbol.color == {"RGB": [246, 215, 167, 35]}
    assert layers["下游流域"].symbology.renderer.symbol.outlineColor == {"RGB": [122, 79, 42, 100]}
    assert layers["支流"].symbology.renderer.symbol.color == {"RGB": [0, 166, 200, 100]}
    assert layers["支流"].symbology.renderer.symbol.size == 1.2


def test_arcpy_renderer_writes_structured_failure_when_template_items_missing(tmp_path, monkeypatch):
    """模板缺少地图框时，应写出结构化失败 result.json。"""
    from app.gis.render import ArcPyRenderer

    template_project = tmp_path / "template.aprx"
    template_project.write_text("template", encoding="utf-8")
    _install_fake_arcpy(
        monkeypatch,
        # include_map_frame=False 模拟模板里没有名为“地图框”的元素。
        lambda opened_path: _FakeProject(opened_path, include_map_frame=False),
    )

    result = ArcPyRenderer().render(
        job_config=_job_config(tmp_path),
        output_dir=tmp_path / "outputs",
        template_project=template_project,
    )

    assert result["status"] == "failed"
    assert "map frame named 地图框" in result["error"]
    saved = json.loads((tmp_path / "outputs" / "result.json").read_text(encoding="utf-8"))
    assert saved["status"] == "failed"
