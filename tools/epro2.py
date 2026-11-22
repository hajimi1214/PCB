"""Read-only parser for plain-text LCEDA Pro .epro2 archives.

This is a structural importer, not an EDA validator. Archive payloads are data;
they are only decoded as JSON and are never interpreted or executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

MODEL_VERSION = "1.0"
MAX_ARCHIVE_BYTES = 80 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 100 * 1024 * 1024
MAX_MEMBER_BYTES = 80 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000
MAX_ZIP_MEMBERS = 5000
MAX_LINE_BYTES = 8 * 1024 * 1024
MAX_JSON_DEPTH = 128


class Epro2Error(ValueError):
    """Invalid, unsupported, encrypted, unsafe, or oversized .epro2 input."""


def _safe_member_name(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name:
        return False
    posix = PurePosixPath(name)
    win = PureWindowsPath(name)
    return not (
        posix.is_absolute() or win.is_absolute() or win.drive
        or any(part in ("..", "") for part in name.rstrip("/").split("/"))
    )


def _json_depth(value: Any, limit: int = MAX_JSON_DEPTH) -> None:
    stack = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > limit:
            raise Epro2Error(f"JSON nesting exceeds {limit} levels")
        if isinstance(current, float) and not math.isfinite(current):
            raise Epro2Error("non-finite JSON numbers are unsupported")
        if isinstance(current, dict):
            stack.extend((v, depth + 1) for v in current.values())
        elif isinstance(current, list):
            stack.extend((v, depth + 1) for v in current)


def _decode_json(text: str, where: str) -> Any:
    try:
        def reject_constant(token: str) -> None:
            raise Epro2Error(f"{where}: non-finite JSON number {token} is unsupported")
        value = json.loads(text, parse_constant=reject_constant)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise Epro2Error(f"{where}: invalid JSON ({exc})") from exc
    _json_depth(value)
    return value


def _inspect_zip(path: str | Path, verify_crc: bool = True) -> tuple[dict, zipfile.ZipFile]:
    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise Epro2Error(f"cannot read archive: {exc}") from exc
    if size > MAX_ARCHIVE_BYTES:
        raise Epro2Error(f"archive exceeds {MAX_ARCHIVE_BYTES} byte limit")
    if size == 0:
        raise Epro2Error("archive is empty")
    try:
        archive = zipfile.ZipFile(source, "r")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise Epro2Error(f"not a valid .epro2 ZIP archive: {exc}") from exc

    infos = archive.infolist()
    if len(infos) > MAX_ZIP_MEMBERS:
        archive.close()
        raise Epro2Error(f"archive exceeds {MAX_ZIP_MEMBERS} member limit")
    total = 0
    seen: set[str] = set()
    rows = []
    for info in infos:
        name = info.filename
        if not _safe_member_name(name):
            archive.close()
            raise Epro2Error(f"unsafe ZIP member path: {name!r}")
        if name in seen:
            archive.close()
            raise Epro2Error(f"duplicate ZIP member name: {name!r}")
        seen.add(name)
        if info.flag_bits & 0x1:
            archive.close()
            raise Epro2Error(f"encrypted ZIP member is not supported: {name!r}")
        if info.file_size > MAX_MEMBER_BYTES:
            archive.close()
            raise Epro2Error(f"ZIP member exceeds size limit: {name!r}")
        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED:
            archive.close()
            raise Epro2Error("total uncompressed ZIP size exceeds limit")
        if info.file_size and info.compress_size == 0:
            archive.close()
            raise Epro2Error(f"invalid ZIP compression size: {name!r}")
        if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            archive.close()
            raise Epro2Error(f"suspicious ZIP compression ratio: {name!r}")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            archive.close()
            raise Epro2Error(f"unsupported ZIP compression method: {name!r}")
        rows.append({
            "name": name,
            "size": info.file_size,
            "compressed_size": info.compress_size,
            "crc32": f"{info.CRC:08x}",
            "encrypted": False,
            "directory": info.is_dir(),
        })
    if verify_crc:
        try:
            bad = archive.testzip()
        except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            archive.close()
            raise Epro2Error(f"ZIP CRC/integrity check failed: {exc}") from exc
        if bad is not None:
            archive.close()
            raise Epro2Error(f"ZIP CRC mismatch in member: {bad!r}")
    return ({"member_count": len(rows), "total_uncompressed_bytes": total, "members": rows}, archive)


def inspect_archive(path: str | Path) -> dict:
    """Validate archive safety/CRC and return a compact member + metadata summary."""
    source = Path(path)
    initial_sha = _sha256_file(source)
    archive_info, archive = _inspect_zip(source, verify_crc=True)
    try:
        project = _read_project_metadata(archive)
        raw_name = _find_log_member(archive.namelist())
        raw = archive.read(raw_name)
        log_info = _inspect_log(raw, raw_name)
    finally:
        archive.close()
    if _sha256_file(source) != initial_sha:
        raise Epro2Error("source archive changed during inspection; retry from a stable copy")
    return {
        "source_path": str(source.resolve()),
        "source_sha256": initial_sha,
        "archive_bytes": source.stat().st_size,
        "archive": archive_info,
        "project": project,
        "log": log_info,
    }


def _sha256_file(path: Path) -> str:
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise Epro2Error(f"archive exceeds {MAX_ARCHIVE_BYTES} byte limit")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_project_metadata(archive: zipfile.ZipFile) -> dict:
    candidates = [n for n in archive.namelist() if PurePosixPath(n).name.lower() in ("project2.json", "project.json")]
    if len(candidates) != 1:
        raise Epro2Error(f"expected exactly one project metadata JSON, found {len(candidates)}")
    name = candidates[0]
    raw = archive.read(name)
    try:
        project = _decode_json(raw.decode("utf-8-sig"), name)
    except UnicodeDecodeError as exc:
        raise Epro2Error(f"{name}: metadata is not UTF-8") from exc
    if not isinstance(project, dict):
        raise Epro2Error(f"{name}: project metadata must be a JSON object")
    return {"archive_member": name, "metadata": project}


def _find_log_member(names: list[str]) -> str:
    logs = [n for n in names if PurePosixPath(n).suffix.lower() in (".epru", ".eprj3")]
    if len(logs) != 1:
        raise Epro2Error(f"expected exactly one project log (.epru/.eprj3), found {len(logs)}")
    return logs[0]


def _split_log_record(line: str, member: str, line_number: int,
                      allow_missing_final_bar: bool = False) -> tuple[dict, Any, bool]:
    if len(line.encode("utf-8")) > MAX_LINE_BYTES:
        raise Epro2Error(f"{member}:{line_number}: record exceeds line size limit")
    text = line.strip()
    if text.startswith("json "):
        text = text[5:].lstrip()
    # The delimiter can legally occur inside JSON string values in either half.
    # Parse the complete header object before looking for the outside separator.
    try:
        _, header_end = json.JSONDecoder().raw_decode(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise Epro2Error(f"{member}:{line_number}: invalid record header ({exc})") from exc
    header_text = text[:header_end]
    remaining = text[header_end:].lstrip()
    if not remaining.startswith("||"):
        raise Epro2Error(f"{member}:{line_number}: missing || record delimiter")
    payload_text = remaining[2:]
    missing_bar = not payload_text.endswith("|")
    if missing_bar and not allow_missing_final_bar:
        raise Epro2Error(f"{member}:{line_number}: record missing terminal |")
    header = _decode_json(header_text, f"{member}:{line_number}:header")
    payload = _decode_json(payload_text[:-1] if not missing_bar else payload_text,
                           f"{member}:{line_number}:payload")
    if not isinstance(header, dict) or not isinstance(header.get("type"), str):
        raise Epro2Error(f"{member}:{line_number}: record header lacks string type")
    return header, payload, missing_bar


def _inspect_log(raw: bytes, member: str) -> dict:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Epro2Error(f"{member}: log is not UTF-8") from exc
    counts: Counter[str] = Counter()
    doc_counts: Counter[str] = Counter()
    current = None
    docs = 0
    records = 0
    line_count = 0
    lines = text.splitlines()
    missing_final_bar = False
    for line_count, line in enumerate(lines, 1):
        if not line:
            continue
        header, payload, missing_bar = _split_log_record(
            line, member, line_count, allow_missing_final_bar=line_count == len(lines)
        )
        missing_final_bar |= missing_bar
        if header["type"] == "DOCHEAD":
            if not isinstance(payload, dict) or not isinstance(payload.get("docType"), str):
                raise Epro2Error(f"{member}:{line_count}: DOCHEAD payload lacks docType")
            current = payload
            docs += 1
            doc_counts[payload["docType"]] += 1
            continue
        if current is None:
            raise Epro2Error(f"{member}:{line_count}: record occurs before first DOCHEAD")
        counts[header["type"]] += 1
        records += 1
    if docs == 0:
        raise Epro2Error(f"{member}: no DOCHEAD documents found")
    return {
        "archive_member": member,
        "line_count": line_count,
        "record_count": records,
        "document_count": docs,
        "document_types": dict(sorted(doc_counts.items())),
        "record_types": dict(sorted(counts.items())),
        "missing_terminal_bar_on_final_record": missing_final_bar,
    }


def _evidence(member: str, line: int, document: dict, header: dict) -> dict:
    return {
        "archive_member": member,
        "line": line,
        "doc_type": document.get("docType"),
        "doc_uuid": document.get("uuid"),
        "header_type": header.get("type"),
        "header_id": header.get("id"),
        "ticket": header.get("ticket"),
        "client": document.get("client"),
    }


def _document_records(raw: bytes, member: str) -> tuple[list[dict], list[dict], list[str]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Epro2Error(f"{member}: log is not UTF-8") from exc
    segments: list[dict] = []
    deletions: list[dict] = []
    warnings: list[str] = []
    current: dict | None = None
    lines = text.splitlines()
    for line_number, line in enumerate(lines, 1):
        if not line:
            continue
        header, payload, missing_bar = _split_log_record(
            line, member, line_number, allow_missing_final_bar=line_number == len(lines)
        )
        if missing_bar:
            warnings.append(f"{member}:{line_number}: final record omitted the documented terminal |; JSON payload was still complete")
        if header["type"] == "DOCHEAD":
            if not isinstance(payload, dict) or not isinstance(payload.get("docType"), str):
                raise Epro2Error(f"{member}:{line_number}: DOCHEAD payload lacks docType")
            doc_type = payload["docType"]
            if not isinstance(payload.get("uuid"), str) or not payload["uuid"]:
                warnings.append(f"{member}:{line_number}: {doc_type} DOCHEAD has no uuid")
            current = {
                "doc_type": doc_type,
                "uuid": payload.get("uuid"),
                "client": payload.get("client"),
                "header": payload,
                "header_evidence": _evidence(member, line_number, payload, header),
                "_candidates": defaultdict(list),
            }
            segments.append(current)
            continue
        if current is None:
            raise Epro2Error(f"{member}:{line_number}: record occurs before first DOCHEAD")
        if not isinstance(header.get("ticket"), (int, float)) or isinstance(header.get("ticket"), bool):
            raise Epro2Error(f"{member}:{line_number}: record ticket must be numeric")
        rec_type = header["type"]
        evidence = _evidence(member, line_number, current["header"], header)
        if rec_type == "DELETE_DOC":
            deletions.append({"payload": payload, "evidence": evidence, "status": "unsupported_document_delete_semantics"})
            continue
        record = {"id": header.get("id"), "ticket": header["ticket"], "type": rec_type,
                  "body": payload, "evidence": evidence, "_sequence": line_number}
        key = (rec_type, json.dumps(header.get("id"), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        current["_candidates"][key].append(record)

    if not segments:
        raise Epro2Error(f"{member}: no DOCHEAD documents found")

    # A log can contain more than one DOCHEAD segment for the same logical
    # document. Merge those segments before resolving type/id/ticket history.
    documents: list[dict] = []
    by_identity: dict[tuple[str, str], dict] = {}
    for segment_index, segment in enumerate(segments):
        uuid = segment.get("uuid")
        identity = (segment["doc_type"], uuid) if isinstance(uuid, str) and uuid else (
            segment["doc_type"], f"<missing-uuid-segment-{segment_index}>"
        )
        document = by_identity.get(identity)
        if document is None:
            document = {
                "doc_type": segment["doc_type"], "uuid": uuid,
                "client": segment.get("client"), "header": segment["header"],
                "header_evidence": segment["header_evidence"],
                "header_segments": [], "_header_candidates": [],
                "_candidates": defaultdict(list),
            }
            by_identity[identity] = document
            documents.append(document)
        document["header_segments"].append({
            "header": segment["header"], "evidence": segment["header_evidence"],
        })
        # Expose the latest header as the current document descriptor; preserve
        # every segment and its client for record-level conflict resolution.
        document["client"] = segment.get("client")
        document["_header_sequence"] = segment_index
        document["_header_candidates"].append({
            "header": segment["header"], "evidence": segment["header_evidence"],
            "sequence": segment_index,
        })
        for key, candidates in segment["_candidates"].items():
            document["_candidates"][key].extend(candidates)

    for document in documents:
        headers = document.pop("_header_candidates")
        numeric_headers = [h for h in headers if isinstance(h["evidence"].get("ticket"), (int, float))]
        if numeric_headers:
            max_header_ticket = max(h["evidence"]["ticket"] for h in numeric_headers)
            header_ties = [h for h in numeric_headers if h["evidence"]["ticket"] == max_header_ticket]
            clients = [h["evidence"].get("client") for h in header_ties if isinstance(h["evidence"].get("client"), str)]
            if clients:
                smallest_client = min(clients)
                header_ties = [h for h in header_ties if h["evidence"].get("client") == smallest_client]
            winner_header = max(header_ties, key=lambda h: h["sequence"])
        else:
            winner_header = max(headers, key=lambda h: h["sequence"])
        document["header"] = winner_header["header"]
        document["header_evidence"] = winner_header["evidence"]
        document["client"] = winner_header["evidence"].get("client")
        document.pop("_header_sequence", None)
        effective: list[dict] = []
        tombstones: list[dict] = []
        for candidates in document.pop("_candidates").values():
            # The local v3 format description specifies max ticket wins. For an
            # equal-ticket tie it specifies lexicographically smaller client wins.
            max_ticket = max(r["ticket"] for r in candidates)
            tied = [r for r in candidates if r["ticket"] == max_ticket]
            clients = [r["evidence"].get("client") for r in tied]
            nonempty_clients = [c for c in clients if isinstance(c, str)]
            winner_client = min(nonempty_clients) if nonempty_clients else None
            if winner_client is not None:
                tied = [r for r in tied if r["evidence"].get("client") == winner_client]
            winner = max(tied, key=lambda r: r["_sequence"])
            if len(tied) > 1 and any(r["body"] != winner["body"] for r in tied):
                warnings.append(
                    f"{winner['evidence']['archive_member']}:{winner['evidence']['line']}: "
                    f"equal ticket/client conflict for {document['doc_type']} {winner['type']} {winner['id']!r}; "
                    "last log occurrence selected because same-client tie semantics are unspecified"
                )
            winner.pop("_sequence", None)
            if winner["body"] == "":
                tombstones.append(winner)
            else:
                effective.append(winner)
        effective.sort(key=lambda r: (r["evidence"]["line"], r["type"], str(r["id"])))
        document["records"] = effective
        document["tombstones"] = tombstones
        grouped: dict[str, list[dict]] = defaultdict(list)
        for record in effective:
            grouped[record["type"]].append(record)
        document["records_by_type"] = dict(grouped)
        document["meta"] = next((r["body"] for r in grouped.get("META", []) if r.get("id") in (None, "META")), None)
        document["record_counts"] = dict(sorted(Counter(r["type"] for r in effective).items()))
    return documents, deletions, warnings


def _records(document: dict, record_type: str) -> list[dict]:
    return document.get("records_by_type", {}).get(record_type, [])


def _attribute_rows(records: list[dict], parent_id: str | None = None) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        body = record["body"]
        if not isinstance(body, dict) or not isinstance(body.get("key"), str):
            continue
        parent = body.get("parentId")
        if parent_id is not None and parent != parent_id:
            continue
        result[str(parent or "")].append(record)
    return dict(result)


def _attribute_values(attribute_records: list[dict]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for record in attribute_records:
        body = record["body"]
        if isinstance(body, dict) and isinstance(body.get("key"), str):
            values[body["key"]] = body.get("value")
    return values


def _device_lookup(documents: list[dict]) -> dict[str, dict]:
    return {d["uuid"]: d for d in documents if d.get("doc_type") == "DEVICE" and d.get("uuid")}


def _footprint_lookup(documents: list[dict]) -> dict[str, dict]:
    return {d["uuid"]: d for d in documents if d.get("doc_type") == "FOOTPRINT" and d.get("uuid")}


def _symbol_lookup(documents: list[dict]) -> dict[str, dict]:
    return {d["uuid"]: d for d in documents if d.get("doc_type") == "SYMBOL" and d.get("uuid")}


def _symbol_parts(symbols: dict[str, dict]) -> dict[tuple[str, str], dict]:
    parts: dict[tuple[str, str], dict] = {}
    for symbol_uuid, symbol in symbols.items():
        for record in _records(symbol, "PART"):
            part_id = str(record["id"])
            pins = [pin for pin in _records(symbol, "PIN")
                    if isinstance(pin.get("body"), dict) and pin["body"].get("partId") == part_id]
            parts[(symbol_uuid, part_id)] = {"symbol_uuid": symbol_uuid, "record": record, "pins": pins}
    return parts


def _library_model(documents: list[dict]) -> dict:
    result: dict[str, dict] = {}
    for kind in ("devices", "symbols", "footprints"):
        doc_type = kind[:-1].upper() if kind != "footprints" else "FOOTPRINT"
        if kind == "devices":
            doc_type = "DEVICE"
        elif kind == "symbols":
            doc_type = "SYMBOL"
        result[kind] = {}
        for document in documents:
            if document.get("doc_type") == doc_type and document.get("uuid"):
                result[kind][document["uuid"]] = {
                    "uuid": document["uuid"],
                    "meta": document.get("meta"),
                    "header": document.get("header"),
                    "header_evidence": document.get("header_evidence"),
                    "records_by_type": document.get("records_by_type", {}),
                    "record_counts": document.get("record_counts", {}),
                }
    return result


def _component_from_pcb(record: dict, attrs: dict[str, Any], devices: dict, footprints: dict,
                        attribute_records: list[dict] | None = None) -> dict:
    body = record["body"]
    attrs_obj = body.get("attrs") if isinstance(body.get("attrs"), dict) else {}
    device_ref = attrs_obj.get("DeviceName")
    if isinstance(device_ref, str):
        try:
            device_ref = _decode_json(device_ref, "PCB COMPONENT attrs.DeviceName")
        except Epro2Error:
            device_ref = {"name": device_ref}
    device_uuid = device_ref.get("uuid") if isinstance(device_ref, dict) else None
    if not device_uuid and isinstance(attrs.get("Device"), str):
        device_uuid = attrs["Device"]
    device = devices.get(device_uuid) if device_uuid else None
    device_meta = device.get("meta") if device else None
    dev_attributes = device_meta.get("attributes", {}) if isinstance(device_meta, dict) else {}
    if not isinstance(dev_attributes, dict):
        dev_attributes = {}
    device_default_footprint = dev_attributes.get("Footprint")
    local_footprint = attrs.get("Footprint")
    effective_footprint = local_footprint or device_default_footprint
    fp = footprints.get(effective_footprint) if effective_footprint else None
    fp_meta = fp.get("meta") if fp else None
    return {
        "id": record.get("id"), "ticket": record.get("ticket"), "evidence": record["evidence"],
        "position": {k: body.get(k) for k in ("x", "y", "angle", "layerId")},
        "locked": body.get("locked"), "instance_attrs": attrs_obj, "attributes": attrs,
        "attribute_evidence": [{"key": r.get("body", {}).get("key"),
                                "value": r.get("body", {}).get("value"),
                                "evidence": r.get("evidence")} for r in (attribute_records or [])],
        "designator": attrs.get("Designator"), "value": attrs.get("Value"),
        "device_uuid": device_uuid, "device_name": device_ref.get("name") if isinstance(device_ref, dict) else None,
        "device_title": device_meta.get("title") if isinstance(device_meta, dict) else None,
        "footprint_uuid": effective_footprint,
        "footprint_source": "instance_override" if local_footprint else ("device_default" if device_default_footprint else None),
        "footprint_name": fp_meta.get("title") if isinstance(fp_meta, dict) else None,
        "footprint_record_counts": fp.get("record_counts") if fp else None,
        "body": body,
    }


def _component_from_schematic(record: dict, attrs: dict[str, Any], devices: dict,
                               symbols: dict, parts: dict,
                               attribute_records: list[dict] | None = None) -> dict:
    body = record["body"]
    device_uuid = attrs.get("Device")
    device = devices.get(device_uuid) if isinstance(device_uuid, str) else None
    device_meta = device.get("meta") if device else None
    device_attributes = device_meta.get("attributes") if isinstance(device_meta, dict) else None
    default_symbol = device_attributes.get("Symbol") if isinstance(device_attributes, dict) else None
    symbol_uuid = attrs.get("Symbol") or default_symbol
    symbol = symbols.get(symbol_uuid) if isinstance(symbol_uuid, str) else None
    # PART ids are scoped to a SYMBOL, not the whole project. Several net flags,
    # sheet frames, and parts may reuse placeholder part ids in different symbols.
    part = parts.get((symbol_uuid, str(body.get("partId")))) if symbol else None
    return {
        "id": record.get("id"), "ticket": record.get("ticket"), "evidence": record["evidence"],
        "position": {k: body.get(k) for k in ("x", "y", "rotation", "isMirror")},
        "part_id": body.get("partId"), "device_uuid": device_uuid, "symbol_uuid": symbol_uuid,
        "symbol_source": "instance_override" if attrs.get("Symbol") else ("device_default" if default_symbol else None),
        "device_title": (device.get("meta") or {}).get("title") if device else None,
        "symbol_title": (symbol.get("meta") or {}).get("title") if symbol else None,
        "part_title": ((part.get("record") or {}).get("body") or {}).get("title") if part else None,
        "part_pin_count": len(part.get("pins", [])) if part else 0,
        "part_pin_ids": [pin.get("id") for pin in part.get("pins", [])] if part else [],
        "attributes": attrs, "designator": attrs.get("Designator"), "name": attrs.get("Name"),
        "attribute_evidence": [{"key": r.get("body", {}).get("key"),
                                "value": r.get("body", {}).get("value"),
                                "evidence": r.get("evidence")} for r in (attribute_records or [])],
        "kind": _schematic_component_kind(attrs, body, symbol.get("meta") if symbol else None),
        "body": body,
    }


def _schematic_component_kind(attrs: dict[str, Any], body: dict, symbol_meta: Any) -> str:
    # Do not infer a net flag solely from a blank designator; retain uncertainty.
    names = " ".join(str(attrs.get(k) or "") for k in ("Designator", "Name", "Value", "Global Net Name"))
    title = symbol_meta.get("title", "") if isinstance(symbol_meta, dict) else ""
    combined = f"{names} {title}".casefold()
    if "sheet" in combined or "图框" in combined or "drawing" in combined:
        return "sheet_frame"
    if "netflag" in combined or "net flag" in combined or "net_flag" in combined:
        return "net_flag"
    if attrs.get("Designator"):
        return "design_component"
    if any(token in combined for token in ("powerflag", "power flag", "netport", "net port", "power port")):
        return "power_or_net_port"
    if attrs.get("Global Net Name") or attrs.get("NET"):
        return "power_or_net_port"
    if not attrs.get("Symbol") and not body.get("partId"):
        return "unresolved_non_component"
    return "unclassified_symbol_or_power_port"


def _build_schematic(document: dict, devices: dict, symbols: dict, parts: dict) -> dict:
    attr_map = _attribute_rows(_records(document, "ATTR"))
    components = []
    for record in _records(document, "COMPONENT"):
        attribute_records = attr_map.get(str(record.get("id")), [])
        attrs = _attribute_values(attribute_records)
        components.append(_component_from_schematic(record, attrs, devices, symbols, parts, attribute_records))
    return {
        "uuid": document.get("uuid"), "title": (document.get("meta") or {}).get("title"),
        "meta": document.get("meta"), "header_evidence": document.get("header_evidence"),
        "pages": [], "all_components": components,
        "design_components": [c for c in components if c["kind"] == "design_component"],
        "wires": _records(document, "WIRE"), "lines": _records(document, "LINE"),
        "records_by_type": document.get("records_by_type", {}),
        "record_refs": _record_refs(document),
        "record_counts": document.get("record_counts", {}),
    }


def _parse_composite_id(value: Any) -> list[Any] | None:
    if not isinstance(value, str) or not value.startswith("["):
        return None
    try:
        decoded = json.loads(value)
    except (json.JSONDecodeError, RecursionError):
        return None
    return decoded if isinstance(decoded, list) else None


def _pcb_layers(document: dict) -> list[dict]:
    layers = []
    for record in _records(document, "LAYER"):
        body = record.get("body")
        if not isinstance(body, dict):
            continue
        composite = _parse_composite_id(record.get("id"))
        layer_id = composite[1] if composite and len(composite) > 1 else body.get("layerId")
        layer_type = body.get("layerType")
        # PLANE is the official internal-electrical-layer value in the SDK.
        # Also accept an explicit POWER layer type as copper. Do not infer
        # copper solely from the user-editable layer name.
        copper = layer_type in (
            "TOP", "BOTTOM", "SIGNAL", "INNER", "INNER_SIGNAL", "PLANE", "POWER",
            "INTERNAL_ELECTRICAL",
        )
        raw_enabled = body.get("use")
        enabled = (True if raw_enabled is True or type(raw_enabled) is int and raw_enabled == 1
                   else False if raw_enabled is False or type(raw_enabled) is int and raw_enabled == 0
                   else None)
        layers.append({
            "id": layer_id, "record_id": record.get("id"), "ticket": record.get("ticket"),
            "layer_type": layer_type, "name": body.get("layerName"), "enabled": enabled,
            "is_copper": copper, "evidence": record["evidence"], "body": body,
        })
    return layers


def _build_pcb(document: dict, devices: dict, footprints: dict) -> dict:
    all_attrs = _records(document, "ATTR")
    attr_rows = _attribute_rows(all_attrs)
    per_component_attrs = {parent: _attribute_values(rows) for parent, rows in attr_rows.items()}
    components = [
        _component_from_pcb(r, per_component_attrs.get(str(r.get("id")), {}), devices, footprints,
                            attr_rows.get(str(r.get("id")), []))
        for r in _records(document, "COMPONENT")
    ]
    layers = _pcb_layers(document)
    copper_layers = [layer for layer in layers if layer["is_copper"]]
    enabled_copper = [layer for layer in copper_layers if layer["enabled"] is True]
    pad_nets = []
    for record in _records(document, "PAD_NET"):
        parts = _parse_composite_id(record.get("id"))
        pad_nets.append({
            "id": record.get("id"), "ticket": record.get("ticket"), "evidence": record["evidence"],
            "component_id": parts[1] if parts and len(parts) > 1 else None,
            "pad_number": parts[2] if parts and len(parts) > 2 else None,
            "footprint_pad_id": parts[3] if parts and len(parts) > 3 else None,
            "net": record.get("body", {}).get("padNet") if isinstance(record.get("body"), dict) else None,
            "body": record.get("body"),
        })
    record_groups = document.get("records_by_type", {})
    return {
        "uuid": document.get("uuid"), "title": (document.get("meta") or {}).get("title"),
        "board_uuid": (document.get("meta") or {}).get("board"),
        "meta": document.get("meta"), "header_evidence": document.get("header_evidence"),
        "layers": layers, "copper_layers": copper_layers, "enabled_copper_layers": enabled_copper,
        "enabled_copper_layer_count": len(enabled_copper),
        "all_components": components, "design_components": components,
        "pad_nets": pad_nets,
        "nets": _records(document, "NET"), "lines": _records(document, "LINE"),
        "vias": _records(document, "VIA"), "pours": _records(document, "POUR"),
        "rules": _records(document, "RULE"), "layer_phys": _records(document, "LAYER_PHYS"),
        "records_by_type": record_groups, "record_refs": _record_refs(document),
        "record_counts": document.get("record_counts", {}),
    }


def _record_refs(document: dict) -> list[dict]:
    return [{"type": r["type"], "id": r.get("id"), "ticket": r.get("ticket"),
             "evidence": r.get("evidence")} for r in document.get("records", [])]


def _document_index(document: dict) -> dict:
    """Compact document metadata; full library/page/PCB records live in their typed views."""
    return {
        "doc_type": document.get("doc_type"), "uuid": document.get("uuid"),
        "client": document.get("client"), "header": document.get("header"),
        "header_evidence": document.get("header_evidence"),
        "header_segments": document.get("header_segments", []),
        "meta": document.get("meta"), "record_counts": document.get("record_counts", {}),
        "record_refs": _record_refs(document), "tombstones": document.get("tombstones", []),
        # Keep only document kinds without a richer typed view here.
        "records_by_type": (document.get("records_by_type", {})
                            if document.get("doc_type") not in
                            ("SYMBOL", "DEVICE", "FOOTPRINT", "SCH_PAGE", "PCB") else {}),
    }


def read_project(path: str | Path) -> dict:
    """Read a plain-text .epro2 archive into a JSON-serializable normalized model."""
    source = Path(path)
    initial_sha = _sha256_file(source)
    archive_info, archive = _inspect_zip(source, verify_crc=True)
    try:
        project_meta = _read_project_metadata(archive)
        log_member = _find_log_member(archive.namelist())
        raw = archive.read(log_member)
        log_sha = hashlib.sha256(raw).hexdigest()
        documents, deletions, warnings = _document_records(raw, log_member)
    finally:
        archive.close()

    source_sha = _sha256_file(source)
    if source_sha != initial_sha:
        raise Epro2Error("source archive changed during parsing; retry from a stable copy")
    libraries = _library_model(documents)
    devices = libraries["devices"]
    footprints = libraries["footprints"]
    symbols = libraries["symbols"]
    parts = _symbol_parts(symbols)
    boards = [
        {"uuid": d.get("uuid"), "meta": d.get("meta"), "header_evidence": d.get("header_evidence"),
         "records": d.get("records", []), "record_counts": d.get("record_counts", {})}
        for d in documents if d.get("doc_type") == "BOARD"
    ]
    schematic_docs = [d for d in documents if d.get("doc_type") == "SCH"]
    pages = [_build_schematic(d, devices, symbols, parts) for d in documents if d.get("doc_type") == "SCH_PAGE"]
    schematics = []
    for doc in schematic_docs:
        meta = doc.get("meta") or {}
        schematics.append({
            "uuid": doc.get("uuid"), "title": meta.get("title"), "board_uuid": meta.get("board"),
            "meta": meta, "header_evidence": doc.get("header_evidence"),
            "pages": [p for p in pages if (p.get("meta") or {}).get("schematic") == doc.get("uuid")],
        })
    pcbs = [_build_pcb(d, devices, footprints) for d in documents if d.get("doc_type") == "PCB"]
    counts = Counter(d.get("doc_type", "UNKNOWN") for d in documents)
    model = {
        "model_version": MODEL_VERSION,
        "source": {
            "path": str(source.resolve()), "sha256": source_sha, "archive_bytes": source.stat().st_size,
            "log_member": log_member, "log_sha256": log_sha,
        },
        "project": project_meta["metadata"],
        "documents": [_document_index(d) for d in documents],
        "document_counts": dict(sorted(counts.items())),
        "libraries": libraries,
        "boards": boards,
        "schematics": schematics,
        "pcb": pcbs,
        "unsupported_deletions": deletions,
        "warnings": warnings,
        "archive": archive_info,
    }
    # Guard the advertised API contract: callers can directly JSON serialize it.
    json.dumps(model, ensure_ascii=False, allow_nan=False)
    return model


def summarize_model(model: dict) -> dict:
    """Return a compact project/board summary without per-record geometry."""
    boards = []
    for board in model.get("pcb", []):
        boards.append({
            "uuid": board.get("uuid"), "title": board.get("title"), "board_uuid": board.get("board_uuid"),
            "enabled_copper_layer_count": board.get("enabled_copper_layer_count"),
            "copper_layers": [{"id": l.get("id"), "name": l.get("name"), "type": l.get("layer_type"),
                               "enabled": l.get("enabled")} for l in board.get("copper_layers", [])],
            "component_count": len(board.get("design_components", [])),
            "named_components": [c.get("designator") for c in board.get("design_components", []) if c.get("designator")],
            "net_count": len(board.get("nets", [])),
            "net_names": [_record_name(n) for n in board.get("nets", []) if _record_name(n) is not None],
            "line_count": len(board.get("lines", [])), "via_count": len(board.get("vias", [])),
            "pour_count": len(board.get("pours", [])), "pad_net_count": len(board.get("pad_nets", [])),
            "record_counts": board.get("record_counts", {}),
            "evidence": board.get("header_evidence"),
        })
    schematics = []
    for schematic in model.get("schematics", []):
        pages = []
        for page in schematic.get("pages", []):
            pages.append({
                "uuid": page.get("uuid"), "title": page.get("title"),
                "component_count": len(page.get("all_components", [])),
                "design_component_count": len(page.get("design_components", [])),
                "component_kinds": dict(sorted(Counter(c.get("kind") for c in page.get("all_components", [])).items())),
                "wire_count": len(page.get("wires", [])), "segment_count": len(page.get("lines", [])),
                "record_counts": page.get("record_counts", {}), "evidence": page.get("header_evidence"),
            })
        schematics.append({"uuid": schematic.get("uuid"), "title": schematic.get("title"),
                           "board_uuid": schematic.get("board_uuid"), "pages": pages})
    return {
        "model_version": model.get("model_version"), "source": model.get("source"),
        "project": {k: model.get("project", {}).get(k) for k in ("title", "editorVersion", "cbb_project")},
        "document_counts": model.get("document_counts", {}),
        "library_counts": {k: len(v) for k, v in model.get("libraries", {}).items()},
        "boards": [{"uuid": b.get("uuid"), "title": (b.get("meta") or {}).get("title"),
                    "evidence": b.get("header_evidence")} for b in model.get("boards", [])],
        "schematics": schematics, "pcb": boards,
        "unsupported_deletions": len(model.get("unsupported_deletions", [])),
        "warnings": model.get("warnings", []),
    }


def _record_name(record: dict) -> Any:
    body = record.get("body")
    if not isinstance(body, dict):
        return None
    composite = _parse_composite_id(record.get("id"))
    if composite and len(composite) > 1:
        return composite[1]
    return body.get("name")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--summary", action="store_true", help="emit a compact project summary (default)")
    args = parser.parse_args(argv)
    try:
        model = read_project(args.archive)
        # Keep the CLI bounded. Library users can call read_project() to store
        # full private models deliberately; raw BLOBs never belong on stdout.
        output = summarize_model(model)
    except (Epro2Error, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    json.dump(output, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
