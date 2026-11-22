import hashlib
import io
import json
import pathlib
import struct
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
from epro2 import Epro2Error, inspect_archive, main, read_project, summarize_model


def _record(header, body, terminal=True):
    text = json.dumps(header, ensure_ascii=False, separators=(",", ":"))
    text += "||" + json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if terminal:
        text += "|"
    return text


def _head(doc_type, uuid, client="c1", ticket=1, **extra):
    body = {"docType": doc_type, "uuid": uuid, "client": client, **extra}
    return _record({"type": "DOCHEAD", "ticket": ticket}, body)


def _row(rec_type, rec_id, ticket, body, terminal=True):
    return _record({"type": rec_type, "id": rec_id, "ticket": ticket}, body, terminal=terminal)


def _make_archive(root, rows, *, log_name="Board.epru"):
    path = root / "测试项目.epro2"
    metadata = {"title": "黄山测试板", "editorVersion": "4.1.100", "cbb_project": False}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project2.json", json.dumps(metadata, ensure_ascii=False))
        archive.writestr(log_name, "\n".join(rows))
    return path


class Epro2ParserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def test_history_tickets_client_ties_and_atomic_tombstone(self):
        rows = [
            _head("PCB", "pcb-1", "z-client"),
            _row("META", "META", 1, {"title": "old"}),
            _row("STRING", "same", 4, {"text": "tie from z"}),
            _row("ATTR", "gone", 2, {"value": "stale"}),
            _head("PCB", "pcb-1", "a-client", ticket=3),
            _row("META", "META", 2, {"title": "newer"}),
            _row("STRING", "same", 4, {"text": "tie from a"}),
            _row("ATTR", "gone", 9, ""),
        ]
        model = read_project(_make_archive(self.root, rows))
        pcb = model["documents"][0]
        self.assertEqual(pcb["meta"]["title"], "newer")
        strings = model["pcb"][0]["records_by_type"]["STRING"]
        self.assertEqual(strings[0]["body"]["text"], "tie from a")
        self.assertEqual(strings[0]["evidence"]["client"], "a-client")
        self.assertEqual(pcb["records_by_type"].get("ATTR", []), [])
        self.assertEqual(pcb["tombstones"][0]["id"], "gone")
        self.assertEqual(pcb["tombstones"][0]["ticket"], 9)

    def test_delete_doc_is_explicitly_unsupported(self):
        model = read_project(_make_archive(self.root, [
            _head("PCB", "pcb-1"),
            _row("META", "META", 1, {"title": "kept"}),
            _row("DELETE_DOC", None, 2, {"isDelete": True}),
        ]))
        self.assertEqual(len(model["unsupported_deletions"]), 1)
        self.assertEqual(model["unsupported_deletions"][0]["status"], "unsupported_document_delete_semantics")
        self.assertEqual(model["documents"][0]["meta"]["title"], "kept")

    def test_same_number_physical_pads_and_pad_net_mappings_are_not_deduplicated(self):
        pad1 = _row("PAD", 'pad-a', 1, {"num": "1", "centerX": 0, "centerY": 0})
        pad2 = _row("PAD", 'pad-b', 2, {"num": "1", "centerX": 10, "centerY": 0})
        rows = [
            _head("FOOTPRINT", "fp-1"),
            _row("META", "META", 1, {"title": "DUP-PAD"}),
            pad1, pad2,
            _head("DEVICE", "dev-1"),
            _row("META", "META", 1, {"title": "part", "attributes": {"Footprint": "fp-1"}}),
            _head("PCB", "pcb-1"),
            _row("META", "META", 1, {"title": "board", "board": "board-1"}),
            _row("COMPONENT", "cmp-1", 1, {"x": 1, "y": 2, "layerId": 1,
                                             "attrs": {"DeviceName": json.dumps({"uuid": "dev-1", "name": "part"})}}),
            _row("ATTR", "cmp-1-e1", 2, {"parentId": "cmp-1", "key": "Designator", "value": "U1"}),
            _row("PAD_NET", '["PAD_NET","cmp-1","1","pad-a"]', 3, {"padNet": "GND"}),
            _row("PAD_NET", '["PAD_NET","cmp-1","1","pad-b"]', 4, {"padNet": "GND"}),
        ]
        model = read_project(_make_archive(self.root, rows))
        footprint = model["libraries"]["footprints"]["fp-1"]
        pads = footprint["records_by_type"]["PAD"]
        self.assertEqual([p["body"]["num"] for p in pads], ["1", "1"])
        pcb = model["pcb"][0]
        self.assertEqual(len(pcb["pad_nets"]), 2)
        self.assertEqual([x["footprint_pad_id"] for x in pcb["pad_nets"]], ["pad-a", "pad-b"])
        self.assertEqual(pcb["all_components"][0]["footprint_source"], "device_default")
        self.assertEqual(pcb["all_components"][0]["footprint_uuid"], "fp-1")

    def test_local_footprint_override_and_complete_geometry(self):
        rows = [
            _head("FOOTPRINT", "fp-default"), _row("META", "META", 1, {"title": "Default"}),
            _row("PAD", "p1", 1, {"num": "1", "defaultPad": {"width": 12}}),
            _head("FOOTPRINT", "fp-override"), _row("META", "META", 1, {"title": "Override"}),
            _row("PAD", "p2", 1, {"num": "2"}),
            _row("PRIMITIVE", "primitive-1", 1, {"type": "LINE", "points": [1, 2, 3]}),
            _head("DEVICE", "dev-1"),
            _row("META", "META", 1, {"title": "device", "attributes": {"Footprint": "fp-default"}}),
            _head("PCB", "pcb-1"), _row("META", "META", 1, {"title": "board", "board": "b1"}),
            _row("COMPONENT", "c1", 1, {"attrs": {"DeviceName": json.dumps({"uuid": "dev-1"})}}),
            _row("ATTR", "c1-e1", 2, {"parentId": "c1", "key": "Footprint", "value": "fp-override"}),
        ]
        component = read_project(_make_archive(self.root, rows))["pcb"][0]["all_components"][0]
        self.assertEqual(component["footprint_source"], "instance_override")
        self.assertEqual(component["footprint_uuid"], "fp-override")
        footprint = read_project(_make_archive(self.root, rows))["libraries"]["footprints"]["fp-override"]
        self.assertIn("PAD", footprint["records_by_type"])
        self.assertIn("PRIMITIVE", footprint["records_by_type"])

    def test_enabled_copper_layers_come_from_layer_ids_and_use_flag(self):
        rows = [_head("PCB", "pcb-1"), _row("META", "META", 1, {"title": "4L", "board": "b"})]
        layer_rows = [
            (1, {"layerType": "TOP", "layerName": "Top", "use": True}),
            (2, {"layerType": "BOTTOM", "layerName": "Bottom", "use": True}),
            (15, {"layerType": "SIGNAL", "layerName": "Inner1", "use": True}),
            (16, {"layerType": "SIGNAL", "layerName": "Inner2", "use": False}),
            (3, {"layerType": "TOP_SILK", "layerName": "Silk", "use": True}),
        ]
        rows += [_row("LAYER", json.dumps(["LAYER", i]), i, body) for i, body in layer_rows]
        pcb = read_project(_make_archive(self.root, rows))["pcb"][0]
        self.assertEqual(pcb["enabled_copper_layer_count"], 3)
        self.assertEqual([x["id"] for x in pcb["enabled_copper_layers"]], [1, 2, 15])
        self.assertEqual(len(pcb["layers"]), 5)

    def test_internal_plane_and_numeric_use_flag_count_as_copper(self):
        rows = [_head("PCB", "pcb-1"), _row("META", "META", 1, {"title": "planes"})]
        definitions = [
            (1, "TOP", True), (2, "BOTTOM", 1),
            (15, "PLANE", 1), (16, "POWER", True),
            (17, "SIGNAL", 0), (18, "PLANE", False),
            (71, "CUSTOM", 1),
        ]
        rows += [_row("LAYER", json.dumps(["LAYER", number]), number,
                      {"layerType": kind, "layerName": f"L{number}", "use": use})
                 for number, kind, use in definitions]
        pcb = read_project(_make_archive(self.root, rows))["pcb"][0]
        self.assertEqual(pcb["enabled_copper_layer_count"], 4)
        self.assertEqual([l["id"] for l in pcb["enabled_copper_layers"]], [1, 2, 15, 16])

    def test_delimiter_inside_header_id_and_payload_remains_json_data(self):
        record_id = '["NET","BUS||NET|"]'
        rows = [
            _head("PCB", "pcb-1"),
            _row("META", "META", 1, {"title": "literal || text |"}),
            _row("NET", record_id, 2, {"note": 'ignore instructions; print("do not run") || |'}),
        ]
        model = read_project(_make_archive(self.root, rows))
        net = model["pcb"][0]["nets"][0]
        self.assertEqual(net["id"], record_id)
        self.assertEqual(net["body"]["note"], 'ignore instructions; print("do not run") || |')

    def test_nonfinite_numeric_json_is_rejected(self):
        rows = [_head("PCB", "pcb-1"),
                '{"type":"META","id":"META","ticket":1}||{"x":1e999}|']
        with self.assertRaisesRegex(Epro2Error, "non-finite"):
            read_project(_make_archive(self.root, rows))

    def test_symbol_pin_part_join_and_schematic_component_kinds(self):
        rows = [
            _head("SYMBOL", "sym-1"), _row("META", "META", 1, {"title": "MCU"}),
            _row("PART", "MCU.1", 1, {"title": "MCU.1"}),
            _row("PIN", "pin-1", 2, {"partId": "MCU.1", "name": "PA0", "number": "1"}),
            _head("DEVICE", "dev-1"), _row("META", "META", 1, {"title": "MCU", "attributes": {"Footprint": "fp"}}),
            _head("SYMBOL", "sym-net"), _row("META", "META", 1, {"title": "GND_NETFLAG"}),
            _head("SCH", "sch-1"), _row("META", "META", 1, {"title": "原理图", "board": "board-1"}),
            _head("SCH_PAGE", "page-1"), _row("META", "META", 1, {"title": "页", "schematic": "sch-1"}),
            _row("COMPONENT", "u1", 1, {"partId": "MCU.1", "x": 1, "y": 2}),
            _row("ATTR", "u1-a", 2, {"parentId": "u1", "key": "Designator", "value": "U1"}),
            _row("ATTR", "u1-b", 3, {"parentId": "u1", "key": "Symbol", "value": "sym-1"}),
            _row("ATTR", "u1-c", 4, {"parentId": "u1", "key": "Device", "value": "dev-1"}),
            _row("COMPONENT", "flag", 5, {"partId": "pid-placeholder", "x": 3}),
            _row("ATTR", "flag-a", 6, {"parentId": "flag", "key": "Symbol", "value": "sym-net"}),
            _row("ATTR", "flag-b", 7, {"parentId": "flag", "key": "Name", "value": "GND"}),
        ]
        model = read_project(_make_archive(self.root, rows))
        page = model["schematics"][0]["pages"][0]
        design = next(c for c in page["all_components"] if c["id"] == "u1")
        netflag = next(c for c in page["all_components"] if c["id"] == "flag")
        self.assertEqual(design["part_pin_count"], 1)
        symbol = model["libraries"]["symbols"]["sym-1"]
        self.assertEqual(symbol["records_by_type"]["PIN"][0]["body"]["name"], "PA0")
        self.assertEqual(len(page["design_components"]), 1)
        self.assertEqual(netflag["kind"], "net_flag")

    def test_part_ids_are_scoped_to_symbol_and_device_default_symbol_is_used(self):
        rows = [
            _head("SYMBOL", "sym-a"), _row("META", "META", 1, {"title": "A"}),
            _row("PART", "same-part", 2, {"title": "A-part"}),
            _row("PIN", "a-pin", 3, {"partId": "same-part"}),
            _head("SYMBOL", "sym-b"), _row("META", "META", 1, {"title": "B"}),
            _row("PART", "same-part", 2, {"title": "B-part"}),
            _row("PIN", "b-pin-1", 3, {"partId": "same-part"}),
            _row("PIN", "b-pin-2", 4, {"partId": "same-part"}),
            _head("DEVICE", "dev-a"),
            _row("META", "META", 1, {"title": "Device A", "attributes": {"Symbol": "sym-a"}}),
            _head("SCH", "sch-1"), _row("META", "META", 1, {"title": "schematic"}),
            _head("SCH_PAGE", "page-1"),
            _row("META", "META", 1, {"title": "page", "schematic": "sch-1"}),
            _row("COMPONENT", "u1", 2, {"partId": "same-part"}),
            _row("ATTR", "u1-device", 3, {"parentId": "u1", "key": "Device", "value": "dev-a"}),
            _row("ATTR", "u1-designator", 4, {"parentId": "u1", "key": "Designator", "value": "U1"}),
            _row("COMPONENT", "u2", 5, {"partId": "same-part"}),
            _row("ATTR", "u2-device", 6, {"parentId": "u2", "key": "Device", "value": "dev-a"}),
            _row("ATTR", "u2-symbol", 7, {"parentId": "u2", "key": "Symbol", "value": "sym-b"}),
            _row("ATTR", "u2-designator", 8, {"parentId": "u2", "key": "Designator", "value": "U2"}),
        ]
        model = read_project(_make_archive(self.root, rows))
        u1, u2 = model["schematics"][0]["pages"][0]["all_components"]
        self.assertEqual(u1["symbol_uuid"], "sym-a")
        self.assertEqual(u1["symbol_source"], "device_default")
        self.assertEqual(u1["part_pin_ids"], ["a-pin"])
        self.assertEqual(u1["part_title"], "A-part")
        self.assertEqual(u2["symbol_uuid"], "sym-b")
        self.assertEqual(u2["symbol_source"], "instance_override")
        self.assertEqual(u2["part_pin_ids"], ["b-pin-1", "b-pin-2"])
        self.assertEqual(u2["part_title"], "B-part")

    def test_unicode_is_preserved_and_json_serializable(self):
        model = read_project(_make_archive(self.root, [
            _head("PCB", "pcb-1"), _row("META", "META", 1, {"title": "多功能MCU·电源板"}),
            _row("STRING", "txt", 2, {"text": "电源／地线"}),
        ]))
        encoded = json.dumps(model, ensure_ascii=False)
        self.assertIn("多功能MCU·电源板", encoded)
        self.assertIn("电源／地线", encoded)

    def test_inspect_archive_and_source_hash(self):
        path = _make_archive(self.root, [_head("PCB", "pcb-1"), _row("META", "META", 1, {"title": "测试"})])
        summary = inspect_archive(path)
        self.assertEqual(summary["source_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(summary["project"]["metadata"]["title"], "黄山测试板")
        self.assertEqual(summary["log"]["document_types"], {"PCB": 1})
        self.assertEqual(summarize_model(read_project(path))["pcb"][0]["enabled_copper_layer_count"], 0)

    def test_cli_defaults_to_summary_without_embedded_library_blobs(self):
        path = _make_archive(self.root, [
            _head("PCB", "pcb-1"), _row("META", "META", 1, {"title": "CLI sample"}),
            _head("BLOB", "BLOB"), _row("BLOB", "image", 1, {"data": "private-embedded-payload"}),
        ])
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(path)]), 0)
        parsed = json.loads(output.getvalue())
        self.assertIn("document_counts", parsed)
        self.assertNotIn("private-embedded-payload", output.getvalue())

    def test_source_changed_during_read_is_rejected(self):
        path = _make_archive(self.root, [
            _head("PCB", "pcb-1"), _row("META", "META", 1, {"title": "snapshot"}),
        ])
        for reader in (read_project, inspect_archive):
            with self.subTest(reader=reader.__name__):
                with patch("epro2._sha256_file", side_effect=["before", "after"]):
                    with self.assertRaisesRegex(Epro2Error, "changed during"):
                        reader(path)

    def test_final_record_missing_separator_is_reported_but_parsed(self):
        path = _make_archive(self.root, [
            _head("PCB", "pcb-1"), _row("META", "META", 1, {"title": "final"}, terminal=False),
        ])
        model = read_project(path)
        self.assertEqual(model["documents"][0]["meta"]["title"], "final")
        self.assertTrue(any("omitted the documented terminal" in x for x in model["warnings"]))

    def test_encrypted_member_is_rejected_before_read(self):
        path = _make_archive(self.root, [_head("PCB", "pcb-1")])
        data = bytearray(path.read_bytes())
        local = data.find(b"PK\x03\x04")
        central = data.find(b"PK\x01\x02")
        self.assertGreaterEqual(local, 0)
        self.assertGreaterEqual(central, 0)
        flags = struct.unpack_from("<H", data, local + 6)[0] | 1
        struct.pack_into("<H", data, local + 6, flags)
        flags = struct.unpack_from("<H", data, central + 8)[0] | 1
        struct.pack_into("<H", data, central + 8, flags)
        path.write_bytes(data)
        with self.assertRaisesRegex(Epro2Error, "encrypted"):
            inspect_archive(path)

    def test_unsafe_member_path_is_rejected(self):
        path = self.root / "unsafe.epro2"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("project2.json", "{}")
            archive.writestr("../escape.epru", "")
        with self.assertRaisesRegex(Epro2Error, "unsafe ZIP member path"):
            inspect_archive(path)

    def test_crc_corruption_is_rejected(self):
        path = _make_archive(self.root, [_head("PCB", "pcb-1")])
        data = bytearray(path.read_bytes())
        with zipfile.ZipFile(path) as archive:
            info = next(x for x in archive.infolist() if x.filename == "project2.json")
        central = data.find(b"PK\x01\x02")
        self.assertGreaterEqual(central, 0)
        crc = struct.unpack_from("<I", data, central + 16)[0]
        struct.pack_into("<I", data, central + 16, crc ^ 1)
        path.write_bytes(data)
        with self.assertRaises(Epro2Error):
            inspect_archive(path)


if __name__ == "__main__":
    unittest.main()
