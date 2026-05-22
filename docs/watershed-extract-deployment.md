# 流域提取功能部署说明

这份说明只针对 `http://localhost:5173/watershed-extract` 这条“流域提取”功能，不适用于老的“流域出图”流程。

## 1. 功能结构

当前项目把两个能力拆成了两套后端进程，避免 Python 环境互相冲突：

- 流域出图：继续走 ArcGIS Pro / ArcPy 环境
- 流域提取：单独走 `D:\python3.9.5\python.exe`

前端通过 Vite 代理分流：

- `/api/watershed/*` -> `http://127.0.0.1:5001`
- 其余 `/api/*` -> `http://127.0.0.1:5000`

也就是说，流域提取功能依赖的是：

- Vue 前端开发服务：`5173`
- 流域提取 Flask 服务：`5001`

## 2. 必要环境

建议至少准备下面这些环境：

### 前端

- Node.js 18+
- npm 9+

### 流域提取后端

- Python 3.9.5
- 推荐直接使用：
  - `D:\python3.9.5\python.exe`

安装后端依赖时，使用项目根目录的 `requirements.txt`：

```powershell
cd D:\work\2026\code\life\gis_flask_study
D:\python3.9.5\python.exe -m pip install -r requirements.txt
```

如果还缺流域提取相关包，重点检查这些是否已安装成功：

- `flask`
- `numpy`
- `geopandas`
- `rasterio`
- `pysheds`
- `shapely`
- `fiona`

## 3. 关键目录配置

当前流域提取功能默认使用这些路径：

- 默认 DEM：
  - `D:\work\2026\code\data\data\dem\dem.tif`
- 结果目录根路径：
  - `D:\work\2026\code\life\gis_flask_study\docs\program`

其中：

- `docs\program\output_ori` 用于算法输出中间结果
- `docs\program\<方案名称>` 用于第 4 步合并 / 删除后的方案结果

如果你要换机器部署，至少要确认：

1. 默认 DEM 路径存在
2. `docs\program` 可写
3. 上传目录 `uploads\` 可写

## 4. 启动流域提取后端

在项目根目录执行：

```powershell
cd D:\work\2026\code\life\gis_flask_study
$env:FLASK_PORT="5001"
D:\python3.9.5\python.exe backend\run.py
```

启动后可用健康检查确认：

```powershell
Invoke-RestMethod http://127.0.0.1:5001/api/health
```

返回里应能看到类似字段：

- `status: ok`
- `watershed_default_dem_path`
- `watershed_program_root`

## 5. 启动前端

另开一个终端：

```powershell
cd D:\work\2026\code\life\gis_flask_study\frontend
npm install
npm run dev
```

浏览器访问：

```text
http://127.0.0.1:5173/watershed-extract
```

## 6. 流域提取接口

前端页面会用到这些接口：

- `POST /api/watershed/acc_threshold`
- `POST /api/watershed/step0_streams`
- `POST /api/watershed/step1`
- `POST /api/watershed/step2`
- `POST /api/watershed/preview-layer`
- `POST /api/watershed/validate-plan-name`
- `POST /api/watershed/uploads`

## 7. 上传与输入规则

### DEM

- 可不上传
- 不上传时，直接使用默认 DEM：
  - `D:\work\2026\code\data\data\dem\dem.tif`
- 上传时支持：
  - `.tif`
  - `.tiff`

### 流域边界

支持：

- `.geojson`
- `.json`
- `.kml`
- `.zip`
- shapefile 组件上传：
  - `.shp`
  - `.shx`
  - `.dbf`
  - `.prj`

### 方案名称

- 需要手动填写
- 前端会在失焦时检查 `docs\program\<方案名称>` 是否已存在
- 如果已存在，会提示：
  - `检测到同名方案，继续可能复用旧结果，建议更换名称`

## 8. 已实现的页面行为

当前页面已经支持：

- 第一步上传边界并计算默认阈值
- 第二步显示默认阈值，并允许改成自定义阈值
- 第三步手动输入或地图点击添加 `break_points`
- 第四步多次执行合并 / 删除
- OpenLayers 地图预览
- 子流域 / 河段 / 节点 / 控制点图层树联动

其中有两个重要约定：

1. `break_points` 在第 3 步生成后，后续步骤默认沿用，不会在第 4 步重新变化
2. 第 4 步每次成功后，前端会清空已选流域，避免把旧 ID 带入下一次操作

## 9. 常见问题

### 1）`No module named 'pysheds'`

说明你可能不是用 `D:\python3.9.5\python.exe` 启动的流域提取后端，或者这个环境里没装依赖。

### 2）页面能打开，但请求失败

先检查：

```powershell
Invoke-RestMethod http://127.0.0.1:5001/api/health
```

如果 5001 不通，前端的流域提取功能就不可用。

### 3）方案名称重复导致结果串用

如果使用同名方案，后端可能会复用这个方案目录下的旧结果。建议每次新的实验都换一个方案名称。

### 4）第 4 步合并 / 删除后控制点没显示

当前前端已做回退处理：如果 `step2` 不返回 `break_points`，会继续沿用 `step1` 的控制点。

## 10. 推荐部署顺序

建议按这个顺序检查：

1. 确认 `D:\python3.9.5\python.exe` 可用
2. 安装根目录 `requirements.txt`
3. 确认默认 DEM 路径存在
4. 启动 `5001` 流域提取后端
5. 健康检查 `api/health`
6. 启动前端 `5173`
7. 打开 `/watershed-extract` 做一次完整流程验证

