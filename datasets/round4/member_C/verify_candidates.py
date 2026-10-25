"""Independent structural and provenance review for C's Round4 candidates."""
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
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from build_candidates import (  # noqa: E402
    INPUTS, LINE_WINDOW_EV, TARGET_ELEMENTS, canonical, components_to_elements,
    cross_member_round4, distance_reports, line_evidence, load_history, read_json, sha256,
    within_source_ranges,
)

ALLOWED_ROLES = {"train_nominal", "validation_nominal", "sealed_test_nominal"}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def resolve_source(path: str, round3_root: pathlib.Path) -> pathlib.Path:
    prefix = "datasets/round3/"
    if path.startswith(prefix):
        return round3_root / pathlib.Path(path[len(prefix):])
    return ROOT / pathlib.Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=pathlib.Path, default=HERE / "candidates")
    parser.add_argument("--round3-root", type=pathlib.Path, default=ROOT / "datasets/round3")
    args = parser.parse_args()
    source = args.input.resolve()
    round3_root = args.round3_root.resolve()
    errors: list[str] = []
    samples_doc = read_json(source / "C_samples.json")
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
    if len(samples) != 1000 or len({r["id"] for r in samples}) != 1000:
        fail(errors, "expected 1000 unique candidate recipes")
    if len(families) != 320 or len({r["design_family_id"] for r in families}) != 320:
        fail(errors, "expected 320 provisional design families")
    if checks.get("cross_member_confirmation") != "pending_B_D_round4_merge_and_A_global_closure":
        fail(errors, "cross-member closure is misreported")
    if checks.get("role_and_stage_assignments") != "pending_global_freeze":
        fail(errors, "role or stage assignment is misreported")
    if checks.get("status") != "passed_C_local_candidate_checks":
        fail(errors, "candidate checks are not marked as local-only checks")
    if checks.get("line_window_eV") != LINE_WINDOW_EV:
        fail(errors, "line window in checks differs from the builder")
    if checks.get("line_interference_pairs") != 40:
        fail(errors, "expected 40 line-interference families")

    source_manifest_hash = hashlib.sha256(
        json.dumps(source_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if identity.get("source_manifest_sha256") != source_manifest_hash:
        fail(errors, "input identity does not bind the source manifest")
    if identity.get("builder_sha256") != sha256(HERE / "build_candidates.py"):
        fail(errors, "input identity does not bind the current candidate builder")

    by_family: dict[str, list[dict]] = {}
    seen_compositions = set()
    role_recipe_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    matrix_counts: dict[str, int] = {}
    for row in samples:
        provenance = row["provenance"]
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
        ledger = provenance["compensation_ledger"]
        conversion = ledger["conversion"]
        rebuilt, _ = components_to_elements(conversion["compounds_percent"], conversion["trace_ppm"], closure="strict")
        rebuilt = {e: float(rebuilt.get(e, 0.0)) for e in (*TARGET_ELEMENTS, "O")}
        if canonical(rebuilt) != canonical(comp):
            fail(errors, f"{row['id']}: composition cannot be rebuilt from the saved source recipe")
        if set(provenance["controlled_element_ppm"]) != set(ledger["controlled_element_ppm"]):
            fail(errors, f"{row['id']}: controlled labels and compensation ledger differ")
        for element, actual_ppm in provenance["controlled_element_ppm"].items():
            if not np.isclose(comp[element] * 10000.0, actual_ppm, rtol=1e-9, atol=1e-8):
                fail(errors, f"{row['id']}: controlled {element} concentration mismatch")
        if provenance["production_noise_seed"] is not None or provenance["production_condition"] is not None:
            fail(errors, f"{row['id']}: production conditions/noise were assigned")
        if provenance["requested_role"] not in ALLOWED_ROLES:
            fail(errors, f"{row['id']}: unexpected nominal role")
        if provenance["global_role_status"] != "pending_global_freeze" or provenance["eligible_for_training"] is not False:
            fail(errors, f"{row['id']}: role or eligibility was assigned prematurely")
        controlled = set(provenance["controlled_element_ppm"])
        if not within_source_ranges(ledger, specs[provenance["matrix_class"]]["routine"], controlled):
            fail(errors, f"{row['id']}: uncontrolled components left the source design ranges")
        if provenance["design_type"] == "matrix_interference":
            evidence = provenance.get("line_interference_evidence")
            recomputed = line_evidence(provenance["target_element"], provenance["interferent_element"])
            if not evidence:
                fail(errors, f"{row['id']}: line evidence is missing")
            else:
                for field in ("target_line", "interferent_line", "delta_eV",
                              "target_line_energy_eV", "interferent_line_energy_eV"):
                    if evidence.get(field) != recomputed.get(field):
                        fail(errors, f"{row['id']}: line evidence field {field} does not recompute")
                if float(evidence["delta_eV"]) > LINE_WINDOW_EV:
                    fail(errors, f"{row['id']}: line evidence is outside the candidate window")
        by_family.setdefault(provenance["design_family_id"], []).append(row)
        category_counts[provenance["design_type"]] = category_counts.get(provenance["design_type"], 0) + 1
        matrix_counts[provenance["matrix_class"]] = matrix_counts.get(provenance["matrix_class"], 0) + 1
        role_recipe_counts[provenance["requested_role"]] = role_recipe_counts.get(provenance["requested_role"], 0) + 1

    if category_counts != {"element_gradient": 400, "zero_spike": 200,
                           "matrix_interference": 200, "routine_coverage": 200}:
        fail(errors, f"category quotas differ: {category_counts}")
    if matrix_counts != {"silicate_oxide": 500, "iron_oxide": 500}:
        fail(errors, f"matrix quotas differ: {matrix_counts}")
    if role_recipe_counts != {"train_nominal": 800, "validation_nominal": 100,
                              "sealed_test_nominal": 100}:
        fail(errors, f"nominal role recipe quotas differ: {role_recipe_counts}")

    family_by_id = {f["design_family_id"]: f for f in families}
    if set(by_family) != set(family_by_id):
        fail(errors, "recipe families do not match the family registry")
    role_family_counts: dict[str, int] = {}
    for fid, family in family_by_id.items():
        rows = by_family.get(fid, [])
        if len(rows) != family["variant_count"]:
            fail(errors, f"{fid}: expected {family['variant_count']} variants, found {len(rows)}")
        if rows and len({canonical(r["provenance"]["original_composition_percent"]) for r in rows}) != 1:
            fail(errors, f"{fid}: family variants do not share the recorded base recipe")
        if rows and {r["provenance"]["requested_role"] for r in rows} != {family["requested_role"]}:
            fail(errors, f"{fid}: family and recipe roles differ")
        if family.get("global_role_status") != "pending_global_freeze":
            fail(errors, f"{fid}: family role is not pending global freeze")
        role_family_counts[family["requested_role"]] = role_family_counts.get(family["requested_role"], 0) + 1
        target = family["target"]
        values = [r["composition_percent"].get(target, 0.0) * 10000 for r in rows] if target else []
        if family["design_type"] == "element_gradient":
            if values[0] != 0 or not all(a < b for a, b in zip(values, values[1:])):
                fail(errors, f"{fid}: gradient is not zero plus nine increasing levels")
        if family["design_type"] == "zero_spike":
            if values[0] != 0 or not all(v > 0 for v in values[1:]) or not all(
                    a < b for a, b in zip(values[1:], values[2:])):
                fail(errors, f"{fid}: zero/spike levels invalid")
        if family["design_type"] == "matrix_interference":
            other = family["interferent"]
            interferent_values = [r["composition_percent"].get(other, 0.0) * 10000 for r in rows]
            if not (values[0] == values[2] == 0 and values[1] > 0 and values[4] > values[3] > 0
                    and np.isclose(values[1], values[3], rtol=1e-9, atol=1e-8)
                    and np.isclose(interferent_values[0], interferent_values[1], rtol=1e-9, atol=1e-8)
                    and np.isclose(interferent_values[2], interferent_values[3], rtol=1e-9, atol=1e-8)
                    and np.isclose(interferent_values[3], interferent_values[4], rtol=1e-9, atol=1e-8)
                    and interferent_values[2] > interferent_values[0]):
                fail(errors, f"{fid}: matrix-interaction controls invalid")
            evidence = family.get("line_interference_evidence")
            recomputed = line_evidence(family["target"], family["interferent"])
            if not evidence:
                fail(errors, f"{fid}: family line evidence is missing")
            else:
                for field in ("target_line", "interferent_line", "delta_eV",
                              "target_line_energy_eV", "interferent_line_energy_eV"):
                    if evidence.get(field) != recomputed.get(field):
                        fail(errors, f"{fid}: family line evidence field {field} does not recompute")
    if role_family_counts != {"train_nominal": 256, "validation_nominal": 32,
                              "sealed_test_nominal": 32}:
        fail(errors, f"nominal role family quotas differ: {role_family_counts}")

    with (source / "candidate_registry.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        registry = list(csv.DictReader(stream))
    if len(registry) != 1000 or {r["candidate_id"] for r in registry} != {r["id"] for r in samples}:
        fail(errors, "candidate_registry.csv is not a one-to-one index of the composition file")
    sample_by_id = {r["id"]: r for r in samples}
    for record in registry:
        row = sample_by_id[record["candidate_id"]]
        provenance = row["provenance"]
        if canonical(json.loads(record["composition_used_json"])) != canonical(row["composition_percent"]):
            fail(errors, f"{record['candidate_id']}: registry used-composition mismatch")
        if canonical(json.loads(record["original_composition_json"])) != canonical(
                provenance["original_composition_percent"]):
            fail(errors, f"{record['candidate_id']}: registry original-composition mismatch")
        if json.loads(record["compensation_ledger_json"]) != provenance["compensation_ledger"]:
            fail(errors, f"{record['candidate_id']}: registry compensation-ledger mismatch")
        if record["requested_role"] != provenance["requested_role"]:
            fail(errors, f"{record['candidate_id']}: registry role mismatch")
        if record["global_role_status"] != "pending_global_freeze":
            fail(errors, f"{record['candidate_id']}: registry role is not pending global freeze")
        if record["historical_source_id"] != provenance["historical_source"]:
            fail(errors, f"{record['candidate_id']}: registry historical source mismatch")
        if record["historical_exposure"] != provenance["historical_exposure"]:
            fail(errors, f"{record['candidate_id']}: registry historical exposure mismatch")

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

    history, _ = load_history(INPUTS / "historical_compositions.json", round3_root)
    nearest, backgrounds, edges, distance_summary = distance_reports(samples, families, history)
    if len(history) != checks["historical_rows_compared"]:
        fail(errors, "historical row count differs from the checks")
    for key in ("candidate_to_history_min_L1_pp", "background_to_history_min_L1_pp"):
        if not math.isclose(float(checks["distance_summary"][key]),
                            float(distance_summary[key]), rel_tol=1e-12, abs_tol=1e-12):
            fail(errors, f"historical distance summary mismatch: {key}")
    for key in ("candidate_history_links_at_0_5pp", "background_history_links_at_0_5pp",
                "cross_family_candidate_edges_at_0_5pp"):
        if int(checks["distance_summary"][key]) != int(distance_summary[key]):
            fail(errors, f"historical distance count mismatch: {key}")
    with (source / "nearest_history.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        nearest_csv = list(csv.DictReader(stream))
    if len(nearest_csv) != 1000 or {r["candidate_id"] for r in nearest_csv} != {r["id"] for r in samples}:
        fail(errors, "nearest_history.csv is not a one-to-one candidate index")
    with (source / "original_background_nearest_history.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        background_csv = list(csv.DictReader(stream))
    if len(background_csv) != 320 or {r["design_family_id"] for r in background_csv} != set(family_by_id):
        fail(errors, "original_background_nearest_history.csv is not a one-to-one family index")
    with (source / "cross_family_near_edges.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        edge_csv = list(csv.DictReader(stream))
    if len(edge_csv) != len(edges):
        fail(errors, "cross_family_near_edges.csv row count differs from recomputation")

    a_round4_path = ROOT / "datasets/round4/member_A/candidates_v1/A_samples.json"
    cross_edges, cross_summary = cross_member_round4(samples, a_round4_path)
    reported_cross = checks.get("cross_member_round4_A", {})
    for key in ("other_candidate_count", "pairs_at_0_5pp", "exact_composition_matches"):
        if int(reported_cross.get(key, -1)) != int(cross_summary[key]):
            fail(errors, f"cross-member A summary mismatch: {key}")
    if not math.isclose(float(reported_cross.get("minimum_L1_percentage_points", -1)),
                        float(cross_summary["minimum_L1_percentage_points"]), rel_tol=1e-12, abs_tol=1e-12):
        fail(errors, "cross-member A minimum L1 differs from recomputation")
    with (source / "cross_member_near_edges.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        cross_csv = list(csv.DictReader(stream))
    if len(cross_csv) != len(cross_edges):
        fail(errors, "cross_member_near_edges.csv row count differs from recomputation")

    with (source / "line_interference_evidence.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        evidence_csv = list(csv.DictReader(stream))
    interference_families = [f for f in families if f["design_type"] == "matrix_interference"]
    if len(evidence_csv) != 40 or {r["design_family_id"] for r in evidence_csv} != {
            f["design_family_id"] for f in interference_families}:
        fail(errors, "line_interference_evidence.csv is not a one-to-one interference-family index")
    for record in evidence_csv:
        family = family_by_id[record["design_family_id"]]
        recomputed = line_evidence(family["target"], family["interferent"])
        if record["target_element"] != family["target"] or record["interferent_element"] != family["interferent"]:
            fail(errors, f"{record['design_family_id']}: line evidence labels differ")
        if record["target_line"] != recomputed["target_line"] or record["interferent_line"] != recomputed["interferent_line"]:
            fail(errors, f"{record['design_family_id']}: line names do not recompute")
        if not math.isclose(float(record["delta_eV"]), float(recomputed["delta_eV"]), rel_tol=0, abs_tol=1e-9):
            fail(errors, f"{record['design_family_id']}: line delta does not recompute")
        if float(record["delta_eV"]) > LINE_WINDOW_EV:
            fail(errors, f"{record['design_family_id']}: line delta is outside the window")

    coverage = read_json(source / "coverage.json")
    if coverage.get("target_elements_tracked") != len(TARGET_ELEMENTS) or set(coverage.get("elements", {})) != set(TARGET_ELEMENTS):
        fail(errors, "coverage.json does not track exactly the 32 target elements")
    else:
        for element, row in coverage["elements"].items():
            total = sum(int(row[key]) for key in (
                "zero", "positive_below_1ppm", "positive_1_to_10ppm",
                "positive_10_to_100ppm", "positive_100_to_1000ppm",
                "positive_at_least_1000ppm",
            ))
            if total != 1000:
                fail(errors, f"coverage bins for {element} sum to {total}, not 1000")

    result = {
        "schema": "round4-C-independent-candidate-review/1",
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "candidate_count": len(samples),
        "design_family_count_before_global_merge": len(families),
        "category_counts": category_counts,
        "matrix_counts": matrix_counts,
        "nominal_role_recipe_counts": role_recipe_counts,
        "nominal_role_family_counts": role_family_counts,
        "line_interference_pairs": len(evidence_csv),
        "line_window_eV": LINE_WINDOW_EV,
        "historical_rows_compared": len(history),
        "distance_summary": distance_summary,
        "cross_member_round4_A": cross_summary,
        "historical_global_closure": "pending all members and global role freeze",
        "production_started": False,
        "spectra_generated": 0,
        "eligible_for_training": False,
    }
    verification_path = source / "independent_verification.json"
    verification_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    verification_entry = {
        "path": verification_path.name,
        "bytes": verification_path.stat().st_size,
        "sha256": sha256(verification_path),
    }
    delivery["files"] = [x for x in delivery["files"] if x["path"] != verification_path.name]
    delivery["files"].append(verification_entry)
    delivery["files"].sort(key=lambda x: x["path"])
    (source / "delivery_manifest.json").write_text(
        json.dumps(delivery, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
