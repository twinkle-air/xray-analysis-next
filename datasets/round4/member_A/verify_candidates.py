"""Independent structural and provenance review for A's Round4 candidates."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(HERE))
from build_candidates import (  # noqa: E402
    INPUTS, TARGET_ELEMENTS, canonical, components_to_elements, read_json, sha256,
    within_source_ranges,
)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def resolve_source(path: str, round3_root: pathlib.Path) -> pathlib.Path:
    prefix = "datasets/round3/"
    if path.startswith(prefix):
        return round3_root / pathlib.Path(path[len(prefix):])
    return ROOT / pathlib.Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=pathlib.Path, default=HERE / "candidates_v1")
    parser.add_argument("--round3-root", type=pathlib.Path, default=ROOT / "datasets/round3")
    args = parser.parse_args()
    source = args.input.resolve()
    round3_root = args.round3_root.resolve()
    errors: list[str] = []
    samples_doc = read_json(source / "A_samples.json")
    family_doc = read_json(source / "family_registry.json")
    source_manifest = read_json(source / "source_manifest.json")
    identity = read_json(source / "input_identity.json")
    checks = read_json(source / "candidate_checks.json")
    delivery = read_json(source / "delivery_manifest.json")
    samples = samples_doc["samples"]
    families = family_doc["families"]
    specs = read_json(INPUTS / "design_ranges.json")

    if samples_doc.get("production_started") is not False or samples_doc.get("eligible_for_training") is not False:
        fail(errors, "candidate file contains a non-candidate production/training state")
    if checks.get("production_started") is not False or checks.get("spectra_generated") != 0:
        fail(errors, "candidate checks claim production or generated spectra")
    if identity.get("noise_seeds_allocated") is not False:
        fail(errors, "production noise seeds were allocated")
    if len(samples) != 2000 or len({r["id"] for r in samples}) != 2000:
        fail(errors, "expected 2000 unique candidate recipes")
    if len(families) != 640 or len({r["design_family_id"] for r in families}) != 640:
        fail(errors, "expected 640 provisional design families")
    if checks.get("cross_member_confirmation") != "pending_B_C_D":
        fail(errors, "cross-member closure is misreported")
    if checks.get("role_and_stage_assignments") != "pending_global_freeze":
        fail(errors, "role or stage assignment is misreported")
    source_manifest_hash = hashlib.sha256(json.dumps(source_manifest, ensure_ascii=False, sort_keys=True,
                                                     separators=(",", ":")).encode("utf-8")).hexdigest()
    if identity.get("source_manifest_sha256") != source_manifest_hash:
        fail(errors, "input identity does not bind the source manifest")
    if identity.get("builder_sha256") != sha256(HERE / "build_candidates.py"):
        fail(errors, "input identity does not bind the current candidate builder")

    by_family: dict[str, list[dict]] = {}
    seen_compositions = set()
    for row in samples:
        p = row["provenance"]
        comp = row["composition_percent"]
        if set(comp) != set((*TARGET_ELEMENTS, "O")):
            fail(errors, f"{row['id']}: expected exactly 32 target labels plus O")
            continue
        if not math.isclose(sum(float(x) for x in comp.values()), 100.0, rel_tol=0, abs_tol=2e-9) or comp["O"] <= 0:
            fail(errors, f"{row['id']}: composition does not close or O is absent")
        key = canonical(comp)
        if key in seen_compositions:
            fail(errors, f"{row['id']}: duplicate composition")
        seen_compositions.add(key)
        ledger = p["compensation_ledger"]
        conversion = ledger["conversion"]
        rebuilt, _ = components_to_elements(conversion["compounds_percent"], conversion["trace_ppm"], closure="strict")
        rebuilt = {e: float(rebuilt.get(e, 0.0)) for e in (*TARGET_ELEMENTS, "O")}
        if canonical(rebuilt) != canonical(comp):
            fail(errors, f"{row['id']}: composition cannot be rebuilt from the saved source recipe")
        if set(p["controlled_element_ppm"]) != set(ledger["controlled_element_ppm"]):
            fail(errors, f"{row['id']}: controlled labels and compensation ledger differ")
        for element, actual_ppm in p["controlled_element_ppm"].items():
            if not np.isclose(comp[element] * 10000.0, actual_ppm, rtol=1e-10, atol=1e-7):
                fail(errors, f"{row['id']}: controlled {element} concentration mismatch")
        if p["production_noise_seed"] is not None or p["production_condition"] is not None:
            fail(errors, f"{row['id']}: production conditions/noise were assigned")
        if p["requested_role"] != "unassigned_pending_global_freeze" or p["eligible_for_training"] is not False:
            fail(errors, f"{row['id']}: role or eligibility was assigned prematurely")
        controlled = set(p["controlled_element_ppm"])
        if not within_source_ranges(ledger, specs[p["matrix_class"]]["routine"], controlled):
            fail(errors, f"{row['id']}: uncontrolled components left the source design ranges")
        by_family.setdefault(p["design_family_id"], []).append(row)

    family_by_id = {f["design_family_id"]: f for f in families}
    if set(by_family) != set(family_by_id):
        fail(errors, "recipe families do not match the family registry")
    for fid, family in family_by_id.items():
        rows = by_family.get(fid, [])
        if len(rows) != family["variant_count"]:
            fail(errors, f"{fid}: expected {family['variant_count']} variants, found {len(rows)}")
        if rows and len({canonical(r["provenance"]["original_composition_percent"]) for r in rows}) != 1:
            fail(errors, f"{fid}: family variants do not share the recorded base recipe")

    expected_categories = {"element_gradient": 800, "zero_spike": 400, "matrix_interference": 400, "routine_coverage": 400}
    actual_categories: dict[str, int] = {}
    for row in samples:
        kind = row["provenance"]["design_type"]
        actual_categories[kind] = actual_categories.get(kind, 0) + 1
    if actual_categories != expected_categories:
        fail(errors, f"category quotas differ: {actual_categories}")

    with (source / "candidate_registry.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        registry = list(csv.DictReader(stream))
    if len(registry) != 2000 or {r["candidate_id"] for r in registry} != {r["id"] for r in samples}:
        fail(errors, "candidate_registry.csv is not a one-to-one index of the composition file")
    sample_by_id = {r["id"]: r for r in samples}
    for record in registry:
        row = sample_by_id[record["candidate_id"]]
        if canonical(json.loads(record["composition_used_json"])) != canonical(row["composition_percent"]):
            fail(errors, f"{record['candidate_id']}: registry used-composition mismatch")
        if record["requested_role"] != "unassigned_pending_global_freeze":
            fail(errors, f"{record['candidate_id']}: registry contains a preassigned role")

    for entry in source_manifest["inputs"]:
        path = resolve_source(entry["path"], round3_root)
        if not path.is_file():
            fail(errors, f"missing source input: {entry['path']}")
        elif sha256(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            fail(errors, f"source hash/size mismatch: {entry['path']}")

    manifest_paths = {x["path"] for x in delivery["files"]}
    for entry in delivery["files"]:
        path = source / entry["path"]
        if not path.is_file() or sha256(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            fail(errors, f"delivery file hash/size mismatch: {entry['path']}")
    if "delivery_manifest.json" in manifest_paths:
        fail(errors, "delivery manifest must not recursively hash itself")
    if checks.get("status") != "passed_A_local_candidate_checks":
        fail(errors, "candidate checks are not marked as local-only checks")

    result = {
        "schema": "round4-A-independent-candidate-review/1",
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "candidate_count": len(samples), "design_family_count_before_global_merge": len(families),
        "historical_global_closure": "pending all members and global role freeze",
        "production_started": False, "spectra_generated": 0, "eligible_for_training": False,
    }
    verification_path = source / "independent_verification.json"
    verification_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    verification_entry = {"path": verification_path.name, "bytes": verification_path.stat().st_size,
                          "sha256": sha256(verification_path)}
    delivery["files"] = [x for x in delivery["files"] if x["path"] != verification_path.name]
    delivery["files"].append(verification_entry)
    delivery["files"].sort(key=lambda x: x["path"])
    (source / "delivery_manifest.json").write_text(
        json.dumps(delivery, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
