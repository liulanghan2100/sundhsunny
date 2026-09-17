# -*- coding: utf-8 -*-
"""product_os_mcp 启动入口。

依赖跨多个包内位置，sys.path 缺一个都起不来：
  engine/mcps    -> _shared 及相邻模块
  engine/memory  -> 记忆引擎
  core           -> 治理核
"""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve()
_MCPS = _HERE.parent.parent
_HUB = _MCPS.parent.parent

for p in (_MCPS, _HUB / "engine" / "memory", _HUB / "core"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from product_os_mcp.common import main  # noqa: E402


if __name__ == "__main__":
    main()
