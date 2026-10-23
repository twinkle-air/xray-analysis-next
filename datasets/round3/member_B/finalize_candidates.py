"""Summarize local candidate checks and write a file hash list for A's review."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATES = HERE / "candidates"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    checks = read(CANDIDATES / "candidate_checks.json")
    samples = read(CANDIDATES / "B_samples.json")["samples"]
    families = read(CANDIDATES / "family_registry.json")["design_families"]
    coverage = read(CANDIDATES / "coverage.json")["targets"]
    rebuild = read(HERE / "rebuild_verification.json")
    assert checks["status"] == "passed_local_candidate_checks" and not checks["errors"]
    assert checks["historical_rows_compared"] == 3800 and len(checks["historical_nearest"]) == 250
    assert len(samples) == 250 and len(families) == 105
    assert rebuild["status"] == "passed" and all(r["byte_identical"] for r in rebuild["files"])
    nearest = checks["historical_nearest"]
    summary = {
        "status": "passed_local_candidate_checks_pending_A_global_review",
        "candidate_count": len(samples),
        "design_family_count": len(families),
        "category_counts": checks["category_counts"],
        "matrix_counts": checks["matrix_counts"],
        "target_count": len(coverage),
        "targets_with_positive_candidate": sum(v["positive_below_10ppm"] + v["positive_at_least_10ppm"] > 0 for v in coverage.values()),
        "historical_rows_compared": checks["historical_rows_compared"],
        "minimum_local_historical_L1_percentage_points": min(r["L1_percentage_points"] for r in nearest),
        "local_historical_pairs_within_0_5": sum(r["within_0_5"] for r in nearest),
        "cross_B_design_family_edges_within_0_5": len(checks["cross_design_family_near_edges"]),
        "independent_byte_identical_rebuilds": rebuild["independent_rebuilds"],
        "production_started": False,
        "pending_A_review": [
            "Remaining historical lineage and C/D candidate connected-family closure",
            "Final use split and family/profile assignment",
            "Production profile, source, dependency, noise-seed and command freeze",
            "90-spectrum pilot and subsequent sealed production",
        ],
    }
    write(HERE / "selfcheck_summary.json", summary)
    paths = [
        HERE / "README.md", HERE / "A_review_request.md", HERE / "build_candidates.py",
        HERE / "finalize_candidates.py", HERE / "rebuild_verification.json",
        HERE / "selfcheck_summary.json", HERE / "inputs/design_allocation.json",
        HERE / "inputs/design_ranges.json",
    ] + sorted(CANDIDATES.iterdir())
    manifest = {
        "status": "candidate_handoff_pr_pending_A_review",
        "files": [{"path": p.relative_to(HERE).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in paths],
    }
    write(HERE / "candidate_manifest.json", manifest)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
