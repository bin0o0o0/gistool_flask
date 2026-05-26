# home 分支部署说明

这份说明用于另一台电脑从远程 `home` 分支拉取并运行当前项目，重点确认两部分功能已经包含在代码里：

- `生成流域边界`
- 改版后的 `流域出图` 三栏工作台

## 1. 先确认拿到的是最新 home

在项目根目录执行：

```powershell
git fetch origin
git checkout home
git pull origin home
git rev-parse HEAD
```

当前应看到的提交是：

```text
2e34fda0476d85d80b34fb06ab0f6c56133c7f7f
```

如果不是这个提交，说明本地还没有拉到最新远程 `home`。

## 2. 代码里应该能看到的关键文件

拉到最新 `home` 后，下面这些文件应该存在：

### 生成流域边界

- `frontend/src/views/WatershedBoundaryGeneratorView.vue`
- `frontend/src/components/WatershedBoundaryPreviewMap.vue`
- `frontend/src/api/watershedBoundary.ts`
- `backend/app/api/watershed_boundary.py`
- `backend/app/gis/vendor/point_to_basin_shp.py`

### 流域出图改版

- `frontend/src/views/WorkspaceView.vue`
- `frontend/src/components/WorkspacePreviewMap.vue`
- `frontend/src/components/MapOutputControlPanel.vue`
- `frontend/src/components/WorkspaceSidebar.vue`

### 导航与路由

- `frontend/src/components/SiteNav.vue`
- `frontend/src/router/routes.ts`

## 3. 前端启动

```powershell
cd D:\work\2026\code\gistool\frontend
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

重点检查两个页面：

- `http://127.0.0.1:5173/watershed-boundary-generator`
- `http://127.0.0.1:5173/map-output`

如果页面还是旧样式，先清掉旧依赖和构建缓存后再重装：

```powershell
cd D:\work\2026\code\gistool\frontend
Remove-Item -Recurse -Force node_modules, dist
npm install
npm run dev
```

## 4. 后端启动

当前仓库还没有现成的 Docker/Compose 编排文件，所以现在仍按项目现有方式启动后端。

先准备依赖：

```powershell
cd D:\work\2026\code\gistool
.\scripts\setup.ps1
```

然后用 ArcGIS Pro Python 启动：

```powershell
cd D:\work\2026\code\gistool
& "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\propy.bat" backend\run.py
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

## 5. 生成流域边界功能的关键说明

这次补齐到远程 `home` 的关键点是：

- `backend/app/api/watershed_boundary.py` 现在会优先加载仓库内置的
  `backend/app/gis/vendor/point_to_basin_shp.py`
- 如果仓库内置文件不存在，才回退到仓库外部的 `../point_to_basin_shp/point_to_basin_shp.py`

这意味着：

- 另一台电脑只要直接拉当前仓库，就已经具备默认运行所需的边界提取脚本
- 不再强依赖你手工在仓库外再放一份 `point_to_basin_shp` 项目

## 6. 如果另一台电脑看不到改动，优先检查这几件事

1. `git rev-parse HEAD` 是否等于上面的提交号
2. 前端是否重新执行过 `npm install`
3. 是否仍在使用旧的 `node_modules` 或旧浏览器缓存
4. 后端是否重启到了最新代码
5. `backend/app/gis/vendor/point_to_basin_shp.py` 是否真实存在

## 7. 本次远程补齐内容

本次补到 `home` 的内容包含：

- 流域边界后端 vendor 加载逻辑
- 仓库内置 `point_to_basin_shp.py`
- 后端回归测试
- 本部署说明
