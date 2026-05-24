"""Backend API 测试。

这些测试关注 Flask 接口层，不真正调用 ArcPy。

为什么不直接在这里跑 ArcPy？
    ArcPy 很慢，并且只能在 ArcGIS Pro Python 中运行。
    API 层测试只需要证明：
    - 路由能访问。
    - 参数能校验。
    - 请求能转换成 renderer.render() 的参数。
    - 返回 JSON 格式正确。

所以这里使用 FakeRenderer 代替真实 ArcPyRenderer。
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def test_runtime_site_packages_adds_project_venv_path(tmp_path):
    """运行时依赖搜索路径应能加入项目 .venv，并让它优先于用户目录。"""
    from app import _add_existing_site_package_dirs

    project_site_packages = tmp_path / ".venv" / "Lib" / "site-packages"
    user_site_packages = tmp_path / "user_site" / "site-packages"
    project_site_packages.mkdir(parents=True)
    user_site_packages.mkdir(parents=True)
    project_path_text = str(project_site_packages)
    user_path_text = str(user_site_packages)
    for path_text in (project_path_text, user_path_text):
        while path_text in sys.path:
            sys.path.remove(path_text)

    _add_existing_site_package_dirs([project_site_packages, user_site_packages])

    assert project_path_text in sys.path
    assert user_path_text in sys.path
    assert sys.path.index(project_path_text) < sys.path.index(user_path_text)


def test_create_app_adds_numpy_in1d_compatibility():
    """create_app should restore np.in1d for older GIS dependencies on NumPy 2.x."""
    import numpy as np
    from app import _ensure_numpy_compatibility

    original = getattr(np, "in1d", None)
    if hasattr(np, "in1d"):
        delattr(np, "in1d")

    try:
        _ensure_numpy_compatibility()
        assert hasattr(np, "in1d")
        result = np.in1d([1, 2, 3], [2, 4])
        assert result.tolist() == [False, True, False]
    finally:
        if original is None and hasattr(np, "in1d"):
            delattr(np, "in1d")
        elif original is not None:
            np.in1d = original


class FakeRenderer:
    """假的渲染器，用来隔离 API 测试和 ArcPy。

    它实现和 ArcPyRenderer 一样的 render() 方法签名，
    但只写一个假的 PNG 和 result.json，不做任何 GIS 操作。
    """

    def __init__(self) -> None:
        # calls 用来记录 API 层传给 renderer 的参数，方便断言转换是否正确。
        self.calls = []

    def render(self, *, job_config, output_dir, template_project):
        """模拟一次成功渲染。"""
        self.calls.append(
            {
                "job_config": job_config,
                "output_dir": output_dir,
                "template_project": template_project,
            }
        )
        # FakeRenderer 也真实写文件，这样测试可以断言 output_png 路径存在。
        output_dir.mkdir(parents=True, exist_ok=True)
        output_png = output_dir / "map.png"
        result_json = output_dir / "result.json"
        output_png.write_bytes(b"fake-png")
        payload = {
            "status": "succeeded",
            "output_png": str(output_png),
            "feature_counts": {
                "station_layers": len(job_config["inputs"]["station_layers"]),
            },
            "warnings": [],
            "elapsed_seconds": 0,
        }
        result_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload


class FakeWatershedService:
    """Fake watershed algorithm service used by API tests."""

    instances = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.calls = []
        FakeWatershedService.instances.append(self)

    def acc_default_value(self):
        self.calls.append("acc_default_value")
        return 35.95

    def random_folder_name_r(self):
        return "program"

    def step0_streams(self):
        self.calls.append("step0_streams")
        return ("boundary.geojson", "streams.geojson", self.kwargs["random_folder_name"])

    def step1_fill_depressions_and_flow(self):
        self.calls.append("step1_fill_depressions_and_flow")

    def step2_identify_streams(self):
        self.calls.append("step2_identify_streams")

    def step3_generate_subwatersheds(self):
        self.calls.append("step3_generate_subwatersheds")

    def generate_final_outputs(self):
        self.calls.append("generate_final_outputs")
        return {
            "prePath": "program",
            "subWatersheds": {"type": "FeatureCollection", "features": []},
            "reaches": {"type": "FeatureCollection", "features": []},
            "junctions": {"type": "FeatureCollection", "features": []},
            "breakPoints": {"type": "FeatureCollection", "features": []},
        }


class FakeMergeDeleteService:
    """Fake merge/delete service used by API tests."""

    instances = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        FakeMergeDeleteService.instances.append(self)

    def step4_merge_or_delete_watersheds(self, *, operation, watershed_ids):
        return {"status": f"watersheds {operation}d", "operation": operation, "ids": watershed_ids}

    def generate_final_outputs(self):
        return {
            "prePath": "program",
            "subWatersheds": {"type": "FeatureCollection", "features": []},
            "reaches": {"type": "FeatureCollection", "features": []},
            "junctions": {"type": "FeatureCollection", "features": []},
        }


def _watershed_test_app(tmp_path: Path):
    """Create an app with fake watershed services injected."""
    from app import create_app

    FakeWatershedService.instances = []
    FakeMergeDeleteService.instances = []
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "WATERSHED_PROGRAM_ROOT": str(tmp_path / "program"),
            "WATERSHED_DEFAULT_DEM_PATH": str(tmp_path / "dem.tif"),
            "RENDERER": FakeRenderer(),
        }
    )
    app.extensions["watershed_service_factory"] = FakeWatershedService
    app.extensions["watershed_merge_service_factory"] = FakeMergeDeleteService
    return app


def _fake_watershed_boundary_runner(*, dem_path: str, points: list[dict], bbox: dict, snap_threshold: int):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "dem_path": dem_path,
                    "bbox": bbox,
                    "snap_threshold": snap_threshold,
                    "point_count": len(points),
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [105.0, 27.2],
                        [105.4, 27.2],
                        [105.4, 26.9],
                        [105.0, 26.9],
                        [105.0, 27.2],
                    ]],
                },
            }
        ],
    }


def _valid_render_payload(tmp_path: Path) -> dict:
    """构造一份合法的 /api/render 请求体。

    tmp_path 是 pytest 提供的临时目录，每个测试独立，不会污染项目真实文件。
    这里特意放两组站点：
    - 绿色圆形站点
    - 红色三角形站点

    这样测试能保护你前面确认过的“总共 4 个站点，两种样式”需求。
    """
    basin = tmp_path / "basin.geojson"
    rivers = tmp_path / "rivers.geojson"
    green_stations = tmp_path / "green.xlsx"
    red_stations = tmp_path / "red.xlsx"
    for path in (basin, rivers, green_stations, red_stations):
        # API 层测试不读取真实 GIS 内容，只需要路径存在即可。
        path.write_text("sample", encoding="utf-8")

    return {
        "output_dir": "first-map",
        "map_title": "sample basin map",
        "output": {"width_px": 1600, "height_px": 1200, "dpi": 150},
        "inputs": {
            "basin_boundary": {"path": str(basin)},
            "river_network": {"path": str(rivers)},
            "station_layers": [
                {
                    "path": str(green_stations),
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
                    "path": str(red_stations),
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
            "basemap": "Topographic",
            "legend": {"enabled": True},
            "scale_bar": {"enabled": True},
        },
        "style": {
            "basin_boundary": {"color": "#222222", "width_pt": 1.2},
            "basin_fill": {"color": "#e6f0d4", "opacity": 0.45},
            "river_network": {"color": "#2f80ed", "width_pt": 2.5},
        },
    }


def test_backend_health_reports_output_folder_and_template(tmp_path):
    """健康检查接口应返回服务状态、输出目录和模板路径。"""
    from app import create_app

    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            # 注入 FakeRenderer，避免测试中误触发真实 ArcPy。
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().get("/api/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["service"] == "gis-flask-study-backend"
    assert payload["data"]["output_folder"] == str(tmp_path / "outputs")
    assert payload["data"]["arcpy_template_project"] == str(template_project)
    assert payload["data"]["arcgis_propy_path"] is None


def test_backend_health_reports_configured_propy_path(tmp_path):
    """健康检查应暴露 ArcGIS Pro Python 路径，方便后续前端配置页读取。"""
    from app import create_app

    propy_path = tmp_path / "ArcGIS" / "Pro" / "bin" / "Python" / "Scripts" / "propy.bat"
    propy_path.parent.mkdir(parents=True)
    propy_path.write_text("@echo off", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "ARCGIS_PROPY": str(propy_path),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().get("/api/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["arcgis_propy_path"] == str(propy_path)


def test_config_reads_propy_path_from_environment(tmp_path, monkeypatch):
    """ArcGIS Pro Python 路径应能通过环境变量配置，避免脚本和前端写死路径。"""
    from app.core.config import get_config

    propy_path = tmp_path / "propy.bat"
    monkeypatch.setenv("ARCGIS_PROPY", str(propy_path))

    config = get_config({"OUTPUT_FOLDER": str(tmp_path / "outputs")})

    assert config.arcgis_propy_path == propy_path.resolve()


def test_config_does_not_use_machine_specific_default_template(tmp_path, monkeypatch):
    """未配置模板时，不应回退到某台电脑上的写死 aprx 路径。"""
    from app.core.config import get_config

    monkeypatch.delenv("ARCPY_TEMPLATE_PROJECT", raising=False)

    config = get_config({"OUTPUT_FOLDER": str(tmp_path / "outputs")})

    assert config.arcpy_template_project is None


def test_config_includes_watershed_defaults(tmp_path):
    """Watershed extraction should have a configurable work root and default DEM path."""
    from app.core.config import get_config

    config = get_config({"OUTPUT_FOLDER": str(tmp_path / "outputs")})

    assert config.watershed_program_root == (ROOT / "docs" / "program").resolve()
    assert config.watershed_default_dem_path == Path(r"D:\work\2026\code\data\data\dem\dem.tif")


def test_render_endpoint_requires_template_when_no_default_is_configured(tmp_path, monkeypatch):
    """没有环境变量且请求体没传 template_project 时，应明确返回 400。"""
    from app import create_app

    monkeypatch.delenv("ARCPY_TEMPLATE_PROJECT", raising=False)
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "RENDERER": FakeRenderer(),
        }
    )
    payload = _valid_render_payload(tmp_path)

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "Missing template_project or ARCPY_TEMPLATE_PROJECT" in body["message"]


def test_render_endpoint_rejects_absolute_output_dir_by_default(tmp_path):
    """默认不允许客户端传绝对 output_dir，避免写入服务器任意目录。"""
    from app import create_app

    renderer = FakeRenderer()
    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "RENDERER": renderer,
        }
    )
    payload = _valid_render_payload(tmp_path)
    payload["output_dir"] = str(tmp_path / "outside-output")

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "output_dir must be a relative path" in body["message"]
    assert renderer.calls == []


def test_render_endpoint_rejects_output_dir_path_traversal(tmp_path):
    """相对路径也不能用 .. 逃出 OUTPUT_FOLDER。"""
    from app import create_app

    renderer = FakeRenderer()
    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "RENDERER": renderer,
        }
    )
    payload = _valid_render_payload(tmp_path)
    payload["output_dir"] = "../outside-output"

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "output_dir must stay under OUTPUT_FOLDER" in body["message"]
    assert renderer.calls == []


def test_render_endpoint_can_allow_absolute_output_dir_for_local_debug(tmp_path):
    """显式开启调试开关后，才允许绝对 output_dir。"""
    from app import create_app

    renderer = FakeRenderer()
    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "ALLOW_ABSOLUTE_OUTPUT_DIR": True,
            "RENDERER": renderer,
        }
    )
    absolute_output = tmp_path / "outside-output"
    payload = _valid_render_payload(tmp_path)
    payload["output_dir"] = str(absolute_output)

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 200
    assert renderer.calls[0]["output_dir"] == absolute_output


def test_render_options_include_current_station_styles(tmp_path):
    """选项接口应把站点形状和颜色预设分开暴露。"""
    from app import create_app

    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().get("/api/render-options")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "Topographic" in data["basemaps"]
    assert data["station_symbol_shapes"] == ["circle", "triangle", "square", "diamond", "rectangle"]
    assert data["station_symbol_color_presets"]["green"] == "#00a651"
    assert data["station_symbol_color_presets"]["red"] == "#ff0000"
    assert "station_symbol_presets" not in data


def test_render_endpoint_accepts_split_station_shape_and_color_preset(tmp_path):
    """站点符号应支持 shape 和 color_preset 分开配置，而不依赖组合 preset。"""
    from app import create_app

    renderer = FakeRenderer()
    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "RENDERER": renderer,
        }
    )

    payload = _valid_render_payload(tmp_path)
    payload["inputs"]["station_layers"][0]["symbol"] = {
        "shape": "circle",
        "color_preset": "green",
        "size_pt": 20,
    }
    payload["inputs"]["station_layers"][1]["symbol"] = {
        "shape": "triangle",
        "color_preset": "red",
        "size_pt": 20,
    }

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 200
    symbols = [
        layer["symbol"]
        for layer in renderer.calls[0]["job_config"]["inputs"]["station_layers"]
    ]
    assert symbols[0]["shape"] == "circle"
    assert symbols[0]["color_preset"] == "green"
    assert symbols[1]["shape"] == "triangle"
    assert symbols[1]["color_preset"] == "red"


def test_render_endpoint_accepts_rectangle_station_symbol_shape(tmp_path):
    """长方形站点符号应作为合法 shape 被 API 接受。"""
    from app import create_app

    renderer = FakeRenderer()
    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "RENDERER": renderer,
        }
    )

    payload = _valid_render_payload(tmp_path)
    payload["inputs"]["station_layers"][0]["symbol"] = {
        "shape": "rectangle",
        "color_preset": "green",
        "size_pt": 20,
    }

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 200
    assert renderer.calls[0]["job_config"]["inputs"]["station_layers"][0]["symbol"]["shape"] == "rectangle"


def test_render_endpoint_accepts_per_point_station_styles(tmp_path):
    """Per-point station styles should pass through to the renderer."""
    from app import create_app

    renderer = FakeRenderer()
    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "RENDERER": renderer,
        }
    )

    payload = _valid_render_payload(tmp_path)
    payload["inputs"]["station_layers"][0]["points"] = [
        {
            "row_number": 2,
            "name": "Station A",
            "symbol": {"shape": "circle", "color_preset": "green", "color": "#00a651", "size_pt": 20},
            "label": {"enabled": True, "color": "#000000", "font_size_pt": 20, "position": "top_right"},
        },
        {
            "row_number": 3,
            "name": "Station B",
            "symbol": {"shape": "triangle", "color_preset": "red", "color": "#ff0000", "size_pt": 22},
            "label": {"enabled": True, "color": "#111111", "font_size_pt": 18, "position": "left"},
        },
    ]

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 200
    points = renderer.calls[0]["job_config"]["inputs"]["station_layers"][0]["points"]
    assert [point["row_number"] for point in points] == [2, 3]
    assert points[1]["symbol"]["shape"] == "triangle"
    assert points[1]["label"]["position"] == "left"


def test_render_endpoint_rejects_invalid_per_point_station_shape(tmp_path):
    """Invalid per-point shapes should be rejected before ArcPy rendering."""
    from app import create_app

    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "RENDERER": FakeRenderer(),
        }
    )
    payload = _valid_render_payload(tmp_path)
    payload["inputs"]["station_layers"][0]["points"] = [
        {
            "row_number": 2,
            "name": "Station A",
            "symbol": {"shape": "star", "color_preset": "green", "size_pt": 20},
            "label": {"enabled": True, "color": "#000000", "font_size_pt": 20, "position": "top_right"},
        }
    ]

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "Unsupported station point symbol shape" in body["message"]


def test_render_endpoint_rejects_invalid_per_point_row_number(tmp_path):
    """Per-point style entries must use numeric Excel row numbers."""
    from app import create_app

    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "RENDERER": FakeRenderer(),
        }
    )
    payload = _valid_render_payload(tmp_path)
    payload["inputs"]["station_layers"][0]["points"] = [
        {
            "row_number": "two",
            "name": "Station A",
            "symbol": {"shape": "circle", "color_preset": "green", "size_pt": 20},
            "label": {"enabled": True, "color": "#000000", "font_size_pt": 20, "position": "top_right"},
        }
    ]

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "row_number must be an Excel data row number" in body["message"]


def test_render_endpoint_rejects_invalid_station_symbol_shape(tmp_path):
    """非法站点形状应在进入渲染器前被拒绝。"""
    from app import create_app

    app = create_app({"TESTING": True, "OUTPUT_FOLDER": str(tmp_path), "RENDERER": FakeRenderer()})
    payload = _valid_render_payload(tmp_path)
    payload["inputs"]["station_layers"][0]["symbol"] = {
        "shape": "star",
        "color_preset": "green",
        "size_pt": 20,
    }

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "Unsupported station symbol shape" in body["message"]


def test_render_endpoint_renders_directly_to_requested_output_dir(tmp_path):
    """POST /api/render 应直接渲染到请求指定的 output_dir。"""
    from app import create_app

    # renderer 是同一个对象，测试结束后可以检查它收到了什么参数。
    renderer = FakeRenderer()
    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "RENDERER": renderer,
        }
    )

    payload = _valid_render_payload(tmp_path)
    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["status"] == "succeeded"
    assert Path(body["data"]["output_png"]).exists()
    # 下面这些断言证明 API 层没有再使用 file_id/job_id/数据库，
    # 而是把 output_dir、template_project、station_layers 直接传给渲染器。
    assert renderer.calls[0]["output_dir"] == Path(tmp_path / "outputs" / payload["output_dir"])
    assert renderer.calls[0]["template_project"] == template_project
    assert renderer.calls[0]["job_config"]["inputs"]["station_layers"][0]["symbol"]["preset"] == "circle_green"
    assert renderer.calls[0]["job_config"]["inputs"]["station_layers"][1]["symbol"]["preset"] == "triangle_red"


def test_render_file_endpoint_serves_output_png_under_output_folder(tmp_path):
    """浏览器前端应能通过只读接口预览 OUTPUT_FOLDER 下的 map.png。"""
    from app import create_app

    output_folder = tmp_path / "outputs"
    output_folder.mkdir()
    output_png = output_folder / "map.png"
    output_png.write_bytes(b"fake-png")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(output_folder),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().get("/api/render/file", query_string={"path": str(output_png)})

    assert response.status_code == 200
    assert response.data == b"fake-png"


def test_render_file_endpoint_rejects_path_outside_output_folder(tmp_path):
    """图片预览接口不能读取 OUTPUT_FOLDER 之外的任意文件。"""
    from app import create_app

    output_folder = tmp_path / "outputs"
    outside_png = tmp_path / "outside.png"
    outside_png.write_bytes(b"fake-png")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(output_folder),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().get("/api/render/file", query_string={"path": str(outside_png)})

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_render_endpoint_rejects_invalid_label_position(tmp_path):
    """非法标注位置应在进入渲染器前被拒绝。"""
    from app import create_app

    app = create_app({"TESTING": True, "OUTPUT_FOLDER": str(tmp_path), "RENDERER": FakeRenderer()})
    payload = _valid_render_payload(tmp_path)
    # diagonal 不在 LABEL_POSITIONS 中，所以应该返回 400。
    payload["inputs"]["station_layers"][0]["label"]["position"] = "diagonal"

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "Unsupported label.position" in body["message"]


def test_render_endpoint_accepts_legend_name_overrides(tmp_path):
    """Legend item rename mappings should pass through to the renderer job config."""
    from app import create_app

    renderer = FakeRenderer()
    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "RENDERER": renderer,
        }
    )

    payload = _valid_render_payload(tmp_path)
    payload["layout"]["legend_style"] = {
        "name_overrides": [
            {
                "source_type": "basin",
                "source_key": "basin-layer-1",
                "default_name": "GreenCircleStations",
                "legend_name": "流域边界",
            },
            {
                "source_type": "station_group",
                "source_key": "station-layer-1-group-1",
                "default_name": "GreenCircleStations - 1",
                "legend_name": "雨量站",
            },
        ]
    }

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 200
    overrides = renderer.calls[0]["job_config"]["layout"]["legend_style"]["name_overrides"]
    assert overrides[0]["source_key"] == "basin-layer-1"
    assert overrides[1]["legend_name"] == "雨量站"


def test_render_endpoint_rejects_invalid_legend_name_override_source_type(tmp_path):
    """Legend name override source types should be validated before rendering."""
    from app import create_app

    template_project = tmp_path / "gistool_test.aprx"
    template_project.write_text("template", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path),
            "ARCPY_TEMPLATE_PROJECT": str(template_project),
            "RENDERER": FakeRenderer(),
        }
    )
    payload = _valid_render_payload(tmp_path)
    payload["layout"]["legend_style"] = {
        "name_overrides": [
            {
                "source_type": "station_cluster",
                "source_key": "station-layer-1-group-1",
                "default_name": "GreenCircleStations - 1",
                "legend_name": "雨量站",
            }
        ]
    }

    response = app.test_client().post("/api/render", json=payload)

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "Unsupported legend name override source_type" in body["message"]


def test_watershed_acc_threshold_returns_default_area_and_folder(tmp_path):
    """POST /api/watershed/acc_threshold should call the watershed service and expose the default threshold."""
    dem_path = tmp_path / "dem.tif"
    dem_path.write_bytes(b"fake-dem")
    shapefile_path = tmp_path / "basin.geojson"
    shapefile_path.write_text("{}", encoding="utf-8")
    app = _watershed_test_app(tmp_path)

    response = app.test_client().post(
        "/api/watershed/acc_threshold",
        json={"dem_path": str(dem_path), "shapefile_path": str(shapefile_path)},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["area_threshold"] == 35.95
    assert body["random_folder_name"] == "program"
    assert FakeWatershedService.instances[0].kwargs["plan_name"] == "方案1"


def test_watershed_step0_requires_threshold_and_folder(tmp_path):
    """POST /api/watershed/step0_streams should fail fast when inherited state is missing."""
    dem_path = tmp_path / "dem.tif"
    dem_path.write_bytes(b"fake-dem")
    app = _watershed_test_app(tmp_path)

    response = app.test_client().post("/api/watershed/step0_streams", json={"dem_path": str(dem_path)})

    assert response.status_code == 400
    assert response.get_json()["success"] is False
    assert "area_threshold" in response.get_json()["message"]


def test_watershed_step0_returns_preview_feature_collections(tmp_path, monkeypatch):
    """POST /api/watershed/step0_streams should expose parsed preview layers in addition to file paths."""
    dem_path = tmp_path / "dem.tif"
    dem_path.write_bytes(b"fake-dem")
    app = _watershed_test_app(tmp_path)

    def fake_preview(path: str, entity_type: str = "polygon"):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {"path": path, "entity_type": entity_type},
                }
            ],
        }

    monkeypatch.setattr("app.api.watershed._preview_geo_layer_or_empty", fake_preview)

    response = app.test_client().post(
        "/api/watershed/step0_streams",
        json={
            "dem_path": str(dem_path),
            "area_threshold": 35.95,
            "random_folder_name": "program",
            "plan_name": "方案 01",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["buffered_boundary"]["type"] == "FeatureCollection"
    assert body["streams_ori"]["type"] == "FeatureCollection"
    assert body["buffered_boundary"]["features"][0]["properties"]["entity_type"] == "polygon"
    assert body["streams_ori"]["features"][0]["properties"]["entity_type"] == "line"


def test_watershed_step1_accepts_empty_break_points_and_returns_json_outputs(tmp_path):
    """POST /api/watershed/step1 should let the algorithm auto-pick an outlet when break_points is empty."""
    dem_path = tmp_path / "dem.tif"
    dem_path.write_bytes(b"fake-dem")
    app = _watershed_test_app(tmp_path)

    response = app.test_client().post(
        "/api/watershed/step1",
        json={
            "dem_path": str(dem_path),
            "area_threshold": 35.95,
            "random_folder_name": "program",
            "break_points": [],
            "plan_name": "方案 01",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert isinstance(body["outputs"], dict)
    assert body["outputs"]["subWatersheds"]["type"] == "FeatureCollection"
    assert FakeWatershedService.instances[0].kwargs["control_points"] == []
    assert FakeWatershedService.instances[0].kwargs["plan_name"] == "方案 01"


def test_watershed_step1_clears_stale_merge_outputs_for_same_plan(tmp_path):
    """POST /api/watershed/step1 should remove stale merge artifacts so step2 validates against the latest step1 result."""
    dem_path = tmp_path / "dem.tif"
    dem_path.write_bytes(b"fake-dem")
    plan_dir = tmp_path / "program" / "方案 01" / "basic_file"
    plan_dir.mkdir(parents=True)
    stale_merge_files = [
        plan_dir / "sub_catchment_merge.geojson",
        plan_dir / "upstream_cells_merge.geojson",
        plan_dir / "junctions_merge.geojson",
        plan_dir / "river_network_linestrings_merge.geojson",
        plan_dir / "downstream_dict_merge.json",
    ]
    for path in stale_merge_files:
        path.write_text("stale", encoding="utf-8")

    app = _watershed_test_app(tmp_path)

    response = app.test_client().post(
        "/api/watershed/step1",
        json={
            "dem_path": str(dem_path),
            "area_threshold": 35.95,
            "random_folder_name": "program",
            "break_points": [],
            "plan_name": "方案 01",
        },
    )

    assert response.status_code == 200
    for path in stale_merge_files:
        assert not path.exists()


def test_watershed_preview_layer_returns_feature_collection_for_geojson(tmp_path):
    """POST /api/watershed/preview-layer should parse uploaded GeoJSON into a frontend-ready FeatureCollection."""
    app = _watershed_test_app(tmp_path)
    boundary_geojson = tmp_path / "basin.geojson"
    boundary_geojson.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [[[105, 27], [106, 27], [106, 28], [105, 27]]]},
                        "properties": {"name": "basin"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    response = app.test_client().post("/api/watershed/preview-layer", json={"path": str(boundary_geojson)})

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["layer"]["type"] == "FeatureCollection"
    assert body["layer"]["features"][0]["properties"]["name"] == "basin"


def test_watershed_validate_plan_name_reports_existing_directory(tmp_path):
    """POST /api/watershed/validate-plan-name should warn when the plan directory already exists."""
    app = _watershed_test_app(tmp_path)
    existing_dir = tmp_path / "program" / "方案 01"
    existing_dir.mkdir(parents=True)

    response = app.test_client().post("/api/watershed/validate-plan-name", json={"plan_name": "方案 01"})

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["exists"] is True


def test_watershed_validate_plan_name_reports_missing_directory(tmp_path):
    """POST /api/watershed/validate-plan-name should return exists=false when the plan directory is absent."""
    app = _watershed_test_app(tmp_path)

    response = app.test_client().post("/api/watershed/validate-plan-name", json={"plan_name": "新方案"})

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["exists"] is False


def test_watershed_boundary_generate_uses_default_dem_and_clips_to_bbox(tmp_path):
    """POST /api/watershed-boundary/generate should use the default DEM path and clip result to the requested rectangle."""
    app = _watershed_test_app(tmp_path)
    dem_path = Path(app.config["WATERSHED_DEFAULT_DEM_PATH"])
    dem_path.write_text("fake dem", encoding="utf-8")
    app.extensions["watershed_boundary_runner"] = _fake_watershed_boundary_runner

    response = app.test_client().post(
        "/api/watershed-boundary/generate",
        json={
            "point": {"x": 105.2, "y": 27.06},
            "bbox": {
                "min_x": 105.1,
                "min_y": 26.95,
                "max_x": 105.3,
                "max_y": 27.1,
            },
            "snap_threshold": 2400,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["dem_path"] == str(dem_path)
    assert payload["data"]["snap_threshold"] == 2400
    assert payload["data"]["point"] == {"x": 105.2, "y": 27.06}
    assert payload["data"]["bbox"] == {
        "min_x": 105.1,
        "min_y": 26.95,
        "max_x": 105.3,
        "max_y": 27.1,
    }
    assert payload["data"]["result"]["type"] == "FeatureCollection"
    coordinates = payload["data"]["result"]["features"][0]["geometry"]["coordinates"][0]
    assert coordinates[0] == coordinates[-1]
    xs = [coord[0] for coord in coordinates[:-1]]
    ys = [coord[1] for coord in coordinates[:-1]]
    assert min(xs) == 105.1
    assert max(xs) == 105.3
    assert min(ys) == 26.95
    assert max(ys) == 27.1


def test_watershed_boundary_clip_dem_to_bbox_returns_smaller_raster(tmp_path):
    """The bbox clip helper should write a smaller temporary raster for downstream analysis."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    from app.api.watershed_boundary import _clip_dem_to_bbox

    dem_path = tmp_path / "dem.tif"
    data = np.arange(100, dtype="float32").reshape((1, 10, 10))
    transform = from_origin(105.0, 27.2, 0.01, 0.01)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data)

    clipped_path = _clip_dem_to_bbox(
        dem_path=str(dem_path),
        bbox={
            "min_x": 105.02,
            "min_y": 27.12,
            "max_x": 105.08,
            "max_y": 27.18,
        },
        tmpdir=tmp_path,
    )

    assert clipped_path != dem_path
    assert clipped_path.exists()
    with rasterio.open(clipped_path) as src:
        assert src.width < 10
        assert src.height < 10


