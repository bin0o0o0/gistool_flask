# Watershed Extract Integration Design

Date: 2026-05-20

## Goal

Implement the real watershed extraction workflow at `/watershed-extract` in `gis_flask_study` by integrating the existing, Apifox-tested backend project from:

```text
D:\work\2026\code\work\code\流域处理核心算法整理20260507
```

The feature should fit the current Flask + Vue framework, reuse the existing upload system where possible, and turn the provided HTML prototype into a polished Vue page with a map-oriented, creative GIS interface.

## Source Algorithm

The core algorithm files will be copied into this repository instead of referenced by absolute path. The integration target is:

```text
backend/app/gis/watershed_core/
```

Files to bring in:

- `HFLY.py`
- `merge_delete.py`
- `junction_clibrate.py`
- `app/utils/parse_geojson_to_frontend.py`

The existing standalone Flask file `SQYB_flask.py` will be used as the behavior reference, not copied as an app entrypoint. Its four routes will be adapted into the existing application factory structure.

## Backend API

Add a new module:

```text
backend/app/api/watershed.py
```

Register it from `backend/app/__init__.py` with the same public endpoints used by the tested backend:

- `POST /api/acc_threshold`
- `POST /api/step0_streams`
- `POST /api/step1`
- `POST /api/step2`

The new API layer will:

- Use the current project response helpers where practical.
- Validate required JSON bodies before calling the algorithm.
- Convert `outputs` from Python dictionaries into real JSON objects, not stringified dictionaries.
- Preserve the algorithm's existing field names that the frontend depends on.
- Avoid writing `basin_name` into calculation payloads because it is only the plan display name in the page.

### Endpoint Contracts

`POST /api/acc_threshold`

Input:

```json
{
  "dem_path": "D:\\work\\2026\\code\\data\\data\\dem\\dem.tif",
  "shapefile_path": "optional uploaded boundary path",
  "cell_size_x": 30,
  "cell_size_y": 30
}
```

Output:

```json
{
  "success": true,
  "message": "阈值计算完成",
  "area_threshold": 35.95,
  "random_folder_name": "program"
}
```

`POST /api/step0_streams`

Input:

```json
{
  "dem_path": "...",
  "area_threshold": 35.95,
  "shapefile_path": "...",
  "random_folder_name": "program"
}
```

Output includes the initial boundary and stream GeoJSON paths:

```json
{
  "success": true,
  "message": "流域边界和河道生成完成",
  "buffered_boundary_geojson": "...",
  "streams_ori_geojson": "..."
}
```

`POST /api/step1`

Input:

```json
{
  "dem_path": "...",
  "area_threshold": 35.95,
  "shapefile_path": "...",
  "break_points": [[105.1, 27.0, 1]],
  "random_folder_name": "program"
}
```

`break_points` may be omitted or empty. In that case, the algorithm should keep its existing automatic outlet behavior.

Output:

```json
{
  "success": true,
  "outputs": {
    "prePath": "program",
    "subWatersheds": { "type": "FeatureCollection", "features": [] },
    "reaches": { "type": "FeatureCollection", "features": [] },
    "junctions": { "type": "FeatureCollection", "features": [] },
    "breakPoints": { "type": "FeatureCollection", "features": [] }
  }
}
```

`POST /api/step2`

Input:

```json
{
  "operation": "merge",
  "watershed_ids": ["Watershed1.1", "Watershed1.2"],
  "random_folder": "program",
  "break_points": [[105.1, 27.0, 1]]
}
```

Output:

```json
{
  "success": true,
  "operation": "merge",
  "result": {
    "status": "watersheds merged",
    "operation": "merge",
    "ids": ["Watershed1.1", "Watershed1.2"]
  },
  "outputs": {
    "prePath": "...",
    "subWatersheds": { "type": "FeatureCollection", "features": [] },
    "reaches": { "type": "FeatureCollection", "features": [] },
    "junctions": { "type": "FeatureCollection", "features": [] }
  }
}
```

## Paths And Runtime Data

The copied algorithm currently assumes `FORECAST_SAVE_PATH` and a `program` work folder. In this project, the default watershed work root will be:

```text
D:\work\2026\code\life\gis_flask_study\docs\program
```

This will be exposed through backend configuration so tests can override it.

Frontend state stores `random_folder_name` as returned by the backend, while the backend resolves it against the configured watershed work root. This keeps browser payloads stable and avoids leaking implementation details into multiple UI steps.

Default DEM path:

```text
D:\work\2026\code\data\data\dem\dem.tif
```

If the user uploads a DEM, the browser uploads the `.tif` or `.tiff` file through `/api/uploads`, then uses the returned server-local path as `dem_path`.

