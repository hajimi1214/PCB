#!/usr/bin/env python3
"""Portable checks for this knowledge repository, not for PCB designs."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _local_reference(root: Path, base: Path, value: str, context: str, errors: list[str]) -> Path | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{context}: expected a non-empty relative path")
        return None
    if Path(value).is_absolute() or ".." in value.replace("\\", "/").split("/"):
        errors.append(f"{context}: path must stay inside the plugin package")
        return None
    target = (base / value).resolve()
    if not target.is_relative_to(root.resolve()) or not target.exists():
        errors.append(f"{context}: referenced path is missing or outside the repository")
        return None
    return target


def check_plugin(root: Path) -> list[str]:
    """Validate the repo-local Codex plugin's references and identity wiring."""
    errors: list[str] = []
    manifest_path = root / ".codex-plugin" / "plugin.json"
    marketplace_path = root / ".agents" / "plugins" / "marketplace.json"
    mcp_path = root / ".mcp.json"
    config_path = root / ".codex" / "config.toml"
    paths = (manifest_path, marketplace_path, mcp_path, config_path)
    if not any(path.exists() for path in paths):
        return errors
    if not all(path.is_file() for path in paths):
        missing = [str(path.relative_to(root)) for path in paths if not path.is_file()]
        return ["plugin configuration incomplete: " + ", ".join(missing)]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"plugin JSON invalid: {type(exc).__name__}"]
    if not isinstance(manifest, dict) or not isinstance(manifest.get("name"), str) or not manifest["name"]:
        errors.append(".codex-plugin/plugin.json: missing plugin name")
        return errors
    name = manifest["name"]
    _local_reference(root, root, manifest.get("skills", ""), "plugin skills", errors)
    mcp_reference = _local_reference(root, root, manifest.get("mcpServers", ""), "plugin MCP reference", errors)
    if mcp_reference is not None and mcp_reference != mcp_path.resolve():
        errors.append("plugin manifest must reference the repository's .mcp.json")
    servers = mcp.get("mcpServers") if isinstance(mcp, dict) else None
    if not isinstance(servers, dict) or not servers:
        errors.append(".mcp.json: mcpServers must contain a server")
        servers = {}
    for server_name, server in servers.items():
        if not isinstance(server, dict) or not isinstance(server.get("command"), str):
            errors.append(f".mcp.json: {server_name} must have a command")
            continue
        if server.get("command") != "python":
            errors.append(f".mcp.json: {server_name} must use the portable python launcher")
        args = server.get("args")
        if not isinstance(args, list) or not args or not isinstance(args[0], str):
            errors.append(f".mcp.json: {server_name} must reference its local server script")
            continue
        _local_reference(root, root, args[0], f".mcp.json server {server_name}", errors)
        enabled_tools = server.get("enabled_tools", [])
        if not isinstance(enabled_tools, list) or any(not isinstance(x, str) for x in enabled_tools):
            errors.append(f".mcp.json: {server_name} enabled_tools must be a string list")
    market_name = marketplace.get("name") if isinstance(marketplace, dict) else None
    entries = marketplace.get("plugins", []) if isinstance(marketplace, dict) else []
    matches = [entry for entry in entries if isinstance(entry, dict) and entry.get("name") == name]
    if not isinstance(market_name, str) or not market_name or len(matches) != 1:
        errors.append("marketplace must contain exactly one matching plugin entry")
    else:
        source = matches[0].get("source")
        if not isinstance(source, dict) or source.get("source") != "local":
            errors.append("marketplace plugin source must be local")
        else:
            target = _local_reference(root, root, source.get("path", ""), "marketplace plugin path", errors)
            if target is not None and target.resolve() != root.resolve():
                referenced_manifest = target / ".codex-plugin" / "plugin.json"
                if not referenced_manifest.is_file():
                    errors.append("marketplace plugin path does not contain .codex-plugin/plugin.json")
                else:
                    try:
                        if json.loads(referenced_manifest.read_text(encoding="utf-8")).get("name") != name:
                            errors.append("marketplace plugin identity does not match its manifest")
                    except (OSError, json.JSONDecodeError):
                        errors.append("marketplace plugin manifest is invalid")
    config = config_path.read_text(encoding="utf-8")
    escaped = re.escape(name)
    marketplace_escaped = re.escape(market_name) if isinstance(market_name, str) else "(?!)"
    section = re.search(
        rf'^\[plugins\."{escaped}@{marketplace_escaped}"\]\s*\nenabled\s*=\s*true\s*$',
        config,
        re.M,
    )
    if section is None:
        errors.append(".codex/config.toml must enable the matching repo-local plugin")
    return errors


def check_repo(root: Path) -> list[str]:
    errors = check_plugin(root)
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root)
        if any(p in relative.parts for p in (".git", "snapshots", "raw", "local", ".venv", "__pycache__")):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            for match in LINK.finditer(line):
                target = match.group(1).strip("<>")
                if target.startswith("#") or urlsplit(target).scheme:
                    continue
                if "slug.md" in target or "YYYY-MM-DD.md" in target:
                    # The wiki bootstrap template contains illustrative links.
                    continue
                target = unquote(target.split("#")[0])
                dest = (path.parent / target).resolve()
                if not dest.is_relative_to(root.resolve()):
                    errors.append(f"{relative}:{number}: link leaves project: {target}")
                elif not dest.exists():
                    errors.append(f"{relative}:{number}: broken local link: {target}")
    index_path = root / "wiki" / "index.md"
    if not index_path.is_file():
        errors.append("wiki/index.md missing")
        return errors
    indexed = [(index_path.parent / x.split("#")[0]).resolve() for x in LINK.findall(index_path.read_text(encoding="utf-8"))
               if not urlsplit(x).scheme and x.split("#")[0]]
    for path in (root / "wiki").rglob("*.md"):
        if path.name in ("hot.md", "index.md", "log.md") or "reports" in path.relative_to(root / "wiki").parts:
            continue
        count = indexed.count(path.resolve())
        if count != 1:
            errors.append(f"{path.relative_to(root)}: expected one index entry, got {count}")
    return errors


if __name__ == "__main__":
    errors = check_repo(ROOT)
    for error in errors:
        print(f"ERROR: {error}")
    print(f"Repository link/index errors: {len(errors)}")
    raise SystemExit(int(bool(errors)))

