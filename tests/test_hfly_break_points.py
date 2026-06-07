from __future__ import annotations

import json
from pathlib import Path


def test_replace_user_break_points_preserves_primary_outlet_and_appends_extra_points(tmp_path, monkeypatch):
    from app.gis.watershed_core.HFLY import replace_user_break_points

    monkeypatch.chdir(tmp_path)
    break_point_path = tmp_path / "break_point.geojson"
    break_point_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [105.2, 27.1]},
                        "properties": {"id": 1, "type": "break_point"},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [105.0, 27.0]},
                        "properties": {"id": 7, "type": "break_point"},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    replace_user_break_points([(105.3, 27.2, 1), (105.4, 27.3, 99)], filename=str(break_point_path))

    payload = json.loads(break_point_path.read_text(encoding="utf-8"))
    ids = [feature["properties"]["id"] for feature in payload["features"]]
    coordinates = [feature["geometry"]["coordinates"] for feature in payload["features"]]

    assert ids == [1, 2, 3]
    assert coordinates == [[105.2, 27.1], [105.3, 27.2], [105.4, 27.3]]


def test_replace_user_break_points_creates_primary_outlet_slot_when_missing(tmp_path, monkeypatch):
    from app.gis.watershed_core.HFLY import ensure_primary_outlet_point, replace_user_break_points

    monkeypatch.chdir(tmp_path)
    break_point_path = tmp_path / "break_point.geojson"

    ensure_primary_outlet_point(105.2, 27.1, filename=str(break_point_path))
    replace_user_break_points([(105.3, 27.2, 1)], filename=str(break_point_path))

    payload = json.loads(break_point_path.read_text(encoding="utf-8"))

    assert len(payload["features"]) == 2
    assert payload["features"][0]["properties"]["id"] == 1
    assert payload["features"][0]["geometry"]["coordinates"] == [105.2, 27.1]
    assert payload["features"][1]["properties"]["id"] == 2
    assert payload["features"][1]["geometry"]["coordinates"] == [105.3, 27.2]


def test_ensure_primary_outlet_point_restores_id_one_when_missing(tmp_path, monkeypatch):
    from app.gis.watershed_core.HFLY import ensure_primary_outlet_point

    monkeypatch.chdir(tmp_path)
    break_point_path = tmp_path / "break_point.geojson"
    break_point_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [105.3, 27.2]},
                        "properties": {"id": 2, "type": "break_point"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ensure_primary_outlet_point(105.2, 27.1, filename=str(break_point_path))

    payload = json.loads(break_point_path.read_text(encoding="utf-8"))
    ids = [feature["properties"]["id"] for feature in payload["features"]]
    assert ids == [2, 1] or ids == [1, 2]
    assert any(
        feature["properties"]["id"] == 1 and feature["geometry"]["coordinates"] == [105.2, 27.1]
        for feature in payload["features"]
    )


def test_ensure_primary_outlet_point_allows_same_coordinates_with_different_ids(tmp_path, monkeypatch):
    from app.gis.watershed_core.HFLY import ensure_primary_outlet_point

    monkeypatch.chdir(tmp_path)
    break_point_path = tmp_path / "break_point.geojson"
    break_point_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [105.2, 27.1]},
                        "properties": {"id": 2, "type": "break_point"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ensure_primary_outlet_point(105.2, 27.1, filename=str(break_point_path))

    payload = json.loads(break_point_path.read_text(encoding="utf-8"))
    ids = [feature["properties"]["id"] for feature in payload["features"]]
    assert sorted(ids) == [1, 2]


def test_replace_user_break_points_keeps_string_id_one_and_restarts_manual_ids(tmp_path, monkeypatch):
    from app.gis.watershed_core.HFLY import replace_user_break_points

    monkeypatch.chdir(tmp_path)
    break_point_path = tmp_path / "break_point.geojson"
    break_point_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [105.2, 27.1]},
                        "properties": {"id": "1", "type": "break_point"},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [105.9, 27.9]},
                        "properties": {"id": 9, "type": "break_point"},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    replace_user_break_points([(105.3, 27.2, 2)], filename=str(break_point_path))

    payload = json.loads(break_point_path.read_text(encoding="utf-8"))
    ids = [feature["properties"]["id"] for feature in payload["features"]]
    coordinates = [feature["geometry"]["coordinates"] for feature in payload["features"]]

    assert ids == [1, 2]
    assert coordinates == [[105.2, 27.1], [105.3, 27.2]]


def test_add_break_point_writes_to_the_requested_filename(tmp_path, monkeypatch):
    from app.gis.watershed_core.HFLY import add_break_point

    monkeypatch.chdir(tmp_path)
    break_point_path = tmp_path / "nested" / "break_point.geojson"
    break_point_path.parent.mkdir()

    added = add_break_point(105.3, 27.2, point_id=2, filename=str(break_point_path))

    assert added is True
    assert not (tmp_path / "break_point.geojson").exists()
    payload = json.loads(break_point_path.read_text(encoding="utf-8"))
    assert payload["features"][0]["properties"]["id"] == 2