## Uploads

Extend the existing upload API to support a new upload kind:

```text
dem
```

Allowed DEM suffixes:

- `.tif`
- `.tiff`

Boundary upload remains under `basin_boundary` and must support:

- `.geojson`
- `.json`
- `.kml`
- `.zip`
- shapefile component multi-upload: `.shp`, `.shx`, `.dbf`, `.prj`, plus optional companion files already accepted by the existing upload endpoint.

For shapefile component uploads, `.shp`, `.shx`, and `.dbf` remain required. `.prj` is supported and encouraged.

## Frontend Page

Create:

```text
frontend/src/views/WatershedExtractView.vue
frontend/src/api/watershed.ts
```

Update:

```text
frontend/src/router/routes.ts
frontend/src/types.ts
frontend/src/api/uploads.ts
```

The page replaces the current ComingSoon page at `/watershed-extract`.

### Layout

Use the provided HTML prototype as a visual and workflow reference, but implement it as Vue, not as copied inline JavaScript.

Primary structure:

- Top navigation from the existing site shell.
- A full-page GIS workspace with a left step rail.
- A map-like center stage for boundary, river, sub-watershed, and break-point previews.
- A right-side panel for the active step.
- Result summaries and request-state chips near the panel.

The visual direction should be more map-like and creative than the current placeholder: layered terrain or hydrology imagery, refined buttons, clearer state chips, and richer but still usable GIS-tool styling.

### Workflow State

The page keeps these values after their first successful input or response, and reuses them in later steps:

- `random_folder_name`
- `shapefile_path`
- `dem_path`
- `area_threshold`
- `break_points`

`basin_name` is relabeled as "方案名称" and remains page-only display state. It is not sent to the watershed API payload.

### Step 1: Accumulation Threshold

Fields:

- DEM path, defaulting to the configured default DEM.
- Optional DEM upload.
- Boundary upload, required for the intended workflow.
- Plan name, page-only.

Submit calls `/api/acc_threshold`.

On success:

- Save `random_folder_name`.
- Save `area_threshold`.
- Save `dem_path`.
- Save `shapefile_path`.
- Show `area_threshold` as the default value for Step 2.

### Step 2: Initial Streams

Uses saved `dem_path`, `shapefile_path`, `random_folder_name`, and `area_threshold`.

Submit calls `/api/step0_streams`.

On success:

- Display returned initial boundary and stream outputs.
- Load any returned/available GeoJSON into the map preview when possible.

### Step 3: Generate Watersheds

Uses saved state.

Break points can be added by:

- Manual table entry: longitude, latitude, id.
- Clicking the map stage to add a point.

If no break points are provided, the request is still allowed and the backend uses its automatic outlet behavior.

Submit calls `/api/step1`.

On success:

- Save `break_points` if user entered them.
- Display `outputs.subWatersheds`, `outputs.reaches`, `outputs.junctions`, and `outputs.breakPoints`.
- Use sub-watershed properties to populate selectable watershed ids for Step 4.

### Step 4: Merge Or Delete

Uses the current `random_folder_name`, optional `break_points`, selected watershed ids, and operation mode.

Submit calls `/api/step2`.

On success:

- Replace the map preview with the updated `outputs`.
- Keep the current operation result visible.

## Testing

Backend tests:

- `/api/acc_threshold` validates required DEM path and returns numeric `area_threshold`.
- `/api/step0_streams` rejects missing `random_folder_name` or `area_threshold`.
- `/api/step1` accepts omitted/empty `break_points`.
- `/api/step2` validates `operation` and `watershed_ids`.
- API responses contain JSON objects for `outputs`, not stringified dictionaries.
- Upload API accepts `.tif/.tiff` for `dem`.

Because the real GIS algorithm can be slow and dependency-heavy, tests should use injectable fake watershed services for API-layer behavior where possible. Real algorithm execution remains a manual/integration verification step.

Frontend tests:

- Router points `/watershed-extract` to `WatershedExtractView`.
- Watershed API client sends the expected endpoints and payloads.
- Upload API supports `dem`.
- Payload builders do not include `basin_name`.

Build verification:

- `npm run test`
- `npm run build`
- Backend pytest for API/upload tests

Manual verification:

- Start Flask and Vite.
- Open `http://localhost:5173/watershed-extract`.
- Run the four-step flow with the default DEM and a boundary upload.
- Confirm inherited state is reused without repeated input.

## Open Decisions

The current implementation will not add cross-refresh persistence. State inheritance is page-session state inside the Vue view. If the user refreshes the browser, they should run or re-enter the workflow.

The `docs/program` directory stores generated algorithm outputs for local development. It should be treated as runtime output, not source code.
