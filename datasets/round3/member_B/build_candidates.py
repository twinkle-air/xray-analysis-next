"""Build round-three B composition candidates only; no spectra or split approval."""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import pathlib
import sys

import numpy as np
import xraylib as xl
from scipy.spatial.distance import cdist

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
A_INPUTS = ROOT / "datasets/round3/member_A/inputs"
GENERATOR = A_INPUTS / "generator"
SOURCE_SHA256 = {
    "__init__.py": "3338a26d3706620d0b1eb836a6e39beb4ae15d61a4c04d9441215ec17ffeafa1",
    "core.py": "e820ecdb5ed5fbceb870f382c8c7c411ba85c65673bc19258fb935f562ed83b0",
    "minerals.py": "69fb768c041ef100721794628f46cb8b90c5acbf5f4c4a45c5e088bca6de1662",
}
HISTORY_SHA256 = "8a4461df5020c07a89603adfab164873e854a03498cf62358c5cf80fe1fc6473"
for name, expected in SOURCE_SHA256.items():
    source = GENERATOR / "fp_competition" / name
    if not source.is_file():
        raise FileNotFoundError(f"Required A generator source missing: {source}")
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise ValueError(f"A generator source SHA-256 mismatch: {source}")
sys.path.insert(0, str(GENERATOR))
from fp_competition.core import TARGET_ELEMENTS  # noqa: E402
from fp_competition.minerals import components_to_elements, design_minerals  # noqa: E402

SEED = 202610230301  # A's published design-allocation seed; never a noise seed.
FOCUS = ("Na", "Cu", "Zn", "Cd", "Co", "Rb")
CARRIERS = {"Na": "Na2O", "K": "K2O", "Fe": "Fe2O3T", "Ti": "TiO2"}
QUOTAS = {"ladder": 90, "interference": 50, "paired_negative_spike": 60, "routine": 50}


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def canonical(comp):
    return json.dumps({e: round(float(v), 12) for e, v in sorted(comp.items()) if round(float(v), 12) != 0}, sort_keys=True, separators=(",", ":"))


def stable_seed(text):
    return int.from_bytes(hashlib.sha256((str(SEED) + ":" + text).encode()).digest()[:8], "big") % (2**63 - 1)


def logdraw(rng, lo, hi):
    return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))


def fraction(formula, element):
    parsed = xl.CompoundParser("Fe2O3" if formula == "Fe2O3T" else formula)
    return sum(weight for z, weight in zip(parsed["Elements"], parsed["massFractions"]) if xl.AtomicNumberToSymbol(z) == element)


def modify(base, controls):
    compounds = dict(base["provenance"]["compounds_percent"])
    traces = dict(base["provenance"]["trace_ppm"])
    removed, fixed_compounds, fixed_traces = {}, {}, {}
    for element, ppm in controls.items():
        if not math.isfinite(ppm) or ppm < 0:
            raise ValueError("Invalid controlled concentration")
        for formula in list(compounds):
            if fraction(formula, element) > 0:
                removed[formula] = compounds.pop(formula)
        traces.pop(element, None)
        if element in CARRIERS:
            carrier = CARRIERS[element]
            fixed_compounds[carrier] = ppm / 10000 / fraction(carrier, element)
        else:
            fixed_traces[element] = ppm
    remaining = sum(compounds.values()) + sum(traces.values()) / 10000
    fixed_mass = sum(fixed_compounds.values()) + sum(fixed_traces.values()) / 10000
    if remaining <= 0 or fixed_mass >= 100:
        raise ValueError("Infeasible controlled concentration")
    scale = (100 - fixed_mass) / remaining
    adopted_compounds = {k: v * scale for k, v in compounds.items()}
    adopted_compounds.update(fixed_compounds)
    adopted_traces = {k: v * scale for k, v in traces.items()}
    adopted_traces.update(fixed_traces)
    used, ledger = components_to_elements(adopted_compounds, adopted_traces, closure="strict")
    actual = {e: used.get(e, 0) * 10000 for e in controls}
    if any(not np.isclose(actual[e], v, rtol=1e-10, atol=1e-9) for e, v in controls.items()):
        raise ValueError("Controlled target changed in conversion")
    delta = {e: used.get(e, 0) - base["composition_percent"].get(e, 0) for e in sorted(set(used) | set(base["composition_percent"]))}
    ledger["intervention"] = {
        "controlled_element_ppm": controls,
        "actual_element_ppm": actual,
        "removed_carrier_compounds_percent": removed,
        "fixed_carriers_percent": fixed_compounds,
        "uncontrolled_mixture_scale": scale,
        "compensation": "proportional scaling of remaining compounds and traces; controlled carriers replaced; no hidden normalization",
        "element_delta_percentage_points": delta,
        "controlled_range_override": True,
        "caveat": "Original ranges apply to initial background; controlled target levels intentionally override them.",
    }
    return used, ledger


