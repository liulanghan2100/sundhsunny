# -*- coding: utf-8 -*-
"""Git/PR/CI MCP server.

v5.4 upgrades the previous local planning adapter into a guarded GitHub/CI
integration layer. It can inspect Git/GitHub state, generate CI workflow files
and PR bodies, query CI through GitHub CLI, and optionally create a PR when
dry_run=false. Remote actions remain explicit.
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.state import safe_project

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
CI_TEMPLATE_DIR = DATA_ROOT / "09_投研" / "git_ci" / "templates"
PR_DIR = DATA_ROOT / "09_投研" / "git_ci" / "pr"


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _cwd(path: str = "") -> Path:
    return Path(path) if path else ROOT


def _run(args: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        proc = subprocess.run(args, cwd=str(cwd), text=True, capture_output=True, timeout=20)
        return proc.returncode == 0, (proc.stdout or proc.stderr).strip()
    except Exception as exc:
        return False, str(exc)


def _run_git(args: list[str], cwd: Path) -> tuple[bool, str]:
    return _run(["git", *args], cwd)


def _run_gh(args: list[str], cwd: Path) -> tuple[bool, str]:
    return _run(["gh", *args], cwd)


def _safe_project(project: str) -> str:
    return "".join(c for c in project if c.isalnum() or c in "-_.") or "project"


def _project_dir(project: str) -> Path:
    path = DATA_ROOT / "09_投研" / "git_ci" / _safe_project(project)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _repo_info(path: str = "") -> dict:
    cwd = _cwd(path)
    valid_git_marker = False
    invalid_marker = ""
    for candidate in [cwd, *cwd.parents]:
        marker = candidate / ".git"
        if marker.exists():
            if marker.is_file():
                valid_git_marker = True
                break
            if (marker / "HEAD").exists() or (marker / "config").exists():
                valid_git_marker = True
                break
            invalid_marker = str(marker)
            break
    if not valid_git_marker:
        return {
            "is_git_repo": False,
            "path": str(cwd),
            "reason": f"invalid .git marker: {invalid_marker}" if invalid_marker else ".git marker not found",
            "fallback": "use zip backup + manual-gates state.json + gate_report as delivery evidence",
        }
    ok, top = _run_git(["rev-parse", "--show-toplevel"], cwd)
    if not ok:
        return {
            "is_git_repo": False,
            "path": str(cwd),
            "reason": top,
            "fallback": "use zip backup + manual-gates state.json + gate_report as delivery evidence",
        }
    ok_branch, branch = _run_git(["branch", "--show-current"], cwd)
    ok_status, status = _run_git(["status", "--short"], cwd)
    ok_remote, remote = _run_git(["remote", "-v"], cwd)
    ok_head, head = _run_git(["rev-parse", "--short", "HEAD"], cwd)
    return {
        "is_git_repo": True,
        "repo_root": top,
        "branch": branch if ok_branch else "",
        "head": head if ok_head else "",
        "remotes": remote.splitlines() if ok_remote and remote else [],
        "status_short": status.splitlines() if ok_status and status else [],
    }


def _gh_info(path: str = "") -> dict:
    cwd = _cwd(path)
    ok_version, version = _run_gh(["--version"], cwd)
    if not ok_version:
        return {"gh_available": False, "reason": version}
    ok_auth, auth = _run_gh(["auth", "status"], cwd)
    return {
        "gh_available": True,
        "version": version.splitlines()[0] if version else "",
        "authenticated": ok_auth,
        "auth_status": auth,
    }


def _github_remote(path: str = "") -> dict:
    info = _repo_info(path)
    if not info.get("is_git_repo"):
        return {"repo_available": False, "repo": info}
    github = [r for r in info.get("remotes", []) if "github.com" in r]
    owner_repo = ""
    if github:
        parts = github[0].split()
        raw = parts[1] if len(parts) > 1 else github[0]
        owner_repo = raw.replace("git@github.com:", "").replace("https://github.com/", "").replace(".git", "").strip("/")
    return {"repo_available": True, "github_remote": bool(github), "owner_repo": owner_repo, "repo": info}


def _ci_yaml(project: str, python_version: str, commands: list[str]) -> str:
    test_commands = commands or [
        "python -m py_compile 03_分工MCP/git_ci_mcp/common.py",
        "python Agent_OS_Core/agent_os.py delegate smoke run git-ci-mcp --execute",
    ]
    run_block = "\n".join(f"          {cmd}" for cmd in test_commands)
    return f"""name: manual-gates-ci

