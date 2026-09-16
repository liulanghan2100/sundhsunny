"""Process-local, path-overlap resource locks for Task Queue preflight."""
from __future__ import annotations

import threading
from pathlib import Path


class ResourceBusyError(RuntimeError):
    pass


class ResourceLockManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owners: dict[str, tuple[str, str]] = {}

    @staticmethod
    def _canonical(path: str) -> str:
        return str(Path(path).expanduser().resolve()).casefold()

    def acquire(self, task_id: str, resources: list[dict]) -> list[str]:
        normalized = [
            (self._canonical(item["path"]), str(item.get("access", "read")).lower())
            for item in resources
            if isinstance(item, dict) and item.get("path")
        ]
        with self._lock:
            conflicts = []
            for path, access in normalized:
                for owned_path, (owner, owned_access) in self._owners.items():
                    overlap = path == owned_path or path.startswith(owned_path + "\\") or owned_path.startswith(path + "\\")
                    write_conflict = access != "read" or owned_access != "read"
                    if owner != task_id and overlap and write_conflict:
                        conflicts.append(owner)
            if conflicts:
                raise ResourceBusyError(f"resource conflict with: {sorted(set(conflicts))}")
            for path, access in normalized:
                self._owners[path] = (task_id, access)
        return [path for path, _ in normalized]

    def release(self, task_id: str) -> None:
        with self._lock:
            for path, (owner, _) in list(self._owners.items()):
                if owner == task_id:
                    del self._owners[path]

    def snapshot(self) -> dict[str, dict[str, str]]:
        with self._lock:
            return {path: {"task_id": owner, "access": access} for path, (owner, access) in self._owners.items()}
