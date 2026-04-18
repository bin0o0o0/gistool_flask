"""GIS 渲染模块对外入口。

外部代码只需要：

    from app.gis.render import ArcPyRenderer

不需要知道真实实现文件叫 `arcpy_renderer.py`。
"""

from __future__ import annotations

from app.gis.render.arcpy_renderer import ArcPyRenderer

__all__ = ["ArcPyRenderer"]
