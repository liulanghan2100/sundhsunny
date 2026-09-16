# -*- coding: utf-8 -*-
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from manual_mcp.common import main

if __name__ == "__main__":
    main("strategy")
