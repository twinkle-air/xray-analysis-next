"""Run the 30 sealed D batches, external audit/replay, and ZIP packaging."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]
PKG = WORK.parent / "fp-spectrum-generator-competition-v0.2.1"
APP = PKG / "fp_competition" / "app.py"
CONFIG = WORK / "D_run_config.json"
PRODUCTION = WORK / "production"
BATCHES = PRODUCTION / "batches"
QC = PRODUCTION / "qc"
ZIPS = PRODUCTION / "zips"
LOGS = PRODUCTION / "logs"
SUMMARY = PRODUCTION / "run_summary_D.json"

for path in (BATCHES, QC, ZIPS, LOGS):
    path.mkdir(parents=True, exist_ok=True)

lock = threading.Lock()
summary: dict = {
    "schema": "D-production-run/v1",
    "started_at_utc": datetime.now(timezone.utc).isoformat(),
    "finished_at_utc": None,
    "workers": None,
    "batches": {},
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_summary() -> None:
    with lock:
        SUMMARY.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )


def env() -> dict:
    value = os.environ.copy()
    value.update({
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "PYTHONUNBUFFERED": "1",
    })
    return value


def run_command(name: str, command: list[str]) -> dict:
    log = LOGS / f"{name}.log"
    started = time.monotonic()
    with log.open("a", encoding="utf-8") as stream:
        stream.write(f"\n=== {now()} ===\n")
        stream.write(" ".join(command) + "\n")
        stream.flush()
        completed = subprocess.run(
            command, cwd=PKG, env=env(), text=True,
            stdout=stream, stderr=subprocess.STDOUT, check=False,
        )
        stream.write(f"exit={completed.returncode} seconds={time.monotonic() - started:.3f}\n")
    return {"returncode": completed.returncode,
            "seconds": round(time.monotonic() - started, 3),
            "log": str(log)}


def batch_command(batch_id: str, batch: dict) -> list[str]:
    return [
        sys.executable, str(APP), "batch",
        "--samples", str(WORK / "design" / batch["samples"]),
        "--profile", str(WORK / "frozen_inputs" / f"{batch['profile_id']}.json"),
        "--out", str(BATCHES / batch_id),
        "--seed", str(batch["seed"]),
        "--replicates", str(batch["replicates"]),
        "--closure", str(read_json(CONFIG)["closure"]),
        "--legacy-al", str(read_json(CONFIG)["legacy_al"]),
        "--targets", *read_json(CONFIG)["target_elements"],
        "--split-seed", str(read_json(CONFIG)["split_seed"]),
        "--design-ranges", str(WORK / "frozen_inputs" / "design_ranges.json"),
    ]


def generate(batch_id: str, batch: dict) -> dict:
    out = BATCHES / batch_id
    if out.exists():
        manifest = out / "manifest.json"
        if manifest.is_file() and read_json(manifest).get("status") == "complete":
            return {"status": "existing_complete", "seconds": 0.0}
        return {"status": "existing_incomplete", "seconds": 0.0,
                "errors": ["Existing batch directory is incomplete; kept untouched"]}
    result = run_command(f"{batch_id}.generate", batch_command(batch_id, batch))
    manifest = out / "manifest.json"
    if result["returncode"] != 0:
        return {"status": "failed", **result, "errors": ["Generation command failed"]}
    if not manifest.is_file():
        return {"status": "failed", **result, "errors": ["Missing manifest.json"]}
    value = read_json(manifest)
    if value.get("status") != "complete" or value.get("spectrum_count") != batch["spectra"]:
        return {"status": "failed", **result,
                "errors": [f"Manifest status={value.get('status')} spectra={value.get('spectrum_count')}"]}
    return {"status": "passed", **result}


def audit(batch_id: str, batch: dict) -> dict:
    out = QC / f"{batch_id}.audit.json"
    dataset = BATCHES / batch_id
    if out.is_file():
        value = read_json(out)
        if value.get("status") == "passed" and value.get("spectra_checked") == batch["spectra"]:
            return {"status": "existing_passed", "seconds": 0.0}
        return {"status": "failed", "seconds": 0.0,
                "errors": ["Existing audit is not a full pass; kept untouched"]}
    result = run_command(f"{batch_id}.audit",
                         [sys.executable, str(APP), "audit",
                          "--dataset", str(dataset), "--out", str(out)])
    if result["returncode"] != 0 or not out.is_file():
        return {"status": "failed", **result, "errors": ["Audit command failed"]}
    value = read_json(out)
    if value.get("status") != "passed" or value.get("spectra_checked") != batch["spectra"]:
        return {"status": "failed", **result, "errors": ["Audit did not pass fully"]}
    return {"status": "passed", **result}


def replay(batch_id: str, batch: dict) -> dict:
    out = QC / f"{batch_id}.replay.json"
    dataset = BATCHES / batch_id
    if out.is_file():
        value = read_json(out)
        if (value.get("status") in ("passed", "passed_with_environment_differences")
                and value.get("scope") == "all_records"
                and value.get("spectra_recalculated") == batch["spectra"]):
            return {"status": "existing_passed", "seconds": 0.0}
        return {"status": "failed", "seconds": 0.0,
                "errors": ["Existing replay is not a full pass; kept untouched"]}
    result = run_command(f"{batch_id}.replay",
                         [sys.executable, str(APP), "replay",
                          "--dataset", str(dataset), "--out", str(out)])
    if result["returncode"] != 0 or not out.is_file():
        return {"status": "failed", **result, "errors": ["Replay command failed"]}
    value = read_json(out)
    if value.get("status") not in ("passed", "passed_with_environment_differences"):
        return {"status": "failed", **result, "errors": ["Replay did not pass fully"]}
    if value.get("scope") != "all_records" or value.get("spectra_recalculated") != batch["spectra"]:
        return {"status": "failed", **result, "errors": ["Replay was not a full replay"]}
    return {"status": "passed", **result}


def pack(batch_id: str, batch: dict) -> dict:
    out = ZIPS / f"{batch_id}.zip"
    sidecar = out.with_suffix(out.suffix + ".sha256")
    dataset = BATCHES / batch_id
    if out.is_file() and sidecar.is_file():
        digest = sidecar.read_text(encoding="ascii").split()[0]
        if digest == sha256(out):
            return {"status": "existing_passed", "seconds": 0.0, "zip": str(out), "sha256": digest}
        return {"status": "failed", "seconds": 0.0,
                "errors": ["Existing ZIP hash does not match its sidecar; kept untouched"]}
    if out.exists() or sidecar.exists():
        return {"status": "failed", "seconds": 0.0,
                "errors": ["Incomplete existing ZIP output; kept untouched"]}
    result = run_command(f"{batch_id}.pack",
                         [sys.executable, str(APP), "pack",
                          "--dataset", str(dataset), "--out", str(out)])
    if result["returncode"] != 0 or not out.is_file() or not sidecar.is_file():
        return {"status": "failed", **result, "errors": ["Pack command failed"]}
    digest = sidecar.read_text(encoding="ascii").split()[0]
    if digest != sha256(out):
        return {"status": "failed", **result,
                "errors": ["ZIP sidecar hash does not match the archive"]}
    return {"status": "passed", **result, "zip": str(out), "sha256": digest}


def update(batch_id: str, phase: str, value: dict) -> None:
    with lock:
        row = summary["batches"].setdefault(batch_id, {})
        row[phase] = value
        if phase == "generate":
            row["status"] = value["status"]
        elif value["status"] != "passed" and value["status"] != "existing_passed":
            row["status"] = "failed"
        SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                           encoding="utf-8")


def run_phase(phase: str, jobs: list[tuple[str, dict]], workers: int, function) -> None:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(function, batch_id, batch): batch_id
                   for batch_id, batch in jobs}
        for future in as_completed(futures):
            batch_id = futures[future]
            try:
                value = future.result()
            except Exception as exc:
                value = {"status": "failed", "seconds": 0.0,
                         "errors": [f"{type(exc).__name__}: {exc}"]}
            update(batch_id, phase, value)
            print(f"{phase} {batch_id}: {value['status']}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["all", "generate", "audit", "replay", "pack"],
                        default="all")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--only", default=None, help="Comma-separated batch IDs")
    args = parser.parse_args()

    config = read_json(CONFIG)
    workers = args.workers or int(config.get("workers", 6))
    summary["workers"] = workers
    wanted = set(args.only.split(",")) if args.only else None
    jobs = [(batch_id, batch) for batch_id, batch in config["batches"].items()
            if wanted is None or batch_id in wanted]
    if args.only:
        unknown = wanted - set(config["batches"])
        if unknown:
            raise SystemExit(f"Unknown batch IDs: {sorted(unknown)}")

    phases = (["generate", "audit", "replay", "pack"] if args.phase == "all" else [args.phase])
    functions = {"generate": generate, "audit": audit, "replay": replay, "pack": pack}
    for phase in phases:
        run_phase(phase, jobs, workers, functions[phase])
        write_summary()

    rows = summary["batches"]
    totals = {
        "batches": len(rows),
        "spectra": sum(config["batches"][batch_id]["spectra"] for batch_id in rows),
        "generate_passed": sum(1 for row in rows.values()
                               if row.get("generate", {}).get("status") in ("passed", "existing_complete")),
        "audit_passed": sum(1 for row in rows.values()
                            if row.get("audit", {}).get("status") in ("passed", "existing_passed")),
        "replay_passed": sum(1 for row in rows.values()
                             if row.get("replay", {}).get("status") in ("passed", "existing_passed")),
        "pack_passed": sum(1 for row in rows.values()
                           if row.get("pack", {}).get("status") in ("passed", "existing_passed")),
    }
    summary["totals"] = totals
    summary["finished_at_utc"] = now()
    write_summary()
    print(json.dumps(totals, ensure_ascii=False))
    return 0 if all(totals[key] == len(rows) for key in
                    ("generate_passed", "audit_passed", "replay_passed", "pack_passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
