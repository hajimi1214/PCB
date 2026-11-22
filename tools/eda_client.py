"""Bounded transports for fixed, reviewed LCEDA Pro actions.

No method accepts JavaScript source. Runtime responses are untrusted data and
transport success never implies that a board, netlist, or DRC passed.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
ACTION_DIR = ROOT / "tools" / "eda_actions"
BRIDGE_PORTS = tuple(range(49620, 49630))
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_SCRIPT_BYTES = 256 * 1024
MAX_ARGS_BYTES = 32 * 1024
MAX_JSON_DEPTH = 64
READ_ONLY_ACTIONS = frozenset({
    "inspect_environment", "inspect_project", "inspect_project_by_slug", "open_project_schematic_page", "inspect_reference_library_items", "inspect_project_library_item", "export_connectivity", "inspect_drc", "inspect_source_stability", "inspect_ratlines",
})
DRAWING_ACTIONS = frozenset({"focus_working_copy", "drawing_state", "apply_drawing_batch", "export_drawing_copy",
                             "start_auto_route", "auto_route_status", "cancel_auto_route", "open_project_pcb",
                             "create_gui_pcb_copy", "delete_gui_pcb_copy", "export_manufacturing",
                             "import_reference_project", "create_board_from_schematic", "initialize_layout_board",
                             "associate_reference_layout_board", "register_visual_layout_target"})

ACTION_ARGUMENTS = {
    "focus_working_copy": {"pcb_uuid": str, "expected_project_uuid": str},
    "drawing_state": {"pcb_uuid": str, "expected_project_uuid": str},
    "apply_drawing_batch": {"pcb_uuid": str, "expected_project_uuid": str, "expected_source_sha256": str,
                            "plan_id": str, "operations": list},
    "export_drawing_copy": {"pcb_uuid": str, "expected_project_uuid": str, "expected_source_sha256": str,"artifact_path":str},
    "export_manufacturing": {"pcb_uuid":str,"expected_project_uuid":str,"expected_source_sha256":str,"artifact_directory":str},
    "import_reference_project": {"source_path":str,"project_slug":str,"project_friendly_name":str,"file_type":str,"destination":str},
    "create_board_from_schematic": {"expected_project_uuid":str,"source_board_name":str,"source_pcb_uuid":str,"schematic_uuid":str},
    "initialize_layout_board": {"expected_project_uuid":str,"source_board_name":str,"source_pcb_uuid":str,"source_schematic_uuid":str,
                                "layout_board_name":str,"layout_pcb_uuid":str,"layout_schematic_uuid":str},
    "associate_reference_layout_board":{"expected_project_uuid":str,"source_board_name":str,"source_pcb_uuid":str,
                                "source_schematic_uuid":str,"layout_pcb_uuid":str,"layout_schematic_uuid":str},
    "register_visual_layout_target":{"expected_project_uuid":str,"source_board_name":str,"source_pcb_uuid":str,
                                "layout_board_name":str,"layout_pcb_uuid":str},
    "start_auto_route": {"pcb_uuid":str,"expected_project_uuid":str,"expected_source_sha256":str,"routing_nets":list,"layers":list},
    "auto_route_status": {"pcb_uuid":str,"expected_project_uuid":str,"expected_source_sha256":str,"job_id":str},
    "cancel_auto_route": {"pcb_uuid":str,"expected_project_uuid":str,"job_id":str},
    "open_project_pcb": {"pcb_uuid":str,"expected_project_uuid":str},
    "create_gui_pcb_copy":{"source_pcb_uuid":str,"expected_project_uuid":str},
    "delete_gui_pcb_copy":{"source_pcb_uuid":str,"source_schematic_uuid":str,"expected_project_uuid":str,
                            "copy_board_name":str,"copy_pcb_uuid":str,"copy_schematic_uuid":str},
    "inspect_environment": {"expected_document_uuid": str},
    "inspect_project": {"expected_project_uuid": str, "expected_document_uuid": str},
    "inspect_project_by_slug": {"project_slug":str},
    "open_project_schematic_page":{"expected_project_uuid":str,"board_name":str,"pcb_uuid":str,"schematic_uuid":str,"page_uuid":str},
    "inspect_reference_library_items":{"device_uuid":str,"footprint_uuid":str},
    "inspect_project_library_item":{"library_uuid":str,"device_uuid":str,"footprint_uuid":str},
    "inspect_source_stability":{"expected_document_uuid":str,"expected_project_uuid":str},
    "inspect_ratlines":{"pcb_uuid":str,"expected_document_uuid":str,"expected_project_uuid":str},
    "export_connectivity": {
        "pcb_uuid": str, "expected_project_uuid": str, "expected_document_uuid": str,
        "component_offset": int, "limit": int, "pad_offset": int, "artifact_path": str,
    },
    "inspect_drc": {
        "pcb_uuid": str, "expected_project_uuid": str, "expected_document_uuid": str,
        "run": bool,
    },
}


class EdaClientError(ValueError):
    """Invalid client configuration or action arguments, without raw tool data."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _reject_constant(_token: str):
    raise EdaClientError("Non-finite JSON values are unsupported.")


