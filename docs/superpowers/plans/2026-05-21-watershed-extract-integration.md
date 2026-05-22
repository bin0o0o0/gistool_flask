# 流域提取功能接入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将真实流域处理核心算法接入 `gis_flask_study`，并在 `/watershed-extract` 提供完整四步流域提取页面。

**Architecture:** 后端把原独立 Flask 算法项目复制为 `backend/app/gis/watershed_core` 内置模块，由新增 `backend/app/api/watershed.py` 适配当前 Flask 工厂、配置和统一响应。前端新增 Vue 页面和 API client，复用现有上传接口，页面内保存并传递 `random_folder_name`、`shapefile_path`、`dem_path`、`area_threshold`、`break_points`。

**Tech Stack:** Flask 3、pytest、Vue 3、Pinia/Composition API、Axios、Vitest、Vite。

---

### Task 1: 后端配置、上传类型和算法文件落位

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/api/uploads.py`
- Modify: `frontend/src/types.ts`
- Create: `backend/app/gis/watershed_core/*`
- Test: `tests/test_backend_api.py`
- Test: `frontend/src/tests/uploadsApi.test.ts`

- [ ] **Step 1: 写失败测试**

在 `tests/test_backend_api.py` 增加测试：`AppConfig` 默认 `watershed_program_root` 指向项目 `docs/program`，上传接口接受 `kind=dem` 的 `.tif`。

在 `frontend/src/tests/uploadsApi.test.ts` 增加测试：`uploadsApi.upload(file('dem.tif'), 'dem')` 使用 `kind=dem`。

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
pytest tests/test_backend_api.py -q
cd frontend; npm run test -- uploadsApi.test.ts
```

Expected: Python 测试因配置字段或 DEM kind 缺失失败；前端类型或断言因 `dem` 未支持失败。

- [ ] **Step 3: 最小实现**

给 `AppConfig` 增加：

```python
watershed_program_root: Path
watershed_default_dem_path: Path
```

默认值：

```text
docs/program
D:\work\2026\code\data\data\dem\dem.tif
```

给上传 API 增加 `dem`，允许 `.tif/.tiff`。

复制核心算法文件到 `backend/app/gis/watershed_core/`，并加入必要 `__init__.py`。

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
pytest tests/test_backend_api.py -q
cd frontend; npm run test -- uploadsApi.test.ts
```

Expected: 新增测试通过。

### Task 2: 后端流域 API 适配层

**Files:**
- Create: `backend/app/api/watershed.py`
- Modify: `backend/app/__init__.py`
- Test: `tests/test_backend_api.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_backend_api.py` 增加一个 Fake service factory，验证：

- `POST /api/acc_threshold` 返回 `area_threshold` 和 `random_folder_name`
- `POST /api/step0_streams` 校验 `area_threshold` 和 `random_folder_name`
- `POST /api/step1` 接受空 `break_points`
- `POST /api/step2` 校验 `operation` 只能是 `merge/delete`
- `outputs` 是 JSON 对象，不是字符串
- payload 不要求 `basin_name`

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
pytest tests/test_backend_api.py -q
```

Expected: 新接口不存在或配置注入不存在导致失败。

- [ ] **Step 3: 最小实现**

新增 `watershed.py`：

- 从 `current_app.extensions["watershed_services"]` 读取测试注入服务。
- 无注入时动态导入 `backend/app/gis/watershed_core/HFLY.py` 和 `merge_delete.py` 中的真实类。
- 在调用真实算法前设置 `FORECAST_SAVE_PATH` 为 `docs`，使原算法的 `program` 落到 `docs/program`。
- 使用 `success_response/error_response` 返回当前项目格式。
- 把 `step1/step2` 的 `outputs` 保持为 dict。

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
pytest tests/test_backend_api.py -q
```

Expected: 新增后端接口测试通过。

### Task 3: 前端 API client、类型和路由

**Files:**
- Create: `frontend/src/api/watershed.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/router/routes.ts`
- Test: `frontend/src/tests/router.test.ts`
- Test: `frontend/src/tests/watershedApi.test.ts`

- [ ] **Step 1: 写失败测试**

新增 `watershedApi.test.ts`，mock Axios client，验证四个方法调用：

- `/api/acc_threshold`
- `/api/step0_streams`
- `/api/step1`
- `/api/step2`

修改路由测试，断言 `/watershed-extract` 指向 `WatershedExtractView`，不是 `ComingSoonView`。

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd frontend; npm run test -- watershedApi.test.ts router.test.ts
```

Expected: `watershed.ts` 不存在或路由仍是占位页导致失败。

- [ ] **Step 3: 最小实现**

新增 API client：

```ts
export const watershedApi = {
  calculateThreshold(payload) {
    return api.post('/api/acc_threshold', payload)
  },
  initializeStreams(payload) {
    return api.post('/api/step0_streams', payload)
  },
  generateWatersheds(payload) {
    return api.post('/api/step1', payload)
  },
  mergeOrDelete(payload) {
    return api.post('/api/step2', payload)
  }
}
```

新增流域相关类型，并把路由组件改为 `WatershedExtractView`。

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
cd frontend; npm run test -- watershedApi.test.ts router.test.ts
```

Expected: 新增前端 API 和路由测试通过。

### Task 4: 前端流域提取页面

**Files:**
- Create: `frontend/src/views/WatershedExtractView.vue`
- Modify: `frontend/src/router/routes.ts`
- Test: `frontend/src/tests/router.test.ts`

- [ ] **Step 1: 写失败测试**

用已有路由测试覆盖页面挂载目标；页面内部复杂交互通过 build 和手动浏览器验证。

- [ ] **Step 2: 运行测试确认失败或保持红灯来源明确**

Run:

```powershell
cd frontend; npm run test -- router.test.ts
```

Expected: 若页面未创建，导入失败。

- [ ] **Step 3: 实现页面**

页面必须包含：

- 默认 DEM 路径。
- DEM 上传按钮。
- 边界上传按钮，支持单文件和 shapefile 多组件。
- 四步按钮和状态。
- 第一步保存 `random_folder_name`、`shapefile_path`、`dem_path`、`area_threshold`。
- 第二步复用这些值。
- 第三步支持 break point 表格和地图点击添加。
- 空 `break_points` 可提交。
- 第四步支持 `merge/delete`、选择子流域 ID。
- `basin_name` 只用于页面显示，不进入 payload。

- [ ] **Step 4: 运行前端测试和构建**

Run:

```powershell
cd frontend; npm run test; npm run build
```

Expected: Vitest 和 TypeScript/Vite build 通过。

### Task 5: 全量验证和浏览器检查

**Files:**
- No planned source edits unless verification finds issues.

- [ ] **Step 1: 后端测试**

Run:

```powershell
pytest -q
```

Expected: 后端测试通过。

- [ ] **Step 2: 前端测试和构建**

Run:

```powershell
cd frontend; npm run test; npm run build
```

Expected: 前端测试和构建通过。

- [ ] **Step 3: 启动本地前端**

Run:

```powershell
cd frontend; npm run dev
```

Expected: Vite 在 `http://localhost:5173` 可访问。

- [ ] **Step 4: 浏览器打开页面**

Open:

```text
http://localhost:5173/watershed-extract
```

Expected: 页面非空，布局清晰，按钮文本不溢出，四步表单可见。

- [ ] **Step 5: 最终状态检查**

Run:

```powershell
git status --short
```

Expected: 只包含本任务相关改动和用户原有 `HomeView.vue` 改动。
