# -*- coding: utf-8 -*-
"""tia_template_compiler_mcp 启动入口。

sys.path 要加 engine/mcps —— common.py 依赖 _shared（公共库），
它不在本模块目录下。
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tia_template_compiler_mcp.common import main  # noqa: E402


if __name__ == "__main__":
    main()