def variants(family, rng):
    element, interferent, category = family["target"], family["interferent"], family["category"]
    if category == "ladder":
        intervals = [(10, 50), (50, 200), (200, 1000), (1000, 5000), (5000, 30000)] if element == "Na" else [(.5, 2), (2, 5), (5, 15), (15, 50), (50, 200)]
        return [("zero", {element: 0}, None)] + [(f"level_{i+1}", {element: logdraw(rng, *limits)}, list(limits)) for i, limits in enumerate(intervals)]
    if category in ("interference", "paired_negative_spike"):
        iron = family["matrix"] == "iron_oxide"
        if interferent in ("K", "Fe"):
            if interferent == "Fe":
                low_limits, high_limits = ((42, 48), (65, 73)) if iron else ((2, 5), (12, 18))
            else:
                low_limits, high_limits = ((.1, .3), (1.2, 1.8)) if iron else ((.1, .5), (3, 4.5))
            low = float(rng.uniform(*low_limits)) * fraction(CARRIERS[interferent], interferent) * 10000
            high = float(rng.uniform(*high_limits)) * fraction(CARRIERS[interferent], interferent) * 10000
        else:
            bounds = {
                "Zn": (2000, 3000) if iron else (1000, 2000),
                "Ni": (1000, 2000) if iron else (500, 1000),
                "W": (1000, 2000) if iron else (500, 1000),
                "Y": (700, 1500) if iron else (200, 500),
                "Pb": (2000, 3000) if iron else (1000, 2000),
                "Ba": (2500, 4000) if iron else (1500, 3000),
            }
            low, high = 0.0, logdraw(rng, *bounds[interferent])
        if category == "paired_negative_spike":
            limits = (1000, 10000) if element == "Na" else ((20, 200) if element in ("Cu", "Zn") else (10, 100))
            return [("negative", {element: 0, interferent: high}, None), ("spike", {element: logdraw(rng, *limits), interferent: high}, list(limits))]
        target_low = logdraw(rng, 100, 500) if element == "Na" else logdraw(rng, 3, 15)
        target_high = logdraw(rng, 5000, 20000) if element == "Na" else (logdraw(rng, 2000, 10000) if element == "Ti" else logdraw(rng, 100, 200))
        return [(role, {element: a, interferent: b}, None) for role, a, b in [
            ("target0_interferent_low", 0, low),
            ("target_low_interferent_low", target_low, low),
            ("target0_interferent_high", 0, high),
            ("target_low_interferent_high", target_low, high),
            ("target_high_interferent_high", target_high, high),
        ]]
    return [("routine", {}, None)]


def in_bounds(ledger, spec, controlled):
    compounds, traces = ledger["compounds_percent"], ledger["trace_ppm"]
    bounds = {**spec["compound_ranges_percent"], spec["balance_compound"]: spec["balance_range_percent"]}
    removed = set(ledger["intervention"]["removed_carrier_compounds_percent"])
    for formula, limits in bounds.items():
        if formula in removed or any(fraction(formula, e) > 0 for e in controlled):
            continue
        if not limits[0] - 1e-9 <= compounds.get(formula, 0) <= limits[1] + 1e-9:
            return False
    for e, value in traces.items():
        if e not in controlled and value != 0 and not spec["trace_ranges_ppm"][e][0] - 1e-7 <= value <= spec["trace_ranges_ppm"][e][1] + 1e-7:
            return False
    balance = spec["balance_compound"]
    lo, hi = spec["balance_range_percent"]
    return lo - 1e-9 <= compounds.get(balance, 0) <= hi + 1e-9


