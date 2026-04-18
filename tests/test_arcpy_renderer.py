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


class _FakeLayer:
    """模拟 ArcPy 图层对象。

    ArcPy 的真实 layer 有很多属性。测试只实现当前渲染器会用到的那一小部分：
    - name
    - symbology
    - supports()
    - labelClasses/CIM definition
    """

    def __init__(self, name: str, *, is_basemap: bool = False, extent: str | None = None) -> None:
        self.name = name
        self.isBasemapLayer = is_basemap
        self.extent = extent or f"extent:{name}"
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
        self.name = "地图框"
        self.camera = _FakeCamera()
        self.requested_extent_layers: list[str] = []

    def getLayerExtent(self, layer, *_args):
        # 真实 ArcPy 会计算图层范围；fake 直接返回 layer.extent。
        self.requested_extent_layers.append(layer.name)
        return layer.extent


class _FakeLayout:
    """模拟 Layout 对象。"""

    def __init__(self, map_frame: _FakeMapFrame | None) -> None:
        self._map_frame = map_frame
        self.exported_png: str | None = None

    def listElements(self, element_type=None, wildcard=None):
        # 当前渲染器主要查找 MAPFRAME_ELEMENT。
        # 标题/图例/比例尺在 fake 中故意返回空，用来产生 warnings。
        if element_type == "MAPFRAME_ELEMENT":
            if self._map_frame is None or (wildcard and wildcard != self._map_frame.name):
                return []
            return [self._map_frame]
        return []

    def exportToPNG(self, path: str, resolution: int = 96):
        # 真实 ArcPy 会导出图片；fake 只写一个字节文件表示“导出发生了”。
        self.exported_png = path
        Path(path).write_bytes(b"fake-png")


class _FakeProject:
    """模拟 arcpy.mp.ArcGISProject。"""

    def __init__(self, opened_path: str, *, include_map_frame: bool = True) -> None:
        self.opened_path = opened_path
        self._map = _FakeMap()
        self._map_frame = _FakeMapFrame(self._map) if include_map_frame else None
        self._layout = _FakeLayout(self._map_frame)

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

    def _excel_to_table(input_excel, output_table, sheet_name):
        # 记录调用参数，测试可以检查 Excel 是否真的被转换。
        if fail_on_existing_outputs and Path(output_table).exists():
            raise RuntimeError(f"already exists: {output_table}")
        excel_calls.append((input_excel, output_table, sheet_name))
        Path(output_table).write_text("table", encoding="utf-8")
        return output_table

    def _xy_table_to_point(input_table, output_fc, x_field, y_field, z_field=None, coordinate_system=None):
        # 记录 x/y 字段和坐标系，证明站点 Excel 被转成点图层。
        if fail_on_existing_outputs and Path(output_fc).exists():
            raise RuntimeError(f"already exists: {output_fc}")
        xy_calls.append((input_table, output_fc, x_field, y_field, z_field, coordinate_system))
        Path(output_fc).write_text("points", encoding="utf-8")
        return output_fc

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
        SpatialReference=lambda wkid: f"sr:{wkid}",
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
        "layout": {"legend": {"enabled": True}, "scale_bar": {"enabled": True}},
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
