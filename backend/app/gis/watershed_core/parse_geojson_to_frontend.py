import json
import os


def parse_geojson_to_frontend(file_path, entity_type="polygon"):
    """
    将 GeoJSON 文件解析为前端地图组件可用的格式

    Args:
        file_path: GeoJSON 文件路径
        entity_type: 实体类型 ("polygon" | "line" | "point")

    Returns:
        dict: 包含 type 和 features 的标准 GeoJSON FeatureCollection 结构
    """
    if not file_path or not os.path.exists(file_path):
        return {"type": "FeatureCollection", "features": []}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"type": "FeatureCollection", "features": []}

    features = data.get("features", [])

    parsed_features = []
    for feature in features:
        geometry = feature.get("geometry", {})
        props = feature.get("properties", {})

        parsed_feature = {
            "type": "Feature",
            "geometry": geometry,
            "properties": props,
        }
        parsed_features.append(parsed_feature)

    return {"type": "FeatureCollection", "features": parsed_features}