def construct(specs, assignments):
    samples, families = [], []
    for family in assignments:
        if family["owner"] != "B":
            continue
        spec = specs[family["matrix"]]["routine"]
        rng = np.random.default_rng(family["design_seed"])
        design = variants(family, rng)
        extra = {e: 0.0 for e in FOCUS if e not in (family["target"], family["interferent"]) and rng.random() < .25}
        if family["category"] == "routine" and rng.random() < .25:
            extra["Na"] = 0.0
        for attempt in range(500):
            background_seed = stable_seed(family["design_family_id"] + f":background:{attempt}")
            base = design_minerals(spec, 1, background_seed)["samples"][0]
            rows = []
            for index, (role, control, interval) in enumerate(design):
                controls = {**extra, **control}
                used, ledger = modify(base, controls)
                if not in_bounds(ledger, spec, controls):
                    break
                provenance = {
                    "kind": "round3_matched_compound_design", "round_id": "round3", "owner": "B",
                    "parent_family": family["design_family_id"], "matrix_type": family["matrix"],
                    "scenario": family["category"], "control_role": role,
                    "target": family["target"], "interferent": family["interferent"],
                    "target_bin_ppm": interval, "design_seed": family["design_seed"],
                    "background_seed": background_seed, "background_attempt": attempt,
                    "original_compounds_percent": base["provenance"]["compounds_percent"],
                    "original_trace_ppm": base["provenance"]["trace_ppm"],
                    "original_composition_percent": base["composition_percent"],
                    "conversion": ledger,
                    "lineage": "fresh independent background draw; not derived from a historical error example",
                    "global_status": "candidate_pending_global_freeze",
                    "scope": "synthetic homogeneous compound design; not certified material or measured geological population",
                }
                rows.append({"id": f"{family['design_family_id']}_V{index+1:02d}", "composition_percent": used, "provenance": provenance})
            if len(rows) == family["variants"]:
                samples.extend(rows)
                families.append({**family, "background_seed": background_seed, "background_attempt": attempt, "sample_ids": [r["id"] for r in rows]})
                break
        else:
            raise ValueError("No feasible background for " + family["design_family_id"])
    return samples, families


def local_history():
    path = A_INPUTS / "historical_compositions.json"
    if not path.is_file():
        raise FileNotFoundError(f"Required A historical snapshot missing: {path}")
    actual = digest(path)
    if actual != HISTORY_SHA256:
        raise ValueError(f"A historical snapshot SHA-256 mismatch: {path}")
    rows = read(path)["rows"]
    if len(rows) != 3800 or len({r["id"] for r in rows}) != 3800:
        raise ValueError("Expected 3,800 unique rows in A historical snapshot")
    return rows, [{"path": path.relative_to(ROOT).as_posix(), "sha256": actual, "rows": len(rows)}]


