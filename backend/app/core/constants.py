"""接口枚举常量。

这些常量属于“前后端协议”的一部分：

- 前端或 Apifox 可以根据它们知道有哪些合法选项。
- 后端校验请求时也用同一份常量，避免写成两套后不一致。
"""

from __future__ import annotations


# 站点标注相对点的位置。当前渲染器还没有完全使用 position 做偏移，
# 但 API 先把合法值限定好，后续增强标注摆放时可以直接复用。
LABEL_POSITIONS = [
    "top_left",
    "top",
    "top_right",
    "right",
    "bottom_right",
    "bottom",
    "bottom_left",
    "left",
]

# ArcGIS Pro 常见在线底图名称。当前模板中底图主要由 aprx 决定，
# 这里保留 basemap 字段是为了让请求结构和未来前端表单更完整。
BASemaps = [
    "Topographic",
    "Imagery",
    "Terrain with Labels",
    "Light Gray Canvas",
]

# 站点形状选项。
#
# 这里把“形状”从旧的组合预设里拆出来，前端就可以单独控制：
# - 形状：圆形、三角形、方形、菱形
# - 颜色：从 STATION_SYMBOL_COLOR_PRESETS 里选，或者直接传自定义 hex 色值
STATION_SYMBOL_SHAPES = [
    "circle",
    "triangle",
    "square",
    "diamond",
]

# 站点颜色预设。
#
# 颜色用 dict 而不是 list，是因为前端既需要展示名字，也需要拿到实际色值。
# 如果用户要完全自定义颜色，请求里仍然可以直接传 `symbol.color = "#RRGGBB"`。
STATION_SYMBOL_COLOR_PRESETS = {
    "blue": "#1f78ff",
    "cyan": "#00a6a6",
    "purple": "#8e5cff",
    "orange": "#f59e0b",
    "green": "#00a651",
    "red": "#ff0000",
    "black": "#000000",
}

# 旧版组合预设兼容表。
#
# 之前接口里用过 circle_green、triangle_red 这种“形状+颜色”绑在一起的值。
# 新接口不再向前端暴露它们，但后端仍然兼容旧请求，避免已有示例或 Apifox 请求马上失效。
STATION_SYMBOL_LEGACY_PRESETS = {
    "rain_station": {"shape": "circle", "color_preset": "blue"},
    "hydrology_station": {"shape": "circle", "color_preset": "cyan"},
    "reservoir": {"shape": "circle", "color_preset": "purple"},
    "city": {"shape": "circle", "color_preset": "orange"},
    "circle_green": {"shape": "circle", "color_preset": "green"},
    "triangle_red": {"shape": "triangle", "color_preset": "red"},
}
