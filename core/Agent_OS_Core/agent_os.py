# -*- coding: utf-8 -*-
"""Top-level Agent OS control entrypoint.

This is the daily operator-facing entry for the slimmed Agent OS. It delegates
to existing sidecar control scripts and keeps runtime capabilities in their
current locations.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

CORE_DIR = Path(__file__).resolve().parent
ROOT = CORE_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Agent_OS_Core.policy.unified_intake import build_intake


CONTROL = CORE_DIR / "scripts" / "agent_os_control.py"
DATA_DIR = ROOT / "09_research" / "agent-os-structure-slimming-v1"


def run_control(*args: str) -> int:
    return subprocess.run([sys.executable, str(CONTROL), *args], cwd=ROOT, check=False).returncode


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def intake_task(
    request_text: str,
    *,
    llm_actions: list[str] | None = None,
    task_profile: str = "general",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The single Agent OS intake API used by planners and CLI callers."""
    return build_intake(
        request_text,
        llm_actions=llm_actions,
        task_profile=task_profile,
        context=context,
    )


def cmd_intake(args: argparse.Namespace) -> int:
    context = json.loads(args.context_json) if args.context_json else {}
    actions = [item.strip() for item in (args.actions or "").split(",") if item.strip()]
    result = intake_task(
        args.request,
        llm_actions=actions,
        task_profile=args.task_profile,
        context=context,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    dashboard = read_json(DATA_DIR / "runtime_dashboard.json")
    if not dashboard:
        print(json.dumps({"status": "missing_dashboard", "next": "run dashboard"}, ensure_ascii=False, indent=2))
        return 1

    workflow = dashboard.get("workflow", [])
    completed = sum(1 for item in workflow if item.get("status") == "completed")
    payload = {
        "agent_os_core": str(CORE_DIR.relative_to(ROOT)),
        "mode": "control_entrypoint_only",
        "workflow_completed": f"{completed}/{len(workflow)}",
        "guardrails": dashboard.get("guardrails", {}),
        "legacy_usage_events": dashboard.get("legacy_usage", {}).get("events", 0),
        "archive_plan_items": dashboard.get("archive_plan", {}).get("items", 0),
        "archive_copy_items": dashboard.get("archive_copy", {}).get("items", 0),
        "next": dashboard.get("next", {}),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_workflow(args: argparse.Namespace) -> int:
    return run_control("workflow")


def cmd_dashboard(args: argparse.Namespace) -> int:
    return run_control("dashboard")


def cmd_web_research_intake(args: argparse.Namespace) -> int:
    return run_control("web-research-intake-readonly")


def cmd_source_trust_score(args: argparse.Namespace) -> int:
    return run_control("source-trust-score")


def cmd_router_online_evidence_test(args: argparse.Namespace) -> int:
    return run_control("router-online-evidence-test")


def cmd_legacy_usage(args: argparse.Namespace) -> int:
    return run_control("legacy-usage")


def cmd_retirement(args: argparse.Namespace) -> int:
    return run_control("retirement")


def cmd_approval_packet(args: argparse.Namespace) -> int:
    return run_control("approval-packet")


def cmd_archive_plan(args: argparse.Namespace) -> int:
    return run_control("archive-plan")


def cmd_archive_status(args: argparse.Namespace) -> int:
    report = read_json(DATA_DIR / "archive_copy_report.json")
    if not report:
        print(json.dumps({"status": "missing_archive_copy_report", "next": "owner-gated archive copy"}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_reference_scan(args: argparse.Namespace) -> int:
    return run_control("reference-scan")


def cmd_reference_candidates(args: argparse.Namespace) -> int:
    path = DATA_DIR / "runtime_reference_scan.json"
    payload = read_json(path)
    if not payload:
        print(json.dumps({"status": "missing_reference_scan", "next": "run reference scan"}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_reference_approval_packet(args: argparse.Namespace) -> int:
    return run_control("reference-approval-packet")


def cmd_reference_rewrite_plan(args: argparse.Namespace) -> int:
    return run_control("reference-rewrite-plan")


def cmd_reference_post_rescan(args: argparse.Namespace) -> int:
    return run_control("post-rewrite-rescan")


def cmd_reference_disposition_packet(args: argparse.Namespace) -> int:
    return run_control("remaining-reference-disposition-packet")


def cmd_reference_execution_plan(args: argparse.Namespace) -> int:
    return run_control("remaining-reference-execution-plan")


def cmd_reference_ref002_plan(args: argparse.Namespace) -> int:
    return run_control("ref002-legacy-shim-self-doc-plan")


def cmd_closure_report(args: argparse.Namespace) -> int:
    return run_control("final-closure-report")


def cmd_health(args: argparse.Namespace) -> int:
    return run_control("runtime-health-baseline")


def cmd_router_quality(args: argparse.Namespace) -> int:
    return run_control("router-quality-baseline")


def cmd_router_simulation(args: argparse.Namespace) -> int:
    return run_control("router-simulation-plan")


def cmd_router_shadow_recommend(args: argparse.Namespace) -> int:
    return run_control("router-shadow-recommend-plan")


def cmd_router_shadow_records_template(args: argparse.Namespace) -> int:
    return run_control("router-shadow-records-template")


def cmd_router_shadow_dry_collection_plan(args: argparse.Namespace) -> int:
    return run_control("router-shadow-dry-collection-plan")


def cmd_router_shadow_manual_sample_fill(args: argparse.Namespace) -> int:
    return run_control("router-shadow-manual-sample-fill")


def cmd_router_shadow_owner_review_packet(args: argparse.Namespace) -> int:
    return run_control("router-shadow-owner-review-packet")


def cmd_router_shadow_owner_application_plan(args: argparse.Namespace) -> int:
    return run_control("router-shadow-owner-application-plan")


def cmd_router_turnup_stage1_closure(args: argparse.Namespace) -> int:
    return run_control("router-turnup-stage1-closure")


def cmd_router_stage2_owner_gate(args: argparse.Namespace) -> int:
    return run_control("router-stage2-owner-gate")


def cmd_router_stage2_real_shadow_run_template(args: argparse.Namespace) -> int:
    return run_control("router-stage2-real-shadow-run-template")


def cmd_router_stage2_real_shadow_capture(args: argparse.Namespace) -> int:
    return run_control("router-stage2-real-shadow-capture")


def cmd_router_stage2_real_shadow_recommend(args: argparse.Namespace) -> int:
    return run_control("router-stage2-real-shadow-recommend")


def cmd_router_stage2_owner_review_application(args: argparse.Namespace) -> int:
    return run_control("router-stage2-owner-review-application")


def cmd_router_stage2_metric_calculation(args: argparse.Namespace) -> int:
    return run_control("router-stage2-metric-calculation")


def cmd_router_stage2_failure_attribution(args: argparse.Namespace) -> int:
    return run_control("router-stage2-failure-attribution")


def cmd_router_stage2_closure_report(args: argparse.Namespace) -> int:
    return run_control("router-stage2-closure-report")


def cmd_router_stage3_manual_dispatch_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage3-manual-dispatch-plan")


def cmd_router_stage3_manual_dispatch_record_template(args: argparse.Namespace) -> int:
    return run_control("router-stage3-manual-dispatch-record-template")


def cmd_router_stage3_manual_dispatch_dry_fill_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage3-manual-dispatch-dry-fill-plan")


def cmd_router_stage3_manual_dispatch_dry_fill_records(args: argparse.Namespace) -> int:
    return run_control("router-stage3-manual-dispatch-dry-fill-records")


def cmd_router_stage3_manual_dispatch_owner_review(args: argparse.Namespace) -> int:
    return run_control("router-stage3-manual-dispatch-owner-review")


def cmd_router_stage3_manual_dispatch_metric_calculation(args: argparse.Namespace) -> int:
    return run_control("router-stage3-manual-dispatch-metric-calculation")


def cmd_router_stage3_manual_dispatch_owner_decision_collection_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage3-manual-dispatch-owner-decision-collection-plan")


def cmd_router_stage3_manual_dispatch_owner_decision_application_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage3-manual-dispatch-owner-decision-application-plan")


def cmd_router_stage3_manual_dispatch_owner_decision_filled_sample_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage3-manual-dispatch-owner-decision-filled-sample-plan")


def cmd_router_stage3_manual_dispatch_owner_decision_filled_sample_metrics(args: argparse.Namespace) -> int:
    return run_control("router-stage3-manual-dispatch-owner-decision-filled-sample-metrics")


def cmd_router_stage3_manual_dispatch_closure_report(args: argparse.Namespace) -> int:
    return run_control("router-stage3-manual-dispatch-closure-report")


def cmd_router_stage4_manual_dispatch_pilot_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage4-manual-dispatch-pilot-plan")


def cmd_router_stage4_manual_dispatch_pilot_record_template(args: argparse.Namespace) -> int:
    return run_control("router-stage4-manual-dispatch-pilot-record-template")


def cmd_router_stage4_manual_dispatch_pilot_dry_fill_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage4-manual-dispatch-pilot-dry-fill-plan")


def cmd_router_stage4_manual_dispatch_pilot_dry_fill_records(args: argparse.Namespace) -> int:
    return run_control("router-stage4-manual-dispatch-pilot-dry-fill-records")


def cmd_router_stage4_manual_dispatch_pilot_owner_review(args: argparse.Namespace) -> int:
    return run_control("router-stage4-manual-dispatch-pilot-owner-review")


def cmd_router_stage4_manual_dispatch_pilot_metric_calculation(args: argparse.Namespace) -> int:
    return run_control("router-stage4-manual-dispatch-pilot-metric-calculation")


def cmd_router_stage4_manual_dispatch_pilot_owner_decision_collection_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage4-manual-dispatch-pilot-owner-decision-collection-plan")


def cmd_router_stage4_manual_dispatch_pilot_owner_decision_application_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage4-manual-dispatch-pilot-owner-decision-application-plan")


def cmd_router_stage4_manual_dispatch_pilot_owner_decision_filled_sample_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage4-manual-dispatch-pilot-owner-decision-filled-sample-plan")


def cmd_router_stage4_manual_dispatch_pilot_owner_decision_filled_sample_metrics(args: argparse.Namespace) -> int:
    return run_control("router-stage4-manual-dispatch-pilot-owner-decision-filled-sample-metrics")


def cmd_router_stage4_manual_dispatch_pilot_closure_report(args: argparse.Namespace) -> int:
    return run_control("router-stage4-manual-dispatch-pilot-closure-report")


def cmd_router_stage5_real_manual_dispatch_owner_gate_packet(args: argparse.Namespace) -> int:
    return run_control("router-stage5-real-manual-dispatch-owner-gate-packet")


def cmd_router_stage5_real_manual_dispatch_record_template(args: argparse.Namespace) -> int:
    return run_control("router-stage5-real-manual-dispatch-record-template")


def cmd_router_stage5_real_manual_dispatch_capture_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage5-real-manual-dispatch-capture-plan")


def cmd_router_stage5_real_manual_dispatch_owner_gate_application(args: argparse.Namespace) -> int:
    return run_control("router-stage5-real-manual-dispatch-owner-gate-application")


def cmd_router_stage5_real_manual_dispatch_capture_records(args: argparse.Namespace) -> int:
    return run_control("router-stage5-real-manual-dispatch-capture-records")


def cmd_router_stage5_real_manual_dispatch_router_suggestions(args: argparse.Namespace) -> int:
    return run_control("router-stage5-real-manual-dispatch-router-suggestions")


def cmd_router_stage5_per_row_dispatch_confirmation_packet(args: argparse.Namespace) -> int:
    return run_control("router-stage5-per-row-dispatch-confirmation-packet")


def cmd_router_stage5_h_to_k_closure(args: argparse.Namespace) -> int:
    return run_control("router-stage5-h-to-k-closure")


def cmd_router_stage6a_restricted_auto_routing_canary_owner_gate(args: argparse.Namespace) -> int:
    return run_control("router-stage6a-restricted-auto-routing-canary-owner-gate")


def cmd_router_stage6b_restricted_auto_routing_canary_record_template(args: argparse.Namespace) -> int:
    return run_control("router-stage6b-restricted-auto-routing-canary-record-template")


def cmd_router_stage6c_limited_canary_capture_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage6c-limited-canary-capture-plan")


def cmd_router_stage5_eligibility_repair_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage5-eligibility-repair-plan")


def cmd_router_stage6_canary_candidate_capture_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage6-canary-candidate-capture-plan")


def cmd_router_stage6d_limited_canary_capture_records(args: argparse.Namespace) -> int:
    return run_control("router-stage6d-limited-canary-capture-records")


def cmd_router_stage6e_router_recommendation_for_canary_candidates(args: argparse.Namespace) -> int:
    return run_control("router-stage6e-router-recommendation-for-canary-candidates")


def cmd_router_stage6f_owner_review_for_canary_recommendations(args: argparse.Namespace) -> int:
    return run_control("router-stage6f-owner-review-for-canary-recommendations")


def cmd_router_stage6g_metric_calculation(args: argparse.Namespace) -> int:
    return run_control("router-stage6g-metric-calculation")


def cmd_router_stage6h_failure_attribution(args: argparse.Namespace) -> int:
    return run_control("router-stage6h-failure-attribution")


def cmd_router_stage6i_closure_report(args: argparse.Namespace) -> int:
    return run_control("router-stage6i-closure-report")


def cmd_router_stage7a_release_gate_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage7a-release-gate-plan")


def cmd_router_stage7b_release_readiness_checklist(args: argparse.Namespace) -> int:
    return run_control("router-stage7b-release-readiness-checklist")


def cmd_router_stage7c_rollback_plan(args: argparse.Namespace) -> int:
    return run_control("router-stage7c-rollback-plan")


def cmd_router_stage7d_dashboard_acceptance_view(args: argparse.Namespace) -> int:
    return run_control("router-stage7d-dashboard-acceptance-view")


def cmd_router_stage7e_owner_final_approval_packet(args: argparse.Namespace) -> int:
    return run_control("router-stage7e-owner-final-approval-packet")


def cmd_router_stage7f_closure_report(args: argparse.Namespace) -> int:
    return run_control("router-stage7f-closure-report")


def cmd_router_stage7_owner_decision_record(args: argparse.Namespace) -> int:
    return run_control("router-stage7-owner-decision-record")


def cmd_router_stage8_post_decision_hold_verification(args: argparse.Namespace) -> int:
    return run_control("router-stage8-post-decision-hold-verification")


def cmd_router_release_remediation_cycle(args: argparse.Namespace) -> int:
    return run_control("router-release-remediation-cycle")


def cmd_router_release_publish_approval(args: argparse.Namespace) -> int:
    return run_control("router-release-publish-approval")


def cmd_router_phase_a_real_task_trial_20(args: argparse.Namespace) -> int:
    return run_control("router-phase-a-real-task-trial-20")


def cmd_router_phase_a_owner_review_metrics(args: argparse.Namespace) -> int:
    return run_control("router-phase-a-owner-review-metrics")


def cmd_router_phase_a_remediation_plan(args: argparse.Namespace) -> int:
    return run_control("router-phase-a-remediation-plan")


def cmd_router_phase_a_remediation_owner_approval(args: argparse.Namespace) -> int:
    return run_control("router-phase-a-remediation-owner-approval")


def cmd_router_phase_a_remediation_implementation_plan(args: argparse.Namespace) -> int:
    return run_control("router-phase-a-remediation-implementation-plan")


def cmd_router_phase_a_remediation_local_patch_plan(args: argparse.Namespace) -> int:
    return run_control("router-phase-a-remediation-local-patch-plan")


def cmd_router_phase_a_remediation_local_patch_execution_owner_gate(args: argparse.Namespace) -> int:
    return run_control("router-phase-a-remediation-local-patch-execution-owner-gate")


def cmd_router_suggest(args: argparse.Namespace) -> int:
    script = CORE_DIR / "scripts" / "manual_router_suggestion_entry.py"
    return subprocess.run(
        [sys.executable, str(script), "--input", args.input],
        cwd=ROOT,
        check=False,
    ).returncode


def cmd_delegate(args: argparse.Namespace) -> int:
    return run_control("delegate", args.entry, *args.args)


def cmd_constitution(args: argparse.Namespace) -> int:
    """查询宪法层状态（只读，不可修改）。"""
    import json
    sys.path.insert(0, str(CORE_DIR))
    from constitution.validator import get_constitution_summary, verify_constitution_integrity

    if args.constitution_command == "summary":
        summary = get_constitution_summary()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    elif args.constitution_command == "verify":
        result = verify_constitution_integrity()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "OK" else 1

    elif args.constitution_command == "check":
        from constitution.validator import validate_write
        result = validate_write(args.path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["action"] == "ALLOW" else 1

    return 0
    return run_control("delegate", args.entry, *args.args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent OS Core top-level control entry")
    sub = parser.add_subparsers(dest="command", required=True)

    intake = sub.add_parser("intake", help="run the unified deterministic task intake")
    intake.add_argument("--request", required=True, help="raw user task text")
    intake.add_argument("--actions", default="", help="comma-separated planner action hints")
    intake.add_argument("--task-profile", default="general")
    intake.add_argument("--context-json", default="{}")
    intake.set_defaults(func=cmd_intake)

    status = sub.add_parser("status", help="show current Agent OS control status")
    status.set_defaults(func=cmd_status)

    workflow = sub.add_parser("workflow", help="show slimming workflow stages")
    workflow.set_defaults(func=cmd_workflow)

    dashboard = sub.add_parser("dashboard", help="rebuild runtime dashboard")
    dashboard.set_defaults(func=cmd_dashboard)

    web_research_intake = sub.add_parser(
        "web-research-intake-readonly",
        help="build read-only web research intake evidence without network fetches",
    )
    web_research_intake.set_defaults(func=cmd_web_research_intake)

    source_trust = sub.add_parser(
        "source-trust-score",
        help="score research sources without fetching or writing back",
    )
    source_trust.set_defaults(func=cmd_source_trust_score)

    online_evidence = sub.add_parser(
        "router-online-evidence-test",
        help="test Router online evidence boundaries without fetching or executing",
    )
    online_evidence.set_defaults(func=cmd_router_online_evidence_test)

    router_suggest = sub.add_parser(
        "router-suggest",
        help="return a local recommendation-only Router suggestion",
    )
    router_suggest.add_argument(
        "--input",
        required=True,
        help="JSON file containing a non-sensitive task summary and boundary fields",
    )
    router_suggest.set_defaults(func=cmd_router_suggest)

    closure = sub.add_parser("closure-report", help="build final slimming closure report")
    closure.set_defaults(func=cmd_closure_report)

    health = sub.add_parser("health", help="build read-only Runtime Health Baseline")
    health.set_defaults(func=cmd_health)

    router = sub.add_parser("route-health", help="build read-only Router Quality Baseline")
    router.set_defaults(func=cmd_router_quality)

    route_sim = sub.add_parser("route-sim-plan", help="build plan-only Router Simulation packet")
    route_sim.set_defaults(func=cmd_router_simulation)

    route_shadow = sub.add_parser("route-shadow-recommend", help="build Router Shadow Recommend plan")
    route_shadow.set_defaults(func=cmd_router_shadow_recommend)

    route_shadow_template = sub.add_parser(
        "route-shadow-records-template",
        help="build empty Router Shadow Recommend record template",
    )
    route_shadow_template.set_defaults(func=cmd_router_shadow_records_template)

    route_shadow_dry_collection = sub.add_parser(
        "route-shadow-dry-collection-plan",
        help="build Router Shadow Recommend dry collection plan",
    )
    route_shadow_dry_collection.set_defaults(func=cmd_router_shadow_dry_collection_plan)

    route_shadow_manual_fill = sub.add_parser(
        "route-shadow-manual-sample-fill",
        help="build simulated shadow records from historical samples",
    )
    route_shadow_manual_fill.set_defaults(func=cmd_router_shadow_manual_sample_fill)

    route_shadow_owner_review = sub.add_parser(
        "route-shadow-owner-review-packet",
        help="build owner-review packet for simulated shadow records",
    )
    route_shadow_owner_review.set_defaults(func=cmd_router_shadow_owner_review_packet)

    route_shadow_owner_application = sub.add_parser(
        "route-shadow-owner-application-plan",
        help="build plan for applying future owner review results",
    )
    route_shadow_owner_application.set_defaults(func=cmd_router_shadow_owner_application_plan)

    route_stage1_closure = sub.add_parser(
        "route-turnup-stage1-closure",
        help="build Router turn-up Stage 1 closure report",
    )
    route_stage1_closure.set_defaults(func=cmd_router_turnup_stage1_closure)

    route_stage2_owner_gate = sub.add_parser(
        "route-stage2-owner-gate",
        help="build Router Stage 2A owner gate packet",
    )
    route_stage2_owner_gate.set_defaults(func=cmd_router_stage2_owner_gate)

    route_stage2_template = sub.add_parser(
        "route-stage2-real-shadow-run-template",
        help="build Router Stage 2B real shadow run template",
    )
    route_stage2_template.set_defaults(func=cmd_router_stage2_real_shadow_run_template)

    route_stage2_capture = sub.add_parser(
        "route-stage2-real-shadow-capture",
        help="capture limited real task summaries for Stage 2",
    )
    route_stage2_capture.set_defaults(func=cmd_router_stage2_real_shadow_capture)

    route_stage2_recommend = sub.add_parser(
        "route-stage2-real-shadow-recommend",
        help="write local shadow Router recommendations for Stage 2D",
    )
    route_stage2_recommend.set_defaults(func=cmd_router_stage2_real_shadow_recommend)

    route_stage2_owner_review = sub.add_parser(
        "route-stage2-owner-review-application",
        help="prepare owner review application records for Stage 2E",
    )
    route_stage2_owner_review.set_defaults(func=cmd_router_stage2_owner_review_application)

    route_stage2_metrics = sub.add_parser(
        "route-stage2-metric-calculation",
        help="calculate Router Stage 2F metrics and failure attribution",
    )
    route_stage2_metrics.set_defaults(func=cmd_router_stage2_metric_calculation)

    route_stage2_failure = sub.add_parser(
        "route-stage2-failure-attribution",
        help="build detailed Router Stage 2G failure attribution",
    )
    route_stage2_failure.set_defaults(func=cmd_router_stage2_failure_attribution)

    route_stage2_closure = sub.add_parser(
        "route-stage2-closure-report",
        help="build Router Stage 2H closure report",
    )
    route_stage2_closure.set_defaults(func=cmd_router_stage2_closure_report)

    route_stage3_plan = sub.add_parser(
        "route-stage3-manual-dispatch-plan",
        help="build Router Stage 3A manual dispatch plan only",
    )
    route_stage3_plan.set_defaults(func=cmd_router_stage3_manual_dispatch_plan)

    route_stage3_template = sub.add_parser(
        "route-stage3-manual-dispatch-record-template",
        help="build Router Stage 3B manual dispatch record template",
    )
    route_stage3_template.set_defaults(func=cmd_router_stage3_manual_dispatch_record_template)

    route_stage3_dry_fill = sub.add_parser(
        "route-stage3-manual-dispatch-dry-fill-plan",
        help="build Router Stage 3C manual dispatch dry-fill plan only",
    )
    route_stage3_dry_fill.set_defaults(func=cmd_router_stage3_manual_dispatch_dry_fill_plan)

    route_stage3_dry_records = sub.add_parser(
        "route-stage3-manual-dispatch-dry-fill-records",
        help="write Router Stage 3D dry-filled records only",
    )
    route_stage3_dry_records.set_defaults(func=cmd_router_stage3_manual_dispatch_dry_fill_records)

    route_stage3_owner_review = sub.add_parser(
        "route-stage3-manual-dispatch-owner-review",
        help="build Router Stage 3E owner review packet only",
    )
    route_stage3_owner_review.set_defaults(func=cmd_router_stage3_manual_dispatch_owner_review)

    route_stage3_metrics = sub.add_parser(
        "route-stage3-manual-dispatch-metric-calculation",
        help="calculate Router Stage 3F dry-fill metrics only",
    )
    route_stage3_metrics.set_defaults(func=cmd_router_stage3_manual_dispatch_metric_calculation)

    route_stage3_collection = sub.add_parser(
        "route-stage3-manual-dispatch-owner-decision-collection-plan",
        help="build Router Stage 3G owner decision collection plan only",
    )
    route_stage3_collection.set_defaults(func=cmd_router_stage3_manual_dispatch_owner_decision_collection_plan)

    route_stage3_application = sub.add_parser(
        "route-stage3-manual-dispatch-owner-decision-application-plan",
        help="build Router Stage 3H owner decision application validation plan only",
    )
    route_stage3_application.set_defaults(func=cmd_router_stage3_manual_dispatch_owner_decision_application_plan)

    route_stage3_filled_sample = sub.add_parser(
        "route-stage3-manual-dispatch-owner-decision-filled-sample-plan",
        help="build Router Stage 3I simulated owner-filled sample plan only",
    )
    route_stage3_filled_sample.set_defaults(func=cmd_router_stage3_manual_dispatch_owner_decision_filled_sample_plan)

    route_stage3_filled_sample_metrics = sub.add_parser(
        "route-stage3-manual-dispatch-owner-decision-filled-sample-metrics",
        help="calculate Router Stage 3J sample-only owner-filled metrics",
    )
    route_stage3_filled_sample_metrics.set_defaults(func=cmd_router_stage3_manual_dispatch_owner_decision_filled_sample_metrics)

    route_stage3_closure = sub.add_parser(
        "route-stage3-manual-dispatch-closure-report",
        help="build Router Stage 3K manual dispatch closure report",
    )
    route_stage3_closure.set_defaults(func=cmd_router_stage3_manual_dispatch_closure_report)

    route_stage4_pilot = sub.add_parser(
        "route-stage4-manual-dispatch-pilot-plan",
        help="build Router Stage 4A manual dispatch pilot plan only",
    )
    route_stage4_pilot.set_defaults(func=cmd_router_stage4_manual_dispatch_pilot_plan)

    route_stage4_pilot_template = sub.add_parser(
        "route-stage4-manual-dispatch-pilot-record-template",
        help="build Router Stage 4B manual dispatch pilot record template",
    )
    route_stage4_pilot_template.set_defaults(func=cmd_router_stage4_manual_dispatch_pilot_record_template)

    route_stage4_pilot_dry_fill = sub.add_parser(
        "route-stage4-manual-dispatch-pilot-dry-fill-plan",
        help="build Router Stage 4C manual dispatch pilot dry-fill plan only",
    )
    route_stage4_pilot_dry_fill.set_defaults(func=cmd_router_stage4_manual_dispatch_pilot_dry_fill_plan)

    route_stage4_pilot_dry_fill_records = sub.add_parser(
        "route-stage4-manual-dispatch-pilot-dry-fill-records",
        help="write Router Stage 4D manual dispatch pilot dry-filled records only",
    )
    route_stage4_pilot_dry_fill_records.set_defaults(func=cmd_router_stage4_manual_dispatch_pilot_dry_fill_records)

    route_stage4_pilot_owner_review = sub.add_parser(
        "route-stage4-manual-dispatch-pilot-owner-review",
        help="build Router Stage 4E manual dispatch pilot owner review packet only",
    )
    route_stage4_pilot_owner_review.set_defaults(func=cmd_router_stage4_manual_dispatch_pilot_owner_review)

    route_stage4_pilot_metric = sub.add_parser(
        "route-stage4-manual-dispatch-pilot-metric-calculation",
        help="build Router Stage 4F manual dispatch pilot metric calculation only",
    )
    route_stage4_pilot_metric.set_defaults(func=cmd_router_stage4_manual_dispatch_pilot_metric_calculation)

    route_stage4_pilot_owner_collection = sub.add_parser(
        "route-stage4-manual-dispatch-pilot-owner-decision-collection-plan",
        help="build Router Stage 4G manual dispatch pilot owner decision collection plan only",
    )
    route_stage4_pilot_owner_collection.set_defaults(func=cmd_router_stage4_manual_dispatch_pilot_owner_decision_collection_plan)

    route_stage4_pilot_owner_application = sub.add_parser(
        "route-stage4-manual-dispatch-pilot-owner-decision-application-plan",
        help="build Router Stage 4H manual dispatch pilot owner decision application plan only",
    )
    route_stage4_pilot_owner_application.set_defaults(func=cmd_router_stage4_manual_dispatch_pilot_owner_decision_application_plan)

    route_stage4_pilot_owner_filled_sample = sub.add_parser(
        "route-stage4-manual-dispatch-pilot-owner-decision-filled-sample-plan",
        help="build Router Stage 4I manual dispatch pilot owner decision filled sample plan only",
    )
    route_stage4_pilot_owner_filled_sample.set_defaults(func=cmd_router_stage4_manual_dispatch_pilot_owner_decision_filled_sample_plan)

    route_stage4_pilot_owner_filled_sample_metrics = sub.add_parser(
        "route-stage4-manual-dispatch-pilot-owner-decision-filled-sample-metrics",
        help="build Router Stage 4J manual dispatch pilot owner decision filled sample metrics only",
    )
    route_stage4_pilot_owner_filled_sample_metrics.set_defaults(
        func=cmd_router_stage4_manual_dispatch_pilot_owner_decision_filled_sample_metrics
    )

    route_stage4_pilot_closure = sub.add_parser(
        "route-stage4-manual-dispatch-pilot-closure-report",
        help="build Router Stage 4K manual dispatch pilot closure report only",
    )
    route_stage4_pilot_closure.set_defaults(func=cmd_router_stage4_manual_dispatch_pilot_closure_report)

    route_stage5_owner_gate = sub.add_parser(
        "route-stage5-real-manual-dispatch-owner-gate-packet",
        help="build Router Stage 5A real manual dispatch owner gate packet only",
    )
    route_stage5_owner_gate.set_defaults(func=cmd_router_stage5_real_manual_dispatch_owner_gate_packet)

    route_stage5_template = sub.add_parser(
        "route-stage5-real-manual-dispatch-record-template",
        help="build Router Stage 5B real manual dispatch record template",
    )
    route_stage5_template.set_defaults(func=cmd_router_stage5_real_manual_dispatch_record_template)

    route_stage5_capture_plan = sub.add_parser(
        "route-stage5-real-manual-dispatch-capture-plan",
        help="build Router Stage 5C real manual dispatch capture plan only",
    )
    route_stage5_capture_plan.set_defaults(func=cmd_router_stage5_real_manual_dispatch_capture_plan)

    route_stage5_owner_gate_application = sub.add_parser(
        "route-stage5-real-manual-dispatch-owner-gate-application",
        help="build Router Stage 5D owner gate application evidence",
    )
    route_stage5_owner_gate_application.set_defaults(func=cmd_router_stage5_real_manual_dispatch_owner_gate_application)

    route_stage5_capture_records = sub.add_parser(
        "route-stage5-real-manual-dispatch-capture-records",
        help="write Router Stage 5E limited real manual dispatch capture records",
    )
    route_stage5_capture_records.set_defaults(func=cmd_router_stage5_real_manual_dispatch_capture_records)

    route_stage5_router_suggestions = sub.add_parser(
        "route-stage5-real-manual-dispatch-router-suggestions",
        help="write Router Stage 5F local suggestions for captured records",
    )
    route_stage5_router_suggestions.set_defaults(func=cmd_router_stage5_real_manual_dispatch_router_suggestions)

    route_stage5_confirmation_packet = sub.add_parser(
        "route-stage5-per-row-dispatch-confirmation-packet",
        help="build Router Stage 5G per-row human dispatch confirmation packet",
    )
    route_stage5_confirmation_packet.set_defaults(func=cmd_router_stage5_per_row_dispatch_confirmation_packet)

    route_stage5_closure = sub.add_parser(
        "route-stage5-h-to-k-closure",
        help="build Router Stage 5H-5K closure without execution",
    )
    route_stage5_closure.set_defaults(func=cmd_router_stage5_h_to_k_closure)

    route_stage6a = sub.add_parser(
        "route-stage6a-restricted-auto-routing-canary-owner-gate",
        help="build Router Stage 6A restricted auto-routing Canary owner gate packet only",
    )
    route_stage6a.set_defaults(func=cmd_router_stage6a_restricted_auto_routing_canary_owner_gate)

    route_stage6b = sub.add_parser(
        "route-stage6b-restricted-auto-routing-canary-record-template",
        help="build Router Stage 6B restricted Canary record template only",
    )
    route_stage6b.set_defaults(func=cmd_router_stage6b_restricted_auto_routing_canary_record_template)

    route_stage6c = sub.add_parser(
        "route-stage6c-limited-canary-capture-plan",
        help="build Router Stage 6C limited Canary capture plan only",
    )
    route_stage6c.set_defaults(func=cmd_router_stage6c_limited_canary_capture_plan)

    route_stage5_repair = sub.add_parser(
        "route-stage5-eligibility-repair-plan",
        help="build Stage 5 eligibility repair plan only",
    )
    route_stage5_repair.set_defaults(func=cmd_router_stage5_eligibility_repair_plan)

    route_stage6_cand = sub.add_parser(
        "route-stage6-canary-candidate-capture-plan",
        help="build Stage 6 Canary candidate capture plan only",
    )
    route_stage6_cand.set_defaults(func=cmd_router_stage6_canary_candidate_capture_plan)

    route_stage6d = sub.add_parser(
        "route-stage6d-limited-canary-capture-records",
        help="build Router Stage 6D limited Canary capture records only",
    )
    route_stage6d.set_defaults(func=cmd_router_stage6d_limited_canary_capture_records)

    route_stage6e = sub.add_parser(
        "route-stage6e-router-recommendation-for-canary-candidates",
        help="build Router Stage 6E recommendation-only output for Canary candidates",
    )
    route_stage6e.set_defaults(func=cmd_router_stage6e_router_recommendation_for_canary_candidates)

    route_stage6f = sub.add_parser(
        "route-stage6f-owner-review-for-canary-recommendations",
        help="build Router Stage 6F owner review recommendations without runtime application",
    )
    route_stage6f.set_defaults(func=cmd_router_stage6f_owner_review_for_canary_recommendations)

    route_stage6g = sub.add_parser(
        "route-stage6g-metric-calculation",
        help="build Router Stage 6G metrics from 6F review rows without runtime application",
    )
    route_stage6g.set_defaults(func=cmd_router_stage6g_metric_calculation)

    route_stage6h = sub.add_parser(
        "route-stage6h-failure-attribution",
        help="build Router Stage 6H failure attribution without runtime application",
    )
    route_stage6h.set_defaults(func=cmd_router_stage6h_failure_attribution)

    route_stage6i = sub.add_parser(
        "route-stage6i-closure-report",
        help="build Router Stage 6I closure report without runtime application",
    )
    route_stage6i.set_defaults(func=cmd_router_stage6i_closure_report)

    route_stage7a = sub.add_parser(
        "route-stage7a-release-gate-plan",
        help="build Router Stage 7A release gate plan without release or runtime application",
    )
    route_stage7a.set_defaults(func=cmd_router_stage7a_release_gate_plan)

    route_stage7b = sub.add_parser(
        "route-stage7b-release-readiness-checklist",
        help="build Router Stage 7B release readiness checklist without release or runtime application",
    )
    route_stage7b.set_defaults(func=cmd_router_stage7b_release_readiness_checklist)

    route_stage7c = sub.add_parser(
        "route-stage7c-rollback-plan",
        help="build Router Stage 7C rollback plan without executing rollback or runtime changes",
    )
    route_stage7c.set_defaults(func=cmd_router_stage7c_rollback_plan)

    route_stage7d = sub.add_parser(
        "route-stage7d-dashboard-acceptance-view",
        help="build Router Stage 7D dashboard acceptance view without release or runtime changes",
    )
    route_stage7d.set_defaults(func=cmd_router_stage7d_dashboard_acceptance_view)

    route_stage7e = sub.add_parser(
        "route-stage7e-owner-final-approval-packet",
        help="build Router Stage 7E owner final approval packet without release or runtime changes",
    )
    route_stage7e.set_defaults(func=cmd_router_stage7e_owner_final_approval_packet)

    route_stage7f = sub.add_parser(
        "route-stage7f-closure-report",
        help="build Router Stage 7F closure report without release or runtime changes",
    )
    route_stage7f.set_defaults(func=cmd_router_stage7f_closure_report)

    route_stage7_decision = sub.add_parser(
        "route-stage7-owner-decision-record",
        help="record owner Stage 7 decisions without applying runtime changes",
    )
    route_stage7_decision.set_defaults(func=cmd_router_stage7_owner_decision_record)

    route_stage8 = sub.add_parser(
        "route-stage8-post-decision-hold-verification",
        help="verify post-decision hold/manual-only state without runtime changes",
    )
    route_stage8.set_defaults(func=cmd_router_stage8_post_decision_hold_verification)

    route_remediation = sub.add_parser(
        "route-release-remediation-cycle",
        help="build Router release remediation evidence without release or runtime changes",
    )
    route_remediation.set_defaults(func=cmd_router_release_remediation_cycle)

    route_publish = sub.add_parser(
        "route-release-publish-approval",
        help="record owner approval to publish remediated Router release without runtime writeback",
    )
    route_publish.set_defaults(func=cmd_router_release_publish_approval)

    route_phase_a = sub.add_parser(
        "route-phase-a-real-task-trial-20",
        help="build Phase A real-task Router trial with 20 non-sensitive task summaries",
    )
    route_phase_a.set_defaults(func=cmd_router_phase_a_real_task_trial_20)

    route_phase_a_metrics = sub.add_parser(
        "route-phase-a-owner-review-metrics",
        help="apply Phase A owner labels and calculate Router metrics without runtime actions",
    )
    route_phase_a_metrics.set_defaults(func=cmd_router_phase_a_owner_review_metrics)

    route_phase_a_remediation = sub.add_parser(
        "route-phase-a-remediation-plan",
        help="build Phase A remediation plan only without scoring or runtime changes",
    )
    route_phase_a_remediation.set_defaults(func=cmd_router_phase_a_remediation_plan)

    route_phase_a_remediation_approval = sub.add_parser(
        "route-phase-a-remediation-owner-approval",
        help="build Phase A remediation owner approval packet without implementing changes",
    )
    route_phase_a_remediation_approval.set_defaults(func=cmd_router_phase_a_remediation_owner_approval)

    route_phase_a_remediation_impl = sub.add_parser(
        "route-phase-a-remediation-implementation-plan",
        help="build Phase A remediation implementation, regression, and rollback plan without applying changes",
    )
    route_phase_a_remediation_impl.set_defaults(func=cmd_router_phase_a_remediation_implementation_plan)

    route_phase_a_remediation_patch_plan = sub.add_parser(
        "route-phase-a-remediation-local-patch-plan",
        help="build Phase A remediation local patch plan without editing Router scoring",
    )
    route_phase_a_remediation_patch_plan.set_defaults(func=cmd_router_phase_a_remediation_local_patch_plan)

    route_phase_a_remediation_patch_gate = sub.add_parser(
        "route-phase-a-remediation-local-patch-execution-owner-gate",
        help="build owner gate packet for Phase A local patch execution without applying patches",
    )
    route_phase_a_remediation_patch_gate.set_defaults(func=cmd_router_phase_a_remediation_local_patch_execution_owner_gate)

    legacy = sub.add_parser("legacy-usage", help="summarize legacy entrypoint touches")
    legacy.set_defaults(func=cmd_legacy_usage)

    retirement = sub.add_parser("retirement", help="rebuild retirement candidates")
    retirement.set_defaults(func=cmd_retirement)

    approval = sub.add_parser("approval-packet", help="rebuild owner approval packet")
    approval.set_defaults(func=cmd_approval_packet)

    archive = sub.add_parser("archive", help="archive planning and status")
    archive_sub = archive.add_subparsers(dest="archive_command", required=True)
    archive_plan = archive_sub.add_parser("plan", help="build archive execution plan only")
    archive_plan.set_defaults(func=cmd_archive_plan)
    archive_status = archive_sub.add_parser("copy-status", help="show last owner-approved archive copy result")
    archive_status.set_defaults(func=cmd_archive_status)

    reference = sub.add_parser("reference", help="runtime reference scan")
    reference_sub = reference.add_subparsers(dest="reference_command", required=True)
    reference_scan = reference_sub.add_parser("scan", help="scan old entrypoint references without rewriting")
    reference_scan.set_defaults(func=cmd_reference_scan)
    reference_candidates = reference_sub.add_parser("candidates", help="show reference scan summary")
    reference_candidates.set_defaults(func=cmd_reference_candidates)
    reference_approval = reference_sub.add_parser("approval-packet", help="group reference migration candidates for owner review")
    reference_approval.set_defaults(func=cmd_reference_approval_packet)
    reference_rewrite = reference_sub.add_parser("rewrite-plan", help="build REF-004 rewrite plan only")
    reference_rewrite.set_defaults(func=cmd_reference_rewrite_plan)
    reference_post_rescan = reference_sub.add_parser("post-rescan", help="summarize post-rewrite reference scan")
    reference_post_rescan.set_defaults(func=cmd_reference_post_rescan)
    reference_disposition = reference_sub.add_parser(
        "disposition-packet",
        help="build remaining REF-001/002/005 disposition packet without rewriting",
    )
    reference_disposition.set_defaults(func=cmd_reference_disposition_packet)
    reference_execution = reference_sub.add_parser(
        "execution-plan",
        help="build no-action execution plan for remaining REF-002/005 references",
    )
    reference_execution.set_defaults(func=cmd_reference_execution_plan)
    reference_ref002_plan = reference_sub.add_parser(
        "ref002-plan",
        help="build REF-002 legacy shim self-doc plan only",
    )
    reference_ref002_plan.set_defaults(func=cmd_reference_ref002_plan)

    delegate = sub.add_parser("delegate", help="delegate to an existing unified capability CLI")
    delegate.add_argument("entry", choices=["model-adapter", "owner-review", "smoke"])
    delegate.add_argument("args", nargs=argparse.REMAINDER)
    delegate.set_defaults(func=cmd_delegate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