def verify(samples, families, specs, history):
    errors = []
    if len(samples) != 250 or len({r["id"] for r in samples}) != 250:
        errors.append("Expected 250 unique IDs")
    if len(families) != 105:
        errors.append("Expected 105 families")
    if len({canonical(r["composition_percent"]) for r in samples}) != 250:
        errors.append("Duplicate actual composition")
    category_counts = dict(collections.Counter(r["provenance"]["scenario"] for r in samples))
    matrix_counts = dict(collections.Counter(r["provenance"]["matrix_type"] for r in samples))
    if category_counts != QUOTAS or matrix_counts != {"silicate_oxide": 150, "iron_oxide": 100}:
        errors.append("Category or matrix quota mismatch")
    grouped = collections.defaultdict(list)
    for row in samples:
        comp, provenance = row["composition_percent"], row["provenance"]
        ledger = provenance["conversion"]
        controls = ledger["intervention"]["controlled_element_ppm"]
        if abs(sum(comp.values()) - 100) > 1e-9 or comp.get("O", 0) <= 0:
            errors.append(row["id"] + ": closure/O")
        rebuilt, _ = components_to_elements(ledger["compounds_percent"], ledger["trace_ppm"], closure="strict")
        if canonical(rebuilt) != canonical(comp):
            errors.append(row["id"] + ": conversion")
        if not in_bounds(ledger, specs[provenance["matrix_type"]]["routine"], controls):
            errors.append(row["id"] + ": non-controlled range")
        if any(not np.isclose(comp.get(e, 0) * 10000, v, atol=1e-9, rtol=1e-10) for e, v in controls.items()):
            errors.append(row["id"] + ": controlled ppm")
        original, _ = components_to_elements(provenance["original_compounds_percent"], provenance["original_trace_ppm"], closure="strict")
        if canonical(original) != canonical(provenance["original_composition_percent"]):
            errors.append(row["id"] + ": original background")
        rebuilt_comp, rebuilt_ledger = modify({"provenance": {"compounds_percent": provenance["original_compounds_percent"], "trace_ppm": provenance["original_trace_ppm"]}, "composition_percent": original}, controls)
        if canonical(rebuilt_comp) != canonical(comp) or rebuilt_ledger != ledger:
            errors.append(row["id"] + ": intervention ledger")
        grouped[provenance["parent_family"]].append(row)
    for family in families:
        rows = grouped[family["design_family_id"]]
        element, category = family["target"], family["category"]
        if len(rows) != family["variants"]:
            errors.append(family["design_family_id"] + ": incomplete")
            continue
        if len({canonical(r["provenance"]["original_composition_percent"]) for r in rows}) != 1:
            errors.append(family["design_family_id"] + ": unmatched background")
        actual = [r["composition_percent"].get(element, 0) * 10000 for r in rows] if element else []
        if category == "ladder":
            if actual[0] != 0 or not all(a < b for a, b in zip(actual, actual[1:])):
                errors.append(family["design_family_id"] + ": ladder order")
            for row, value in zip(rows[1:], actual[1:]):
                lo, hi = row["provenance"]["target_bin_ppm"]
                if not lo <= value < hi:
                    errors.append(row["id"] + ": ladder bin")
        if category == "paired_negative_spike" and not (actual[0] == 0 and actual[1] > 0):
            errors.append(family["design_family_id"] + ": negative/spike")
        if category == "interference":
            interferent = family["interferent"]
            vals = [r["composition_percent"].get(interferent, 0) * 10000 for r in rows]
            if not (actual[0] == actual[2] == 0 and np.isclose(actual[1], actual[3]) and actual[4] > actual[3] > 0 and np.isclose(vals[0], vals[1]) and np.isclose(vals[2], vals[3]) and np.isclose(vals[3], vals[4]) and vals[2] > vals[0]):
                errors.append(family["design_family_id"] + ": interference controls")
    elements = sorted(set().union(*(r["composition_percent"] for r in samples + history)))
    a = np.array([[r["composition_percent"].get(e, 0) for e in elements] for r in samples])
    near = []
    if history:
        b = np.array([[r["composition_percent"].get(e, 0) for e in elements] for r in history])
        dist = cdist(a, b, "cityblock")
        nearest = dist.argmin(axis=1)
        near = [{"sample_id": row["id"], "historical_id": history[int(j)]["id"], "L1_percentage_points": float(dist[i, j]), "within_0_5": bool(dist[i, j] <= .5)} for i, (row, j) in enumerate(zip(samples, nearest))]
    within = cdist(a, a, "cityblock")
    edges = [{"a": samples[int(i)]["id"], "b": samples[int(j)]["id"], "L1": float(within[i, j])} for i, j in zip(*np.where(np.triu(within <= .5, 1))) if samples[int(i)]["provenance"]["parent_family"] != samples[int(j)]["provenance"]["parent_family"]]
    return {
        "status": "passed_local_candidate_checks" if not errors else "failed",
        "errors": errors, "candidate_count": len(samples), "design_family_count": len(families),
        "category_counts": category_counts, "matrix_counts": matrix_counts,
        "historical_rows_compared": len(history), "historical_nearest": near,
        "cross_design_family_near_edges": edges,
        "historical_coverage": "A's sealed 3800-row repository snapshot; unavailable or unrecorded lineage and C/D candidates remain for global review",
        "cross_member_confirmation": "pending_A_global_review", "production_started": False,
        "eligible_for_training": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path, default=HERE / "candidates")
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("Refusing to overwrite an existing candidate directory")
    range_path = HERE / "inputs/design_ranges.json"
    allocation_path = HERE / "inputs/design_allocation.json"
    for path, expected in ((range_path, "5f347d179830f7e9c64e0d98fd02397582f263171e83c773513347d5090c9c6d"),
                           (allocation_path, "c07a57c83e3f007bb7dc1667807b3111ec4ee5e9a82baa8dfd1af2c7d950d4d4")):
        if not path.is_file():
            raise FileNotFoundError(f"Required B design input missing: {path}")
        if digest(path) != expected:
            raise ValueError(f"B design input SHA-256 mismatch: {path}")
    specs, allocation = read(range_path), read(allocation_path)
    assignments = allocation["families"]
    for row in assignments:
        if row["design_seed"] != stable_seed(row["design_family_id"]):
            raise ValueError("Allocation seed mismatch: " + row["design_family_id"])
    samples, families = construct(specs, assignments)
    if {f["design_family_id"] for f in families} != {f["design_family_id"] for f in assignments if f["owner"] == "B"}:
        raise ValueError("B family IDs differ from the published allocation")
    history, sources = local_history()
    report = verify(samples, families, specs, history)
    if report["errors"]:
        raise ValueError(report["errors"][:20])
    args.out.mkdir(parents=True)
    write(args.out / "B_samples.json", {"round_id": "round3", "owner": "B", "status": "candidate_pending_global_freeze", "production_started": False, "samples": samples})
    write(args.out / "family_registry.json", {"design_families": families, "status": "pending_global_connected_closure"})
    write(args.out / "candidate_checks.json", report)
    write(args.out / "input_identity.json", {
        "builder_sha256": digest(__file__), "ranges": {"path": "inputs/design_ranges.json", "sha256": digest(range_path)},
        "allocation": {"path": "inputs/design_allocation.json", "sha256": digest(allocation_path)},
        "generator_sources": [{"path": (GENERATOR / "fp_competition" / name).relative_to(ROOT).as_posix(),
                               "sha256": expected} for name, expected in SOURCE_SHA256.items()],
        "historical_sources": sources, "seed": SEED,
    })
    with (args.out / "formula_registry.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["global_recipe_id", "design_family_id", "matrix", "category", "target", "interferent", "control_role", "actual_target_ppm", "composition_sha256", "status"])
        for row in samples:
            p = row["provenance"]
            writer.writerow([row["id"], p["parent_family"], p["matrix_type"], p["scenario"], p["target"], p["interferent"], p["control_role"], row["composition_percent"].get(p["target"], 0) * 10000, hashlib.sha256(canonical(row["composition_percent"]).encode()).hexdigest(), "pending_global_freeze"])
    write(args.out / "coverage.json", {"targets": {e: {"zero": sum(r["composition_percent"].get(e, 0) == 0 for r in samples), "positive_below_10ppm": sum(0 < r["composition_percent"].get(e, 0) < .001 for r in samples), "positive_at_least_10ppm": sum(r["composition_percent"].get(e, 0) >= .001 for r in samples)} for e in TARGET_ELEMENTS}, "scope": "composition labels, not measured detection limits"})
    print(json.dumps({k: v for k, v in report.items() if k != "historical_nearest"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
