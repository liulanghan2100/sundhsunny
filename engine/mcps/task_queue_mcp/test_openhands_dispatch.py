import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
OPENHANDS_ROOT = REPO_ROOT / "external_execution" / "openhands"
if str(OPENHANDS_ROOT) not in sys.path:
    sys.path.insert(0, str(OPENHANDS_ROOT))
MCP_ROOT = REPO_ROOT / "03_分工MCP"
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from external_execution.openhands.bridge import worker as openhands_worker
from external_execution.openhands.bridge.control_plane import WORKSPACES
from external_execution.openhands.tests.test_task_card_adapter import sample_task_card
from task_queue_mcp import common


class TaskQueueOpenHandsDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.queue_root = root / "queue"
        self.runtime_root = root / "runtime"
        self.execution_root = self.queue_root / "execution_evidence"
        self.task_cards = self.runtime_root / "task_cards"
        self.run_states = self.runtime_root / "runs"
        self.workspace = WORKSPACES / "task_queue_bridge_test"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.patches = [
            patch.object(common, "QUEUE_ROOT", self.queue_root),
            patch.object(common, "QUEUE_DB", self.queue_root / "task_queue.sqlite"),
            patch.object(common, "EXECUTION_DIR", self.execution_root),
            patch.object(common, "RUNTIME_ROOT", self.runtime_root),
            patch.object(common, "TASK_CARD_DIR", self.task_cards),
            patch.object(common, "RUN_STATE_DIR", self.run_states),
            patch.object(common, "_refresh_dashboard", return_value={"status": "refreshed"}),
            patch.object(common, "_observe_self_task_result"),
            patch.object(
                common,
                "_mandatory_cycle",
                return_value={"status": "completed", "state_path": "synthetic-state.json"},
            ),
            patch.object(
                common,
                "_verify_completion",
                return_value={"passed": True, "checks": []},
            ),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        if self.workspace.exists():
            import shutil

            shutil.rmtree(self.workspace)
        self.temp.cleanup()

    def _task(self) -> dict:
        card = sample_task_card()
        card["task_id"] = "task-queue-bridge-001"
        card["project"] = "synthetic-queue-bridge"
        card["objective"] = "验证 Task Queue 到 OpenHands Worker 的受控调度"
        card["expected_artifacts"] = [
            {
                "artifact_id": "bridge-result",
                "path": "validation/report.json",
                "artifact_type": "json",
                "required": True,
            }
        ]
        return {
            "id": "queue-bridge-001",
            "project": "synthetic-queue-bridge",
            "task": "run bounded OpenHands worker",
            "status": "running",
            "priority": 1,
            "risk": "low",
            "track": "quick",
            "autonomy": "L2",
            "operation": "local_read",
            "attempts": 0,
            "max_attempts": 1,
            "created": "2026-09-11T12:00:00+08:00",
            "context": {
                "task_class": "B",
                "execution_backend": "openhands",
                "openhands_workspace": str(self.workspace),
                "task_card": card,
            },
            "result": {},
        }

    def test_queue_dispatches_openhands_and_persists_unified_records(self) -> None:
        worker_log = self.execution_root / "worker.log"

        def fake_worker(task_card: dict, *, target_workspace: str) -> dict:
            return {
                "status": "completed",
                "execution_task": {"task_id": task_card["task_id"]},
                "run_state": {
                    "run_id": f"openhands-{task_card['task_id']}",
                    "task_id": task_card["task_id"],
                    "status": "completed",
                },
                "evidence_record": {
                    "evidence_id": f"evidence-{task_card['task_id']}",
                    "task_id": task_card["task_id"],
                    "record_type": "trace",
                    "source": "openhands_worker",
                    "artifact_path": str(worker_log),
                    "artifact_hash": "0" * 64,
                    "created_at": "2026-09-11T12:01:00+08:00",
                    "validation_status": "pass",
                    "artifacts": [],
                    "logs": [str(worker_log)],
                },
                "raw_run": {"status": "completed"},
            }

        with patch.object(openhands_worker, "execute_task_card", side_effect=fake_worker):
            result = common._run_task(self._task())

        self.assertEqual(result["status"], "completed")
        stored = result["task"]["result"]
        execution = stored["execution"]
        self.assertEqual(execution["status"], "completed")
        self.assertEqual(
            execution["evidence_record"]["source"],
            "openhands_worker",
        )
        self.assertTrue(stored["completion_verifier"]["passed"])

        run_states = list(self.run_states.glob("*.json"))
        self.assertEqual(len(run_states), 1)
        run_state = json.loads(run_states[0].read_text(encoding="utf-8"))
        self.assertEqual(run_state["openhands_run_state"]["status"], "completed")
        self.assertEqual(run_state["evidence_record"]["task_id"], "task-queue-bridge-001")

        evidence_dir = self.execution_root / "synthetic-queue-bridge" / "queue-bridge-001"
        evidence = json.loads((evidence_dir / "evidence_record.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["artifact_path"], str(evidence_dir / "openhands_worker_result.json"))
        self.assertEqual(len(evidence["artifact_hash"]), 64)

    def test_failed_or_unverified_result_does_not_write_memory(self) -> None:
        task = self._task()
        with patch.object(
            common,
            "_execute_openhands_worker",
            return_value={"status": "failed", "error": "synthetic failure"},
        ), patch.object(
            common,
            "_verify_completion",
            return_value={"passed": False, "checks": []},
        ), patch.object(common, "_memory_append") as memory_append:
            result = common._run_task(task)

        self.assertEqual(result["status"], "failed")
        memory_append.assert_not_called()


if __name__ == "__main__":
    unittest.main()
