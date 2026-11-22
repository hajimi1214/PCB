"""Runtime MCP boundary tests with a fake EDA transport, no application calls."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pcb_live_test", ROOT / "tools" / "pcb_mcp.py")
pcb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pcb)


class LiveMcpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.server = pcb.PcbMcpServer(self.root)
        self.client = Mock()
        self.server._eda_client = self.client

    def call(self, name, args):
        return self.server.call_tool({"name": name, "arguments": args})["structuredContent"]

    def target(self):
        return {"session_id": "s", "expected_project_uuid": "p", "expected_document_uuid": "d", "pcb_uuid": "b"}

    def test_status_does_not_open_or_invoke(self):
        self.client.probe.return_value = {"status": "unavailable"}
        self.assertEqual(self.call("pcb_eda_status", {}), {"status": "unavailable"})
        self.client.invoke_script.assert_not_called()
        self.client.list_sessions.assert_not_called()

    def test_invalid_identity_and_unknown_code_rejected_before_transport(self):
        for args in ({"session_id": "s", "code": "return 1"}, {"session_id": "s\n"}, {"session_id": "s", "backend": "other"}):
            with self.assertRaises(pcb.ToolError):
                self.call("pcb_eda_inspect", args)
        for args in ({"session_id": "s"}, {**self.target(), "limit": True}, {**self.target(), "limit": 0}):
            with self.assertRaises(pcb.ToolError):
                self.call("pcb_eda_connectivity", args)
        self.client.invoke_script.assert_not_called()

    def test_inspect_stops_on_mismatch(self):
        self.client.invoke_script.return_value = {"status": "target_mismatch", "value": {"ok": False}}
        result = self.call("pcb_eda_inspect", {"session_id": "s", "expected_document_uuid": "d"})
        self.assertEqual(result["project"]["status"], "not_attempted")
        self.assertEqual(self.client.invoke_script.call_count, 1)

    def test_inspect_environment_and_project_binding(self):
        self.client.invoke_script.return_value = {"status": "observed", "value": {"ok": True}}
        self.call("pcb_eda_inspect", {"session_id": "s", "expected_document_uuid": "d", "expected_project_uuid": "p"})
        calls = self.client.invoke_script.call_args_list
        self.assertEqual(calls[0].args, ("inspect_environment", "s", {"expected_document_uuid": "d"}))
        self.assertEqual(calls[1].args, ("inspect_project", "s", {"expected_document_uuid": "d", "expected_project_uuid": "p"}))

    def test_netlist_saved_locally_and_not_in_context(self):
        text="secret-board-net-data"
        def fake_export(_action,_session,args,**_kwargs):
            target=Path(args["artifact_path"]);target.write_bytes(text.encode())
            return {"status":"observed","value":{"ok":True,"native_netlist":{"format":"JLCEDA","artifact_path":str(target),
                "sha256":pcb.hashlib.sha256(text.encode()).hexdigest(),"bytes":len(text.encode())},"pads":[]}}
        self.client.invoke_script.side_effect=fake_export
        result = self.call("pcb_eda_connectivity", self.target())
        evidence = result["value"]["native_netlist"]
        self.assertNotIn("text", evidence)
        self.assertNotIn(text, json.dumps(result))
        self.assertEqual((self.root / evidence["local_path"]).read_bytes(), text.encode())
        # A repeat references the same immutable snapshot.
        self.call("pcb_eda_connectivity", self.target())
        self.assertEqual(len(list((self.root / "local" / "eda-snapshots").iterdir())), 1)
        self.assertFalse(evidence["comparison_performed"])

    def test_linked_evidence_directory_rejected(self):
        self.client.invoke_script.side_effect=lambda *_a,**_k:self.fail("EDA must not be called when evidence paths are linked")
        with patch.object(self.server, "_is_link", return_value=True):
            with self.assertRaises(pcb.ToolError):
                self.call("pcb_eda_connectivity", self.target())

    def test_native_drc_run_is_explicit_and_typed(self):
        self.client.invoke_script.return_value = {"status": "observed", "value": {"native_check_passed": False}}
        self.call("pcb_eda_drc", {**self.target(), "run": True})
        self.assertEqual(self.client.invoke_script.call_args.args[0], "inspect_drc")
        self.assertTrue(self.client.invoke_script.call_args.args[2]["run"])
        with self.assertRaises(pcb.ToolError):
            self.call("pcb_eda_drc", {**self.target(), "run": "true"})

    def test_discovered_bridge_session_uses_client_backend_inference(self):
        self.client._known_sessions = {"s": "bridge"}
        self.client.invoke_script.return_value = {"status": "observed", "value": {"ok": True}}
        self.call("pcb_eda_drc", self.target())
        self.assertEqual(self.client.invoke_script.call_args.kwargs, {})
        self.assertEqual(self.client._known_sessions["s"], "bridge")

    def test_open_pcb_requires_exact_project_and_native_backend(self):
        self.client.invoke_script.return_value={"status":"observed","value":{"ok":True,"read_only":True}}
        result=self.call("pcb_eda_open_pcb",{"session_id":"s","expected_project_uuid":"p","pcb_uuid":"b"})
        self.assertTrue(result["value"]["read_only"])
        self.assertEqual(self.client.invoke_script.call_args.args[:3],("open_project_pcb","s",{"expected_project_uuid":"p","pcb_uuid":"b"}))
        with self.assertRaises(pcb.ToolError):
            self.call("pcb_eda_open_pcb",{"session_id":"s","expected_project_uuid":"p","pcb_uuid":"b","backend":"bridge"})

    def test_drawing_tools_reject_unknown_arguments_before_service_creation(self):
        for name,args in (("pcb_eda_copy",{"path":"board.eprj2","code":"return 1"}),
                          ("pcb_draw_preview",{"copy_id":"x","pcb_uuid":"p","operations":[],"constraints":{},"backend":"cli"}),
                          ("pcb_draw_apply",{"plan_id":"a","operations":[]})):
            with self.assertRaises(pcb.ToolError):self.call(name,args)
        self.assertIsNone(self.server._drawing_service)


if __name__ == "__main__":
    unittest.main()
