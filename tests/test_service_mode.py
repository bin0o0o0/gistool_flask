from __future__ import annotations


def test_service_mode_ports_are_fixed():
    from app.core.service_mode import service_port

    assert service_port("render") == 5000
    assert service_port("watershed") == 5001
    assert service_port("watershed-boundary") == 5002


def test_render_service_mode_rejects_watershed_requests(tmp_path):
    from app import create_app

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "SERVICE_MODE": "render",
        }
    )

    response = app.test_client().post("/api/watershed/acc_threshold", json={})

    assert response.status_code == 404
    body = response.get_json()
    assert body["success"] is False
    assert "not enabled in render service" in body["message"]


def test_watershed_service_mode_keeps_watershed_uploads_available(tmp_path):
    from app import create_app

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "SERVICE_MODE": "watershed",
        }
    )

    response = app.test_client().get("/api/render-options")

    assert response.status_code == 404
    assert "not enabled in watershed service" in response.get_json()["message"]


def test_health_runtime_label_matches_service_mode(tmp_path):
    from app import create_app

    app = create_app(
        {
            "TESTING": True,
            "OUTPUT_FOLDER": str(tmp_path / "outputs"),
            "SERVICE_MODE": "watershed-boundary",
        }
    )

    response = app.test_client().get("/api/health")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["service_mode"] == "watershed-boundary"
    assert data["runtime"] == "Watershed boundary Python"
