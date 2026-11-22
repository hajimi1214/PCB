import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pcb import search, source_path, verify_sources
from check_repo import check_plugin, check_repo


class SourceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        folder = self.root / "research" / "example"
        folder.mkdir(parents=True)
        self.snapshot = folder / "snapshots" / "original.txt"
        self.snapshot.parent.mkdir()
        self.snapshot.write_bytes(b"manufacturer evidence")
        self.record = dict(id="EX-01", title="Example", url="https://example.org/doc",
                           local_path="research/example/snapshots/original.txt",
                           sha256=hashlib.sha256(self.snapshot.read_bytes()).hexdigest(),
                           retrieved_at="2026-11-21T12:00:00+08:00", authority="example manufacturer",
                           license_or_terms="local research only", claims=["Section 1"], limitations=["Not board validation"])
        self.manifest = folder / "sources.json"
        self.save()

    def save(self, records=None):
        self.manifest.write_text(json.dumps(records if records is not None else [self.record]), encoding="utf-8")

    def test_real_bytes_and_corruption(self):
        self.assertEqual(verify_sources(self.root, True)["verified_snapshots"], 1)
        self.snapshot.write_bytes(b"changed")
        self.assertIn("SHA-256 mismatch", " ".join(verify_sources(self.root)["errors"]))

    def test_missing_snapshots_are_explicit_and_strict_mode_fails(self):
        self.snapshot.unlink()
        normal = verify_sources(self.root)
        self.assertEqual(normal["verified_snapshots"], 0)
        self.assertEqual(normal["missing_snapshots"], ["EX-01"])
        self.assertFalse(normal["errors"])
        self.assertTrue(verify_sources(self.root, True)["errors"])

    def test_path_cannot_escape_project(self):
        for path in ("../outside", "research/../../outside", "C:\\secret", "/etc/passwd"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                source_path(self.root, path)

    def test_duplicate_ids_and_missing_evidence(self):
        self.save([self.record, self.record])
        self.assertIn("duplicate", " ".join(verify_sources(self.root)["errors"]))
        self.record.pop("claims")
        self.save()
        self.assertIn("missing fields", " ".join(verify_sources(self.root)["errors"]))

    def test_malformed_json_is_reported(self):
        self.manifest.write_text("not JSON", encoding="utf-8")
        self.assertTrue(verify_sources(self.root)["errors"])


class KnowledgeNavigationTests(unittest.TestCase):
    def test_chinese_and_case_insensitive_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wiki = root / "wiki"
            wiki.mkdir()
            (wiki / "return-path.md").write_text("# 回流路径\n参考平面应连续，USB 使用实际叠层。", encoding="utf-8")
            (wiki / "misc.md").write_text("# 其他\n不相关内容。", encoding="utf-8")
            self.assertEqual(search(root, "回流路径")[0]["path"], "wiki/return-path.md")
            self.assertEqual(search(root, "usb")[0]["line"], 2)
            self.assertEqual(search(root, "unfindable"), [])

    def test_broken_links_and_index_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "wiki").mkdir()
            (root / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")
            (root / "wiki" / "page.md").write_text("# Page\n[missing](absent.md)", encoding="utf-8")
            errors = check_repo(root)
            self.assertTrue(any("broken local link" in e for e in errors))
            self.assertTrue(any("index entry" in e for e in errors))
            (root / "wiki" / "index.md").write_text("# Index\n- [Page](page.md)", encoding="utf-8")
            (root / "wiki" / "page.md").write_text("# Page\n[Home](index.md)", encoding="utf-8")
            self.assertEqual(check_repo(root), [])

    def test_plugin_references_and_repo_marketplace_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "pcb").mkdir(parents=True)
            (root / "skills" / "pcb" / "SKILL.md").write_text("# PCB", encoding="utf-8")
            (root / "tools").mkdir()
            (root / "tools" / "server.py").write_text("pass", encoding="utf-8")
            (root / ".codex-plugin").mkdir()
            (root / ".agents" / "plugins").mkdir(parents=True)
            (root / ".codex").mkdir()
            (root / ".codex-plugin" / "plugin.json").write_text(json.dumps({
                "name": "pcb", "skills": "./skills/pcb/", "mcpServers": "./.mcp.json",
            }), encoding="utf-8")
            (root / ".mcp.json").write_text(json.dumps({"mcpServers": {
                "pcb": {"command": "python", "args": ["tools/server.py"], "enabled_tools": ["search"]},
            }}), encoding="utf-8")
            (root / ".agents" / "plugins" / "marketplace.json").write_text(json.dumps({
                "name": "local-pcb", "plugins": [{"name": "pcb", "source": {"source": "local", "path": "./"}}],
            }), encoding="utf-8")
            (root / ".codex" / "config.toml").write_text(
                '[plugins."pcb@local-pcb"]\nenabled = true\n', encoding="utf-8"
            )
            self.assertEqual(check_plugin(root), [])
            (root / ".agents" / "plugins" / "marketplace.json").write_text(json.dumps({
                "name": "wrong", "plugins": [{"name": "other", "source": {"source": "local", "path": "./"}}],
            }), encoding="utf-8")
            self.assertTrue(check_plugin(root))

if __name__ == "__main__":
    unittest.main()
