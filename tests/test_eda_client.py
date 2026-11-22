import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from eda_client import EdaClient, EdaClientError, MAX_OUTPUT_BYTES


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class FakeProcess:
    def __init__(self, stdout=b"", stderr=b"", returncode=0, timeout=False):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode
        self.timeout = timeout
        self.killed = False

    def wait(self, timeout):
        if self.timeout and not self.killed:
            raise subprocess.TimeoutExpired("fixture-command", timeout)
        return self.returncode

    def kill(self):
        self.killed = True


class FakeResponse:
    def __init__(self, body, status=200):
        self.stream = io.BytesIO(body)
        self.status = status

    def read(self, n):
        return self.stream.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.stream.close()


class EdaTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.actions = Path(self.temp.name) / "eda_actions"
        self.actions.mkdir()
        self.body = "const args=__CLI__.args||{}; return {ok:true,status:'observed',received:args};"
        for action in ("inspect_environment", "inspect_project", "export_connectivity", "inspect_drc", "start_auto_route",
                       "import_reference_project", "create_board_from_schematic"):
            (self.actions / (action + ".js")).write_text(self.body, encoding="utf-8")
        (self.actions / "drawing_common.js").write_text("const args=__CLI__.args||{};",encoding="utf-8")

    def client(self, **kwargs):
        return EdaClient(executable="fixture-eda.exe", action_dir=self.actions, **kwargs)

    def test_discovery_only_uses_two_documented_path_commands(self):
        seen = []

        def which(command):
            seen.append(command)
            return None

        with patch("eda_client.shutil.which", side_effect=which):
            client = EdaClient(action_dir=self.actions)
        self.assertIsNone(client.executable)
        self.assertEqual(seen, ["lceda-pro", "easyeda-pro"])
        with patch("eda_client.subprocess.Popen") as popen:
            self.assertEqual(client._run_cli(["doctor"], "doctor")["status"], "unavailable")
            popen.assert_not_called()

    def test_cli_empty_stdout_is_unsupported_even_at_exit_zero(self):
        process = FakeProcess(stdout=b"", stderr=b"app wrote an unrelated line", returncode=0)
        with patch("eda_client.subprocess.Popen", return_value=process):
            result = self.client()._run_cli(["doctor"], "doctor")
        self.assertEqual(result["status"], "unsupported")
        self.assertFalse(result["transport_ok"])
        self.assertEqual(result["business_status"], "unknown")

    def test_cli_nonzero_exit_cannot_be_overridden_by_ok_json(self):
        process = FakeProcess(stdout=encoded({"ok": True, "value": {"connected": True}}), returncode=2)
        with patch("eda_client.subprocess.Popen", return_value=process):
            result = self.client()._run_cli(["doctor"], "doctor")
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["transport_ok"])

    def test_cli_requires_one_complete_json_envelope(self):
        for raw in (b'{"ok":true', b'hello\n{"ok":true,"value":{}}', b'{"ok":true}{}',
                    b'{"success":true}', b'{"ok":1,"value":{}}', b'{"ok":true,"value":NaN}'):
            with self.subTest(raw=raw), patch("eda_client.subprocess.Popen", return_value=FakeProcess(raw)):
                result = self.client()._run_cli(["doctor"], "doctor")
                self.assertEqual(result["status"], "unsupported")

    def test_cli_timeout_kills_bounded_process(self):
        process = FakeProcess(timeout=True)
        with patch("eda_client.subprocess.Popen", return_value=process):
            result = self.client(timeout=0.05)._run_cli(["doctor"], "doctor")
        self.assertTrue(process.killed)
        self.assertEqual(result["status"], "timeout")

    def test_cli_oversized_stdout_and_stderr_are_rejected(self):
        for stream in ("stdout", "stderr"):
            process = FakeProcess(**{stream: b"x" * (MAX_OUTPUT_BYTES + 1)})
            with self.subTest(stream=stream), patch("eda_client.subprocess.Popen", return_value=process):
                result = self.client()._run_cli(["doctor"], "doctor")
                self.assertEqual(result["status"], "rejected")
                self.assertTrue(process.killed)

    def test_cli_passes_code_and_args_as_separate_no_shell_arguments(self):
        uuid = 'a"; globalThis.payloadWasExecuted=true; //'
        args = {"expected_document_uuid": uuid}
        process = FakeProcess(encoded({"ok": True, "value": {"ok": True, "status": "observed"}}))
        with patch("eda_client.subprocess.Popen", return_value=process) as popen:
            result = self.client().invoke_script("inspect_environment", "session-1", args)
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "fixture-eda.exe")
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertEqual(command[command.index("--code") + 1], self.body)
        self.assertNotIn(uuid, self.body)
        self.assertEqual(json.loads(command[command.index("--args") + 1]), args)
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["business_status"], "observed")

    def test_outer_ok_does_not_infer_board_pass_or_unknown_business_success(self):
        for value in (None, True, {}, {"unexpected": []}, {"status": {"unexpected": "shape"}},
                      {"ok": True, "status": {"unexpected": "shape"}}, {"ok": True, "status": "unrecognized"}):
            with self.subTest(value=value), patch("eda_client.subprocess.Popen", return_value=FakeProcess(encoded({"ok": True, "value": value}))):
                result = self.client().invoke_script("inspect_environment", "s1", {})
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["business_status"], "unknown")
        for value, expected in (({"ok": False, "status": "unsupported"}, "unsupported"),
                                ({"ok": False, "status": "target_mismatch"}, "target_mismatch"),
                                ({"success": False}, "error")):
            with self.subTest(value=value), patch("eda_client.subprocess.Popen", return_value=FakeProcess(encoded({"ok": True, "value": value}))):
                self.assertEqual(self.client().invoke_script("inspect_environment", "s1", {})["status"], expected)
        with patch("eda_client.subprocess.Popen", return_value=FakeProcess(encoded({"ok": True, "value": {"ok": True, "status": "started", "job_id": "job"}}))):
            result=self.client(allow_drawing=True).invoke_script(
                "start_auto_route","s1",{"pcb_uuid":"p","expected_project_uuid":"j","expected_source_sha256":"a"*64,"routing_nets":["GND"],"layers":[15]})
        self.assertEqual(result["status"],"started")
        self.assertEqual(result["business_status"],"in_progress")

    def test_schema_limits_fixed_action_target_identity_and_drc_default(self):
        client = self.client()
        for action, args in (
            ("../arbitrary", {}), ("inspect_environment", {"code": "return true"}),
            ("export_connectivity", {}),
            ("export_connectivity", {"pcb_uuid": "p", "expected_project_uuid": "j", "expected_document_uuid": "d", "limit": 9}),
            ("export_connectivity", {"pcb_uuid": "p", "expected_project_uuid": "j", "expected_document_uuid": "d", "pad_offset": True}),
            ("inspect_drc", {"pcb_uuid": "p", "expected_project_uuid": "j", "expected_document_uuid": "d", "run": True}),
        ):
            with self.subTest(action=action, args=args), self.assertRaises(EdaClientError):
                client.invoke_script(action, "s1", args)
        process = FakeProcess(encoded({"ok": True, "value": {"ok": True, "status": "observed", "passed": False}}))
        with patch("eda_client.subprocess.Popen", return_value=process) as popen:
            result = client.invoke_script("inspect_drc", "s1", {"pcb_uuid": "p", "expected_project_uuid": "j", "expected_document_uuid": "d"})
        command = popen.call_args.args[0]
        self.assertIs(json.loads(command[command.index("--args") + 1])["run"], False)
        self.assertIs(result["value"]["passed"], False)
        self.assertNotIn("passed", result)

    def test_auto_router_and_export_actions_have_strict_arguments(self):
        client=self.client(allow_drawing=True)
        base={"pcb_uuid":"p","expected_project_uuid":"j","expected_source_sha256":"a"*64}
        invalid=[{"routing_nets":[],"layers":[15]},
                 {"routing_nets":["GND"],"layers":[True]},
                 {"routing_nets":[3],"layers":[15]},
                 {"routing_nets":["GND"],"layers":[15,15]}]
        for values in invalid:
            with self.subTest(values=values),self.assertRaises(EdaClientError):client._action_script("start_auto_route",{**base,**values})
        with self.assertRaises(EdaClientError):client._action_script("export_drawing_copy",{**base,"artifact_path":"..\\outside.epro2"})
        writer=EdaClient(action_dir=Path(__file__).resolve().parents[1]/"tools"/"eda_actions",allow_drawing=True)
        manufacturing={"pcb_uuid":"p","expected_project_uuid":"j","expected_source_sha256":"a"*64,
                        "artifact_directory":str(Path(__file__).resolve().parents[1]/"local"/"drawing"/"exports"/("pcb-"+"a"*32+"-"+"a"*16+"-"+"b"*16))}
        with self.assertRaises(EdaClientError):writer._action_script("export_manufacturing",manufacturing)
        output=Path(manufacturing["artifact_directory"]);output.mkdir(parents=True,exist_ok=True)
        self.addCleanup(output.rmdir)
        code,_,_=writer._action_script("export_manufacturing",manufacturing)
        self.assertIn("getGerberFile",code);self.assertIn("getPickAndPlaceFile",code)

    def test_reference_import_requires_public_source_and_explicit_new_project_destination(self):
        writer=EdaClient(action_dir=Path(__file__).resolve().parents[1]/"tools"/"eda_actions",allow_drawing=True)
        source=Path(__file__).resolve().parents[1]/"local"/"board-challenges"/"sources"/"rp2040-minimal"/"rp2040-minimal.zip"
        args={"source_path":str(source),"project_slug":"rp2040-minimal","project_friendly_name":"PCB visual reference - rp2040-minimal",
              "file_type":"KiCad","destination":"new_user_project"}
        code,_,_=writer._action_script("import_reference_project",args)
        self.assertIn("importProjectByProjectFile",code)
        self.assertIn("New Project",code)
        for invalid in ({**args,"destination":"local"},{**args,"file_type":"unknown"},
                        {**args,"source_path":str(Path(__file__).resolve().parents[1]/"README.md")}):
            with self.subTest(invalid=invalid),self.assertRaises(EdaClientError):writer._action_script("import_reference_project",invalid)

    def test_fresh_board_action_requires_exact_source_pcb_and_schematic(self):
        writer=EdaClient(action_dir=Path(__file__).resolve().parents[1]/"tools"/"eda_actions",allow_drawing=True)
        args={"expected_project_uuid":"project","source_board_name":"reference","source_pcb_uuid":"a"*16,"schematic_uuid":"schematic"}
        code,_,_=writer._action_script("create_board_from_schematic",args)
        self.assertIn("createPcb",code);self.assertIn("importChanges",code);self.assertIn("layout_copied:false",code)
        with self.assertRaises(EdaClientError):writer._action_script("create_board_from_schematic",{**args,"source_pcb_uuid":"x"})

    def test_project_lookup_is_fixed_and_returns_only_exact_slug_matches(self):
        writer=EdaClient(action_dir=Path(__file__).resolve().parents[1]/"tools"/"eda_actions",allow_drawing=True)
        code,_,_=writer._action_script("inspect_project_by_slug",{"project_slug":"rp2040-minimal"})
        self.assertIn("getAllProjectsUuid",code)
        with self.assertRaises(EdaClientError):writer._action_script("inspect_project_by_slug",{"project_slug":"../other"})

    def test_windows_batch_wrappers_are_not_shell_false_executables(self):
        for executable in ("lceda-pro.cmd", "easyeda-pro.bat", "runner.ps1"):
            with self.subTest(executable=executable), self.assertRaises(EdaClientError):
                EdaClient(executable=executable)

    def test_nonloopback_credentials_paths_queries_and_redirects_are_rejected(self):
        for origin in ("https://example.com", "http://192.168.1.2:49620", "http://user:password@127.0.0.1:49620",
                       "http://127.0.0.1:49620/path", "http://127.0.0.1:49620?token=secret", "file:///tmp/server"):
            with self.subTest(origin=origin), self.assertRaises(EdaClientError):
                self.client(bridge_url=origin)
        client = self.client(bridge_url="http://localhost:49620")
        self.assertEqual(client.bridge_url, "http://127.0.0.1:49620")
        redirect = HTTPError("http://127.0.0.1:49620/health", 302, "redirect", {}, None)
        with patch.object(client._opener, "open", side_effect=redirect):
            self.assertEqual(client._bridge_probe(client.bridge_url)["status"], "rejected")

    def test_http_identity_schema_size_and_timeout_fail_closed(self):
        client = self.client(bridge_url="http://127.0.0.1:49620")
        cases = [
            ({"service": "other", "edaConnected": True}, "unsupported"),
            ({"service": "easyeda-bridge", "edaConnected": False}, "unavailable"),
            ({"service": "easyeda-bridge"}, "unknown"),
            ({"service": "easyeda-bridge", "edaConnected": True}, "available"),
        ]
        for value, status in cases:
            with self.subTest(value=value), patch.object(client._opener, "open", return_value=FakeResponse(encoded(value))):
                self.assertEqual(client._bridge_probe(client.bridge_url)["status"], status)
        with patch.object(client._opener, "open", return_value=FakeResponse(b"x" * (MAX_OUTPUT_BYTES + 1))):
            self.assertEqual(client._bridge_probe(client.bridge_url)["status"], "rejected")
        with patch.object(client._opener, "open", side_effect=TimeoutError()):
            self.assertEqual(client._bridge_probe(client.bridge_url)["status"], "unavailable")

    def test_bridge_fixed_wrapper_has_json_literal_not_user_code(self):
        client = self.client(bridge_url="http://127.0.0.1:49620")
        dangerous_data = 'doc"};globalThis.evil=true;//\u2028tail'
        seen = []

        def opening(request, **_kwargs):
            seen.append(request)
            if request.full_url.endswith("/health"):
                return FakeResponse(encoded({"service": "easyeda-bridge", "edaConnected": True}))
            return FakeResponse(encoded({"success": True, "result": {"ok": True, "status": "observed"}, "windowId": "w1"}))

        with patch.object(client._opener, "open", side_effect=opening):
            result = client.invoke_script("inspect_environment", "w1", {"expected_document_uuid": dangerous_data}, backend="bridge")
        self.assertEqual(result["status"], "observed")
        execute = next(r for r in seen if r.full_url.endswith("/execute"))
        payload = json.loads(execute.data)
        self.assertEqual(payload["windowId"], "w1")
        self.assertIn(self.body, payload["code"])
        self.assertIn(json.dumps({"expected_document_uuid": dangerous_data}, ensure_ascii=True, separators=(",", ":")), payload["code"])
        self.assertNotIn(dangerous_data, payload["code"])
        self.assertNotIn("\u2028", payload["code"])

    def test_cli_and_bridge_return_values_do_not_expose_credentials(self):
        body = {"ok": True, "status": "observed", "api_key": "secretvalue", "nested": {"Authorization": "Bearer abc"},
                "logs": ["password=leak"], "note": "token=abcd", "source": "https://u:passwd@site.invalid/"}
        with patch("eda_client.subprocess.Popen", return_value=FakeProcess(encoded({"ok": True, "value": body}))):
            result = self.client().invoke_script("inspect_environment", "s1", {})
        text = json.dumps(result)
        for credential in ("secretvalue", "Bearer abc", "password=leak", "token=abcd", "u:passwd"):
            self.assertNotIn(credential, text)
        self.assertEqual(result["value"]["api_key"], "[redacted]")

    def test_probe_scans_only_known_ports_without_mutating_routes(self):
        client = self.client()
        routes = []

        def http(origin, path, **_kwargs):
            routes.append((origin, path))
            return {"status": "ok", "backend": "bridge", "transport_ok": True, "business_status": "unknown",
                    "value": {"service": "easyeda-bridge", "edaConnected": origin.endswith(":49625")},
                    "evidence": {"route": path, "origin": origin}}

        with patch("eda_client.subprocess.Popen", return_value=FakeProcess(b"")), patch.object(client, "_http_json", side_effect=http):
            result = client.probe()
        self.assertEqual(result["status"], "available")
        self.assertEqual(len(routes), 10)
        self.assertEqual({int(o.rsplit(":", 1)[1]) for o, _p in routes}, set(range(49620, 49630)))
        self.assertEqual({p for _o, p in routes}, {"/health"})
        self.assertFalse(result["capabilities"]["writes"])
        self.assertFalse(result["capabilities"]["runtime_apis_verified"])

    def test_native_cli_sessions_and_bridge_windows_are_read_without_selection(self):
        client = self.client(bridge_url="http://127.0.0.1:49620")
        seen = []

        def opening(request, **_kwargs):
            seen.append((request.method, request.full_url))
            if request.full_url.endswith("/health"):
                return FakeResponse(encoded({"service": "easyeda-bridge", "edaConnected": True}))
            return FakeResponse(encoded({"windows": [{"windowId": "w1", "connected": True, "active": False}], "count": 1}))

        process = FakeProcess(encoded({"ok": True, "value": [{"sessionId": "s1", "title": "Board", "status": "alive"}]}))
        with patch("eda_client.subprocess.Popen", return_value=process) as popen, patch.object(client._opener, "open", side_effect=opening):
            result = client.list_sessions()
        self.assertEqual(popen.call_args.args[0], ["fixture-eda.exe", "session", "list"])
        self.assertEqual([(s["session_id"], s["backend"]) for s in result["sessions"]], [("s1", "cli"), ("w1", "bridge")])
        self.assertEqual({m for m, _u in seen}, {"GET"})
        self.assertTrue(all("/eda-windows/select" not in u for _m, u in seen))


if __name__ == "__main__":
    unittest.main()
