"""Watershed extraction API.

This module adapts the previously standalone watershed Flask backend into the
current application factory. The real GIS classes are imported lazily so API
tests can inject lightweight fakes without requiring the full raster stack.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from app.gis.watershed_core.parse_geojson_to_frontend import parse_geojson_to_frontend
from app.utils.responses import error_response


watershed_bp = Blueprint("watershed", __name__)


class WatershedValidationError(ValueError):
    """Raised when a watershed request payload is invalid."""


@watershed_bp.post("/acc_threshold")
def calculate_acc_threshold():
    """Calculate the default accumulation area threshold."""
    try:
        payload = _json_payload()
        dem_path = _dem_path(payload)
        shapefile_path = _optional_path(payload.get("shapefile_path"))
        service = _watershed_service(
            area_threshold=None,
            shapefile_path=shapefile_path,
            s_geojson=payload.get("s_geojson"),
            dem_path=dem_path,
            control_points=None,
            random_folder_name=_default_algorithm_program_path(),
            plan_name=_plan_name(payload),
            state_dir="temp_state",
            cell_size_x=payload.get("cell_size_x", 30),
            cell_size_y=payload.get("cell_size_y", 30),
            step=0,
        )
        with _watershed_runtime():
            area_threshold = service.acc_default_value()
            random_folder_name = service.random_folder_name_r()
    except WatershedValidationError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        return error_response(str(exc), 500)

    return jsonify(
        {
            "success": True,
            "message": "阈值计算完成",
            "area_threshold": round(float(area_threshold), 2),
            "random_folder_name": str(random_folder_name),
        }
    )


@watershed_bp.post("/step0_streams")
def step0_streams():
    """Generate initial watershed boundary and stream previews."""
    try:
        payload = _json_payload()
        _require_fields(payload, ("area_threshold", "random_folder_name"))
        dem_path = _dem_path(payload)
        random_folder_name = _resolve_algorithm_folder(payload["random_folder_name"])
        service = _watershed_service(
            area_threshold=payload["area_threshold"],
            shapefile_path=_optional_path(payload.get("shapefile_path")),
            dem_path=dem_path,
            control_points=None,
            random_folder_name=random_folder_name,
            plan_name=_plan_name(payload),
            state_dir="temp_state",
            step=0,
        )
        with _watershed_runtime():
            boundary_geojson, streams_geojson, _folder = service.step0_streams()
    except WatershedValidationError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        return error_response(str(exc), 500)

    return jsonify(
        {
            "success": True,
            "message": "流域边界和河道生成完成",
            "buffered_boundary_geojson": boundary_geojson,
            "streams_ori_geojson": streams_geojson,
            "buffered_boundary": _preview_geo_layer_or_empty(boundary_geojson, entity_type="polygon"),
            "streams_ori": _preview_geo_layer_or_empty(streams_geojson, entity_type="line"),
        }
    )


@watershed_bp.post("/step1")
def step1():
    """Generate sub-watersheds and topology outputs."""
    try:
        payload = _json_payload()
        _require_fields(payload, ("area_threshold", "random_folder_name"))
        dem_path = _dem_path(payload)
        control_points = payload.get("break_points") or []
        random_folder_name = _resolve_algorithm_folder(payload["random_folder_name"])
        plan_name = _plan_name(payload)
        _clear_stale_merge_outputs(random_folder_name, plan_name)
        service = _watershed_service(
            area_threshold=payload["area_threshold"],
            shapefile_path=_optional_path(payload.get("shapefile_path")),
            dem_path=dem_path,
            control_points=control_points,
            random_folder_name=random_folder_name,
            plan_name=plan_name,
            state_dir="temp_state",
            step=1,
        )
        with _watershed_runtime():
            service.step1_fill_depressions_and_flow()
            service.step2_identify_streams()
            service.step3_generate_subwatersheds()
            outputs = service.generate_final_outputs()
    except WatershedValidationError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        return error_response(str(exc), 500)

    return jsonify({"success": True, "outputs": outputs})


@watershed_bp.post("/step2")
def step2():
    """Merge or delete generated watersheds."""
    try:
        payload = _json_payload()
        operation = payload.get("operation", "merge")
        if operation not in {"merge", "delete"}:
            raise WatershedValidationError("operation must be either merge or delete.")
        _require_fields(payload, ("random_folder",))
        watershed_ids = payload.get("watershed_ids") or []
        if not isinstance(watershed_ids, list) or not watershed_ids:
            raise WatershedValidationError("watershed_ids must contain at least one watershed id.")

        service = _merge_service(
            random_folder_name=_resolve_algorithm_folder(payload["random_folder"]),
            plan_name=_plan_name(payload),
            control_points=payload.get("break_points") or [],
            state_dir="temp_state",
        )
        with _watershed_runtime():
            result = service.step4_merge_or_delete_watersheds(
                operation=operation,
                watershed_ids=watershed_ids,
            )
            outputs = service.generate_final_outputs()
    except WatershedValidationError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        return error_response(str(exc), 500)

    return jsonify({"success": True, "operation": operation, "result": result, "outputs": outputs})


@watershed_bp.post("/preview-layer")
def preview_layer():
    """Read a stored vector path and return a frontend-ready FeatureCollection."""
    try:
        payload = _json_payload()
        _require_fields(payload, ("path",))
        layer = _preview_geo_layer(str(payload["path"]), entity_type=str(payload.get("entity_type") or "polygon"))
    except WatershedValidationError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        return error_response(str(exc), 500)

    return jsonify({"success": True, "layer": layer})


@watershed_bp.post("/validate-plan-name")
def validate_plan_name():
    """Check whether the requested plan directory already exists."""
    try:
        payload = _json_payload()
        plan_name = _plan_name(payload)
        plan_dir = Path(_default_algorithm_program_path()) / plan_name
    except WatershedValidationError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        return error_response(str(exc), 500)

    exists = plan_dir.exists()
    message = "检测到同名方案，继续可能复用旧结果，建议更换名称" if exists else "方案名称可用"
    return jsonify({"success": True, "exists": exists, "message": message})


def _json_payload() -> dict[str, Any]:
    if not request.is_json:
        raise WatershedValidationError("Expected JSON request body.")
    payload = request.get_json() or {}
    if not isinstance(payload, dict):
        raise WatershedValidationError("Expected JSON object request body.")
    return payload


def _require_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if payload.get(field) in (None, "")]
    if missing:
        raise WatershedValidationError(f"Missing required fields: {', '.join(missing)}")


def _dem_path(payload: dict[str, Any]) -> str:
    config = current_app.extensions["app_config"]
    dem_path = payload.get("dem_path") or str(config.watershed_default_dem_path)
    path = Path(dem_path)
    if not path.exists():
        raise WatershedValidationError(f"DEM file does not exist: {dem_path}")
    return str(path)


def _optional_path(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _default_algorithm_program_path() -> str:
    config = current_app.extensions["app_config"]
    return str(config.watershed_program_root)


def _plan_name(payload: dict[str, Any]) -> str:
    value = payload.get("plan_name")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "方案1"


def _preview_geo_layer(path_value: str, entity_type: str = "polygon") -> dict[str, Any]:
    path = Path(path_value)
    if not path.exists():
        raise WatershedValidationError(f"Preview file does not exist: {path_value}")

    suffix = path.suffix.lower()
    if suffix in {".geojson", ".json"}:
        return parse_geojson_to_frontend(str(path), entity_type=entity_type)
    if suffix in {".shp", ".kml"}:
        return _vector_file_to_feature_collection(path)
    raise WatershedValidationError(f"Unsupported preview file suffix: {suffix}")


def _preview_geo_layer_or_empty(path_value: str, entity_type: str = "polygon") -> dict[str, Any]:
    try:
        return _preview_geo_layer(path_value, entity_type=entity_type)
    except WatershedValidationError:
        return {"type": "FeatureCollection", "features": []}


def _vector_file_to_feature_collection(path: Path) -> dict[str, Any]:
    try:
        import geopandas as gpd
    except Exception as exc:
        raise WatershedValidationError(f"Unable to read vector preview file because geopandas is unavailable: {exc}") from exc

    frame = gpd.read_file(path)
    geojson = frame.__geo_interface__
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": feature.get("geometry"),
                "properties": dict(feature.get("properties", {})),
            }
            for feature in geojson.get("features", [])
        ],
    }


def _resolve_algorithm_folder(value: str) -> str:
    config = current_app.extensions["app_config"]
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((config.watershed_program_root.parent / value).resolve())


def _clear_stale_merge_outputs(random_folder_name: str, plan_name: str) -> None:
    base_dir = Path(random_folder_name) / plan_name / "basic_file"
    stale_paths = [
        base_dir / "sub_catchment_merge.geojson",
        base_dir / "upstream_cells_merge.geojson",
        base_dir / "junctions_merge.geojson",
        base_dir / "river_network_linestrings_merge.geojson",
        base_dir / "downstream_dict_merge.json",
        base_dir / "source_deleted.geojson",
        base_dir / "point.geojson",
    ]
    for path in stale_paths:
        if path.exists():
            path.unlink()


def _watershed_service(**kwargs):
    factory = current_app.extensions.get("watershed_service_factory")
    if factory is None:
        from app.gis.watershed_core.HFLY import Generate_subwatersheds

        factory = Generate_subwatersheds
    return factory(**kwargs)


def _merge_service(**kwargs):
    factory = current_app.extensions.get("watershed_merge_service_factory")
    if factory is None:
        from app.gis.watershed_core.merge_delete import Merge_delete

        factory = Merge_delete
    return factory(**kwargs)


@contextmanager
def _watershed_runtime():
    config = current_app.extensions["app_config"]
    previous_forecast_save_path = os.environ.get("FORECAST_SAVE_PATH")
    os.environ["FORECAST_SAVE_PATH"] = str(config.watershed_program_root.parent)
    try:
        yield
    finally:
        if previous_forecast_save_path is None:
            os.environ.pop("FORECAST_SAVE_PATH", None)
        else:
            os.environ["FORECAST_SAVE_PATH"] = previous_forecast_save_path
