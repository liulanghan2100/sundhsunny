import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
MCP_ROOT = ROOT / "03_分工MCP"
AUTOROBOT_BRIDGE = ROOT / "AutoRobot" / "13_mcp_bridge"
for path in (ROOT, MCP_ROOT, AUTOROBOT_BRIDGE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from Agent_OS_Core.schemas import validate_task_card
import agent_os_task_planner as planner
from task_queue_mcp import common


class UnifiedEntrypointTests(unittest.TestCase):
    def test_agent_os_cli_intake_is_machine_readable(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(ROOT / "Agent_OS_Core" / "agent_os.py"),
                "intake",
                "--request",
                "删除临时文件并生成验证报告",
                "--actions",
                "read",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["risk"]["risk_level"], "L3")
        self.assertIn("delete", payload["risk"]["actions"]["effective_actions"])

    def test_autorobot_draft_records_agent_os_intake(self) -> None:
        card = planner.build_task_card_draft(
            "删除临时文件并生成验证报告",
            context={"project": "unified-entrypoint-test", "requested_actions": ["read"]},
            task_id="unified-entrypoint-draft-001",
        )
        self.assertTrue(validate_task_card(card).valid)
        self.assertEqual(card["intake"]["task_profile"], card["task_profile"])
        self.assertEqual(card["risk_tier"], "L3")
        self.assertIn("delete", card["intake"]["effective_actions"])

    def test_only_approved_task_card_can_enter_canonical_queue(self) -> None:
        card = planner.build_task_card_draft(
            "验证统一入口",
            context={"project": "unified-entrypoint-test"},
            task_id="unified-entrypoint-queue-001",
        )
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        patches = [
            patch.object(common, "QUEUE_ROOT", root / "queue"),
            patch.object(common, "QUEUE_DB", root / "queue" / "tasks.sqlite"),
            patch.object(common, "RUNTIME_ROOT", root / "runtime"),
            patch.object(common, "TASK_CARD_DIR", root / "runtime" / "task_cards"),
            patch.object(common, "RUN_STATE_DIR", root / "runtime" / "runs"),
        ]
        for item in patches:
            item.start()
        try:
            server = common.build_server()
            tools = {
                item.name: item.fn
                for item in server._tool_manager.list_tools()
                if item.name in {"enqueue_task", "approved_task_card_enqueue"}
            }

            blocked = json.loads(tools["enqueue_task"]("demo", "direct queue attempt"))
            self.assertEqual(blocked["status"], "blocked")
            self.assertTrue(blocked["no_task_created"])

            unapproved = json.loads(
                tools["approved_task_card_enqueue"](json.dumps(card, ensure_ascii=False))
            )
            self.assertEqual(unapproved["status"], "blocked")
            self.assertTrue(unapproved["no_task_created"])
            api_unapproved = common.approved_task_card_enqueue(card)
            self.assertEqual(api_unapproved["status"], "blocked")

            approved = copy.deepcopy(card)
            approved["status"] = "approved"
            approved["policy_decision"]["decision"] = "allow"
            for item in approved["policy_decision"]["filtered_candidates"]:
                item["decision"] = "allow"
            approved["approval"] = {
                "decision": "approve",
                "decision_id": "DEC-UNIFIED-001",
                "decided_by": "owner",
                "decided_at": "2026-09-11T14:00:00+08:00",
            }
            approved["execution_contract"]["execution_mode"] = "validation"
            admitted = json.loads(
                tools["approved_task_card_enqueue"](
                    json.dumps(approved, ensure_ascii=False),
                    openhands_workspace=str(root / "workspace"),
                )
            )
            self.assertEqual(admitted["status"], "queued")
            self.assertEqual(admitted["admission"], "approved_task_card_enqueue")
            self.assertTrue(Path(admitted["run_state_path"]).exists())
            self.assertTrue(Path(admitted["task_card_path"]).exists())
        finally:
            for item in reversed(patches):
                item.stop()
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
