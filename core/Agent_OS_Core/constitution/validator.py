# -*- coding: utf-8 -*-
"""
Constitution Validator — Immutable Guard

宪法校验器：系统级不可变性守卫。
任何代码在写入操作前必须调用本校验器。
如果目标路径属于宪法层，校验器返回 BLOCK，写入操作必须中止。

设计原则：
- 校验逻辑本身也是宪法的一部分，Agent 无权修改
- 校验结果不可被绕过（无后门、无 override 开关）
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal


CORE_DIR = Path(__file__).resolve().parent.parent
CONSTITUTION_DIR = CORE_DIR / "constitution"

# 宪法层保护路径（相对 CORE_DIR）
CONSTITUTION_FILES = {
    "charter.json",
    "budget_rules.json",
    "security_rules.json",
    "evolution_rules.json",
    "rollback_manifest.json",
}

# 额外保护路径（绝对路径匹配）
PROTECTED_PATHS = {
    "02_执行手册",
    ".git",
    ".env",
    "10_知识储备库/cases",
}

VALIDATION_EVIDENCE_ROOT = Path("09_research/agent-os-structure-slimming-v1").resolve()
WRITEBACK_BLOCK_MARKERS = (
    "/registry/",
    "/status/",
    "/runtime/",
    "/skill/",
    "/skills/",
)


def _boundary_result(
    action: Literal["ALLOW", "BLOCK"],
    reason: str,
    boundary: str,
    violation_type: str | None = None,
    decision_id: str | None = None,
) -> dict[str, Any]:
    """Return one machine-verifiable result shape for execution boundaries."""
    return {
        "action": action,
        "reason": reason,
        "violation_type": violation_type,
        "boundary": boundary,
        "decision_id": decision_id,
    }


def _record_value(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _decision_approved(decision_record: Any) -> bool:
    return _record_value(decision_record, "decision") == "approve"


def _validation_context(run_state: Any) -> bool:
    return bool(_record_value(run_state, "validation_context", False)) and not bool(
        _record_value(run_state, "production_context", False)
    )


def _decision_id(decision_record: Any) -> str | None:
    value = _record_value(decision_record, "decision_id")
    return str(value) if value else None


def _allowlisted_path(path: str | Path, root: Path = VALIDATION_EVIDENCE_ROOT) -> bool:
    candidate = _normalize_path(path)
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def validate_provider_call(
    run_state: Any,
    decision_record: Any,
    provider_name: str,
    *,
    mode: str | None = None,
) -> dict[str, Any]:
    """Guard provider access; real provider use remains explicitly gated."""
    selected_mode = mode or _record_value(run_state, "mode")
    if not _validation_context(run_state):
        return _boundary_result(
            "BLOCK",
            "provider access requires validation context",
            "provider",
            "non_validation_context",
            _decision_id(decision_record),
        )
    if not _decision_approved(decision_record):
        return _boundary_result(
            "BLOCK",
            "provider access requires an approved decision record",
            "provider",
            "missing_or_unapproved_decision",
            _decision_id(decision_record),
        )
    if selected_mode == "monkeypatched_provider":
        return _boundary_result(
            "ALLOW",
            f"monkeypatched provider sequence allowed: {provider_name}",
            "provider",
            decision_id=_decision_id(decision_record),
        )
    if selected_mode == "real_provider_gated" and _record_value(
        run_state, "owner_gate"
    ):
        return _boundary_result(
            "ALLOW",
            f"provider owner gate present: {provider_name}",
            "provider",
            decision_id=_decision_id(decision_record),
        )
    return _boundary_result(
        "BLOCK",
        "real provider requires real_provider_gated mode and owner gate",
        "provider",
        "provider_gate_required",
        _decision_id(decision_record),
    )


def validate_network_access(
    run_state: Any,
    decision_record: Any,
    url_or_host: str,
    *,
    allowlisted_targets: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Guard network access; no network is opened by this validator."""
    if not _validation_context(run_state):
        return _boundary_result(
            "BLOCK",
            "network access requires validation context",
            "network",
            "non_validation_context",
            _decision_id(decision_record),
        )
    if not _decision_approved(decision_record):
        return _boundary_result(
            "BLOCK",
            "network access requires an approved decision record",
            "network",
            "missing_or_unapproved_decision",
            _decision_id(decision_record),
        )
    if url_or_host not in allowlisted_targets:
        return _boundary_result(
            "BLOCK",
            "network target is not allowlisted",
            "network",
            "unknown_network_target",
            _decision_id(decision_record),
        )
    return _boundary_result(
        "ALLOW",
        "network target is explicitly allowlisted",
        "network",
        decision_id=_decision_id(decision_record),
    )


