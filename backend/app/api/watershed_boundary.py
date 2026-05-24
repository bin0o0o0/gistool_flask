"""Watershed boundary generation API backed by the point_to_basin_shp project."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, request

from app.utils.responses import error_response, success_response


watershed_boundary_bp = Blueprint("watershed_boundary", __name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXTERNAL_PROJECT = PROJECT_ROOT.parent / "point_to_basin_shp"
DEFAULT_SNAP_THRESHOLD = 2000
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)


class WatershedBoundaryValidationError(ValueError):
    """Raised when the request payload is invalid."""


@watershed_boundary_bp.post("/generate")
def generate_watershed_boundary():
    """Generate watershed boundary GeoJSON and clip it to the requested bbox."""
    try:
        payload = _json_payload()
        dem_path = _dem_path(payload)
        point = _parse_point(payload.get("point"))
        bbox = _parse_bbox(payload.get("bbox"))
        snap_threshold = _parse_snap_threshold(payload.get("snap_threshold", DEFAULT_SNAP_THRESHOLD))
        result = _watershed_boundary_runner()(
            dem_path=dem_path,
            points=[point],
            bbox=bbox,
            snap_threshold=snap_threshold,
        )
        clipped = _clip_feature_collection(result, bbox)
    except WatershedBoundaryValidationError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        return error_response(str(exc), 500)

    return success_response(
        {
            "dem_path": dem_path,
            "point": point,
            "bbox": bbox,
            "snap_threshold": snap_threshold,
            "result": clipped,
        }
    )


def _json_payload() -> dict[str, Any]:
    if not request.is_json:
        raise WatershedBoundaryValidationError("Expected JSON request body.")
    payload = request.get_json() or {}
    if not isinstance(payload, dict):
        raise WatershedBoundaryValidationError("Expected JSON object request body.")
    return payload


def _dem_path(payload: dict[str, Any]) -> str:
    config = current_app.extensions["app_config"]
    dem_path = str(payload.get("dem_path") or config.watershed_default_dem_path)
    path = Path(dem_path)
    if not path.exists():
        raise WatershedBoundaryValidationError(f"DEM file does not exist: {dem_path}")
    return str(path)


def _parse_point(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise WatershedBoundaryValidationError("point must be an object with x and y.")
    try:
        x = float(value["x"])
        y = float(value["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise WatershedBoundaryValidationError("point.x and point.y must be valid numbers.") from exc
    return {"x": x, "y": y}


def _parse_bbox(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise WatershedBoundaryValidationError("bbox must be an object.")
    try:
        min_x = float(value["min_x"])
        min_y = float(value["min_y"])
        max_x = float(value["max_x"])
        max_y = float(value["max_y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise WatershedBoundaryValidationError("bbox must contain numeric min_x, min_y, max_x, max_y.") from exc
    if min_x >= max_x or min_y >= max_y:
        raise WatershedBoundaryValidationError("bbox min values must be smaller than max values.")
    return {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y}


def _parse_snap_threshold(value: Any) -> int:
    try:
        snap_threshold = int(value)
    except (TypeError, ValueError) as exc:
        raise WatershedBoundaryValidationError("snap_threshold must be an integer.") from exc
    if snap_threshold <= 0:
        raise WatershedBoundaryValidationError("snap_threshold must be greater than 0.")
    return snap_threshold


def _watershed_boundary_runner():
    runner = current_app.extensions.get("watershed_boundary_runner")
    if runner is not None:
        return runner
    return _run_external_watershed_boundary


def _run_external_watershed_boundary(
    *,
    dem_path: str,
    points: list[dict[str, float]],
    bbox: dict[str, float],
    snap_threshold: int,
) -> dict[str, Any]:
    module = _load_external_boundary_module()
    with tempfile.TemporaryDirectory(prefix="watershed_boundary_") as tmpdir:
        point_path = Path(tmpdir) / "points.geojson"
        output_path = Path(tmpdir) / "watershed.geojson"
        clipped_dem_path = _clip_dem_to_bbox(dem_path=dem_path, bbox=bbox, tmpdir=Path(tmpdir))
        module.points_to_geojson(points, output_path=str(point_path))
        module.process_watershed_analysis(
            point_geojson=str(point_path),
            dem_filename=str(clipped_dem_path),
            dirmap=DIRMAP,
            snap_threshold=snap_threshold,
            output_filename=str(output_path),
        )
        with output_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


def _clip_dem_to_bbox(*, dem_path: str, bbox: dict[str, float], tmpdir: Path) -> Path:
    try:
        import rasterio
        from rasterio.mask import mask
        from rasterio.warp import transform_geom
    except Exception as exc:
        raise WatershedBoundaryValidationError(
            f"Unable to clip DEM because rasterio is unavailable: {exc}"
        ) from exc

    source_path = Path(dem_path)
    target_path = tmpdir / "clipped_dem.tif"
    bbox_geom = {
        "type": "Polygon",
        "coordinates": [[
            [bbox["min_x"], bbox["min_y"]],
            [bbox["max_x"], bbox["min_y"]],
            [bbox["max_x"], bbox["max_y"]],
            [bbox["min_x"], bbox["max_y"]],
            [bbox["min_x"], bbox["min_y"]],
        ]],
    }

    with rasterio.open(source_path) as src:
        clip_geom = bbox_geom
        if src.crs:
            clip_geom = transform_geom("EPSG:4326", src.crs, bbox_geom, precision=12)

        clipped, transform = mask(src, [clip_geom], crop=True)
        meta = src.meta.copy()
        meta.update(
            {
                "height": clipped.shape[1],
                "width": clipped.shape[2],
                "transform": transform,
            }
        )

        with rasterio.open(target_path, "w", **meta) as dst:
            dst.write(clipped)

    return target_path


def _load_external_boundary_module():
    project_dir = current_app.extensions["app_config"].to_flask_mapping().get(
        "WATERSHED_BOUNDARY_PROJECT_ROOT",
        None,
    )
    if project_dir:
        candidate = Path(project_dir)
    else:
        candidate = Path(
            current_app.config.get("WATERSHED_BOUNDARY_PROJECT_ROOT")
            or DEFAULT_EXTERNAL_PROJECT
        )
    module_path = candidate / "point_to_basin_shp.py"
    if not module_path.exists():
        raise WatershedBoundaryValidationError(
            f"point_to_basin_shp project not found: {module_path}"
        )

    module_name = "gistool_point_to_basin_shp"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise WatershedBoundaryValidationError(f"Unable to load watershed module from: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _clip_feature_collection(collection: dict[str, Any], bbox: dict[str, float]) -> dict[str, Any]:
    try:
        from shapely.geometry import box, mapping, shape
    except Exception as exc:
        raise WatershedBoundaryValidationError(f"Unable to clip GeoJSON because shapely is unavailable: {exc}") from exc

    clip_box = box(bbox["min_x"], bbox["min_y"], bbox["max_x"], bbox["max_y"])
    features = []
    for feature in collection.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        clipped = shape(geometry).intersection(clip_box)
        if clipped.is_empty:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(clipped),
                "properties": dict(feature.get("properties") or {}),
            }
        )
    return {"type": "FeatureCollection", "features": features}
