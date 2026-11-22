import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pcb_mcp_under_test", ROOT / "tools" / "pcb_mcp.py")
pcb_mcp = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(pcb_mcp)


class MpcServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tools").mkdir()
        (self.root / "wiki" / "concepts").mkdir(parents=True)
        (self.root / "docs").mkdir()
        (self.root / "research" / "eda").mkdir(parents=True)
        (self.root / "raw").mkdir()
        (self.root / "tools" / "pcb.py").write_text(
            "import json, unicodedata\n"
            "def normalize(s): return unicodedata.normalize('NFKC', s).casefold()\n"
            "def query_terms(s): return [x for x in normalize(s).split() if x]\n"
            "def search(root, query, limit): return [{'path':'wiki/concepts/test.md','line':1,'title':'四层回流','score':1,'snippet':'四层板要保持参考平面连续。'}][:limit]\n"
            "def read_sources(root): return json.loads((root/'research/eda/sources.json').read_text(encoding='utf-8'))\n",
            encoding="utf-8",
        )
        self.sources = [{
            "id": "eda-cli", "title": "专业版 CLI 指南", "url": "https://example.org/cli",
            "local_path": "research/eda/snapshots/cli.md", "sha256": "0" * 64,
            "retrieved_at": "2026-11-21T00:00:00Z", "authority": "官方文档",
            "license_or_terms": "本地研究", "claims": ["专业版提供只读 API 探测"],
            "limitations": ["未验证用户安装环境"], "evidence": [],
        }]
        (self.root / "research" / "eda" / "sources.json").write_text(
            json.dumps(self.sources, ensure_ascii=False), encoding="utf-8"
        )
        (self.root / "wiki" / "concepts" / "test.md").write_text("# 四层回流\n", encoding="utf-8")
        self.server = pcb_mcp.PcbMcpServer(self.root)

    def test_initialize_and_tool_catalog(self):
        reply = self.server.dispatch({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
        })
        self.assertEqual(reply["result"]["protocolVersion"], "2025-03-26")
        catalog = self.server.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        self.assertEqual([x["name"] for x in catalog], ["pcb_search", "pcb_sources", "pcb_case_search", "pcb_inspect_local_project", "pcb_query_board",
            "pcb_eda_status", "pcb_eda_sessions", "pcb_eda_inspect", "pcb_eda_open_pcb", "pcb_eda_open_schematic_page", "pcb_eda_connectivity", "pcb_eda_ratlines", "pcb_eda_drc",
            "pcb_eda_copy", "pcb_import_reference_project", "pcb_eda_create_layout_board", "pcb_eda_initialize_layout_board", "pcb_eda_resume_layout", "pcb_eda_register_visual_target",
            "pcb_draw_preview", "pcb_draw_apply", "pcb_draw_export", "pcb_draw_export_manufacturing",
            "pcb_route_preview", "pcb_route_start", "pcb_route_status", "pcb_route_cancel", "pcb_route_export",
            "pcb_eda_test_copy", "pcb_eda_test_copy_cleanup"])
        self.assertTrue(all(x["annotations"]["readOnlyHint"] for x in catalog[:9]))
        self.assertFalse(catalog[-1]["annotations"]["readOnlyHint"])
        self.assertTrue(all(x["annotations"]["openWorldHint"] is False for x in catalog[:5]))
        self.assertTrue(all(x["annotations"]["openWorldHint"] is True for x in catalog[5:]))

    def test_codex_plugin_package_and_local_marketplace_agree(self):
        plugin = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        mcp_manifest = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        config = (ROOT / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertEqual(plugin["name"], "pcb")
        self.assertTrue((ROOT / plugin["skills"] / "pcb" / "SKILL.md").is_file())
        self.assertEqual(plugin["mcpServers"], "./.mcp.json")
        self.assertEqual(set(mcp_manifest["mcpServers"]["pcb"]["enabled_tools"]),
                         {tool["name"] for tool in pcb_mcp.PcbMcpServer(ROOT).tool_catalog()})
        windows = mcp_manifest["mcpServers"]["windows_control"]
        self.assertEqual(windows["command"], "python")
        self.assertEqual(windows["args"], ["tools/windows_mcp_launcher.py"])
        self.assertFalse(any(name in windows["enabled_tools"] for name in ("PowerShell", "Registry", "FileSystem", "Process")))
        self.assertEqual(windows["env"]["ANONYMIZED_TELEMETRY"], "false")
        self.assertEqual(marketplace["name"], "local-pcb")
        self.assertEqual(marketplace["plugins"][0]["name"], plugin["name"])
        self.assertEqual(marketplace["plugins"][0]["source"]["path"], "./")
        self.assertIn('[plugins."pcb@local-pcb"]', config)
        self.assertIn("enabled = true", config)
        self.assertNotIn("[mcp_servers.pcb]", config)

    def test_notification_returns_no_message(self):
        self.assertIsNone(self.server.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertTrue(self.server.initialized)

    def test_unknown_method_and_invalid_request(self):
        result = self.server.dispatch({"jsonrpc": "2.0", "id": 8, "method": "not/a/method"})
        self.assertEqual(result["error"]["code"], -32601)
        result = self.server.dispatch([{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
        self.assertEqual(result["error"]["code"], -32600)

    def test_search_call_returns_structured_and_text_content(self):
        result = self.server.dispatch({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "pcb_search", "arguments": {"query": "四层 回流", "limit": 1}},
        })["result"]
        self.assertFalse(result.get("isError", False))
        self.assertEqual(result["structuredContent"]["count"], 1)
        self.assertEqual(result["content"][0]["type"], "text")

    def test_source_call_contains_citation_but_not_local_path(self):
        result = self.server.dispatch({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "pcb_sources", "arguments": {"query": "CLI"}},
        })["result"]["structuredContent"]
        source = result["sources"][0]
        self.assertEqual(source["url"], "https://example.org/cli")
        self.assertNotIn("local_path", source)

    def test_private_case_search_has_bounded_line_citations(self):
        guide = self.root / "local" / "board-case" / "learning-guide.md"
        guide.parent.mkdir(parents=True)
        guide.write_text("# 四层板经验\n\n四层板的内层分配和回流路径需要结合板厂叠层核实。\n\nUSB阻抗必须根据指定叠层计算。\n", encoding="utf-8")
        result = self.server.dispatch({
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "pcb_case_search", "arguments": {"query": "USB阻抗", "limit": 2}},
        })["result"]["structuredContent"]
        self.assertEqual(result["results"][0]["path"], "local/board-case/learning-guide.md")
        self.assertEqual(result["results"][0]["line"], 5)
        self.assertIn("private local", result["scope"])

    def test_case_search_missing_guide_and_arbitrary_path_fail_closed(self):
        missing = self.server.dispatch({
            "jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {"name": "pcb_case_search", "arguments": {"query": "回流"}},
        })["result"]
        self.assertTrue(missing["isError"])
        self.assertIn("No private", missing["content"][0]["text"])
        external_path = self.server.dispatch({
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {"name": "pcb_case_search", "arguments": {"query": "回流", "path": "C:/secret.md"}},
        })["result"]
        self.assertTrue(external_path["isError"])
        self.assertNotIn("C:/secret", external_path["content"][0]["text"])

    def test_case_search_rejects_linked_ancestor_before_opening_file(self):
        guide = self.root / "local" / "board-case" / "learning-guide.md"
        guide.parent.mkdir(parents=True)
        guide.write_text("# Local\nUSB input data", encoding="utf-8")
        original = Path.is_symlink

        def fake_link(node):
            return node == self.root / "local" or original(node)

        with patch.object(Path, "is_symlink", fake_link):
            with self.assertRaises(pcb_mcp.ToolError):
                self.server._case_search({"query": "USB"})

    def test_case_search_quotes_matching_rows_inside_long_tables(self):
        guide = self.root / "local" / "board-case" / "learning-guide.md"
        guide.parent.mkdir(parents=True)
        rows = ["| unrelated history | " + "x" * 80 + " |" for _ in range(30)]
        rows.append("| USB | historical width cannot be reused as a new design default |")
        guide.write_text("\n".join(rows), encoding="utf-8")
        result = self.server._case_search({"query": "USB"})
        self.assertIn("USB", result["results"][0]["excerpt"])
        self.assertIn("cannot be reused", result["results"][0]["excerpt"])
        self.assertEqual(result["results"][0]["line"], 31)

    def test_case_search_keeps_part_heading_with_specific_rule_row(self):
        guide = self.root / "local" / "board-case" / "learning-guide.md"
        guide.parent.mkdir(parents=True)
        guide.write_text(
            "# Sensor A123\n\n| Rule | Evidence |\n|---|---|\n"
            "| no current carrying traces below sensor | PDF p.5 |\n"
            "| operating voltage | PDF p.4 |\n\n"
            "# Source metadata\n\nA123 A123 A123 supplier URL.\n",
            encoding="utf-8",
        )
        result = self.server._case_search({"query": "A123 current", "limit": 1})
        self.assertIn("current carrying", result["results"][0]["excerpt"])
        self.assertIn("Sensor A123", result["results"][0]["section"])
        self.assertEqual(result["results"][0]["line"], 5)

    def test_case_search_cites_the_matching_numbered_item(self):
        guide = self.root / "local" / "board-case" / "learning-guide.md"
        guide.parent.mkdir(parents=True)
        guide.write_text(
            "# Charger A123\n\n1. unrelated description.\n2. VDD capacitor values conflict; review both PDF pages.\n",
            encoding="utf-8",
        )
        result = self.server._case_search({"query": "A123 VDD conflict", "limit": 1})
        self.assertIn("VDD capacitor values conflict", result["results"][0]["excerpt"])
        self.assertEqual(result["results"][0]["line"], 4)

    def test_invalid_tool_arguments_fail_as_tool_error(self):
        result = self.server.dispatch({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "pcb_search", "arguments": {"query": "x", "path": "C:/secret"}},
        })["result"]
        self.assertTrue(result["isError"])
        self.assertNotIn("C:/secret", result["content"][0]["text"])

    def test_inspection_rejects_paths_outside_root_and_symlinks(self):
        for value in ("../outside.epro2", "C:\\secret.epro2", "/etc/passwd.epro2", "tools/pcb.py"):
            with self.subTest(value=value):
                with self.assertRaises(pcb_mcp.ToolError):
                    self.server._resolve_archive(value)
        secret = self.root.parent / (self.root.name + "-secret.epro2")
        secret.write_bytes(b"secret")
        self.addCleanup(lambda: secret.unlink(missing_ok=True))
        link = self.root / "outside.epro2"
        try:
            link.symlink_to(secret)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks are unavailable in this environment")
        with self.assertRaises(pcb_mcp.ToolError):
            self.server._resolve_archive("outside.epro2")

    def test_archive_without_reader_fails_closed(self):
        archive = self.root / "sample.epro2"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("project2.json", "{}")
        result = self.server.dispatch({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "pcb_inspect_local_project", "arguments": {"path": archive.name}},
        })["result"]
        self.assertTrue(result["isError"])
        self.assertIn("parser", result["content"][0]["text"].lower())

    def _board_archive(self, *, pad_count=3, component_count=2):
        (self.root / "tools" / "epro2.py").write_bytes((ROOT / "tools" / "epro2.py").read_bytes())
        rows = []
        ticket = 0

        def record(kind, identifier, body):
            nonlocal ticket
            ticket += 1
            header = {"type": kind, "ticket": ticket}
            if identifier is not None:
                header["id"] = identifier
            rows.append(json.dumps(header, ensure_ascii=False) + "||" + json.dumps(body, ensure_ascii=False) + "|")

        def head(kind, uuid):
            record("DOCHEAD", None, {"docType": kind, "uuid": uuid, "client": "fixture-client", "editVersion": "4.1.105"})

        head("DEVICE", "device-1")
        record("META", "META", {"title": "Test MCU", "attributes": {"Footprint": "footprint-1"}})
        head("PCB", "pcb-1")
        record("META", "META", {"title": "Four layer fixture", "board": "parent-board-1"})
        record("LAYER", '["LAYER",1]', {"layerType": "TOP", "layerName": "Top", "use": True})
        record("LAYER", '["LAYER",2]', {"layerType": "BOTTOM", "layerName": "Bottom", "use": True})
        record("NET", '["NET","GND"]', {})
        record("NET", '["NET","VCC"]', {})
        for index in range(component_count):
            cid = f"component-{index + 1}"
            record("COMPONENT", cid, {"x": 10 + index, "y": 20, "angle": 90, "layerId": 1,
                                      "attrs": {"DeviceName": json.dumps({"uuid": "device-1"})}})
            record("ATTR", f"{cid}-ref", {"parentId": cid, "key": "Designator", "value": f"U{index + 1}"})
            count = pad_count if index == 0 else 1
            for pad_index in range(count):
                # Two different physical pads intentionally share logical pad number 1.
                pad_number = "1" if pad_index < 2 else str(pad_index)
                net = "GND" if pad_index != 2 or pad_count > 3 else "VCC"
                composite = json.dumps(["PAD_NET", cid, pad_number, f"physical-{pad_index + 1}"])
                record("PAD_NET", composite, {"padNet": net})
        record("LINE", "segment-1", {"netName": "GND", "layerId": 1, "width": 4.1,
                                     "startX": 10, "startY": 20, "endX": 30, "endY": 20})
        record("LINE", "segment-2", {"netName": "GND", "layerId": 2, "width": 6.7,
                                     "startX": 20, "startY": 20, "endX": 30, "endY": 20})
        record("VIA", "via-1", {"netName": "GND", "centerX": 20, "centerY": 20})
        head("PCB", "pcb-2")
        record("META", "META", {"title": "Separate fixture", "board": "parent-board-2"})
        record("LAYER", '["LAYER",1]', {"layerType": "TOP", "layerName": "Top", "use": True})
        record("NET", '["NET","GND"]', {})
        record("COMPONENT", "component-1", {"x": 999, "y": 999, "angle": 0, "layerId": 1, "attrs": {}})
        record("ATTR", "component-1-ref", {"parentId": "component-1", "key": "Designator", "value": "U1"})
        record("PAD_NET", '["PAD_NET","component-1","1","separate-physical"]', {"padNet": "GND"})
        record("LINE", "other-segment", {"netName": "GND", "layerId": 1, "width": 100,
                                         "startX": 999, "startY": 999, "endX": 998, "endY": 999})
        archive = self.root / "board.epro2"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("project2.json", json.dumps({"title": "Synthetic fixture", "editorVersion": "4.1.100"}))
            z.writestr("test-board.epru", "\n".join(rows) + "\n")
        return archive

    def _query(self, archive, **arguments):
        args = {"path": archive.name, "board_uuid": "pcb-1", **arguments}
        response = self.server.dispatch({"jsonrpc": "2.0", "id": 30, "method": "tools/call",
                                         "params": {"name": "pcb_query_board", "arguments": args}})["result"]
        self.assertFalse(response.get("isError"), response)
        return response["structuredContent"]

    def test_board_query_keeps_repeated_physical_pads_and_exact_source_evidence(self):
        archive = self._board_archive()
        result = self._query(archive, component_ref="U1")
        self.assertTrue(result["found"])
        component = result["components"][0]
        self.assertEqual(component["device_title"], "Test MCU")
        self.assertEqual(component["side"], "top")
        self.assertEqual(component["x"], 10)
        self.assertEqual(component["pads"][0]["pad_number"], component["pads"][1]["pad_number"])
        self.assertNotEqual(component["pads"][0]["footprint_pad_id"], component["pads"][1]["footprint_pad_id"])
        self.assertEqual(component["evidence"]["archive_member"], "test-board.epru")
        self.assertEqual(component["evidence"]["client"], "fixture-client")
        self.assertTrue(component["pads"][0]["evidence"]["line"] > 0)
        self.assertEqual(result["unit"], "mil")
        self.assertEqual(result["routing"]["segment_count"], 2)
        self.assertEqual(result["routing"]["via_count"], 1)
        self.assertNotIn(100, [row["width"] for row in result["routing"]["segments_by_layer_width"]])
        self.assertIn("No schematic", result["scope"])

    def test_board_query_intersects_literal_selectors_and_rejects_unknown_board(self):
        archive = self._board_archive()
        result = self._query(archive, component_ref="U1", net_name="VCC")
        self.assertEqual(result["component_count_total"], 1)
        self.assertEqual([row["net"] for row in result["components"][0]["pads"]], ["VCC"])
        self.assertEqual(result["routing"]["segment_count"], 0)
        no_match = self._query(archive, component_ref="U2", net_name="VCC")
        self.assertFalse(no_match["found"])
        self.assertEqual(no_match["components"], [])
        with self.assertRaises(pcb_mcp.ToolError):
            self.server._query_board({"path": archive.name, "board_uuid": "parent-board-1", "component_ref": "U1"})
        selector = "__import__('pathlib').Path('MUST_NOT_EXIST').touch()"
        result = self._query(archive, component_ref=selector)
        self.assertFalse(result["found"])
        self.assertFalse((self.root / "MUST_NOT_EXIST").exists())

    def test_board_query_paginates_physical_pad_rows_and_limits_endpoint_components(self):
        archive = self._board_archive(pad_count=102, component_count=14)
        result = self._query(archive, component_ref="U1")
        self.assertEqual(result["pad_count_total"], 102)
        self.assertTrue(1 <= result["pad_count_returned"] <= 100)
        self.assertEqual(result["next_pad_offset"], result["pad_count_returned"])
        self.assertTrue(result["pads_truncated"])
        pad_ids = [row["id"] for row in result["components"][0]["pads"]]
        next_offset = result["next_pad_offset"]
        while next_offset is not None:
            page = self._query(archive, component_ref="U1", pad_offset=next_offset)
            self.assertTrue(page["pad_count_returned"] > 0)
            self.assertLess(self.server._tool_result_bytes(page), pcb_mcp.MAX_TOOL_OUTPUT_BYTES)
            pad_ids.extend(row["id"] for row in page["components"][0]["pads"])
            next_offset = page["next_pad_offset"]
        self.assertEqual(len(pad_ids), 102)
        self.assertEqual(len(set(pad_ids)), 102)
        net = self._query(archive, net_name="GND", limit=2)
        self.assertEqual(net["component_count_total"], 14)
        self.assertEqual(net["component_count_returned"], 2)
        self.assertTrue(net["components_truncated"])
        references = [item["designator"] for item in net["components"]]
        next_component = net["next_component_offset"]
        while next_component is not None:
            next_page = self._query(archive, net_name="GND", limit=2, component_offset=next_component)
            references.extend(item["designator"] for item in next_page["components"])
            next_component = next_page["next_component_offset"]
        self.assertEqual(len(references), 14)
        self.assertEqual(len(set(references)), 14)

    def test_board_query_validates_input_bounds(self):
        archive = self._board_archive()
        for args in ({"board_uuid": "pcb-1"}, {"board_uuid": "pcb-1", "component_ref": "x" * 129},
                     {"board_uuid": "pcb-1", "net_name": "GND", "limit": 13},
                     {"board_uuid": "pcb-1", "net_name": "GND", "pad_offset": -1}):
            with self.subTest(args=args), self.assertRaises(pcb_mcp.ToolError):
                self.server._query_board({"path": archive.name, **args})

    def test_archive_resolution_rejects_mock_windows_junction(self):
        archive = self._board_archive()
        raw = self.root / "raw"
        with patch.object(Path, "is_junction", lambda path: path == raw, create=True):
            for relative in (None, archive.name, "raw/board.epro2"):
                with self.subTest(relative=relative), self.assertRaises(pcb_mcp.ToolError):
                    self.server._resolve_archive(relative)
        nested = raw / "linked"
        nested.mkdir()
        with patch.object(Path, "is_junction", lambda path: path == nested, create=True):
            with self.assertRaises(pcb_mcp.ToolError):
                self.server._resolve_archive("raw/linked/board.epro2")

    def test_inspector_returns_compact_summary_without_absolute_paths(self):
        archive = self.root / "sample.epro2"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("project2.json", "{}")
        (self.root / "tools" / "epro2.py").write_text(
            "def read_project(path): return {'source': str(path)}\n"
            "def summarize_model(model): return {'model_version':'test','source':{'path':model['source'],'sha256':'hash'},"
            "'project':{'title':'示例板'},'document_counts':{'PCB':1},'library_counts':{},'boards':[],"
            "'schematics':[],'pcb':[{'title':'核心板','enabled_copper_layer_count':4,'copper_layers':["
            "{'id':1,'name':'Top','type':'TOP','enabled':True},{'id':17,'name':'Inner5','type':'SIGNAL','enabled':False}],"
            "'component_count':2,'net_count':2,'net_names':['GND','VCC'],'named_components':['U1','R1'],"
            "'evidence':{'archive_member':'project.epru','line':3}}],'warnings':[],'unsupported_deletions':[],"
            "'geometry':{'raw':'must not escape'}}\n",
            encoding="utf-8",
        )
        result = self.server.dispatch({
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {"name": "pcb_inspect_local_project", "arguments": {"path": archive.name}},
        })["result"]["structuredContent"]
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn("geometry", encoded)
        self.assertEqual(result["summary"]["pcb"][0]["enabled_copper_layer_count"], 4)
        self.assertEqual([x["id"] for x in result["summary"]["pcb"][0]["copper_layers"]], [1])

    def test_stdio_newline_protocol_and_parse_error(self):
        incoming = b"\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}).encode(),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode(),
            b"{bad json}",
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}).encode(),
        ]) + b"\n"
        out = io.BytesIO()
        pcb_mcp.serve(io.BytesIO(incoming), out, self.server)
        responses = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(len(responses), 3)  # notification emits no response
        self.assertEqual(responses[0]["id"], 1)
        self.assertEqual(responses[1]["error"]["code"], -32700)
        self.assertEqual(responses[2]["id"], 2)

    def test_oversized_line_is_rejected_and_stream_recovers(self):
        incoming = b"x" * 80 + b"\n" + json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}).encode() + b"\n"
        out = io.BytesIO()
        pcb_mcp.serve(io.BytesIO(incoming), out, self.server, max_request_bytes=64)
        responses = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(responses[0]["error"]["code"], -32600)
        self.assertEqual(responses[1]["id"], 9)


if __name__ == "__main__":
    unittest.main()
