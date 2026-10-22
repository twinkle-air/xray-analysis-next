"""Create D's seed manifest and run configuration from the confirmed plan."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "frozen_inputs"

TARGETS = [
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "K", "Ca", "Ti", "V", "Cr",
    "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "As", "Se", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Cd", "Sn", "Sb", "Ba", "W", "Pb",
]

DESIGN_SEEDS = {
    "silicate_routine": 2026102201,
    "silicate_sparse_boundary": 2026102202,
    "silicate_interference_bases": 2026102203,
    "iron_routine": 2026102204,
    "iron_sparse_boundary": 2026102205,
    "iron_interference_bases": 2026102206,
    "backup_silicate_routine": 2026102207,
    "backup_silicate_sparse_boundary": 2026102208,
    "backup_silicate_interference_bases": 2026102209,
    "backup_iron_routine": 2026102210,
    "backup_iron_sparse_boundary": 2026102211,
    "backup_iron_interference_bases": 2026102212,
}

BATCH_ROOTS = {"P1": 202610220101, "P2": 202610220102, "P3": 202610220103}
SPLIT_SEED = 20261022
REPLICATES = 2
WORKERS = 6


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    shard_families = {f"S{i:02d}": ("silicate_oxide" if i <= 6 else "iron_oxide") for i in range(1, 11)}
    batch_seeds = {}
    batches = {}
    for profile, root in BATCH_ROOTS.items():
        for i in range(1, 11):
            shard = f"S{i:02d}"
            key = f"{profile}_{shard}"
            seed = root * 100 + i
            batch_seeds[key] = seed
            batches[key] = {
                "profile_id": profile,
                "family": shard_families[shard],
                "samples": f"shards/{shard}.json",
                "seed": seed,
                "recipes": 25,
                "replicates": REPLICATES,
                "spectra": 50,
            }

    frozen_hashes = {name: sha256_file(FROZEN / name) for name in
                     ("P1.json", "P2.json", "P3.json", "design_ranges.json", "A_run_config.json")}

    seed_manifest = {
        "owner": "D",
        "round_id": "round2-20261021",
        "status": "proposed_pending_A_confirmation",
        "design_seeds": DESIGN_SEEDS,
        "batch_roots": BATCH_ROOTS,
        "batch_seeds": batch_seeds,
        "split_seed": SPLIT_SEED,
        "replicates": REPLICATES,
        "jitter": {},
        "seed_derivation": "batch_seed = batch_root * 100 + shard_index (S01=1 ... S10=10)",
        "not_reused": {
            "A_batch_seeds": {"P1": 202610210101, "P2": 202610210102, "P3": 202610210103},
            "A_split_seed": 20261021,
            "note": "A's seeds are A-only and are not reused by D.",
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    run_config = {
        "round_id": "round2-20261021",
        "owner": "D",
        "scope": "D production only; uses byte-identical A-frozen P1/P2/P3, design_ranges and generator pending cross-member confirmation",
        "seed_manifest": "D_seed_manifest.json",
        "design_seeds": DESIGN_SEEDS,
        "batch_seeds": {k: v["seed"] for k, v in batches.items()},
        "split_seed": SPLIT_SEED,
        "replicates": REPLICATES,
        "jitter": {},
        "target_elements": TARGETS,
        "target_count": len(TARGETS),
        "thread_environment": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
        "workers": WORKERS,
        "max_concurrency": WORKERS,
        "software_version": "0.2.1",
        "physics_version": "0.2.0",
        "closure": "strict",
        "legacy_al": "reject",
        "frozen_inputs": frozen_hashes,
        "frozen_manifest_scope": "A-only production freeze; global use pending",
        "cross_member_confirmation": "pending",
        "design_counts": {
            "silicate_oxide": {"routine": 90, "sparse_boundary": 30, "interference": 30, "total": 150},
            "iron_oxide": {"routine": 60, "sparse_boundary": 20, "interference": 20, "total": 100},
            "total": 250,
        },
        "backup_counts": {
            "silicate_oxide": {"routine": 5, "sparse_boundary": 5, "interference": 5, "total": 15},
            "iron_oxide": {"routine": 5, "sparse_boundary": 5, "interference": 5, "total": 15},
            "total": 30,
            "note": "Not counted in the 250; used only to replace candidates excluded by A.",
        },
        "batch_count": len(batches),
        "spectra_total": len(batches) * 50,
        "batches": batches,
        "version": "D-sharded-production-v1",
        "reason": "Ten whole-family shards per profile, 25 recipes per shard, two independent replicates, 30 independent CLI batches; unchanged physical solver.",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    (ROOT / "D_seed_manifest.json").write_text(
        json.dumps(seed_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "D_run_config.json").write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "seed_manifest": str(ROOT / "D_seed_manifest.json"),
        "run_config": str(ROOT / "D_run_config.json"),
        "batches": len(batches),
        "spectra_total": run_config["spectra_total"],
        "target_count": len(TARGETS),
        "frozen_hashes": frozen_hashes,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