def validate_sandbox_execution(
    run_state: Any,
    decision_record: Any,
    sandbox_name: str,
    *,
    allowlisted_sandboxes: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Guard sandbox execution; validation context and allowlist are required."""
    if not _validation_context(run_state):
        return _boundary_result(
            "BLOCK",
            "sandbox execution requires validation context",
            "sandbox",
            "non_validation_context",
            _decision_id(decision_record),
        )
    if not _decision_approved(decision_record):
        return _boundary_result(
            "BLOCK",
            "sandbox execution requires an approved decision record",
            "sandbox",
            "missing_or_unapproved_decision",
            _decision_id(decision_record),
        )
    if bool(_record_value(run_state, "runtime_writeback_allowed", False)):
        return _boundary_result(
            "BLOCK",
            "sandbox execution cannot enable runtime writeback",
            "sandbox",
            "runtime_writeback_enabled",
            _decision_id(decision_record),
        )
    if sandbox_name not in allowlisted_sandboxes:
        return _boundary_result(
            "BLOCK",
            "sandbox is not allowlisted",
            "sandbox",
            "unknown_sandbox",
            _decision_id(decision_record),
        )
    return _boundary_result(
        "ALLOW",
        "sandbox is explicitly allowlisted",
        "sandbox",
        decision_id=_decision_id(decision_record),
    )


def validate_runtime_dispatch(
    run_state: Any,
    decision_record: Any,
    dispatch_target: str,
    *,
    allowlisted_targets: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Guard runtime dispatch; validation-only dispatch is the default boundary."""
    if not _validation_context(run_state):
        return _boundary_result(
            "BLOCK",
            "runtime dispatch requires validation context",
            "runtime_dispatch",
            "non_validation_context",
            _decision_id(decision_record),
        )
    if _record_value(run_state, "status") != "approved":
        return _boundary_result(
            "BLOCK",
            "runtime dispatch requires approved RunState",
            "runtime_dispatch",
            "run_state_not_approved",
            _decision_id(decision_record),
        )
    if not _decision_approved(decision_record):
        return _boundary_result(
            "BLOCK",
            "runtime dispatch requires an approved decision record",
            "runtime_dispatch",
            "missing_or_unapproved_decision",
            _decision_id(decision_record),
        )
    if dispatch_target not in allowlisted_targets:
        return _boundary_result(
            "BLOCK",
            "dispatch target is not allowlisted",
            "runtime_dispatch",
            "unknown_dispatch_target",
            _decision_id(decision_record),
        )
    return _boundary_result(
        "ALLOW",
        "dispatch target is explicitly allowlisted",
        "runtime_dispatch",
        decision_id=_decision_id(decision_record),
    )


def validate_writeback(
    run_state: Any,
    decision_record: Any,
    target_path: str | Path,
    *,
    writeback_type: str = "evidence",
) -> dict[str, Any]:
    """Allow only validation evidence writes; block operational writeback."""
    normalized = str(_normalize_path(target_path)).replace("\\", "/").lower()
    if not _validation_context(run_state):
        return _boundary_result(
            "BLOCK",
            "writeback requires validation context",
            "writeback",
            "non_validation_context",
            _decision_id(decision_record),
        )
    if not _decision_approved(decision_record):
        return _boundary_result(
            "BLOCK",
            "writeback requires an approved decision record",
            "writeback",
            "missing_or_unapproved_decision",
            _decision_id(decision_record),
        )
    if writeback_type != "evidence":
        return _boundary_result(
            "BLOCK",
            "only validation evidence writeback is allowed",
            "writeback",
            "operational_writeback_blocked",
            _decision_id(decision_record),
        )
    if any(marker in normalized for marker in WRITEBACK_BLOCK_MARKERS):
        return _boundary_result(
            "BLOCK",
            "registry/status/runtime/Skill writeback is blocked",
            "writeback",
            "protected_writeback_target",
            _decision_id(decision_record),
        )
    if not _allowlisted_path(target_path):
        return _boundary_result(
            "BLOCK",
            "evidence path is outside the validation evidence root",
            "writeback",
            "evidence_path_not_allowlisted",
            _decision_id(decision_record),
        )
    return _boundary_result(
        "ALLOW",
        "validation evidence path is allowlisted",
        "writeback",
        decision_id=_decision_id(decision_record),
    )


def validate_file_mutation(
    action: str,
    src_path: str | Path,
    dst_path: str | Path | None = None,
    *,
    decision_record: Any = None,
) -> dict[str, Any]:
    """Guard file mutation; move/delete remain blocked pending a separate gate."""
    normalized_action = action.lower()
    if normalized_action in {"move", "rename", "delete"}:
        return _boundary_result(
            "BLOCK",
            "file move/delete requires a separate owner gate",
            "file_mutation",
            "destructive_file_mutation_blocked",
            _decision_id(decision_record),
        )
    if normalized_action in {"write", "create", "append"}:
        return validate_writeback(
            {
                "validation_context": True,
                "production_context": False,
            },
            decision_record,
            dst_path or src_path,
            writeback_type="evidence",
        )
    return _boundary_result(
        "BLOCK",
        f"unknown file mutation action: {action}",
        "file_mutation",
        "unknown_file_mutation",
        _decision_id(decision_record),
    )


def validate_action(
    run_state: Any,
    decision_record: Any,
    action: str,
    *,
    allowed_actions: tuple[str, ...] = (),
    blocked_actions: tuple[str, ...] = (),
    estimated_cost_usd: float = 0.0,
    remaining_budget_usd: float | None = None,
) -> dict[str, Any]:
    """Single pre-action guard used by queue and worker execution paths."""
    normalized = str(action).strip().lower()
    if not normalized:
        return _boundary_result("BLOCK", "action is required", "action", "missing_action", _decision_id(decision_record))
    if normalized in {str(item).lower() for item in blocked_actions}:
        return _boundary_result("BLOCK", "action is explicitly forbidden by TaskCard", "action", "forbidden_action", _decision_id(decision_record))
    if not _decision_approved(decision_record):
        return _boundary_result("BLOCK", "every action requires an approved decision record", "action", "missing_or_unapproved_decision", _decision_id(decision_record))
    if normalized not in {str(item).lower() for item in allowed_actions}:
        return _boundary_result("BLOCK", "action is not in the TaskCard allowlist", "action", "action_not_allowlisted", _decision_id(decision_record))
    if estimated_cost_usd < 0 or (
        remaining_budget_usd is not None and estimated_cost_usd > float(remaining_budget_usd)
    ):
        return _boundary_result("BLOCK", "action exceeds the remaining cost budget", "action", "cost_budget_exceeded", _decision_id(decision_record))
    return _boundary_result("ALLOW", "action is allowlisted and budgeted", "action", decision_id=_decision_id(decision_record))


def _normalize_path(path: str | Path) -> Path:
    """统一路径为绝对 Path 对象。"""
    p = Path(path).resolve()
    return p


def is_constitution_path(path: str | Path) -> bool:
    """
    判断目标路径是否属于宪法层保护范围。
    返回 True 表示该路径受宪法保护，禁止写入/修改/删除。
    """
    p = _normalize_path(path)

    # 1. 直接匹配宪法文件
    if p.parent == CONSTITUTION_DIR and p.name in CONSTITUTION_FILES:
        return True

    # 2. 匹配宪法目录本身
    if p == CONSTITUTION_DIR or CONSTITUTION_DIR in p.parents:
        return True

    # 3. 匹配其他受保护路径
    try:
        rel = p.relative_to(CORE_DIR.parent)
        rel_str = str(rel).replace("\\", "/")
        for protected in PROTECTED_PATHS:
            if rel_str.startswith(protected):
                return True
    except ValueError:
        pass

    return False


def validate_write(path: str | Path) -> dict:
    """
    写入操作前的校验接口。

    返回:
        {
            "action": "ALLOW" | "BLOCK",
            "reason": str,
            "protected_path": str | None,
            "violation_type": str | None,
        }
    """
    if is_constitution_path(path):
        return {
            "action": "BLOCK",
            "reason": "CONSTITUTION_IMMUTABLE: 该路径受宪法层保护，禁止修改",
            "protected_path": str(_normalize_path(path)),
            "violation_type": "constitution_write_attempt",
        }

    return {
        "action": "ALLOW",
        "reason": "Path not in constitution scope",
        "protected_path": None,
        "violation_type": None,
    }


def validate_delete(path: str | Path) -> dict:
    """删除操作前的校验接口。"""
    return validate_write(path)


def validate_rename(src: str | Path, dst: str | Path) -> dict:
    """重命名操作前的校验接口（源或目标涉及宪法层都禁止）。"""
    if is_constitution_path(src):
        return {
            "action": "BLOCK",
            "reason": "CONSTITUTION_IMMUTABLE: 源路径受宪法保护，禁止移动/重命名",
            "protected_path": str(_normalize_path(src)),
            "violation_type": "constitution_rename_attempt",
        }
    if is_constitution_path(dst):
        return {
            "action": "BLOCK",
            "reason": "CONSTITUTION_IMMUTABLE: 目标路径在宪法层，禁止写入",
            "protected_path": str(_normalize_path(dst)),
            "violation_type": "constitution_rename_attempt",
        }
    return {
        "action": "ALLOW",
        "reason": "Neither path in constitution scope",
        "protected_path": None,
        "violation_type": None,
    }


def compute_constitution_hash() -> str:
    """
    计算当前宪法层的整体指纹（SHA-256）。
    用于检测宪法文件是否被篡改。
    """
    hasher = hashlib.sha256()
    for name in sorted(CONSTITUTION_FILES):
        fpath = CONSTITUTION_DIR / name
        if fpath.exists():
            hasher.update(fpath.read_bytes())
    return hasher.hexdigest()


def verify_constitution_integrity(expected_hash: str | None = None) -> dict:
    """
    校验宪法层完整性。

    如果提供 expected_hash，对比当前哈希；否则返回当前哈希。
    """
    current_hash = compute_constitution_hash()

    # 检查所有宪法文件是否存在
    missing = []
    for name in CONSTITUTION_FILES:
        if not (CONSTITUTION_DIR / name).exists():
            missing.append(name)

    result = {
        "status": "OK" if not missing else "CORRUPTED",
        "current_hash": current_hash,
        "expected_hash": expected_hash,
        "hash_match": expected_hash == current_hash if expected_hash else None,
        "missing_files": missing,
        "checked_at": None,  # 由调用方填充
    }
    return result


def get_constitution_summary() -> dict:
    """获取宪法层摘要（只读，用于 Agent 了解边界）。"""
    summary = {
        "version": None,
        "files": {},
        "hash": compute_constitution_hash(),
    }
    for name in sorted(CONSTITUTION_FILES):
        fpath = CONSTITUTION_DIR / name
        if fpath.exists():
            data = json.loads(fpath.read_text(encoding="utf-8"))
            summary["files"][name] = {
                "size": fpath.stat().st_size,
                "version": data.get("_meta", {}).get("version", "unknown"),
            }
            if name == "charter.json":
                summary["version"] = data.get("_meta", {}).get("version", "unknown")
    return summary


def guard_write(path: str | Path) -> Literal["ALLOW", "BLOCK"]:
    """
    硬守卫接口：直接返回 ALLOW/BLOCK。
    用于需要简洁判断的场景。
    """
    result = validate_write(path)
    return result["action"]


# CLI 接口，用于手动校验
if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Constitution Validator CLI")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="校验指定路径是否可写入")
    check.add_argument("path", help="要校验的文件或目录路径")

    verify = sub.add_parser("verify", help="校验宪法层完整性")
    verify.add_argument("--expected-hash", default=None, help="预期的哈希值")

    summary = sub.add_parser("summary", help="输出宪法层摘要")

    args = parser.parse_args()

    if args.command == "check":
        result = validate_write(args.path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["action"] == "ALLOW" else 1)

    elif args.command == "verify":
        result = verify_constitution_integrity(args.expected_hash)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["status"] == "OK" else 1)

    elif args.command == "summary":
        print(json.dumps(get_constitution_summary(), ensure_ascii=False, indent=2))
        sys.exit(0)

    else:
        parser.print_help()
        sys.exit(1)
