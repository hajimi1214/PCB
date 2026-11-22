"""Start the repository-local, allowlisted Windows-MCP stdio server."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "local" / "windows-mcp-venv" / "Scripts" / "python.exe"
ARGS = [
    "-m", "windows_mcp", "serve", "--transport", "stdio", "--control",
    "--control-policy", "relaxed", "--control-idle-timeout", "10",
    "--tools", "App,Snapshot,Screenshot,Click,Type,Shortcut,Wait,WaitFor,ControlStatus",
]


def main() -> int:
    if not SERVER.is_file() or not SERVER.resolve().is_relative_to((ROOT / "local").resolve()):
        print("Windows-MCP local Python environment is not installed under this project.", file=sys.stderr)
        return 2
    try:
        return subprocess.call(
            [str(SERVER), *ARGS],
            stdin=sys.stdin.buffer,
            stdout=sys.stdout.buffer,
            stderr=sys.stderr.buffer,
        )
    except OSError as exc:
        print(f"Windows-MCP could not start: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
