# -*- coding: utf-8 -*-
"""Helpers for compatibility proxy MCP modules."""
import hashlib
import importlib.util
from pathlib import Path
import sys


def load_proxy_exports(module_globals: dict, canonical: Path) -> None:
    canonical = canonical.resolve()
    package_dir = canonical.parent
    init_file = package_dir / "__init__.py"

    if init_file.exists():
        digest = hashlib.sha1(str(package_dir).encode("utf-8")).hexdigest()[:12]
        package_name = f"_canonical_proxy_{package_dir.name}_{digest}"
        if package_name not in sys.modules:
            package_spec = importlib.util.spec_from_file_location(
                package_name,
                init_file,
                submodule_search_locations=[str(package_dir)],
            )
            package = importlib.util.module_from_spec(package_spec)
            sys.modules[package_name] = package
            package_spec.loader.exec_module(package)
        module_name = f"{package_name}.{canonical.stem}"
    else:
        module_name = f"_{canonical.stem}_canonical_common"

    spec = importlib.util.spec_from_file_location(module_name, canonical)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    for name in dir(module):
        if not name.startswith("__"):
            module_globals[name] = getattr(module, name)
