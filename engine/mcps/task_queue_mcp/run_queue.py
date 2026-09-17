# -*- coding: utf-8 -*-
"""task_queue_mcp 启动入口。

这是依赖最多的模块，跨 4 个包内位置，缺一个都起不来：
  engine/mcps    -> _shared / completion_verifier_mcp / dashboard_mcp
                    / mandatory_runtime_hook_mcp
  engine/memory  -> experience_memory_mcp
  core           -> Agent_OS_Core（治理核：校验、审批、锁、预算）
"""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve()
_MCPS = _HERE.parent.parent              # engine/mcps
_HUB = _MCPS.parent.parent               # 包根

for p in (_MCPS, _HUB / "engine" / "memory", _HUB / "core"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from task_queue_mcp.common import main  # noqa: E402


if __name__ == "__main__":
    main()
