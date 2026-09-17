import json
import tempfile
import unittest
from pathlib import Path

from common import (
    _component_changes,
    _runner_route,
    _template_catalog,
    _validation_errors,
    build_server,
)


class TiaTemplateCompilerTests(unittest.TestCase):
    def test_project_spec_validation(self):
        self.assertTrue(_validation_errors({"project_name": "P", "tia_version": "V21"}) == [])
        errors = _validation_errors({"project_name": "", "tia_version": "V20", "servos": "bad"})
        self.assertGreaterEqual(len(errors), 3)

    def test_static_catalog_detects_ap21_and_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Demo.ap21").write_text("project", encoding="utf-8")
            (root / "ProjectInfo.txt").write_text(
                "TechnicalVersion: 21.00.00.00\n- Name: test.gsdml\n",
                encoding="utf-8",
            )
            (root / "YWW").mkdir()
            (root / "YWW" / "IO.xlsm").write_bytes(b"fake")
            catalog = _template_catalog(root)
            self.assertEqual(catalog["inventory"]["ap21_count"], 1)
            self.assertEqual(catalog["project_info"]["tia_version"], "21.00.00.00")
            self.assertEqual(len(catalog["inventory"]["engineering_documents"]), 1)

    def test_business_component_is_closure_not_single_file(self):
        catalog = {"anchors": {
            "component_container": "FB_Component",
            "valve_container": "FB_ValveCall",
            "alarm_root": "DB_PromptBeeper",
        }}
        spec = {
            "project_name": "P",
            "tia_version": "V21",
            "servos": [{"name": "ST30_V90_01", "station": "ST30"}],
        }
        changes = _component_changes(spec, catalog)
        self.assertEqual(len(changes), 1)
        self.assertIn("clone_component_network", changes[0]["operations"])
        self.assertIn("readback_verify", changes[0]["operations"])

    def test_server_builds(self):
        self.assertIsNotNone(build_server())

    def test_runner_route_requires_explicit_profile(self):
        blocked = _runner_route("servo", {"name": "V90-01"})
        self.assertEqual(blocked["status"], "blocked")
        ready = _runner_route(
            "cylinder",
            {"name": "Z13", "execution_profile": "st10_pair_next"},
        )
        self.assertEqual(ready["command"], "--apply-st10-cylinder-pair-next")
        servo = _runner_route(
            "servo",
            {
                "name": "V90-01",
                "execution_profile": "component_servo",
                "template_path": "FB_Component.xml",
                "servo_start_index": 1,
            },
        )
        self.assertEqual(servo["command"], "--apply-component-servo-plan")
        self.assertIn("--template", servo["arguments"])


if __name__ == "__main__":
    unittest.main()
