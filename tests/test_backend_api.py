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

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


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
        "output_dir": str(tmp_path / "outputs" / "first-map"),
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


def test_render_options_include_current_station_styles(tmp_path):
    """选项接口应把站点形状和颜色预设分开暴露。"""
    from app import create_app

    app = create_app({"TESTING": True, "OUTPUT_FOLDER": str(tmp_path), "RENDERER": FakeRenderer()})

    response = app.test_client().get("/api/render-options")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert "Topographic" in data["basemaps"]
    assert data["station_symbol_shapes"] == ["circle", "triangle", "square", "diamond"]
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
    assert renderer.calls[0]["output_dir"] == Path(payload["output_dir"])
    assert renderer.calls[0]["template_project"] == template_project
    assert renderer.calls[0]["job_config"]["inputs"]["station_layers"][0]["symbol"]["preset"] == "circle_green"
    assert renderer.calls[0]["job_config"]["inputs"]["station_layers"][1]["symbol"]["preset"] == "triangle_red"


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
