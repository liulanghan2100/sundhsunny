import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
MCP_ROOT = ROOT / "03_分工MCP"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from task_queue_mcp import common
class QueueAdmissionTests(unittest.TestCase):
    def test_plain_string_admission_is_blocked(self):
        with patch.object(common, "_save_task") as save_task:
            server = common.build_server()
            tool = next(item for item in server._tool_manager.list_tools() if item.name == "enqueue_task")
            result = json.loads(tool.fn("demo", "read-only task"))
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["no_task_created"])
        save_task.assert_not_called()


if __name__ == "__main__":
    unittest.main()
