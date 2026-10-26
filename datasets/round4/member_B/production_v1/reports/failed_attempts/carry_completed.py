"""Carry verified completed batches into a fresh revision so the runner can resume.

The runner refuses to continue in an output directory that still holds partial or
failed batches.  This script copies only batches whose summary.json says
`passed_all_records`, whose archive SHA matches, and whose QC evidence hashes
match, into a new (empty) output directory.  Partial/failed batches stay where
they are as evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import sys


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", required=True, type=pathlib.Path)
    parser.add_argument("--to", dest="target", required=True, type=pathlib.Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source, target = args.source.resolve(), args.target.resolve()
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"refusing to write into non-empty {target}")

    carried, refused, records = 0, [], 0
    for summary in sorted((source / "reports").glob("*/summary.json")):
        doc = json.loads(summary.read_text(encoding="utf-8"))
        if doc.get("status") != "passed_all_records":
            refused.append((summary.parent.name, "status:" + str(doc.get("status"))))
            continue
        batch_id = doc["batch_id"]
        archive = source / "archives" / (batch_id + ".zip")
        if not archive.is_file() or sha256(archive) != doc["archive_sha256"]:
            refused.append((batch_id, "archive missing or hash mismatch"))
            continue
        for name, digest in doc.get("qc_files_sha256", {}).items():
            evidence = summary.parent / name
            if not evidence.is_file() or sha256(evidence) != digest:
                refused.append((batch_id, "QC evidence mismatch: " + name))
                break
        else:
            carried += 1
            records += int(doc.get("records", 0))
            if args.dry_run:
                continue
            for sub in ("sealed_batches", "reports", "archives"):
                (target / sub).mkdir(parents=True, exist_ok=True)
            if not (target / "sealed_batches" / batch_id).exists():
                shutil.copytree(source / "sealed_batches" / batch_id,
                                target / "sealed_batches" / batch_id)
            shutil.copytree(summary.parent, target / "reports" / batch_id, dirs_exist_ok=True)
            shutil.copy2(archive, target / "archives" / archive.name)
            sidecar = archive.with_suffix(".zip.sha256")
            if sidecar.is_file():
                shutil.copy2(sidecar, target / "archives" / sidecar.name)

    if not args.dry_run and carried:
        shutil.copy2(source / "resource_preflight.json", target / "resource_preflight.json")
    print(json.dumps({"carried_batches": carried, "carried_records": records,
                      "refused": refused[:10], "refused_count": len(refused),
                      "target": str(target), "dry_run": args.dry_run}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
