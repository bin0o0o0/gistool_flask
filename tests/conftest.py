"""pytest 公共配置。

pytest 默认从项目根目录或 tests 目录运行时，不一定能直接导入 `backend/app`。
这里把项目根目录和 backend 目录都加入 `sys.path`，让测试可以写：

    from app import create_app

而不用写很长的相对导入。
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

# 把路径插到 sys.path 最前面，优先导入当前项目里的代码，而不是其他地方同名包。
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
