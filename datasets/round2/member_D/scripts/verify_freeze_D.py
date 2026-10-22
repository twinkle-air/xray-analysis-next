"""Verify every file in A's freeze manifest against local frozen copies.

Shard files are reconstructed from the cached PR #14 patch when absent locally.
Reconstruction is verification-only; D production uses its own generated shards.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "frozen_inputs"
GENERATOR = Path(r"C:/Users/陈/Desktop/AI开发/fp-spectrum-generator-competition-v0.2.1")
PR_CACHE = Path(
    r"C:/Users/陈/.qoder/tmp/C--Users---Desktop-AI--/"
    r"8cb7b4c7-9ae6-46aa-839f-4064f9f803d8/tool-results/"
    r"github_pull_request_read_cf3a1b92ac1a.txt"
)
REPORT = ROOT / "reports" / "freeze_verification_D.json"
RECON = ROOT / "verification" / "a_pr14"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def patch_lines(patch: str) -> list[str] | None:
    lines = patch.split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("@@")), None)
    if start is None:
        return None
    out: list[str] = []
    for line in lines[start + 1:]:
        if line.startswith("+") and not line.startswith("+++"):
            out.append(line[1:])
        elif line.startswith(" "):
            out.append(line[1:])
    return out


def reconstruct(lines: list[str], expected: str, dest: Path) -> dict | None:
    variants = [
        ("crlf_no_trailing", "\r\n".join(lines)),
        ("crlf_trailing", "\r\n".join(lines) + "\r\n"),
        ("lf_no_trailing", "\n".join(lines)),
        ("lf_trailing", "\n".join(lines) + "\n"),
    ]
    for name, text in variants:
        data = text.encode("utf-8")
        if sha256_bytes(data) == expected:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return {"line_endings": name, "bytes": len(data)}
    return None


def local_path_for(key: str) -> Path:
    if key.startswith("generator/fp_competition/"):
        return GENERATOR / key[len("generator/"):]
    if key.startswith("profiles/"):
        return FROZEN / Path(key).name
    if key in {"A_run_config.json", "A_samples.json", "design_ranges.json"}:
        return FROZEN / key
    if key.startswith("shards/"):
        return RECON / key
    raise ValueError("Unmapped manifest key: " + key)


def main() -> int:
    manifest = json.loads((FROZEN / "freeze_manifest.json").read_text(encoding="utf-8"))
    files: dict[str, str] = manifest["files"]

    cached: dict[str, str] = {}
    cache_note = None
    if PR_CACHE.is_file():
        try:
            raw = json.loads(PR_CACHE.read_text(encoding="utf-8"))
            entries = raw.get("result", []) if isinstance(raw, dict) else raw
            for entry in entries:
                name = entry.get("filename")
                if name and entry.get("patch"):
                    cached[name] = entry["patch"]
        except Exception as exc:  # noqa: BLE001
            cache_note = f"PR cache unreadable: {exc}"
    else:
        cache_note = "PR cache not found"

    results: dict[str, dict] = {}
    matched = reconstructed = missing = mismatched = 0

    for key, expected in sorted(files.items()):
        entry: dict = {"expected_sha256": expected}
        path = local_path_for(key)
        try:
            if path.is_file():
                actual = sha256_file(path)
                entry.update(path=str(path), actual_sha256=actual, bytes=path.stat().st_size)
                if actual == expected:
                    entry["status"] = "matched"
                    matched += 1
                else:
                    entry["status"] = "mismatch"
                    mismatched += 1
            else:
                pr_name = key
                if key.startswith("shards/"):
                    pr_name = "datasets/round2/member_A/production_inputs_v2/" + key
                patch = cached.get(pr_name)
                lines = patch_lines(patch) if patch else None
                info = reconstruct(lines, expected, path) if lines else None
                if info:
                    entry.update(path=str(path), actual_sha256=expected, status="reconstructed_matched", **info)
                    reconstructed += 1
                else:
                    entry["status"] = "missing"
                    entry["note"] = "Not present locally and not reconstructable from cached PR patch"
                    missing += 1
        except Exception as exc:  # noqa: BLE001
            entry.update(status="error", error=str(exc))
            mismatched += 1
        results[key] = entry

    baseline_entry: dict = {"status": "not_checked"}
    baseline_path = GENERATOR / "fp_competition" / "physics_baseline.json"
    if baseline_path.is_file():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        protected = {}
        for name, expected in baseline.get("files", {}).items():
            p = GENERATOR / "fp_competition" / name
            actual = sha256_file(p) if p.is_file() else None
            protected[name] = {
                "expected_sha256": expected,
                "actual_sha256": actual,
                "status": "matched" if actual == expected else "mismatch",
            }
        statuses = {v["status"] for v in protected.values()}
        baseline_entry = {
            "status": "matched" if statuses == {"matched"} else "mismatch",
            "files": protected,
        }

    status = "passed"
    notes = []
    if mismatched:
        status = "failed"
    elif missing:
        status = "passed_with_missing_inputs"
        notes.append("Some manifest entries are absent locally; see results.")
    if cache_note:
        notes.append(cache_note)
    if baseline_entry["status"] != "matched":
        status = "failed"
        notes.append("physics_baseline protected module mismatch")

    report = {
        "status": status,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.platform(),
            "python": sys.version,
        },
        "manifest": str(FROZEN / "freeze_manifest.json"),
        "manifest_scope": manifest.get("scope"),
        "generator_root": str(GENERATOR),
        "counts": {
            "total": len(files),
            "matched": matched,
            "reconstructed_matched": reconstructed,
            "missing": missing,
            "mismatch_or_error": mismatched,
        },
        "physics_baseline": baseline_entry,
        "results": results,
        "notes": notes,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": status,
        "counts": report["counts"],
        "physics_baseline": baseline_entry["status"],
        "report": str(REPORT),
        "notes": notes,
    }, ensure_ascii=False, indent=2))
    return 0 if status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