def _strict_json(data: bytes) -> Any:
    try:
        value = json.loads(data.decode("utf-8-sig"), parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EdaClientError("Response is not a complete UTF-8 JSON document.") from exc
    stack = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise EdaClientError("JSON response nesting exceeds the local limit.")
        if isinstance(node, float) and not math.isfinite(node):
            raise EdaClientError("Non-finite JSON values are unsupported.")
        if isinstance(node, dict):
            stack.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, list):
            stack.extend((v, depth + 1) for v in node)
    return value


def _safe_value(value: Any) -> Any:
    """Retain useful JSON data while suppressing credential-bearing fields/logs."""
    if isinstance(value, dict):
        output = {}
        for key, child in value.items():
            normalized = re.sub(r"[^a-z]", "", key.casefold())
            if normalized in {"logs", "stdout", "stderr", "stack", "stacktrace"}:
                continue
            if any(token in normalized for token in ("password", "secret", "token", "apikey", "authorization", "cookie", "credential")):
                output[key] = "[redacted]"
            else:
                output[key] = _safe_value(child)
        return output
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"\b(?:sk|pk)-[A-Za-z0-9_-]{12,}", "[redacted]", value)
        value = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redacted]", value)
        value = re.sub(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1[redacted]@", value)
        value = re.sub(r"(?i)\b(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;&]+", r"\1=[redacted]", value)
    return value


def _outcome(status: str, backend: str, *, transport_ok: bool = False,
             business_status: str = "unknown", value: Any = None, reason: str | None = None,
             evidence: dict | None = None) -> dict:
    result = {
        "status": status, "backend": backend, "transport_ok": transport_ok,
        "business_status": business_status, "value": _safe_value(value),
        "evidence": evidence or {},
    }
    if reason:
        result["reason"] = reason
    return result


def _business(value: Any) -> tuple[str, str]:
    """Interpret only explicit business markers; unknown objects remain unknown."""
    if not isinstance(value, dict):
        return "unknown", "unknown"
    status = value.get("status")
    if status == "started" and value.get("ok") is True:
        return "started", "in_progress"
    if isinstance(status, str) and status in {"unsupported", "unavailable", "mismatch", "target_mismatch", "rejected", "error", "failed"}:
        return ("error" if status == "failed" else status), ("failed" if status in {"error", "failed", "mismatch", "target_mismatch", "rejected"} else "unknown")
    if value.get("ok") is False or value.get("success") is False:
        return "error", "failed"
    if status is not None and (not isinstance(status, str) or status not in {"ok", "available", "completed", "observed"}):
        return "unknown", "unknown"
    if status == "observed" and value.get("ok") is True:
        return "observed", "observed"
    if isinstance(status, str) and status in {"ok", "available", "completed"} or value.get("ok") is True or value.get("success") is True:
        return "ok", "ok"
    return "unknown", "unknown"


def _loopback_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 300:
        raise EdaClientError("bridge_url must be a short loopback HTTP URL.")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise EdaClientError("Invalid loopback bridge URL.") from exc
    if (parts.scheme not in {"http", "https"} or parts.username is not None or parts.password is not None
            or parts.path not in {"", "/"} or parts.query or parts.fragment or not host):
        raise EdaClientError("Bridge URL must be a loopback origin without credentials, path, or query.")
    if host.casefold() == "localhost":
        host = "127.0.0.1"  # Never rely on arbitrary name resolution for the bridge.
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise EdaClientError("Only literal loopback IP addresses are supported.") from exc
    if not address.is_loopback:
        raise EdaClientError("Non-loopback bridge URLs are not allowed.")
    if port is None:
        port = 443 if parts.scheme == "https" else 80
    if not 1 <= port <= 65535:
        raise EdaClientError("Invalid loopback bridge port.")
    formatted_host = f"[{address}]" if address.version == 6 else str(address)
    return f"{parts.scheme}://{formatted_host}:{port}"


class EdaClient:
    def __init__(self, executable: str | Path | None = None, bridge_url: str | None = None,
                 timeout: float = 10, *, action_dir: str | Path | None = None,
                 allow_drc_run: bool = False, allow_drawing: bool = False):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 120:
            raise EdaClientError("timeout must be a finite number between 0 and 120 seconds.")
        self.timeout = float(timeout)
        self.executable = str(executable) if executable is not None else (shutil.which("lceda-pro") or shutil.which("easyeda-pro"))
        if self.executable is not None and (not self.executable or any(c in self.executable for c in "\x00\r\n")):
            raise EdaClientError("Invalid CLI executable argument.")
        if self.executable is not None and Path(self.executable).suffix.casefold() in {".cmd", ".bat", ".ps1"}:
            raise EdaClientError("Shell wrapper executables are not supported; use the official CLI executable.")
        self.bridge_url = _loopback_url(bridge_url) if bridge_url is not None else None
        self.action_dir = Path(action_dir) if action_dir is not None else ACTION_DIR
        self.allow_drc_run = allow_drc_run is True
        self.allow_drawing = allow_drawing is True
        self._selected_bridge: str | None = None
        self._known_sessions: dict[str, str] = {}
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def _run_cli(self, arguments: list[str], operation: str) -> dict:
        evidence = {"operation": operation}
        if self.executable is None:
            return _outcome("unavailable", "cli", reason="CLI executable was not found on PATH.", evidence=evidence)
        try:
            process = subprocess.Popen(
                [self.executable, *arguments], shell=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except (OSError, ValueError):
            return _outcome("unavailable", "cli", reason="The configured CLI could not be executed.", evidence=evidence)
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        total = [0]
        lock = threading.Lock()
        overflow = threading.Event()

        def read_pipe(name, pipe):
            try:
                while True:
                    block = pipe.read(65536)
                    if not block:
                        break
                    with lock:
                        total[0] += len(block)
                        if total[0] > MAX_OUTPUT_BYTES:
                            overflow.set()
                        else:
                            buffers[name].extend(block)
                    if overflow.is_set():
                        try:
                            process.kill()
                        except OSError:
                            pass
                        break
            except (OSError, ValueError):
                pass

        readers = [threading.Thread(target=read_pipe, args=(name, pipe), daemon=True)
                   for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr))]
        for thread in readers:
            thread.start()
        try:
            exit_code = process.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
            for thread in readers:
                thread.join(timeout=0.2)
            return _outcome("timeout", "cli", reason="CLI exceeded the bounded execution timeout.", evidence=evidence)
        for thread in readers:
            thread.join(timeout=0.2)
        if any(thread.is_alive() for thread in readers):
            return _outcome("unsupported", "cli", reason="CLI output streams did not close within the local limit.", evidence=evidence)
        for pipe in (process.stdout, process.stderr):
            try:
                pipe.close()
            except OSError:
                pass
        evidence["exit_code"] = exit_code
        if overflow.is_set():
            return _outcome("rejected", "cli", reason="CLI output exceeded the local byte limit.", evidence=evidence)
        if exit_code != 0:
            return _outcome("error", "cli", reason="CLI returned a nonzero process exit code.", evidence=evidence)
        if not buffers["stdout"].strip():
            return _outcome("unsupported", "cli", reason="CLI exited without a JSON stdout result; execution is not confirmed.", evidence=evidence)
        try:
            envelope = _strict_json(bytes(buffers["stdout"]))
        except EdaClientError:
            return _outcome("unsupported", "cli", reason="CLI did not return one complete JSON result envelope.", evidence=evidence)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("ok"), bool):
            return _outcome("unsupported", "cli", reason="CLI JSON did not match the official ok/value envelope.", evidence=evidence)
        if envelope["ok"] is False:
            return _outcome("error", "cli", transport_ok=True, business_status="failed",
                            reason="The CLI envelope reported failure.", evidence=evidence)
        if "value" not in envelope:
            return _outcome("unknown", "cli", transport_ok=True,
                            reason="CLI reported ok without a value; business result is unknown.", evidence=evidence)
        return _outcome("ok", "cli", transport_ok=True, value=envelope["value"], evidence=evidence)

    def _http_json(self, origin: str, path: str, *, payload: dict | None = None, timeout: float | None = None) -> dict:
        # Internal callers use only these known routes; do not expose URL/path/code input.
        if path not in {"/health", "/eda-windows", "/execute"}:
            raise EdaClientError("Unsupported bridge route.")
        origin = _loopback_url(origin)
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8") if payload is not None else None
        request = Request(origin + path, data=encoded, method="POST" if encoded is not None else "GET",
                          headers={"Content-Type": "application/json", "Accept": "application/json"})
        evidence = {"route": path, "origin": origin}
        budget = timeout or self.timeout
        started = time.monotonic()
        try:
            with self._opener.open(request, timeout=budget) as response:
                if response.status != 200:
                    return _outcome("error", "bridge", reason="Bridge returned a non-success HTTP status.", evidence=evidence)
                chunks, received = [], 0
                while True:
                    remaining = budget - (time.monotonic() - started)
                    if remaining <= 0:
                        raise TimeoutError()
                    sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                    if sock is not None:
                        sock.settimeout(remaining)
                    block = response.read(min(65536, MAX_OUTPUT_BYTES + 1 - received))
                    if not block:
                        break
                    chunks.append(block)
                    received += len(block)
                    if received > MAX_OUTPUT_BYTES:
                        break
                raw = b"".join(chunks)
        except HTTPError as exc:
            status = "rejected" if 300 <= exc.code < 400 else "error"
            return _outcome(status, "bridge", reason="Bridge redirect refused." if status == "rejected" else "Bridge request failed.", evidence=evidence)
        except (TimeoutError, OSError, URLError):
            return _outcome("unavailable", "bridge", reason="The loopback bridge could not be reached.", evidence=evidence)
        if len(raw) > MAX_OUTPUT_BYTES:
            return _outcome("rejected", "bridge", reason="Bridge response exceeded the local byte limit.", evidence=evidence)
        try:
            value = _strict_json(raw)
        except EdaClientError:
            return _outcome("unsupported", "bridge", reason="Bridge returned an incomplete or unsupported JSON document.", evidence=evidence)
        return _outcome("ok", "bridge", transport_ok=True, value=value, evidence=evidence)

    def _bridge_probe(self, origin: str) -> dict:
        result = self._http_json(origin, "/health", timeout=min(self.timeout, 1))
        if result["status"] != "ok":
            return result
        value = result["value"]
        if not isinstance(value, dict) or value.get("service") != "easyeda-bridge":
            return _outcome("unsupported", "bridge", transport_ok=True,
                            reason="Loopback service identity did not match easyeda-bridge.", evidence=result["evidence"])
        connected = value.get("edaConnected")
        result["status"] = "available" if connected is True else "unavailable" if connected is False else "unknown"
        result["business_status"] = "ok" if connected is True else "unknown"
        result["value"] = {k: value.get(k) for k in ("service", "edaConnected", "edaWindowCount", "activeWindowId")}
        return result

    def probe(self) -> dict:
        """Probe only the official CLI doctor and known loopback bridge health routes."""
        cli = self._run_cli(["doctor"], "doctor")
        if cli["status"] == "ok":
            value = cli["value"]
            connected = value.get("connected") if isinstance(value, dict) else None
            cli["status"] = "available" if connected is True else "unavailable" if connected is False else "unknown"
            cli["business_status"] = "ok" if connected is True else "unknown"
        candidates = [self.bridge_url] if self.bridge_url else [f"http://127.0.0.1:{p}" for p in BRIDGE_PORTS]
        bridges = [self._bridge_probe(origin) for origin in candidates]
        connected_bridges = [b for b in bridges if b["status"] == "available"]
        if connected_bridges:
            self._selected_bridge = connected_bridges[0]["evidence"]["origin"]
        bridge = connected_bridges[0] if connected_bridges else next((b for b in bridges if b["transport_ok"]), bridges[0])
        return {
            "status": "available" if cli["status"] == "available" or bridge["status"] == "available" else "unavailable",
            "backends": {"cli": cli, "bridge": bridge},
            "capabilities": {
                "list_sessions": cli["status"] == "available" or bridge["status"] == "available",
                "fixed_scripts": sorted(READ_ONLY_ACTIONS) if cli["status"] == "available" or bridge["status"] == "available" else [],
                "arbitrary_code": False, "writes": self.allow_drawing, "drc_run_enabled": self.allow_drc_run,
                "runtime_apis_verified": False,
            },
            "policy": "No application startup, installation, project opening, selection or writes are performed.",
        }

    def list_sessions(self) -> dict:
        """Read CLI sessions and verified bridge windows without selecting a target."""
        # Session identities are ephemeral; discard mappings absent from a later
        # listing before rebuilding the transport routing table.
        self._known_sessions = {}
        sessions = []
        cli = self._run_cli(["session", "list"], "session.list")
        if cli["status"] == "ok":
            if isinstance(cli["value"], list) and all(isinstance(x, dict) and isinstance(x.get("sessionId"), str) for x in cli["value"]):
                for item in cli["value"]:
                    sid = item["sessionId"]
                    sessions.append({"session_id": sid, "backend": "cli", **{k: item.get(k) for k in ("title", "status", "origin", "headless")}})
                    self._known_sessions[sid] = "cli"
                cli["business_status"] = "ok"
            else:
                cli["status"] = "unknown"
                cli["reason"] = "CLI session value did not match the documented list schema."
        origins = [self._selected_bridge] if self._selected_bridge else ([self.bridge_url] if self.bridge_url else [])
        bridge = _outcome("unavailable", "bridge", reason="No verified loopback bridge was selected; run probe first.")
        for origin in origins:
            bridge = self._bridge_probe(origin)
            if bridge["status"] != "available":
                continue
            bridge = self._http_json(origin, "/eda-windows")
            windows = bridge["value"].get("windows") if isinstance(bridge.get("value"), dict) else None
            if bridge["status"] == "ok" and isinstance(windows, list) and all(isinstance(w, dict) and isinstance(w.get("windowId"), str) for w in windows):
                for window in windows:
                    sid = window["windowId"]
                    sessions.append({"session_id": sid, "backend": "bridge", "connected": window.get("connected"), "active": window.get("active")})
                    self._known_sessions[sid] = "bridge"
                bridge["business_status"] = "ok"
            elif bridge["status"] == "ok":
                bridge["status"] = "unknown"
                bridge["reason"] = "Bridge windows did not match the documented schema."
        return {"status": "ok" if cli["status"] == "ok" or bridge["status"] == "ok" else "unavailable",
                "sessions": sessions, "backends": {"cli": cli, "bridge": bridge}}

    def _action_script(self, action: str, args: Any) -> tuple[str, dict, str]:
        if not isinstance(action, str) or action not in READ_ONLY_ACTIONS | DRAWING_ACTIONS:
            raise EdaClientError("Action is not in the fixed read-only allowlist.")
        if action in DRAWING_ACTIONS and not self.allow_drawing:
            raise EdaClientError("Drawing actions require a managed working copy.")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise EdaClientError("Action arguments must be a JSON object.")
        schema = ACTION_ARGUMENTS[action]
        if set(args) - set(schema):
            raise EdaClientError("Action contains unsupported argument keys.")
        for key, value in args.items():
            if type(value) is not schema[key]:
                raise EdaClientError("Action argument types did not match the fixed schema.")
            if isinstance(value, str) and (not value or len(value) > 256 or any(ord(c) < 32 for c in value)):
                raise EdaClientError("Action identity arguments must be short nonempty strings.")
            if type(value) is int and (value < 0 or value > 1000000):
                raise EdaClientError("Action offset arguments must remain in 0..1000000.")
        if action in {"export_connectivity", "inspect_drc", "inspect_ratlines"}:
            if any(not args.get(key) for key in ("pcb_uuid", "expected_project_uuid", "expected_document_uuid")):
                raise EdaClientError("This action requires explicit PCB, project and document UUIDs.")
        if action=="export_connectivity" and not args.get("artifact_path"):
            raise EdaClientError("Native netlist export requires a managed local path.")
        if action == "inspect_source_stability" and any(not args.get(k) for k in ("expected_document_uuid","expected_project_uuid")):
            raise EdaClientError("Source stability requires explicit project and document UUIDs.")
        if action in {"drawing_state", "apply_drawing_batch", "open_project_pcb", "export_manufacturing"} and any(not args.get(k) for k in ("pcb_uuid", "expected_project_uuid")):
            raise EdaClientError("Drawing requires PCB and project UUIDs.")
        if action=="open_project_schematic_page" and any(not args.get(k) for k in ACTION_ARGUMENTS[action]):
            raise EdaClientError("Opening a schematic page requires exact Board/project/document identities.")
        if action == "create_board_from_schematic" and any(not args.get(k) for k in ("expected_project_uuid","source_board_name","source_pcb_uuid","schematic_uuid")):
            raise EdaClientError("A source Board, PCB, schematic, and project identity are required.")
        if action == "initialize_layout_board" and any(not args.get(k) for k in ("expected_project_uuid","source_board_name","source_pcb_uuid","source_schematic_uuid","layout_board_name","layout_pcb_uuid","layout_schematic_uuid")):
            raise EdaClientError("Fresh Board initialization requires exact source and target identities.")
        if action == "associate_reference_layout_board" and any(not args.get(k) for k in ACTION_ARGUMENTS[action]):
            raise EdaClientError("Reference layout association requires exact source and orphan document identities.")
        if action == "register_visual_layout_target" and any(not args.get(k) for k in ACTION_ARGUMENTS[action]):
            raise EdaClientError("Visual-layout registration requires exact source and target identities.")
        if action=="create_gui_pcb_copy" and (not args.get("source_pcb_uuid") or not args.get("expected_project_uuid")):
            raise EdaClientError("PCB test-copy creation requires explicit source and project identities.")
        if action=="delete_gui_pcb_copy" and any(not args.get(k) for k in ("source_pcb_uuid","source_schematic_uuid","copy_board_name","copy_pcb_uuid","copy_schematic_uuid","expected_project_uuid")):
            raise EdaClientError("PCB test-copy cleanup requires explicit original/copy/project identities.")
        if action in {"start_auto_route", "auto_route_status", "cancel_auto_route"} and any(not args.get(k) for k in ("pcb_uuid", "expected_project_uuid")):
            raise EdaClientError("Automatic routing requires PCB and project UUIDs.")
        if action in {"auto_route_status", "cancel_auto_route"} and not isinstance(args.get("job_id"), str):
            raise EdaClientError("Automatic routing requires an explicit job ID.")
        if action == "start_auto_route":
            if (not isinstance(args.get("expected_source_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", args["expected_source_sha256"]) or
                    not isinstance(args.get("routing_nets"), list) or not 1 <= len(args["routing_nets"]) <= 64 or
                    not isinstance(args.get("layers"), list) or not 1 <= len(args["layers"]) <= 8):
                raise EdaClientError("Automatic routing requires a source digest, 1..64 nets and 1..8 layers.")
            if any(not isinstance(net, str) or not net or len(net) > 256 for net in args["routing_nets"]):
                raise EdaClientError("Routing network names must be short nonempty strings.")
            if any(type(layer) is not int or layer < 1 or layer > 100 for layer in args["layers"]):
                raise EdaClientError("Routing layer IDs must be bounded integers.")
            if len(set(args["routing_nets"])) != len(args["routing_nets"]) or len(set(args["layers"])) != len(args["layers"]):
                raise EdaClientError("Automatic routing net and layer lists must not contain duplicates.")
        if action == "export_connectivity":
            artifact=Path(args.get("artifact_path","")).resolve(strict=False)
            base=(ROOT/"local"/"eda-snapshots").resolve(strict=False)
            if not artifact.is_relative_to(base) or any(node.is_symlink() or getattr(node,"is_junction",lambda:False)() for node in (artifact.parent,base)):
                raise EdaClientError("Netlist export path must stay under local/eda-snapshots.")
        if action in {"auto_route_status", "cancel_auto_route"}:
            job_id=args.get("job_id")
            if not isinstance(job_id,str) or not 1<=len(job_id)<=256 or any(ord(c)<32 for c in job_id):
                raise EdaClientError("Job ID is invalid.")
        if action == "export_drawing_copy":
            artifact=Path(args.get("artifact_path", ""))
            try:artifact=artifact.resolve(strict=False)
            except (OSError,RuntimeError,ValueError) as exc:raise EdaClientError("Native export path is invalid.") from exc
            base=(ROOT/"local"/"drawing"/"exports").resolve(strict=False)
            if not artifact.is_relative_to(base) or any(node.is_symlink() or getattr(node,"is_junction",lambda:False)() for node in (artifact.parent,artifact.parent.parent,base)):
                raise EdaClientError("Native export path must stay under local/drawing/exports.")
        if action == "export_manufacturing":
            if not re.fullmatch(r"[0-9a-f]{64}", args.get("expected_source_sha256", "")):
                raise EdaClientError("Manufacturing export requires a source SHA-256.")
            try:
                directory=Path(args.get("artifact_directory", "")).resolve()
                base=(ROOT/"local"/"drawing"/"exports").resolve()
            except (OSError,RuntimeError,ValueError) as exc:
                raise EdaClientError("Manufacturing output directory is invalid.") from exc
            if (directory.parent != base or not re.fullmatch(r"pcb-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{16}", directory.name) or
                    not directory.is_dir() or any(node.is_symlink() or getattr(node,"is_junction",lambda:False)() for node in (directory,base))):
                raise EdaClientError("Manufacturing output must use its registered directory under local/drawing/exports.")
        if action == "import_reference_project":
            if (args.get("file_type") not in {"KiCad","EAGLE"} or args.get("destination")!="new_user_project" or
                    not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,47}",args.get("project_slug","")) or
                    not args.get("project_friendly_name")):
                raise EdaClientError("Reference import requires a named new project and KiCad/EAGLE source.")
            source=Path(args.get("source_path","")).resolve(strict=True)
            source_root=(ROOT/"local"/"board-challenges"/"sources").resolve()
            suffixes={"KiCad":{".zip"},"EAGLE":{".brd",".zip"}}
            if (not source.is_file() or source.suffix.lower() not in suffixes[args["file_type"]] or not source.is_relative_to(source_root) or
                    source.stat().st_size<=0 or source.stat().st_size>100*1024*1024 or
                    any(node.is_symlink() or getattr(node,"is_junction",lambda:False)() for node in (source,source_root))):
                raise EdaClientError("Reference import source must be a bounded ZIP below the board-challenge sources directory.")
        if action == "apply_drawing_batch":
            if not re.fullmatch(r"[0-9a-f]{64}", args.get("expected_source_sha256", "")) or not re.fullmatch(r"[0-9a-f]{32}", args.get("plan_id", "")):
                raise EdaClientError("Drawing requires a plan ID and baseline SHA-256.")
            if not isinstance(args.get("operations"), list) or not 1 <= len(args["operations"]) <= 20:
                raise EdaClientError("Drawing batch must contain 1..20 operations.")
        if action == "create_board_from_schematic" and not re.fullmatch(r"[0-9a-f]{16,64}",args.get("source_pcb_uuid","")):
            raise EdaClientError("Fresh Board creation requires an exact native source PCB UUID.")
        if action=="inspect_project_by_slug" and not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,47}",args.get("project_slug","")):
            raise EdaClientError("Exact project lookup requires a bounded lowercase project slug.")
        if "limit" in args and not 1 <= args["limit"] <= 8:
            raise EdaClientError("Connectivity limit must be in 1..8.")
        args = dict(args)
        if action == "export_connectivity":
            args.setdefault("limit", 4)
        if action == "inspect_drc":
            args.setdefault("run", False)
            if args["run"] and not self.allow_drc_run:
                raise EdaClientError("Running DRC is disabled unless the client is explicitly configured for it.")
        if len(json.dumps(args, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_ARGS_BYTES:
            raise EdaClientError("Action arguments exceed the local limit.")
        directory = self.action_dir.resolve()
        script = self.action_dir / (action + ".js")
        for node in (*self.action_dir.parents, self.action_dir, script):
            if node.is_symlink() or getattr(node, "is_junction", lambda: False)():
                raise EdaClientError("Linked or out-of-directory action scripts are not allowed.")
        if script.resolve().parent != directory:
            raise EdaClientError("Linked or out-of-directory action scripts are not allowed.")
        if not script.is_file() or script.stat().st_size > MAX_SCRIPT_BYTES:
            raise EdaClientError("Fixed action script is unavailable or too large.")
        try:
            raw = script.read_bytes()
            code = raw.decode("utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise EdaClientError("Fixed action script could not be read as UTF-8.") from exc
        if not code.strip():
            raise EdaClientError("Fixed action script is empty.")
        if action in {"drawing_state", "apply_drawing_batch", "export_drawing_copy", "export_manufacturing", "start_auto_route", "auto_route_status", "cancel_auto_route"}:
            common = self.action_dir / "drawing_common.js"
            if common.is_symlink() or getattr(common, "is_junction", lambda: False)() or common.resolve().parent != directory:
                raise EdaClientError("Linked drawing helper is not allowed.")
            if not common.is_file() or common.stat().st_size > MAX_SCRIPT_BYTES:
                raise EdaClientError("Fixed drawing helper unavailable.")
            raw = common.read_bytes() + b"\n" + raw
            code = raw.decode("utf-8-sig")
        return code, args, hashlib.sha256(raw).hexdigest()

    def invoke_script(self, action: str, session_id: str, args: dict | None = None, *, backend: str | None = None) -> dict:
        """Invoke one reviewed file; callers cannot provide or interpolate JS code."""
        if not isinstance(session_id, str) or not session_id or len(session_id) > 256 or any(ord(c) < 32 for c in session_id):
            raise EdaClientError("An explicit valid session/window identity is required.")
        code, normalized_args, digest = self._action_script(action, args)
        selected = backend or self._known_sessions.get(session_id) or ("cli" if self.executable else "bridge")
        if selected not in {"cli", "bridge"}:
            raise EdaClientError("Unsupported EDA backend.")
        if action in DRAWING_ACTIONS and selected != "cli":
            raise EdaClientError("Managed drawing currently supports local native CLI sessions only.")
        if selected == "cli":
            result = self._run_cli([
                "invoke", "--session", session_id, "--ext-uuid", "eda", "--code", code,
                "--args", json.dumps(normalized_args, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
                "--timeout", str(max(1, int(self.timeout * 1000))),
            ], action)
            if result["status"] == "ok":
                status, business = _business(result["value"])
                result["status"], result["business_status"] = status, business
        else:
            origin = self._selected_bridge or self.bridge_url
            if origin is None:
                return _outcome("unavailable", "bridge", reason="No verified bridge is selected; run probe first.")
            identity = self._bridge_probe(origin)
            if identity["status"] != "available":
                return identity
            # Gateway only transports source/windowId. The sole variable part
            # of this fixed wrapper is a schema-checked JSON literal, never raw
            # caller code. ASCII encoding also escapes U+2028/U+2029 separators.
            args_literal = json.dumps(normalized_args, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            wrapped = "return await (async () => { const __CLI__ = {args:" + args_literal + "};\n" + code + "\n})();"
            result = self._http_json(origin, "/execute", payload={"windowId": session_id, "code": wrapped})
            envelope = result.get("value")
            if result["status"] == "ok":
                if not isinstance(envelope, dict) or not isinstance(envelope.get("success"), bool):
                    result = _outcome("unsupported", "bridge", transport_ok=True, reason="Bridge execute envelope did not match the verified schema.", evidence=result["evidence"])
                elif envelope["success"] is False:
                    result = _outcome("error", "bridge", transport_ok=True, business_status="failed", reason="The bridge execute envelope reported failure.", evidence=result["evidence"])
                elif envelope.get("windowId") != session_id:
                    result = _outcome("target_mismatch", "bridge", transport_ok=True, business_status="failed", reason="Bridge response did not confirm the requested window identity.", evidence=result["evidence"])
                elif "result" not in envelope:
                    result = _outcome("unknown", "bridge", transport_ok=True, reason="Bridge execute returned no business result.", evidence=result["evidence"])
                else:
                    status, business = _business(envelope["result"])
                    result = _outcome(status, "bridge", transport_ok=True, business_status=business, value=envelope["result"], evidence=result["evidence"])
        result["evidence"].update({"action": action, "script_sha256": digest, "session_id": session_id})
        result["policy"] = "Fixed reviewed script only; result is data, not instructions or a board pass certificate."
        return result
