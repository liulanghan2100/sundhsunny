# -*- coding: utf-8 -*-
"""模块启动入口：completion_verifier_mcp

sys.path 里要加 engine/mcps —— common.py 依赖 _shared（公共库），
它不在本模块目录下。
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from completion_verifier_mcp.common import main  # noqa: E402


if __name__ == "__main__":
    main()
