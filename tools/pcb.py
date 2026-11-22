#!/usr/bin/env python3
"""Offline PCB knowledge navigation and evidence checks. Not a board validator."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "id", "title", "url", "local_path", "sha256", "retrieved_at",
    "authority", "license_or_terms", "claims", "limitations",
}


def read_sources(root: Path) -> list[dict]:
    records = []
    for path in sorted((root / "research").glob("*/sources.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("sources")
        if not isinstance(data, list) or any(not isinstance(x, dict) for x in data):
            raise ValueError(f"{path.relative_to(root)}: expected an array of source records")
        records.extend(data)
    return records


def source_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("local_path must be a nonempty relative path")
    relative = relative.replace("\\", "/")
    if Path(relative).is_absolute() or PureWindowsPath(relative).drive:
        raise ValueError("absolute local_path is not allowed")
    path = (root / relative).resolve()
    if not path.is_relative_to((root / "research").resolve()):
        raise ValueError("local_path must remain inside research/")
    return path


def verify_sources(root: Path, require_snapshots: bool = False) -> dict:
    errors, missing = [], []
    checked = 0
    try:
        records = read_sources(root)
    except (ValueError, OSError) as exc:
        return {"records": 0, "verified_snapshots": 0, "missing_snapshots": [], "errors": [str(exc)]}
    if not records:
        errors.append("No source records found")
    ids = set()
    for record in records:
        sid = record.get("id", "<missing-id>")
        missing_fields = REQUIRED - record.keys()
        if missing_fields:
            errors.append(f"{sid}: missing fields: {', '.join(sorted(missing_fields))}")
            continue
        if not isinstance(sid, str) or not sid or sid in ids:
            errors.append(f"{sid}: empty, non-string or duplicate id")
            continue
        ids.add(sid)
        url = record["url"]
        try:
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
                raise ValueError("expected public HTTP(S) URL without credentials")
        except (ValueError, TypeError) as exc:
            errors.append(f"{sid}: invalid URL ({exc})")
        for field in ("title", "retrieved_at", "authority", "license_or_terms"):
            if not record[field] or not isinstance(record[field], str):
                errors.append(f"{sid}: {field} must be a nonempty string")
        for field in ("claims", "limitations"):
            if not isinstance(record[field], (list, str)) or not record[field]:
                errors.append(f"{sid}: {field} must contain evidence or a scope statement")
        digest = record["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            errors.append(f"{sid}: invalid sha256")
            continue
        try:
            path = source_path(root, record["local_path"])
        except ValueError as exc:
            errors.append(f"{sid}: {exc}")
            continue
        if not path.is_file():
            missing.append(sid)
            if require_snapshots:
                errors.append(f"{sid}: local snapshot missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest.lower():
            errors.append(f"{sid}: snapshot SHA-256 mismatch")
        else:
            checked += 1
    return {"records": len(records), "verified_snapshots": checked, "missing_snapshots": missing, "errors": errors}


def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def query_terms(query: str) -> list[str]:
    terms = []
    for part in re.findall(r"[a-z0-9_+.-]+|[\u3400-\u9fff]+", normalize(query)):
        terms.append(part)
        if re.fullmatch(r"[\u3400-\u9fff]{3,}", part):
            terms.extend(part[i:i + 2] for i in range(len(part) - 1))
    return list(dict.fromkeys(terms))


def search(root: Path, query: str, limit: int = 8) -> list[dict]:
    terms = query_terms(query)
    if not terms:
        return []
    paths = list((root / "wiki").rglob("*.md")) + list((root / "docs").glob("*.md"))
    paths += list((root / "research").glob("*/findings.md"))
    results = []
    for path in sorted(paths):
        if path.name in ("log.md", "index.md") or "reports" in path.relative_to(root).parts:
            continue
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        title = next((x.lstrip("# ") for x in lines if x.startswith("# ")), path.stem)
        scores = [sum(min(normalize(line).count(t), 3) * len(t) for t in terms) for line in lines]
        if not any(scores):
            continue
        best = max(range(len(scores)), key=scores.__getitem__)
        score = sum(min(normalize(title).count(t), 3) * len(t) * 6 for t in terms) + sum(scores)
        results.append({"path": path.relative_to(root).as_posix(), "line": best + 1, "title": title,
                        "score": score, "snippet": lines[best][:260]})
    return sorted(results, key=lambda r: (-r["score"], r["path"]))[:limit]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("verify-sources", help="Check metadata and hashes; never contacts EDA or the network")
    check.add_argument("--require-snapshots", action="store_true", help="Fail if a private local snapshot is absent")
    check.add_argument("--json", action="store_true")
    find = sub.add_parser("search", help="Search original Chinese summaries and engineering notes")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=8)
    find.add_argument("--json", action="store_true")
    sources = sub.add_parser("sources", help="Find source metadata by ID or keywords")
    sources.add_argument("query", nargs="?", default="")
    args = parser.parse_args(argv)
    if args.command == "verify-sources":
        report = verify_sources(ROOT, args.require_snapshots)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"Sources: {report['records']}; hashed locally: {report['verified_snapshots']}; "
                  f"local snapshots absent: {len(report['missing_snapshots'])}; errors: {len(report['errors'])}")
            if report["missing_snapshots"]:
                print("Absent snapshots were NOT verified. Full third-party originals are kept locally, outside Git.")
            for error in report["errors"]:
                print(f"ERROR: {error}")
        return int(bool(report["errors"]))
    if args.command == "search":
        if not 1 <= args.limit <= 50:
            parser.error("--limit must be between 1 and 50")
        results = search(ROOT, args.query, args.limit)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for result in results:
                print(f"{result['path']}:{result['line']} — {result['title']}\n  {result['snippet']}")
            if not results:
                print("No matches. Try a shorter technical term or source ID.")
        return 0
    try:
        records = read_sources(ROOT)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    terms = query_terms(args.query)
    matches = [r for r in records if not terms or any(t in normalize(json.dumps(r, ensure_ascii=False)) for t in terms)]
    print(json.dumps(matches, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

