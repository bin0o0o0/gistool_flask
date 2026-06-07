from __future__ import annotations

from dataclasses import dataclass


SERVICE_MODE_ALL = "all"
SERVICE_MODE_RENDER = "render"
SERVICE_MODE_WATERSHED = "watershed"
SERVICE_MODE_WATERSHED_BOUNDARY = "watershed-boundary"


@dataclass(frozen=True)
class ServiceModeConfig:
    port: int
    allowed_prefixes: tuple[str, ...]


SERVICE_MODES: dict[str, ServiceModeConfig] = {
    SERVICE_MODE_ALL: ServiceModeConfig(
        port=0,
        allowed_prefixes=("/api/",),
    ),
    SERVICE_MODE_RENDER: ServiceModeConfig(
        port=5000,
        allowed_prefixes=(
            "/api/health",
            "/api/render",
            "/api/render-options",
            "/api/uploads",
        ),
    ),
    SERVICE_MODE_WATERSHED: ServiceModeConfig(
        port=5001,
        allowed_prefixes=(
            "/api/health",
            "/api/watershed",
        ),
    ),
    SERVICE_MODE_WATERSHED_BOUNDARY: ServiceModeConfig(
        port=5002,
        allowed_prefixes=(
            "/api/health",
            "/api/watershed-boundary",
        ),
    ),
}


def normalize_service_mode(value: str | None) -> str:
    mode = (value or SERVICE_MODE_ALL).strip().lower()
    if mode in {"boundary", "watershed_boundary", "watershed-boundary-generator"}:
        mode = SERVICE_MODE_WATERSHED_BOUNDARY
    if mode not in SERVICE_MODES:
        allowed = ", ".join(SERVICE_MODES)
        raise ValueError(f"Unsupported SERVICE_MODE: {value}. Expected one of: {allowed}.")
    return mode


def service_port(mode: str) -> int:
    normalized = normalize_service_mode(mode)
    config = SERVICE_MODES[normalized]
    if config.port <= 0:
        raise ValueError("The all service mode is for tests and WSGI only; it has no fixed dev port.")
    return config.port


def is_path_enabled_for_service(path: str, mode: str) -> bool:
    normalized = normalize_service_mode(mode)
    for prefix in SERVICE_MODES[normalized].allowed_prefixes:
        if prefix.endswith("/") and path.startswith(prefix):
            return True
        if path == prefix or path.startswith(f"{prefix}/"):
            return True
    return False