def test_watershed_step2_rejects_invalid_operation(tmp_path):
    """POST /api/watershed/step2 should only accept merge and delete operations."""
    app = _watershed_test_app(tmp_path)

    response = app.test_client().post(
        "/api/watershed/step2",
        json={"operation": "split", "watershed_ids": ["Watershed1.1"], "random_folder": "program"},
    )

    assert response.status_code == 400
    assert response.get_json()["success"] is False
    assert "operation" in response.get_json()["message"]


def test_watershed_step2_returns_json_outputs(tmp_path):
    """POST /api/watershed/step2 should return merge/delete outputs as JSON objects."""
    app = _watershed_test_app(tmp_path)

    response = app.test_client().post(
        "/api/watershed/step2",
        json={"operation": "merge", "watershed_ids": ["Watershed1.1"], "random_folder": "program", "plan_name": "方案 01"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["operation"] == "merge"
    assert body["result"]["ids"] == ["Watershed1.1"]
    assert isinstance(body["outputs"], dict)
    assert FakeMergeDeleteService.instances[0].kwargs["plan_name"] == "方案 01"


def test_upload_endpoint_saves_geojson_and_returns_path(tmp_path):
    """上传 GeoJSON 后应保存到 UPLOAD_FOLDER，并返回可供 /api/render 使用的绝对路径。"""
    from app import create_app

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().post(
        "/api/uploads",
        data={
            "kind": "basin_boundary",
            "file": (io.BytesIO(b'{"type":"FeatureCollection","features":[]}'), "basin.geojson"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    data = body["data"]
    assert data["kind"] == "basin_boundary"
    assert data["original_name"] == "basin.geojson"
    assert data["suffix"] == ".geojson"
    assert Path(data["path"]).exists()
    assert Path(data["path"]).is_absolute()


def test_upload_endpoint_saves_dem_tif(tmp_path):
    """DEM rasters should upload through the shared upload endpoint and return a server path."""
    from app import create_app

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().post(
        "/api/uploads",
        data={
            "kind": "dem",
            "file": (io.BytesIO(b"fake-tif"), "dem.tif"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    data = body["data"]
    assert data["kind"] == "dem"
    assert data["suffix"] == ".tif"
    assert Path(data["path"]).exists()


def test_watershed_upload_endpoint_saves_dem_tif(tmp_path):
    """Watershed-specific uploads should be available under /api/watershed/uploads."""
    from app import create_app

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().post(
        "/api/watershed/uploads",
        data={
            "kind": "dem",
            "file": (io.BytesIO(b"fake-tif"), "dem.tif"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    data = body["data"]
    assert data["kind"] == "dem"
    assert data["suffix"] == ".tif"
    assert Path(data["path"]).exists()


def test_upload_endpoint_saves_xlsx_and_aprx(tmp_path):
    """站点 Excel 和模板 aprx 都应能通过同一个上传接口保存。"""
    from app import create_app

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "RENDERER": FakeRenderer(),
        }
    )

    client = app.test_client()
    excel_response = client.post(
        "/api/uploads",
        data={
            "kind": "station_excel",
            "file": (io.BytesIO(b"fake-xlsx"), "stations.xlsx"),
        },
        content_type="multipart/form-data",
    )
    aprx_response = client.post(
        "/api/uploads",
        data={
            "kind": "template_project",
            "file": (io.BytesIO(b"fake-aprx"), "template.aprx"),
        },
        content_type="multipart/form-data",
    )

    assert excel_response.status_code == 200
    assert excel_response.get_json()["data"]["suffix"] == ".xlsx"
    assert Path(excel_response.get_json()["data"]["path"]).exists()
    assert aprx_response.status_code == 200
    assert aprx_response.get_json()["data"]["suffix"] == ".aprx"
    assert Path(aprx_response.get_json()["data"]["path"]).exists()


def test_upload_endpoint_rejects_invalid_suffix(tmp_path):
    """不在白名单内的文件类型应被拒绝，避免任意文件写入。"""
    from app import create_app

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().post(
        "/api/uploads",
        data={
            "kind": "basin_boundary",
            "file": (io.BytesIO(b"bad"), "bad.exe"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "Unsupported file suffix" in body["message"]


def test_upload_endpoint_extracts_shapefile_zip(tmp_path):
    """shp 以 zip 上传时，后端应解压并返回主 .shp 路径。"""
    from app import create_app

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        archive.writestr("basin.shp", b"fake-shp")
        archive.writestr("basin.dbf", b"fake-dbf")
        archive.writestr("basin.shx", b"fake-shx")
    zip_buffer.seek(0)

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().post(
        "/api/uploads",
        data={
            "kind": "basin_boundary",
            "file": (zip_buffer, "basin.zip"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["suffix"] == ".shp"
    assert Path(data["path"]).name == "basin.shp"
    assert Path(data["path"]).exists()


def test_upload_endpoint_accepts_shapefile_component_files(tmp_path):
    """用户一次选择 shp/shx/dbf 多个组件文件时，应保存并返回主 .shp 路径。"""
    from app import create_app

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().post(
        "/api/uploads",
        data={
            "kind": "basin_boundary",
            "files": [
                (io.BytesIO(b"fake-shp"), "basin.shp"),
                (io.BytesIO(b"fake-shx"), "basin.shx"),
                (io.BytesIO(b"fake-dbf"), "basin.dbf"),
                (io.BytesIO(b"fake-prj"), "basin.prj"),
            ],
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["suffix"] == ".shp"
    assert data["original_name"] == "basin.shp"
    assert Path(data["path"]).name == "basin.shp"
    assert Path(data["path"]).exists()
    assert (Path(data["path"]).parent / "basin.shx").exists()
    assert (Path(data["path"]).parent / "basin.dbf").exists()


def test_upload_endpoint_rejects_incomplete_shapefile_component_files(tmp_path):
    """少选 shp 必需组件时，应提示用户至少选择 shp/shx/dbf。"""
    from app import create_app

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().post(
        "/api/uploads",
        data={
            "kind": "basin_boundary",
            "files": [
                (io.BytesIO(b"fake-shp"), "basin.shp"),
                (io.BytesIO(b"fake-shx"), "basin.shx"),
            ],
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "Please select at least .shp, .shx and .dbf" in body["message"]


def test_upload_endpoint_rejects_zip_without_shapefile(tmp_path):
    """zip 中没有 .shp 时应返回明确错误。"""
    from app import create_app

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        archive.writestr("readme.txt", "no shapefile")
    zip_buffer.seek(0)

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "RENDERER": FakeRenderer(),
        }
    )

    response = app.test_client().post(
        "/api/uploads",
        data={
            "kind": "basin_boundary",
            "file": (zip_buffer, "basin.zip"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert "No .shp file found" in body["message"]
