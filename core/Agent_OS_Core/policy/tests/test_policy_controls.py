import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from Agent_OS_Core.governance.owner_gate import build_decision_record, validate_decision_for_task
from Agent_OS_Core.policy.action_pre_scan import scan_requested_actions
from Agent_OS_Core.policy.cost_budget_guard import CostBudgetExceeded, CostBudgetGuard
from Agent_OS_Core.policy.depth_policy import depth_policy
from Agent_OS_Core.policy.resource_lock_manager import ResourceBusyError, ResourceLockManager
from Agent_OS_Core.policy.risk_classifier import classify_risk
from Agent_OS_Core.policy.unified_intake import build_intake
from Agent_OS_Core.constitution.validator import validate_action


class PolicyControlTests(unittest.TestCase):
    def test_action_scan_catches_llm_omission(self):
        result = scan_requested_actions("请删除临时文件", llm_actions=["read"])
        self.assertIn("delete", result.effective_actions)
        self.assertIn("delete", result.disagreements)

    def test_risk_takes_highest_action(self):
        self.assertEqual(classify_risk("生成报告并调用真实 provider")["risk_level"], "L3")
        self.assertEqual(classify_risk("修改本地文件")["risk_level"], "L2")
        self.assertEqual(classify_risk("只读检查")["risk_level"], "L1")

    def test_depth_policy_requires_gate_for_l3(self):
        self.assertTrue(depth_policy("L3")["owner_gate"])
        self.assertFalse(depth_policy("L1")["owner_gate"])

    def test_resource_write_conflict_is_blocked(self):
        locks = ResourceLockManager()
        locks.acquire("one", [{"path": "workspace/a.py", "access": "write"}])
        with self.assertRaises(ResourceBusyError):
            locks.acquire("two", [{"path": "workspace/a.py", "access": "read"}])

    def test_cost_budget_is_hard(self):
        budget = CostBudgetGuard(0.1)
        budget.reserve(0.1)
        with self.assertRaises(CostBudgetExceeded):
            budget.reserve(0.01)

    def test_owner_gate_expiry_blocks(self):
        card = {"task_id": "task-owner-001", "objective": "test"}
        record = build_decision_record(
            card,
            decision="approve",
            decided_by="owner",
            decision_id="DEC-001",
            expires_at="2020-01-01T00:00:00+00:00",
        )
        card["approval"] = record
        self.assertEqual(validate_decision_for_task(card)["status"], "expired")

    def test_l1_l2_l3_intake_regression(self):
        cases = (
            ("只读查看本地报告", "L1", False),
            ("修改本地报告", "L2", True),
            ("删除文件并发布", "L3", True),
        )
        for request, expected_level, expected_gate in cases:
            with self.subTest(request=request):
                result = build_intake(request, context={"cost_budget_usd": 0})
                self.assertEqual(result["risk"]["risk_level"], expected_level)
                self.assertEqual(result["depth"]["owner_gate"], expected_gate)

    def test_runtime_action_guard_blocks_undeclared_action(self):
        result = validate_action(
            {"validation_context": True, "production_context": False},
            {"decision": "approve", "decision_id": "DEC-001"},
            "delete",
            allowed_actions=("read",),
            blocked_actions=("delete",),
            remaining_budget_usd=0,
        )
        self.assertEqual(result["action"], "BLOCK")
        self.assertEqual(result["violation_type"], "forbidden_action")


if __name__ == "__main__":
    unittest.main()
