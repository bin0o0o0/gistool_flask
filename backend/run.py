"""Fixed-mode Flask backend entrypoint.

Development uses three separate backend services:
- render: port 5000, must be started by ArcGIS Pro Python / propy.bat.
- watershed: port 5001, normal GIS Python environment.
- watershed-boundary: port 5002, normal GIS Python environment.

Set GIS_TOOL_SERVICE to choose the service. If it is omitted, this entrypoint
defaults to render, because port 5000 is the safest default for map output.
"""

from __future__ import annotations

import os
import sys

from app import create_app
from app.core.service_mode import SERVICE_MODE_RENDER, normalize_service_mode, service_port


def _ensure_utf8_stdio() -> None:
    """Avoid Windows GBK stdout/stderr crashes when GIS logs contain symbols like km²."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_ensure_utf8_stdio()

app = create_app({"SERVICE_MODE": os.getenv("GIS_TOOL_SERVICE", "all")})


def _service_mode_from_env() -> str:
    return normalize_service_mode(os.getenv("GIS_TOOL_SERVICE", SERVICE_MODE_RENDER))


def _ensure_render_runtime(mode: str) -> None:
    if mode != SERVICE_MODE_RENDER:
        return
    try:
        import arcpy  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "GIS_TOOL_SERVICE=render must run on fixed port 5000 with ArcGIS Pro Python / propy.bat. "
            "Do not start the map-output backend with ordinary python.exe."
        ) from exc


if __name__ == "__main__":
    service_mode = _service_mode_from_env()
    _ensure_render_runtime(service_mode)

    app = create_app({"SERVICE_MODE": service_mode})
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = service_port(service_mode)
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    print(f"Starting {service_mode} backend on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
