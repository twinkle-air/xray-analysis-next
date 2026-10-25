"""Independent structural and provenance review for B's Round4 candidates.

This verifier does not import the builder.  It re-reads the delivered files,
recomputes closure, compensation, range compliance, zero labels, line-table
evidence, history distances and cross-member distances, and compares every
count with the claims in candidate_checks.json.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import pathlib
import sys

import numpy as np
import xraylib as xl
from scipy.spatial.distance import cdist

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUTS = ROOT / "datasets/round3/member_A/inputs"
sys.path.insert(0, str(INPUTS / "generator"))
from fp_competition.core import TARGET_ELEMENTS  # noqa: E402
from fp_competition.minerals import components_to_elements  # noqa: E402

THRESHOLD_L1 = 0.5
WINDOW_EV = 150.0
CARRIERS = {"Na": "Na2O", "Mg": "MgO", "Al": "Al2O3", "Si": "SiO2", "P": "P2O5",
            "K": "K2O", "Ca": "CaO", "Ti": "TiO2", "Mn": "MnO", "Fe": "Fe2O3T"}
TRACE_ELEMENTS = set(("V", "Cr", "Co", "Ni", "Cu", "Zn", "As", "Se", "Rb", "Sr", "Y", "Zr",
                      "Nb", "Mo", "Cd", "Sn", "Sb", "Ba", "W", "Pb", "S", "Cl"))
LINE_DEFS = {"KA1": xl.KA1_LINE, "KA2": xl.KA2_LINE, "KB1": xl.KB1_LINE,
             "LA1": xl.LA1_LINE, "LA2": xl.LA2_LINE, "LB1": xl.LB1_LINE,
             "LB2": xl.LB2_LINE, "MA1": xl.MA1_LINE, "MB": xl.MB_LINE}

FIELDS = ["candidate_id", "member", "design_family_id", "parent_family_id", "design_type",
          "variant_id", "matrix_class", "composition_used_json", "original_composition_json",
          "compensation_ledger_json", "historical_source_id", "historical_exposure",
          "requested_role", "global_role_status"]


def read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: dict) -> str:
    return json.dumps({k: round(float(v), 12) for k, v in sorted(value.items())
                       if round(float(v), 12) != 0},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fraction(formula: str, element: str) -> float:
    parsed = xl.CompoundParser("Fe2O3" if formula == "Fe2O3T" else formula)
    for z, weight in zip(parsed["Elements"], parsed["massFractions"]):
        if xl.AtomicNumberToSymbol(z) == element:
            return float(weight)
    return 0.0


def element_lines(element: str) -> list[tuple[str, float, float]]:
    z = xl.SymbolToAtomicNumber(element)
    rows = []
    for name, code in LINE_DEFS.items():
        try:
            energy = xl.LineEnergy(z, code)
            rate = xl.RadRate(z, code)
        except Exception:
            continue
        if energy and energy > 0 and rate and rate > 0:
            rows.append((name, float(energy) * 1000.0, float(rate)))
    return rows


def best_overlap(a: str, b: str) -> dict:
    best = None
    for a_name, a_e, a_i in element_lines(a):
        for b_name, b_e, b_i in element_lines(b):
            delta = abs(a_e - b_e)
            if best is None or delta < best["delta_eV"]:
                best = {"target_line": a_name, "target_line_energy_eV": round(a_e, 1),
                        "target_rad_rate": round(a_i, 5),
                        "interferent_line": b_name, "interferent_line_energy_eV": round(b_e, 1),
                        "interferent_rad_rate": round(b_i, 5), "delta_eV": round(delta, 1)}
    return best


def to_matrix(rows: list[dict], elements: list[str]) -> np.ndarray:
    def comp(row):
        return row.get("composition_percent", row.get("composition", {}))
    return np.array([[float(comp(r).get(e, 0.0)) for e in elements] for r in rows], dtype=float)


def main() -> int:
    parser = argparse.ArgumentParser(description="Independent review of B round-four candidates")
    parser.add_argument("--out", default=str(HERE / "candidates"))
    args = parser.parse_args()
    out = pathlib.Path(args.out)

    errors: list[str] = []
    notes: list[str] = []

    def fail(message: str) -> None:
        errors.append(message)

    samples_doc = read_json(out / "B_samples.json")
    samples = samples_doc["samples"]
    families_doc = read_json(out / "family_registry.json")
    families = families_doc["design_families"]
    checks = read_json(out / "candidate_checks.json")
    manifest = read_json(out / "delivery_manifest.json")
    specs = read_json(INPUTS / "design_ranges.json")

    # ---------------------------------------------------------------- hashes
    for entry in manifest["files"]:
        path = out / entry["path"]
        if not path.exists():
            fail(f"delivery manifest lists missing file {entry['path']}")
            continue
        if path.stat().st_size != entry["bytes"]:
            fail(f"size mismatch for {entry['path']}")
        if sha256(path) != entry["sha256"]:
            fail(f"sha256 mismatch for {entry['path']}")

    # ---------------------------------------------------------------- counts
    counts = collections.Counter(s["provenance"]["design_type"] for s in samples)
    matrices = collections.Counter(s["provenance"]["matrix_class"] for s in samples)
    roles = collections.Counter(s["provenance"]["requested_role"] for s in samples)
    family_counts = collections.Counter(f["design_type"] for f in families)
    if len(samples) != 1000:
        fail(f"candidate count {len(samples)} != 1000")
    if len(families) != 320:
        fail(f"family count {len(families)} != 320")
    for key, value in (("element_gradient", 400), ("zero_spike", 200),
                       ("matrix_interference", 200), ("routine_coverage", 200)):
        if counts.get(key) != value:
            fail(f"{key} count {counts.get(key)} != {value}")
    for key, value in (("silicate_oxide", 500), ("iron_oxide", 500)):
        if matrices.get(key) != value:
            fail(f"{key} count {matrices.get(key)} != {value}")
    for key, value in (("train_nominal", 800), ("validation_nominal", 100),
                       ("sealed_test_nominal", 100)):
        if roles.get(key) != value:
            fail(f"role {key} {roles.get(key)} != {value}")
    if counts != collections.Counter(checks["category_counts"]):
        fail("category counts disagree with candidate_checks.json")
    if matrices != collections.Counter(checks["matrix_counts"]):
        fail("matrix counts disagree with candidate_checks.json")
    if roles != collections.Counter(checks["nominal_role_recipe_counts"]):
        fail("role counts disagree with candidate_checks.json")

    ids = [s["id"] for s in samples]
    if len(set(ids)) != len(ids):
        fail("duplicate candidate ids")
    family_ids = [f["design_family_id"] for f in families]
    if len(set(family_ids)) != len(family_ids):
        fail("duplicate design family ids")
    variant_union = {vid for f in families for vid in f["variant_ids"]}
    if variant_union != set(ids):
        fail("family_registry variant ids do not match B_samples ids")

    # ----------------------------------------------------------- variant shape
    by_family = collections.defaultdict(list)
    for sample in samples:
        by_family[sample["provenance"]["design_family_id"]].append(sample["provenance"]["control_role"])
    for family in families:
        roles_in_family = sorted(by_family[family["design_family_id"]])
        kind = family["design_type"]
        if kind == "element_gradient" and len(roles_in_family) != 10:
            fail(f"{family['design_family_id']} has {len(roles_in_family)} variants, expected 10")
        if kind == "zero_spike":
            if len(roles_in_family) != 5 or "true_zero" not in roles_in_family:
                fail(f"{family['design_family_id']} is not one true zero plus four spikes")
        if kind == "matrix_interference" and len(roles_in_family) != 5:
            fail(f"{family['design_family_id']} has {len(roles_in_family)} interference variants")
        if kind == "routine_coverage" and len(roles_in_family) != 1:
            fail(f"{family['design_family_id']} routine family has {len(roles_in_family)} rows")

    # --------------------------------------------------------------- closure
    worst_sum, worst_id = 0.0, None
    negative = 0
    for sample in samples:
        values = sample["composition_percent"]
        if any(v < 0 for v in values.values()):
            negative += 1
        total = sum(values.values())
        if abs(total - 100.0) > abs(worst_sum):
            worst_sum, worst_id = total - 100.0, sample["id"]
        if abs(total - 100.0) > 1e-6:
            fail(f"closure failure {sample['id']}: {total:.9f}")
    if negative:
        fail(f"{negative} compositions contain negative values")

    # ------------------------------------------------------- compensation rebuild
    rebuild_worst, rebuild_id = 0.0, None
    for sample in samples:
        ledger = sample["provenance"]["compensation_ledger"]
        compounds = ledger["final_compounds_percent"]
        traces = ledger["final_trace_ppm"]
        rebuilt, _ = components_to_elements(compounds, traces)
        for element, value in rebuilt.items():
            delta = abs(value - sample["composition_percent"].get(element, 0.0))
            if delta > rebuild_worst:
                rebuild_worst, rebuild_id = delta, sample["id"]
            if delta > 1e-6:
                fail(f"compensation rebuild mismatch {sample['id']} {element}: {delta:.3e}")
                break
        controlled = ledger["controlled_element_ppm"]
        for element, ppm in controlled.items():
            actual = sample["composition_percent"].get(element, 0.0) * 10000.0
            if abs(actual - ppm) > 1e-5:
                fail(f"controlled level not honoured {sample['id']} {element}: "
                     f"{actual:.6f} vs {ppm:.6f}")

    # ------------------------------------------------------------- range check
    range_failures = 0
    for sample in samples:
        provenance = sample["provenance"]
        spec = specs[provenance["matrix_class"]][
            "interference" if provenance["design_type"] == "matrix_interference" else "routine"]
        ledger = provenance["compensation_ledger"]
        controlled_compounds = set(ledger["removed_compounds_percent"])
        controlled_traces = set(ledger["removed_trace_ppm"])
        for formula, value in ledger["final_compounds_percent"].items():
            if formula in controlled_compounds:
                continue
            ceiling = (spec["balance_range_percent"][1] if formula == spec["balance_compound"]
                       else spec["compound_ranges_percent"].get(formula, [0, 0])[1])
            if value > ceiling + 1e-6:
                range_failures += 1
                fail(f"{sample['id']} uncontrolled {formula}={value:.6f} exceeds {ceiling}")
        for element, value in ledger["final_trace_ppm"].items():
            if element in controlled_traces or value <= 0:
                continue
            if element in spec["trace_ranges_ppm"]:
                ceiling = spec["trace_ranges_ppm"][element][1]
            elif element == "S":
                ceiling = spec["compound_ranges_percent"]["CaSO4"][1] * fraction("CaSO4", "S") * 1e4
            elif element == "Cl":
                ceiling = spec["compound_ranges_percent"]["NaCl"][1] * fraction("NaCl", "Cl") * 1e4
            else:
                range_failures += 1
                fail(f"{sample['id']} unexpected trace {element}")
                continue
            if value > ceiling + 1e-6:
                range_failures += 1
                fail(f"{sample['id']} uncontrolled {element}={value:.3f}ppm exceeds {ceiling:.3f}")

    # ------------------------------------------------------------ zero labels
    zero_conflicts = 0
    zero_entries = 0
    for sample in samples:
        for element, ppm in sample["provenance"]["controlled_element_ppm"].items():
            if ppm == 0.0 and sample["composition_percent"].get(element, 0.0) != 0.0:
                zero_conflicts += 1
                fail(f"zero label not zero {sample['id']} {element}")
        zero_entries += sum(1 for v in sample["composition_percent"].values() if v == 0.0)
    if zero_entries != checks["exact_zero_labels_verified"]:
        fail(f"zero entry count {zero_entries} != claim {checks['exact_zero_labels_verified']}")

    # ------------------------------------------------------- line evidence
    evidence_rows = list(csv.DictReader((out / "line_interference_evidence.csv").open(encoding="utf-8")))
    if len(evidence_rows) != 40:
        fail(f"line evidence rows {len(evidence_rows)} != 40")
    for row in evidence_rows:
        overlap = best_overlap(row["target"], row["interferent"])
        if float(row["delta_eV"]) != overlap["delta_eV"]:
            fail(f"line evidence delta mismatch {row['family_id']}")
        if float(row["delta_eV"]) > WINDOW_EV:
            fail(f"line evidence outside window {row['family_id']} {row['delta_eV']}")
        if row["target_line"] != overlap["target_line"] or row["interferent_line"] != overlap["interferent_line"]:
            fail(f"line evidence line name mismatch {row['family_id']}")
    interference_samples = [s for s in samples
                            if s["provenance"]["design_type"] == "matrix_interference"]
    if any(s["provenance"].get("line_interference_evidence") is None for s in interference_samples):
        fail("interference sample without line_interference_evidence")

    # -------------------------------------------------------------- distances
    history = read_json(INPUTS / "historical_compositions.json")
    hist_rows = [{"id": r["id"], "composition": r["composition_percent"]}
                 for r in history["rows"]]
    for member in ("A", "B", "C", "D"):
        for candidate in (ROOT / f"datasets/round3/member_{member}/candidates/{member}_samples.json",
                          ROOT / f"datasets/round3/member_{member}/candidates_v1/{member}_samples.json"):
            if candidate.exists():
                hist_rows.extend({"id": r["id"], "composition": r["composition_percent"]}
                                 for r in read_json(candidate)["samples"])
                break
    elements = sorted({e for s in samples for e in s["composition_percent"]} |
                      {e for h in hist_rows for e in h["composition"]})
    distances = cdist(to_matrix(samples, elements), to_matrix(hist_rows, elements),
                      metric="cityblock")
    min_history = float(distances.min())
    history_links = int((distances <= THRESHOLD_L1).sum())
    if history_links != checks["distance_summary"]["candidate_history_links_at_0_5pp"]:
        fail("history link count disagrees with candidate_checks.json")
    if abs(min_history - checks["distance_summary"]["candidate_to_history_min_L1_pp"]) > 1e-6:
        fail("minimum history L1 disagrees with candidate_checks.json")

    # ----------------------------------------------------------- cross member
    cross = {}
    for member, path in (("A", ROOT / "datasets/round4/member_A/candidates_v1/A_samples.json"),
                         ("C", ROOT / "datasets/round4/member_C/candidates/C_samples.json"),
                         ("D", ROOT / "datasets/round4/member_D/candidates/D_samples.json")):
        if not path.exists():
            cross[member] = {"status": "not_available_in_workspace"}
            notes.append(f"round4 {member} candidates unavailable; cross screen not recomputed")
            continue
        other = read_json(path)["samples"]
        wide = sorted({e for s in other for e in s["composition_percent"]} | set(elements))
        matrix = cdist(to_matrix(samples, wide), to_matrix(other, wide), metric="cityblock")
        other_keys = {canonical(s["composition_percent"]) for s in other}
        exact = sum(1 for s in samples if canonical(s["composition_percent"]) in other_keys)
        cross[member] = {
            "other_candidate_count": len(other),
            "minimum_L1_percentage_points": float(matrix.min()),
            "pairs_at_0_5pp": int((matrix <= THRESHOLD_L1).sum()),
            "exact_composition_matches": exact,
        }
        claim = checks["cross_member_round4"].get(member, {})
        if claim.get("status", "").startswith("not_available"):
            fail(f"checks mark {member} unavailable but the file exists")
            continue
        for key in ("other_candidate_count", "pairs_at_0_5pp", "exact_composition_matches"):
            if cross[member][key] != claim[key]:
                fail(f"cross-member {member} {key} disagreement")
        if abs(cross[member]["minimum_L1_percentage_points"]
               - claim["minimum_L1_percentage_points"]) > 1e-6:
            fail(f"cross-member {member} minimum L1 disagreement")
        if cross[member]["pairs_at_0_5pp"]:
            fail(f"{cross[member]['pairs_at_0_5pp']} B-vs-{member} pairs at or below 0.5 pp")

    # ------------------------------------------------------------- registry
    rows = list(csv.DictReader((out / "candidate_registry.csv").open(encoding="utf-8")))
    if len(rows) != len(samples):
        fail(f"registry rows {len(rows)} != {len(samples)}")
    if rows and list(rows[0].keys()) != FIELDS:
        fail("registry columns differ from the shared template")
    by_id = {s["id"]: s for s in samples}
    for row in rows:
        sample = by_id.get(row["candidate_id"])
        if sample is None:
            fail(f"registry row without sample {row['candidate_id']}")
            continue
        if canonical(sample["composition_percent"]) != canonical(json.loads(row["composition_used_json"])):
            fail(f"registry composition mismatch {row['candidate_id']}")
        if row["global_role_status"] != "pending_global_freeze":
            fail(f"registry row claims a frozen role {row['candidate_id']}")
        if row["member"] != "B":
            fail(f"registry row member wrong {row['candidate_id']}")

    # --------------------------------------------------------------- no spectra
    for flag in ("production_started", "eligible_for_training", "noise_seeds_allocated"):
        if samples_doc.get(flag) is not False:
            fail(f"B_samples.json {flag} is not false")
    if samples_doc.get("spectra_generated") != 0:
        fail("B_samples.json declares generated spectra")
    if checks.get("production_started") is not False or checks.get("spectra_generated") != 0:
        fail("candidate_checks.json claims production or spectra")
    if any(s["provenance"]["production_noise_seed"] is not None for s in samples):
        fail("a candidate declares a production noise seed")

    result = {
        "schema": "round4-B-independent-candidate-review/1",
        "status": "passed" if not errors else "failed",
        "errors": errors[:200],
        "error_count": len(errors),
        "notes": notes,
        "reviewed_files": {
            "B_samples.json": {"sha256": sha256(out / "B_samples.json"),
                               "bytes": (out / "B_samples.json").stat().st_size},
            "candidate_registry.csv": {"sha256": sha256(out / "candidate_registry.csv"),
                                       "bytes": (out / "candidate_registry.csv").stat().st_size},
            "family_registry.json": {"sha256": sha256(out / "family_registry.json"),
                                     "bytes": (out / "family_registry.json").stat().st_size},
            "line_interference_evidence.csv": {
                "sha256": sha256(out / "line_interference_evidence.csv"),
                "bytes": (out / "line_interference_evidence.csv").stat().st_size},
        },
        "checks": {
            "candidate_count": len(samples),
            "design_family_count": len(families),
            "category_counts": dict(counts),
            "matrix_counts": dict(matrices),
            "requested_role_counts": dict(roles),
            "worst_closure_residual_percent": round(worst_sum, 12),
            "worst_closure_candidate": worst_id,
            "worst_rebuild_delta_percent": rebuild_worst,
            "worst_rebuild_candidate": rebuild_id,
            "range_violations": range_failures,
            "controlled_zero_labels": sum(
                1 for s in samples for ppm in s["provenance"]["controlled_element_ppm"].values()
                if ppm == 0.0),
            "zero_entry_count": zero_entries,
            "zero_label_conflicts": zero_conflicts,
            "line_evidence_rows": len(evidence_rows),
            "line_window_eV": WINDOW_EV,
            "history_rows_compared": len(hist_rows),
            "history_min_L1_pp": min_history,
            "history_links_at_0_5pp": history_links,
            "cross_member_round4": cross,
        },
        "scope": "Structural, closure, compensation, range, line-table and distance review of candidate compositions only. No spectra exist and no accuracy claim is made.",
    }
    (out / "independent_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "errors": result["error_count"],
                      "checks": result["checks"]}, ensure_ascii=False, indent=2)[:2500])
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
