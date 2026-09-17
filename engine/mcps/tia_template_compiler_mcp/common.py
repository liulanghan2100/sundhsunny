# -*- coding: utf-8 -*-
"""TIA V21 template compiler MCP.

This server is the planning and evidence layer. It does not call Siemens
Openness directly; the generated runner bundle is consumed by the existing
Windows V21 runner.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

try:
    from _shared.io import _json
except ImportError:  # pragma: no cover - direct execution fallback
    def _json(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, indent=2)


ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
DEFAULT_EVIDENCE_DIR = DATA_ROOT / "06_演进记录" / "tia-template-compiler-mcp" / "artifacts"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_id(value: str, fallback: str = "change") -> str:
    value = (value or "").strip()
    if _SAFE_ID.fullmatch(value):
        return value
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return cleaned[:101] or fallback


def _path(value: str, must_exist: bool = True) -> Path:
    path = Path(value).expanduser().resolve()
    if must_exist and not path.exists():
        raise ValueError(f"path does not exist: {path}")
    return path


def _project_file(template_root: Path) -> Path | None:
    files = sorted(template_root.glob("*.ap21"))
    return files[0] if files else None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _list_files(root: Path, pattern: str) -> list[str]:
    return [str(p.relative_to(root)) for p in sorted(root.rglob(pattern)) if p.is_file()]


def _read_project_info(root: Path) -> dict[str, Any]:
    path = root / "ProjectInfo.txt"
    if not path.exists():
        return {"path": None, "tia_version": None, "support_packages": []}
    text = path.read_text(encoding="utf-8", errors="replace")
    version = re.search(r"TechnicalVersion:\s*(21\.\d+(?:\.\d+){2})", text)
    packages = re.findall(r"- Name:\s*(.+)", text)
    return {
        "path": str(path),
        "tia_version": version.group(1) if version else None,
        "support_packages": [p.strip() for p in packages],
    }


def _template_catalog(root: Path) -> dict[str, Any]:
    project = _project_file(root)
    gsd = _list_files(root / "AdditionalFiles", "*.xml") if (root / "AdditionalFiles").exists() else []
    xlsm = _list_files(root / "YWW", "*.xlsm") if (root / "YWW").exists() else []
    temp_files = [
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and (p.name.startswith("~$") or p.name.endswith(".db-journal"))
    ]
    return {
        "catalog_version": "0.1",
        "generated_at": _now(),
        "template_root": str(root),
        "project_file": str(project) if project else None,
        "project_sha256": _hash_file(project) if project else None,
        "project_info": _read_project_info(root),
        "inventory": {
            "gsdml_files": gsd,
            "engineering_documents": xlsm,
            "ap21_count": len(list(root.glob("*.ap21"))),
            "xml_count": len(list(root.rglob("*.xml"))),
        },
        "temporary_files": temp_files,
        "semantic_catalog_status": "runner_required",
        "semantic_catalog_missing": [
            "plc_targets",
            "hmi_targets",
            "hardware_devices",
            "plc_blocks",
            "tag_tables",
            "call_networks",
            "cross_references",
        ],
        "anchors": {
            "component_container": "FB_Component",
            "valve_container": "FB_ValveCall",
            "alarm_root": "DB_PromptBeeper",
        },
    }


def _validation_errors(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["project_spec must be an object"]
    if not str(spec.get("project_name", "")).strip():
        errors.append("project_name is required")
    if spec.get("tia_version") not in (None, "", "V21", "21", "21.00.00.00"):
        errors.append("tia_version must be V21 for this MCP")
    for key in ("hardware", "servos", "cylinders", "io_points", "hmi_requirements"):
        value = spec.get(key, [])
        if not isinstance(value, list):
            errors.append(f"{key} must be an array")
    for i, servo in enumerate(spec.get("servos", [])):
        if not isinstance(servo, dict):
            errors.append(f"servos[{i}] must be an object")
            continue
        for field in ("name", "station"):
            if not str(servo.get(field, "")).strip():
                errors.append(f"servos[{i}].{field} is required")
        if servo.get("ip") and not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", str(servo["ip"])):
            errors.append(f"servos[{i}].ip is not a valid IPv4 shape")
    for i, cylinder in enumerate(spec.get("cylinders", [])):
        if not isinstance(cylinder, dict):
            errors.append(f"cylinders[{i}] must be an object")
            continue
        for field in ("name", "station"):
            if not str(cylinder.get(field, "")).strip():
                errors.append(f"cylinders[{i}].{field} is required")
    return errors


def _component_changes(spec: dict[str, Any], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for servo in spec.get("servos", []):
        name = _safe_id(str(servo.get("name", "")), "servo")
        changes.append({
            "change_id": f"add-servo-{name}",
            "kind": "servo",
            "target": servo,
            "runner_route": _runner_route("servo", servo),
            "source_anchors": {
                "hardware": servo.get("source_hardware", "V90_T111"),
                "container_block": catalog["anchors"]["component_container"],
                "alarm_root": catalog["anchors"]["alarm_root"],
            },
            "operations": [
                "add_hardware",
                "configure_profinet",
                "assign_telegram",
                "create_plc_tags",
                "clone_component_network",
                "add_alarm_path",
                "compile_hardware",
                "compile_plc",
                "readback_verify",
            ],
            "acceptance": {
                "hardware_exists": True,
                "network_exists": True,
                "static_member_exists": True,
                "missing_bindings": 0,
                "plc_compile_errors": 0,
            },
        })
    for cylinder in spec.get("cylinders", []):
        name = _safe_id(str(cylinder.get("name", "")), "cylinder")
        changes.append({
            "change_id": f"add-cylinder-{name}",
            "kind": "cylinder",
            "target": cylinder,
            "runner_route": _runner_route("cylinder", cylinder),
            "source_anchors": {
                "container_block": catalog["anchors"]["valve_container"],
                "alarm_root": catalog["anchors"]["alarm_root"],
            },
            "operations": [
                "create_input_tags",
                "create_output_tags",
                "clone_valve_network",
                "add_alarm_path",
                "compile_plc",
                "readback_verify",
            ],
            "acceptance": {
                "static_member_exists": True,
                "shared_instance_db_preserved": True,
                "missing_bindings": 0,
                "plc_compile_errors": 0,
            },
        })
    return changes


def _runner_route(kind: str, target: dict[str, Any]) -> dict[str, Any]:
    """Resolve only an explicitly supported route; never infer a destructive command."""
    requested = str(target.get("runner_route", "")).strip().lower()
    execution_profile = str(target.get("execution_profile", "")).strip().lower()
    if requested == "compile-plc":
        return {"status": "ready", "command": "--compile-plc", "arguments": []}
    if requested == "apply-template-only":
        return {"status": "ready", "command": "--apply-template-only", "arguments": []}
    if requested == "apply-hmi-tags-only":
        return {"status": "ready", "command": "--apply-hmi-tags-only", "arguments": []}
    if kind == "cylinder" and execution_profile == "st10_pair_next":
        return {
            "status": "ready",
            "command": "--apply-st10-cylinder-pair-next",
            "arguments": [],
        }
    if kind == "servo" and execution_profile == "component_servo":
        template_path = str(target.get("template_path", "")).strip()
        if template_path:
            start_index = str(target.get("servo_start_index", "")).strip()
            return {
                "status": "ready",
                "command": "--apply-component-servo-plan",
                "arguments": [
                    "--template", template_path,
                ] + (["--servo-start-index", start_index] if start_index else []),
            }
    return {
        "status": "blocked",
        "command": None,
        "arguments": [],
        "reason": (
            "No explicit V21 Runner route is bound to this business component. "
            "Supply runner_route/execution_profile and the required plan paths."
        ),
    }


def build_server() -> FastMCP:
    mcp = FastMCP(
        "tia-template-compiler-mcp",
        instructions=(
            "TIA Portal V21 模板差异编译规划 MCP。先 scan_template，再 "
            "validate_project_spec/build_change_spec/preview_change，最后 "
            "stage_runner_bundle。此 MCP 不直接执行 Siemens Openness 写入；"
            "实际修改必须由受控 Windows V21 Runner 消费执行包。"
        ),
    )

    @mcp.tool()
    def tia_template_compiler_brief() -> str:
        """返回能力边界、工具顺序和当前实现状态。"""
        return _json({
            "name": "tia-template-compiler-mcp",
            "version": "0.1.0",
            "purpose": "文档驱动的 TIA V21 模板差异规划与执行包生成",
            "pipeline": [
                "scan_template",
                "validate_project_spec",
                "build_change_spec",
                "preview_change",
                "stage_runner_bundle",
                "dispatch_runner_bundle",
                "runner_apply_and_compile",
                "verify_change",
            ],
            "implemented_here": [
                "静态模板目录",
                "项目规格校验",
                "业务组件级差异计划",
                "预览与执行包",
                "执行包完整性验收",
            ],
            "delegated_to_runner": [
                "Siemens.Engineering V21 调用",
                "真实硬件/PLC/HMI修改",
                "分层编译",
                "TIA工程回读",
            ],
            "blocked_by_design": [
                "在线连接、下载、上传",
                "原始模板工程直接修改",
                "任意 Openness 命令",
            ],
        })

    @mcp.tool()
    def scan_template(template_root: str) -> str:
        """扫描 V21 模板目录，输出文件基线和待由 Runner 回读的语义目录。"""
        try:
            root = _path(template_root)
            if not root.is_dir():
                return _json({"ok": False, "errors": ["template_root must be a directory"]})
            catalog = _template_catalog(root)
            catalog["ok"] = bool(catalog["project_file"])
            catalog["errors"] = [] if catalog["ok"] else ["no .ap21 project found"]
            return _json(catalog)
        except ValueError as exc:
            return _json({"ok": False, "errors": [str(exc)]})

    @mcp.tool()
    def validate_project_spec(project_spec: dict) -> str:
        """校验文档解析后的 ProjectSpec，不修改工程。"""
        errors = _validation_errors(project_spec)
        return _json({
            "valid": not errors,
            "errors": errors,
            "required_sections": [
                "project_name", "tia_version", "stations", "hardware",
                "servos", "cylinders", "io_points", "hmi_requirements",
            ],
            "next": "build_change_spec" if not errors else "补齐错误字段后重试",
        })

    @mcp.tool()
    def build_change_spec(template_catalog: dict, project_spec: dict) -> str:
        """把模板目录和项目规格转换为可审阅的业务组件 ChangeSpec。"""
        errors = _validation_errors(project_spec)
        if errors:
            return _json({"ok": False, "errors": errors, "changes": []})
        if not isinstance(template_catalog, dict) or not template_catalog.get("template_root"):
            return _json({"ok": False, "errors": ["template_catalog is required"], "changes": []})
        changes = _component_changes(project_spec, template_catalog)
        return _json({
            "ok": True,
            "change_spec_version": "0.1",
            "created_at": _now(),
            "template": {
                "root": template_catalog["template_root"],
                "project_file": template_catalog.get("project_file"),
                "sha256": template_catalog.get("project_sha256"),
            },
            "project": {
                "name": project_spec.get("project_name"),
                "tia_version": project_spec.get("tia_version", "V21"),
                "project_file": project_spec.get("project_file"),
                "project_copy_path": project_spec.get("project_copy_path"),
                "output_root": project_spec.get("output_root"),
            },
            "preserve": [
                "core_blocks",
                "call_order",
                "container_hierarchy",
                "alarm_conventions",
                "shared_instance_db_model",
            ],
            "changes": changes,
            "manual_confirmation_required": [
                "模板语义目录尚未由 V21 Runner 完整回读",
                "实际硬件型号、地址和 HMI 绑定必须以 TIA 回读为准",
            ],
        })

    @mcp.tool()
    def preview_change(change_spec: dict) -> str:
        """生成不落地 TIA 的变更预览和风险分类。"""
        changes = change_spec.get("changes", []) if isinstance(change_spec, dict) else []
        risks = []
        for change in changes:
            kind = change.get("kind")
            risks.append({
                "change_id": change.get("change_id"),
                "risk": "R3_disposable_project_compile",
                "reason": f"{kind} component changes project state and requires compile/readback",
                "allowed_next": "stage_runner_bundle",
            })
        return _json({
            "ok": bool(changes),
            "preview_only": True,
            "will_modify": [c.get("change_id") for c in changes],
            "will_not_modify": ["original template", "online PLC", "broker APIs"],
            "risks": risks,
            "approval": {
                "required": bool(changes),
                "token": "owner approval must be supplied to the runner, not inferred by the model",
            },
        })

    @mcp.tool()
    def stage_runner_bundle(change_spec: dict, output_dir: str = "") -> str:
        """把已预览的 ChangeSpec 写成 V21 Runner 可消费的离线执行包。"""
        if not isinstance(change_spec, dict) or not change_spec.get("changes"):
            return _json({"ok": False, "errors": ["change_spec.changes is required"]})
        out = _path(output_dir, must_exist=False) if output_dir else DEFAULT_EVIDENCE_DIR
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bundle_id = _safe_id(f"tia-change-{stamp}")
        bundle = {
            "schema": "OpennessTask",
            "schema_version": "0.1",
            "bundle_id": bundle_id,
            "created_at": _now(),
            "risk": "R3",
            "mode": "offline_disposable_copy_only",
            "source": change_spec.get("template", {}),
            "project": change_spec.get("project", {}),
            "tasks": [
                {
                    "task_id": c.get("change_id"),
                    "action": "apply_business_component",
                    "kind": c.get("kind"),
                    "target": c.get("target", {}),
                    "runner_route": c.get("runner_route", {
                        "status": "blocked",
                        "command": None,
                        "arguments": [],
                        "reason": "runner route missing",
                    }),
                    "operations": c.get("operations", []),
                    "acceptance": c.get("acceptance", {}),
                }
                for c in change_spec["changes"]
            ],
            "side_effects": {
                "project_modified": False,
                "original_project_modified": False,
                "online_connected": False,
                "download_attempted": False,
                "upload_attempted": False,
            },
            "runner_contract": {
                "required": "Windows TIA Portal V21 Openness Runner",
                "must_create_disposable_copy": True,
                "must_compile": True,
                "must_readback": True,
                "must_return_evidence": True,
            },
        }
        path = out / f"{bundle_id}.json"
        path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({
            "ok": True,
            "status": "staged_not_executed",
            "bundle_path": str(path),
            "bundle_id": bundle_id,
            "next": "交给 Windows V21 Runner；Runner 完成后调用 verify_change",
        })

    @mcp.tool()
    def dispatch_runner_bundle(
        bundle_path: str,
        runner_executable: str,
        execute: bool = False,
        timeout_seconds: int = 1800,
    ) -> str:
        """Preview or dispatch an OpennessTask to the existing V21 Runner.

        The default is dry-run. Real execution additionally requires the
        explicit environment gate OPENNISS_RUNNER_ALLOW_EXECUTION=1.
        """
        try:
            path = _path(bundle_path)
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            return _json({"ok": False, "status": "blocked", "errors": [str(exc)]})

        validation = json.loads(verify_staged_bundle(str(path)))
        if not validation.get("valid"):
            return _json({
                "ok": False,
                "status": "blocked",
                "reason": "staged bundle validation failed",
                "validation": validation,
            })

        executable = _path(runner_executable)
        project = bundle.get("project", {})
        project_copy_path = str(project.get("project_copy_path", "")).strip()
        if not project_copy_path:
            return _json({
                "ok": False,
                "status": "blocked",
                "reason": "project.project_copy_path is required for Runner dispatch",
                "next": "create and validate a disposable V21 project copy first",
            })
        project_copy = _path(project_copy_path)
        template_project = str(bundle.get("source", {}).get("project_file", "")).strip()
        if template_project and project_copy == _path(template_project):
            return _json({
                "ok": False,
                "status": "blocked",
                "reason": "project_copy_path must not equal the template project file",
            })
        tasks = bundle.get("tasks", [])
        commands = []
        blocked = []
        for task in tasks:
            route = task.get("runner_route", {})
            if route.get("status") != "ready" or not route.get("command"):
                blocked.append({
                    "task_id": task.get("task_id"),
                    "reason": route.get("reason", "runner route is not ready"),
                })
                continue
            commands.append({
                "task_id": task.get("task_id"),
                "command": route["command"],
                "arguments": route.get("arguments", []),
            })

        if blocked:
            return _json({
                "ok": False,
                "status": "blocked",
                "reason": "one or more tasks have no explicit V21 Runner route",
                "blocked_tasks": blocked,
                "dispatch": commands,
            })

        preview = {
            "bundle_id": bundle.get("bundle_id"),
            "runner_executable": str(executable),
            "project_copy_path": str(project_copy),
            "project_copy_required": bundle.get("runner_contract", {}).get(
                "must_create_disposable_copy", True
            ),
            "commands": commands,
        }
        output_root = str(project.get("output_root", "")).strip()
        for item in commands:
            item["arguments"] = [
                "--project", str(project_copy),
            ] + (["--output", output_root] if output_root else []) + item["arguments"]
        if not execute:
            return _json({
                "ok": True,
                "status": "dry_run",
                "execution_started": False,
                "preview": preview,
                "next": "set execute=true and OPENNISS_RUNNER_ALLOW_EXECUTION=1 to dispatch",
            })

        if os.environ.get("OPENNISS_RUNNER_ALLOW_EXECUTION") != "1":
            return _json({
                "ok": False,
                "status": "blocked",
                "reason": "execution gate missing: OPENNISS_RUNNER_ALLOW_EXECUTION=1",
                "preview": preview,
            })
        if timeout_seconds < 1 or timeout_seconds > 7200:
            return _json({
                "ok": False,
                "status": "blocked",
                "reason": "timeout_seconds must be between 1 and 7200",
            })

        results = []
        for item in commands:
            command_line = [str(executable), item["command"]] + [
                str(value) for value in item["arguments"]
            ]
            try:
                completed = subprocess.run(
                    command_line,
                    cwd=str(executable.parent),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                results.append({
                    "task_id": item["task_id"],
                    "command": command_line,
                    "return_code": completed.returncode,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-4000:],
                })
            except subprocess.TimeoutExpired as exc:
                results.append({
                    "task_id": item["task_id"],
                    "command": command_line,
                    "return_code": None,
                    "timeout": True,
                    "stdout": (exc.stdout or "")[-4000:] if exc.stdout else "",
                    "stderr": (exc.stderr or "")[-4000:] if exc.stderr else "",
                })
                break
            if results[-1]["return_code"] != 0:
                break

        success = len(results) == len(commands) and all(
            item.get("return_code") == 0 for item in results
        )
        return _json({
            "ok": success,
            "status": "runner_completed" if success else "runner_failed",
            "execution_started": True,
            "preview": preview,
            "results": results,
        })

    @mcp.tool()
    def verify_staged_bundle(bundle_path: str) -> str:
        """检查执行包是否满足 Runner 边界和验收契约。"""
        try:
            path = _path(bundle_path)
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            return _json({"ok": False, "errors": [str(exc)]})
        errors = []
        for key in ("schema", "bundle_id", "source", "tasks", "runner_contract"):
            if key not in bundle:
                errors.append(f"missing bundle field: {key}")
        if bundle.get("schema") != "OpennessTask":
            errors.append("schema must be OpennessTask")
        for task in bundle.get("tasks", []):
            if not task.get("task_id") or not task.get("operations"):
                errors.append("each task needs task_id and operations")
        return _json({
            "ok": not errors,
            "valid": not errors,
            "errors": errors,
            "status": "ready_for_runner" if not errors else "blocked",
            "side_effects": bundle.get("side_effects", {}),
        })

    @mcp.tool()
    def verify_change(bundle_path: str, evidence: dict | None = None) -> str:
        """根据 Runner 回传证据判断 PASS/FAIL；未提供证据时明确阻断。"""
        if not evidence:
            return _json({
                "status": "blocked",
                "reason": "真实 TIA 编译和回读证据尚未提供",
                "required_evidence": [
                    "runner_response",
                    "compile_errors",
                    "readback_objects",
                    "project_copy_path",
                ],
            })
        errors = []
        if evidence.get("compile_errors", 0) != 0:
            errors.append("compile_errors must be 0")
        if not evidence.get("readback_objects"):
            errors.append("readback_objects is required")
        if evidence.get("original_project_modified"):
            errors.append("original_project_modified must be false")
        return _json({
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "evidence": evidence,
            "bundle_path": bundle_path,
        })

    @mcp.resource("tia://template-compiler/usage")
    def usage_guide() -> str:
        return (
            "调用顺序：scan_template -> validate_project_spec -> "
            "build_change_spec -> preview_change -> stage_runner_bundle -> "
            "dispatch_runner_bundle -> Windows V21 Runner -> verify_change。"
        )

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
