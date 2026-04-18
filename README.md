# GIS Flask Study Backend

这是一个简化后的 ArcGIS Pro 出图后端。现在项目只保留标准 Flask backend 结构，不再使用 CLI、不再使用 SQLite、不再创建异步 job；Apifox 可以直接请求接口，让后端把地图输出到你指定的 `output_dir`。

## 项目结构

```text
backend/
  run.py
  app/
    __init__.py
    api/
      health.py
      options.py
      render.py
    core/
      config.py
      constants.py
    gis/
      render/
        arcpy_renderer.py
    utils/
      responses.py
tests/
  test_backend_api.py
  test_arcpy_renderer.py
```

## 启动方式

因为方案 A 是“后端进程内直接使用 ArcPy”，所以必须用 ArcGIS Pro 自带 Python 启动：

```powershell
& "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\propy.bat" backend\run.py
```

## 通用环境部署

这个后端有一个特殊点：Flask 服务和 ArcPy 必须在同一个 Python 进程里运行。因为 ArcPy 只能由 ArcGIS Pro Python 提供，所以新电脑部署时，关键不是“普通 Python 有没有 Flask”，而是：

```text
ArcGIS Pro Python 能不能 import flask
```

可以先用这条命令检查：

```powershell
& "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\propy.bat" -c "import flask; print(flask.__version__)"
```

如果能打印 Flask 版本，就可以直接启动后端。如果报 `ModuleNotFoundError: No module named 'flask'`，需要给 ArcGIS Pro Python 配 Flask。

### 推荐方式：ArcGIS Pro Python 直接安装 Flask

如果新电脑能正常联网，可以直接安装：

```powershell
& "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\propy.bat" -m pip install Flask
```

安装后再次检查：

```powershell
& "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\propy.bat" -c "import flask; print(flask.__version__)"
```

### 更稳方式：使用 ArcGIS Pro 克隆环境

如果不想改 ArcGIS Pro 默认环境，推荐在 ArcGIS Pro 里克隆一个 Python 环境，然后在克隆环境里安装 Flask，再用克隆环境的 Python 启动后端。这样不会污染默认 `arcgispro-py3`。

### 兼容方式：用户 site-packages

有些电脑上，Flask 可能被安装到了当前用户目录，例如：

```text
C:\Users\<用户名>\AppData\Roaming\Python\Python39\site-packages
```

`backend/app/__init__.py` 里的 `_ensure_user_site_packages()` 会自动调用 `site.getusersitepackages()`，把当前用户的 site-packages 加入 `sys.path`。这个函数没有写死用户名或固定电脑路径，所以换电脑也会自动计算对应用户目录。

注意：这个函数只是“让 Python 多找一个目录”，不会自动安装 Flask。新电脑仍然要先确保 Flask 已安装在 ArcGIS Pro Python 能访问的位置。

`flask-cors` 目前不是必需依赖；如果后续接浏览器前端再安装也可以。Apifox 调试不需要它。

默认模板工程路径是：

```text
D:\work\2026\arcgis_file\gistool_test\gistool_test.aprx
```

如果以后要换模板，可以设置环境变量：

```powershell
$env:ARCPY_TEMPLATE_PROJECT="D:\your\template.aprx"
$env:OUTPUT_FOLDER="D:\your\output"
& "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\propy.bat" backend\run.py
```

## 接口

### GET /api/health

检查服务是否启动，并返回当前输出目录和模板工程路径。

### GET /api/render-options

返回前端或 Apifox 可用的固定选项，包括底图、标注位置、站点形状和站点颜色预设。

站点形状和颜色已经拆开，前端可以自由组合：

```text
station_symbol_shapes:
circle
triangle
square
diamond

station_symbol_color_presets:
blue
cyan
purple
orange
green
red
black
```

旧版 `preset` 字段仍然兼容，例如 `circle_green`、`triangle_red`，但新请求建议使用
`shape + color_preset` 或 `shape + color`。

### POST /api/render

直接出图。请求体里传真实文件路径和输出目录，不再传 `file_id`。

Apifox 示例：

```json
{
  "output_dir": "D:/work/2026/code/life/gis_flask_study/output/demo_001",
  "map_title": "示例流域水系图",
  "output": {
    "width_px": 1600,
    "height_px": 1200,
    "dpi": 150
  },
  "inputs": {
    "basin_boundary": {
      "path": "D:/data/basin.geojson"
    },
    "river_network": {
      "path": "D:/data/rivers.geojson"
    },
    "station_layers": [
      {
        "path": "D:/data/green_stations.xlsx",
        "sheet_name": "Sheet1",
        "x_field": "lon",
        "y_field": "lat",
        "name_field": "name",
        "layer_name": "GreenCircleStations",
        "symbol": {
          "shape": "circle",
          "color_preset": "green",
          "size_pt": 20
        },
        "label": {
          "enabled": true,
          "color": "#000000",
          "font_size_pt": 20,
          "position": "top_right",
          "rotation_deg": 0
        }
      },
      {
        "path": "D:/data/red_stations.xlsx",
        "sheet_name": "Sheet1",
        "x_field": "lon",
        "y_field": "lat",
        "name_field": "name",
        "layer_name": "RedTriangleStations",
        "symbol": {
          "shape": "triangle",
          "color_preset": "red",
          "size_pt": 20
        },
        "label": {
          "enabled": true,
          "color": "#000000",
          "font_size_pt": 20,
          "position": "top_right",
          "rotation_deg": 0
        }
      }
    ]
  },
  "layout": {
    "basemap": "Topographic",
    "legend": {
      "enabled": true
    },
    "scale_bar": {
      "enabled": true
    }
  },
  "style": {
    "basin_boundary": {
      "color": "#222222",
      "width_pt": 1.2
    },
    "basin_fill": {
      "color": "#e6f0d4",
      "opacity": 0.45
    },
    "river_network": {
      "color": "#2f80ed",
      "width_pt": 2.5
    }
  }
}
```

成功后会在 `output_dir` 生成：

```text
map.png
result.json
gistool_test.aprx
```

## 模板工程要求

当前 ArcPy 渲染器会在 `.aprx` 里查找这些对象：

```text
Map: 地图
Layout: 布局
Map Frame: 地图框
Title text element: 标题
```

标题、图例、比例尺这些布局元素暂时不是强制项。如果模板里没有，出图仍会继续，缺失信息会写入 `result.json.warnings`。

## 测试

普通单元测试不需要 ArcGIS Pro：

```powershell
python -m pytest tests -q
```

真实 ArcPy 出图需要用 `propy.bat` 启动后端，然后用 Apifox 请求 `POST /api/render`。

## tests 目录说明

`tests/` 主要用来保护两类核心行为：

- `test_backend_api.py`：测试 Flask API 层，使用 `FakeRenderer` 替代真实 `ArcPyRenderer`，确认接口能正确校验参数、传递参数并返回统一 JSON。
- `test_arcpy_renderer.py`：测试 `ArcPyRenderer` 本身，但使用 fake `arcpy` 和一组假的 ArcGIS Pro 对象，确认渲染器对 ArcPy 的调用方式、参数、样式、标注和输出结果是否正确。

这些测试能防止应用代码被改坏，但不能替代真实 ArcGIS Pro 环境验证。真正确认 ArcPy、模板工程和用户数据能跑通，仍然需要在 ArcGIS Pro Python 环境中用真实数据单独跑一次。
