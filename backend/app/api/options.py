"""渲染表单选项接口。

这个接口主要给前端或 Apifox 调试使用：

    GET /api/render-options

它不会访问 ArcPy，也不会读写文件，只返回固定枚举。
你可以把它理解成“告诉调用方，哪些参数值是后端认可的”。
"""

from __future__ import annotations

from flask import Blueprint

from app.core.constants import (
    BASemaps,
    LABEL_POSITIONS,
    STATION_SYMBOL_COLOR_PRESETS,
    STATION_SYMBOL_SHAPES,
)
from app.utils.responses import success_response


options_bp = Blueprint("options", __name__)


@options_bp.get("")
def render_options():
    """返回出图请求中可用的枚举值。"""
    return success_response(
        {
            "label_positions": LABEL_POSITIONS,
            "basemaps": BASemaps,
            # 站点符号拆成形状和颜色两组，前端可以自由组合。
            "station_symbol_shapes": STATION_SYMBOL_SHAPES,
            "station_symbol_color_presets": STATION_SYMBOL_COLOR_PRESETS,
        }
    )