on:
  pull_request:
  push:
    branches: [ main, master ]

jobs:
  verify:
    name: Verify {project}
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '{python_version}'
      - name: Run manual-gates checks
        shell: pwsh
        run: |
{run_block}
"""


def build_server() -> FastMCP:
    mcp = FastMCP("git-ci-mcp")

    @mcp.tool()
    def git_ci_brief() -> str:
        """Describe Git/PR/CI integration scope."""
        return _json({
            "name": "git-ci-mcp",
            "version": "v5.4",
            "purpose": "connect manual-gates delivery to Git, GitHub PRs, CI workflow, and release evidence",
            "default_safety": "dry-run; remote operations require dry_run=false",
            "tools": [
                "repo_status",
                "github_status",
                "branch_plan",
                "ci_plan",
                "write_ci_workflow",
                "pr_checklist",
                "generate_pr_body",
                "github_pr_plan",
                "create_github_pr",
                "ci_status",
                "release_evidence",
                "pr_ci_dry_run_loop",
                "ci_failure_repair_plan",
            ],
        })

    @mcp.tool()
    def repo_status(path: str = "") -> str:
        """Check local git repository status or fallback mode."""
        return _json(_repo_info(path))

    @mcp.tool()
    def github_status(path: str = "") -> str:
        """Check GitHub remote and gh CLI availability."""
        return _json({"repo": _github_remote(path), "gh": _gh_info(path)})

    @mcp.tool()
    def branch_plan(project: str, change_type: str = "feature", base_branch: str = "main",
                    path: str = "") -> str:
        """Generate a branch plan for a manual-gates project."""
        info = _repo_info(path)
        branch = f"{change_type}/{project}".replace(" ", "-").lower()
        return _json({
            "project": project,
            "repo": info,
            "recommended_branch": branch,
            "base_branch": base_branch,
            "commands": [
                f"git checkout {base_branch}",
                f"git checkout -b {branch}",
            ] if info["is_git_repo"] else [],
            "fallback": None if info["is_git_repo"] else info["fallback"],
        })

    @mcp.tool()
    def ci_plan(project: str, tests: str = "", path: str = "") -> str:
        """Create a CI checklist for a manual-gates project."""
        test_list = [x.strip() for x in tests.split(",") if x.strip()]
        info = _repo_info(path)
        return _json({
            "project": project,
            "repo_available": info["is_git_repo"],
            "required_checks": test_list or ["smoke tests", "unit tests", "gate_report"],
            "ci_contract": [
                "all smoke/unit tests pass",
                "manual-gates gate_report is green",
                "PR body references state.json and evidence files",
                "release package includes source, tests, gate state, and backup path",
            ],
            "fallback": None if info["is_git_repo"] else info["fallback"],
        })

    @mcp.tool()
    def write_ci_workflow(project: str, output_path: str = "",
                          python_version: str = "3.12",
                          test_commands_json: str = "[]",
                          overwrite: bool = False) -> str:
        """Write a GitHub Actions workflow file for manual-gates verification."""
        commands = _loads(test_commands_json, [])
        if not isinstance(commands, list):
            return _json({"error": "test_commands_json must be a JSON list"})
        out = Path(output_path) if output_path else DATA_ROOT / ".github" / "workflows" / "manual-gates-ci.yml"
        if out.exists() and not overwrite:
            return _json({"status": "exists", "path": str(out), "hint": "set overwrite=true to replace"})
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_ci_yaml(project, python_version, [str(x) for x in commands]), encoding="utf-8")
        CI_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        template = CI_TEMPLATE_DIR / f"{_safe_project(project)}_manual_gates_ci.yml"
        template.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        return _json({"status": "written", "path": str(out), "template_copy": str(template)})

    @mcp.tool()
    def pr_checklist(project: str, gate_report_path: str = "", evidence_paths: str = "") -> str:
        """Generate a PR checklist that maps to manual-gates evidence."""
        evidence = [x.strip() for x in evidence_paths.split(",") if x.strip()]
        return _json({
            "project": project,
            "title": f"[manual-gates] {project}",
            "checklist": [
                "scope/contract recorded",
                "implementation files listed",
                "tests passed and named",
                "gate_report passed",
                "risks, boundaries, rollback/fallback documented",
                "experience memory recorded or explicitly not applicable",
            ],
            "gate_report_path": gate_report_path,
            "evidence_paths": evidence,
        })

    @mcp.tool()
    def generate_pr_body(project: str, summary: str = "", gate_report_path: str = "",
                         evidence_paths: str = "", risks: str = "",
                         output_path: str = "") -> str:
        """Generate a PR body that references manual-gates evidence."""
        evidence = [x.strip() for x in evidence_paths.split(",") if x.strip()]
        risk_lines = [x.strip() for x in risks.split("|") if x.strip()]
        body = "\n".join([
            f"# {project}",
            "",
            "## Summary",
            summary or "Manual-gates governed change.",
            "",
            "## Verification",
            f"- Gate report: {gate_report_path or 'pending'}",
            *[f"- Evidence: {p}" for p in evidence],
            "",
            "## Risks / Boundaries",
            *(f"- {r}" for r in (risk_lines or ["No additional risk recorded."])),
            "",
            "## Manual-Gates Checklist",
            "- [ ] Scope and MVP recorded",
            "- [ ] Interface/contract recorded",
            "- [ ] Smoke tests passed",
            "- [ ] Gate report passed",
            "- [ ] Backup created",
            "",
            f"Generated: {_now()}",
        ])
        PR_DIR.mkdir(parents=True, exist_ok=True)
        out = Path(output_path) if output_path else PR_DIR / f"{_safe_project(project)}_pr_body.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        return _json({"status": "written", "path": str(out), "body": body})

    @mcp.tool()
    def github_pr_plan(project: str, title: str = "", body_path: str = "",
                       base: str = "main", head: str = "", path: str = "") -> str:
        """Create a GitHub PR execution plan."""
        repo = _github_remote(path)
        gh = _gh_info(path)
        branch = head or (_repo_info(path).get("branch") if repo.get("repo_available") else "")
        commands = []
        if repo.get("repo_available") and gh.get("gh_available"):
            commands = [
                f"git push -u origin {branch}" if branch else "git push -u origin <branch>",
                f"gh pr create --base {base} --head {branch or '<branch>'} --title \"{title or project}\" --body-file \"{body_path or '<body.md>'}\"",
            ]
        return _json({
            "project": project,
            "cwd": str(_cwd(path)),
            "repo": repo,
            "gh": gh,
            "base": base,
            "head": branch,
            "title": title or project,
            "body_path": body_path,
            "dry_run_commands": commands,
            "can_create_pr": bool(repo.get("repo_available") and repo.get("github_remote") and gh.get("gh_available") and gh.get("authenticated")),
        })

    @mcp.tool()
    def create_github_pr(project: str, title: str, body_path: str,
                         base: str = "main", head: str = "",
                         path: str = "", dry_run: bool = True) -> str:
        """Create a GitHub PR through gh CLI when dry_run=false."""
        plan = json.loads(github_pr_plan(project, title, body_path, base, head, path))
        if dry_run:
            plan["status"] = "dry_run"
            return _json(plan)
        if not plan.get("can_create_pr"):
            return _json({"status": "blocked", "reason": "GitHub repo or gh authentication is not ready", "plan": plan})
        body = Path(body_path)
        if not body.exists():
            return _json({"status": "blocked", "reason": f"body_path not found: {body_path}", "plan": plan})
        args = ["pr", "create", "--base", base, "--title", title, "--body-file", str(body)]
        if plan.get("head"):
            args.extend(["--head", plan["head"]])
        ok, out = _run_gh(args, _cwd(path))
        return _json({"status": "created" if ok else "failed", "output": out, "plan": plan})

    @mcp.tool()
    def ci_status(path: str = "", pr_number: int = 0) -> str:
        """Read GitHub CI status through gh CLI when available."""
        repo = _github_remote(path)
        gh = _gh_info(path)
        if not (repo.get("repo_available") and gh.get("gh_available")):
            return _json({"status": "unavailable", "repo": repo, "gh": gh})
        args = ["pr", "checks", str(pr_number)] if pr_number else ["run", "list", "--limit", "5"]
        ok, out = _run_gh(args, _cwd(path))
        return _json({"status": "ok" if ok else "failed", "command": ["gh", *args], "output": out})

    @mcp.tool()
    def release_evidence(project: str, artifact_paths: str = "", backup_path: str = "",
                         gate_status: str = "") -> str:
        """Create a release evidence manifest."""
        artifacts = [x.strip() for x in artifact_paths.split(",") if x.strip()]
        missing = [p for p in artifacts if not Path(p).exists()]
        return _json({
            "project": project,
            "artifacts": artifacts,
            "missing_artifacts": missing,
            "backup_path": backup_path,
            "backup_exists": Path(backup_path).exists() if backup_path else False,
            "gate_status": gate_status,
            "release_ready": not missing and bool(gate_status),
        })

    @mcp.tool()
    def pr_ci_dry_run_loop(project: str, summary: str = "", tests: str = "",
                           evidence_paths: str = "", gate_report_path: str = "",
                           backup_path: str = "", base: str = "main",
                           python_version: str = "3.12") -> str:
        """Generate a local PR/CI closed-loop dry-run without remote actions."""
        out_dir = _project_dir(project)
        test_list = [x.strip() for x in tests.split(",") if x.strip()]
        evidence = [x.strip() for x in evidence_paths.split(",") if x.strip()]
        branch = json.loads(branch_plan(project, "feature", base, ""))
        ci_contract = json.loads(ci_plan(project, tests, ""))
        workflow_path = out_dir / "manual-gates-ci.yml"
        workflow = json.loads(write_ci_workflow(
            project=project,
            output_path=str(workflow_path),
            python_version=python_version,
            test_commands_json=json.dumps(test_list, ensure_ascii=False),
            overwrite=True,
        ))
        pr_body_path = out_dir / "pr_body.md"
        pr_body = json.loads(generate_pr_body(
            project=project,
            summary=summary or "Manual Agent OS governed change.",
            gate_report_path=gate_report_path,
            evidence_paths=",".join(evidence),
            risks="dry-run only|remote PR/CI requires explicit approval",
            output_path=str(pr_body_path),
        ))
        pr_plan = json.loads(github_pr_plan(project, project, str(pr_body_path), base, "", ""))
        release = json.loads(release_evidence(
            project,
            artifact_paths=",".join([str(workflow_path), str(pr_body_path), *evidence]),
            backup_path=backup_path,
            gate_status=gate_report_path or "dry-run gate evidence pending",
        ))
        state = {
            "project": project,
            "generated": _now(),
            "mode": "dry_run",
            "remote_actions": "not_executed",
            "branch_plan": branch,
            "ci_plan": ci_contract,
            "workflow": workflow,
            "pr_body": {"path": pr_body.get("path")},
            "github_pr_plan": pr_plan,
            "release_evidence": release,
            "next_external_step_requires_approval": True,
        }
        state_path = out_dir / "pr_ci_dry_run_loop.json"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({"status": "dry_run_completed", "path": str(state_path), "state": state})

    @mcp.tool()
    def ci_failure_repair_plan(project: str, ci_output: str = "",
                               failing_check: str = "", output_path: str = "") -> str:
        """Create a local repair plan from CI failure text."""
        lower = ci_output.lower()
        actions = []
        if "syntax" in lower or "compile" in lower or "py_compile" in lower:
            actions.append("run python -m py_compile on changed Python files")
        if "test" in lower or "assert" in lower or "failed" in lower:
            actions.append("rerun targeted smoke test and inspect first failing assertion")
        if "import" in lower or "module" in lower:
            actions.append("check sys.path, package __init__.py, and optional dependency availability")
        if not actions:
            actions.append("collect CI log, map failure to changed files, rerun local smoke test")
        plan = {
            "project": project,
            "generated": _now(),
            "failing_check": failing_check,
            "ci_output_excerpt": ci_output[:2000],
            "repair_actions": actions,
            "requires_remote_action": False,
        }
        out = Path(output_path) if output_path else _project_dir(project) / "ci_failure_repair_plan.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({"status": "planned", "path": str(out), "plan": plan})

    return mcp


def main() -> None:
    build_server().run()
