"""Build A's round-four composition candidates only; never generate spectra."""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import pathlib
import platform
import sys

import numpy as np
import xraylib as xl
from scipy.spatial.distance import cdist

ROOT = pathlib.Path(__file__).resolve().parents[3]
INPUTS = ROOT / "datasets/round3/member_A/inputs"
GENERATOR = INPUTS / "generator"
sys.path.insert(0, str(GENERATOR))
from fp_competition.core import TARGET_ELEMENTS  # noqa: E402
from fp_competition.minerals import components_to_elements, design_minerals  # noqa: E402
from fp_competition.version import VERSION as GENERATOR_VERSION  # noqa: E402

FOCUS = ("Na", "Mg", "Al", "Si", "Fe")
MATRIX_NAMES = {"silicate_oxide": "silicate_oxide", "iron_oxide": "iron_oxide"}
CARRIERS = {
    "Na": "Na2O", "Mg": "MgO", "Al": "Al2O3", "Si": "SiO2", "Fe": "Fe2O3T",
    "P": "P2O5", "K": "K2O", "Ca": "CaO", "Ti": "TiO2", "Mn": "MnO",
}
THRESHOLD_L1 = 0.5
SCHEMA = "round4-A-candidate-compositions/1"


def read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: dict) -> str:
    return json.dumps({k: round(float(v), 12) for k, v in sorted(value.items()) if round(float(v), 12) != 0},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def candidate_seed(key: str) -> int:
    """Deterministic composition-design seed; it is not a production/noise seed."""
    raw = hashlib.sha256(("round4-A-candidate-only-v1:" + key).encode("utf-8")).digest()
    return int.from_bytes(raw[:4], "big")


def formula_fraction(formula: str, element: str) -> float:
    parsed = xl.CompoundParser("Fe2O3" if formula == "Fe2O3T" else formula)
    return sum(float(w) for z, w in zip(parsed["Elements"], parsed["massFractions"])
               if xl.AtomicNumberToSymbol(z) == element)


def formula_has(formula: str, element: str) -> bool:
    parsed = xl.CompoundParser("Fe2O3" if formula == "Fe2O3T" else formula)
    return any(xl.AtomicNumberToSymbol(z) == element for z in parsed["Elements"])


def element_max_ppm(matrix_spec: dict, element: str) -> float:
    carrier = CARRIERS[element]
    if carrier in matrix_spec["compound_ranges_percent"]:
        oxide_max = matrix_spec["compound_ranges_percent"][carrier][1]
    elif carrier == matrix_spec["balance_compound"]:
        oxide_max = matrix_spec["balance_range_percent"][1]
    else:
        raise ValueError(f"No supported carrier range for {element}/{carrier}")
    return oxide_max * formula_fraction(carrier, element) * 10000.0


def positive_ladder(matrix_spec: dict, element: str) -> list[float]:
    maximum = element_max_ppm(matrix_spec, element)
    raw = [1.0, 10.0, 100.0, 1000.0, 5000.0, maximum * .1, maximum * .3, maximum * .6, maximum]
    values = sorted({min(maximum, float(x)) for x in raw if x > 0})
    if len(values) != 9:
        values = sorted(set(float(x) for x in np.geomspace(1.0, maximum, 9)))
    if len(values) != 9:
        raise ValueError(f"Could not form nine distinct positive levels for {element}")
    return values


def spike_levels(matrix_spec: dict, element: str) -> list[float]:
    maximum = element_max_ppm(matrix_spec, element)
    return sorted({10.0, 100.0, 1000.0, maximum * .5})


def base_composition(sample: dict) -> dict:
    return {e: float(sample["composition_percent"].get(e, 0.0)) for e in (*TARGET_ELEMENTS, "O")}


def apply_controls(base: dict, controls_ppm: dict[str, float]) -> tuple[dict, dict]:
    """Replace controlled elements with oxide/element inputs, then scale the rest explicitly."""
    source = base["provenance"]
    compounds = {k: float(v) for k, v in source["compounds_percent"].items()}
    traces = {k: float(v) for k, v in source["trace_ppm"].items()}
    removed_compounds: dict[str, float] = {}
    removed_traces: dict[str, float] = {}
    fixed_compounds: dict[str, float] = {}
    fixed_traces: dict[str, float] = {}
    for element, ppm in controls_ppm.items():
        if not math.isfinite(ppm) or ppm < 0:
            raise ValueError(f"Invalid concentration for {element}: {ppm}")
        for formula in list(compounds):
            if formula_has(formula, element):
                removed_compounds[formula] = compounds.pop(formula)
        if element in traces:
            removed_traces[element] = traces.pop(element)
        if element in CARRIERS:
            formula = CARRIERS[element]
            amount = float(ppm) / 10000.0 / formula_fraction(formula, element)
            if amount:
                fixed_compounds[formula] = fixed_compounds.get(formula, 0.0) + amount
        elif ppm:
            fixed_traces[element] = float(ppm)

    remaining_mass = sum(compounds.values()) + sum(traces.values()) / 10000.0
    fixed_mass = sum(fixed_compounds.values()) + sum(fixed_traces.values()) / 10000.0
    if remaining_mass <= 0 or fixed_mass >= 100:
        raise ValueError("Infeasible candidate composition")
    scale = (100.0 - fixed_mass) / remaining_mass
    adopted_compounds = {k: v * scale for k, v in compounds.items()}
    for k, v in fixed_compounds.items():
        adopted_compounds[k] = adopted_compounds.get(k, 0.0) + v
    adopted_traces = {k: v * scale for k, v in traces.items()}
    adopted_traces.update(fixed_traces)
    used, conversion = components_to_elements(adopted_compounds, adopted_traces, closure="strict")
    full_used = {e: float(used.get(e, 0.0)) for e in (*TARGET_ELEMENTS, "O")}
    if set(used) - set(full_used):
        raise ValueError(f"Unexpected non-target elements after conversion: {sorted(set(used)-set(full_used))}")
    actual_ppm = {e: full_used[e] * 10000.0 for e in controls_ppm}
    if any(not np.isclose(actual_ppm[e], float(v), rtol=1e-10, atol=1e-7) for e, v in controls_ppm.items()):
        raise ValueError("Controlled elemental concentration changed during conversion")
    baseline = base_composition(base)
    ledger = {
        "kind": "round4_explicit_element_control_and_mass_compensation",
        "controlled_element_ppm": {k: float(v) for k, v in controls_ppm.items()},
        "actual_element_ppm": actual_ppm,
        "removed_compounds_percent": removed_compounds,
        "removed_trace_ppm": removed_traces,
        "added_carrier_compounds_percent": fixed_compounds,
        "added_trace_ppm": fixed_traces,
        "uncontrolled_mixture_scale": scale,
        "compensation": "replace every source compound containing a controlled element; add the declared oxide/trace level; proportionally scale all remaining compounds and traces; record resulting elemental deltas",
        "element_delta_percentage_points": {e: full_used[e] - baseline[e] for e in (*TARGET_ELEMENTS, "O")},
        "conversion": conversion,
    }
    return full_used, ledger


def within_source_ranges(ledger: dict, spec: dict, controlled: set[str]) -> bool:
    compounds = ledger["conversion"]["compounds_percent"]
    traces = ledger["conversion"]["trace_ppm"]
    for formula, bounds in spec["compound_ranges_percent"].items():
        if any(formula_has(formula, e) for e in controlled):
            continue
        value = compounds.get(formula, 0.0)
        if not bounds[0] - 1e-9 <= value <= bounds[1] + 1e-9:
            return False
    balance = spec["balance_compound"]
    balance_value = compounds.get(balance, 0.0)
    if not spec["balance_range_percent"][0] - 1e-9 <= balance_value <= spec["balance_range_percent"][1] + 1e-9:
        return False
    for element, bounds in spec["trace_ranges_ppm"].items():
        if element in controlled:
            continue
        value = traces.get(element, 0.0)
        if value == 0 and float(spec.get("trace_absence_probability", {}).get(element, 0.0)) > 0:
            continue
        if not bounds[0] - 1e-7 <= value <= bounds[1] + 1e-7:
            return False
    return True


def matrix_for(target: str, index: int) -> str:
    if target == "Fe":
        return "silicate_oxide"
    if target == "Si":
        return "iron_oxide"
    return "silicate_oxide" if index % 2 == 0 else "iron_oxide"


def interference_element(target: str, matrix: str, index: int) -> str:
    balance_element = "Si" if matrix == "silicate_oxide" else "Fe"
    options = [e for e in FOCUS if e not in {target, balance_element}]
    if not options:
        raise ValueError(f"No independent focus interferent for {target}/{matrix}")
    return options[index % len(options)]


def allocation() -> list[dict]:
    families: list[dict] = []
    category_specs = [
        ("element_gradient", 80, 10),
        ("zero_spike", 80, 5),
        ("matrix_interference", 80, 5),
    ]
    for category, family_count, variants in category_specs:
        for i in range(family_count):
            target = FOCUS[(i // 16) % len(FOCUS)]
            target_index = i % 16
            matrix = matrix_for(target, target_index)
            interferent = interference_element(target, matrix, target_index) if category == "matrix_interference" else None
            families.append({
                "design_family_id": f"R4_A_{category.upper()}_{i+1:04d}",
                "member": "A", "design_type": category, "target": target, "interferent": interferent,
                "matrix_class": matrix, "variant_count": variants,
                "requested_role": "unassigned_pending_global_freeze",
                "global_role_status": "pending_all_member_candidate_closure",
            })
    for i in range(400):
        matrix = "silicate_oxide" if i % 2 == 0 else "iron_oxide"
        families.append({
            "design_family_id": f"R4_A_ROUTINE_{i+1:04d}", "member": "A",
            "design_type": "routine_coverage", "target": None, "interferent": None,
            "matrix_class": matrix, "variant_count": 1,
            "requested_role": "unassigned_pending_global_freeze",
            "global_role_status": "pending_all_member_candidate_closure",
        })
    return families


def family_controls(family: dict, spec: dict) -> list[tuple[str, dict[str, float]]]:
    target = family["target"]
    if family["design_type"] == "element_gradient":
        return [(f"gradient_{i+1:02d}", {target: v})
                for i, v in enumerate([0.0, *positive_ladder(spec, target)])]
    if family["design_type"] == "zero_spike":
        return [("true_zero", {target: 0.0})] + [
            (f"spike_{i+1:02d}", {target: v}) for i, v in enumerate(spike_levels(spec, target))
        ]
    if family["design_type"] == "matrix_interference":
        other = family["interferent"]
        tmax, imax = element_max_ppm(spec, target), element_max_ppm(spec, other)
        tlow, thigh = min(100.0, tmax * .01), tmax * .6
        ilow, ihigh = imax * .2, imax * .8
        return [
            ("target_zero_interferent_low", {target: 0.0, other: ilow}),
            ("target_low_interferent_low", {target: tlow, other: ilow}),
            ("target_zero_interferent_high", {target: 0.0, other: ihigh}),
            ("target_low_interferent_high", {target: tlow, other: ihigh}),
            ("target_high_interferent_high", {target: thigh, other: ihigh}),
        ]
    return [("routine", {})]


def load_history(history_path: pathlib.Path, round3_root: pathlib.Path) -> tuple[list[dict], list[dict]]:
    history_doc = read_json(history_path)
    rows = []
    for item in history_doc["rows"]:
        rows.append({
            "id": str(item["id"]), "composition_percent": item["composition_percent"],
            "parent_family": item.get("parent_family"), "exposure": item.get("exposure", "prior_round_exposed"),
            "source_round": str(item["id"]).split("/", 1)[0],
            "source_path": history_path.relative_to(ROOT).as_posix(),
        })
    source_entries = [{"path": history_path.relative_to(ROOT).as_posix(), "sha256": sha256(history_path),
                       "bytes": history_path.stat().st_size, "records": len(history_doc["rows"]),
                       "coverage": "Round1/2 history prepared for Round3 A; see embedded source manifest and coverage limit"}]
    for member in "ABCD":
        rel = pathlib.Path("member_A/candidates_v1/A_samples.json") if member == "A" else pathlib.Path(f"member_{member}/candidates/{member}_samples.json")
        path = round3_root / rel
        doc = read_json(path)
        if doc.get("production_started") is not False:
            raise ValueError(f"Round3 source is not a candidate-only record: {path}")
        for item in doc["samples"]:
            rows.append({
                "id": f"round3/{item['id']}", "composition_percent": item["composition_percent"],
                "parent_family": item.get("provenance", {}).get("parent_family"),
                "exposure": "prior_round_candidate_visible_in_shared_repository",
                "source_round": "round3", "source_path": f"datasets/round3/{rel.as_posix()}",
            })
        source_entries.append({
            "path": f"datasets/round3/{rel.as_posix()}", "sha256": sha256(path),
            "bytes": path.stat().st_size, "records": len(doc["samples"]),
            "coverage": f"Round3 member {member} candidate compositions; all were visible in the shared repository",
        })
    return rows, source_entries


def full_composition(comp: dict) -> dict:
    return {e: float(comp.get(e, 0.0)) for e in (*TARGET_ELEMENTS, "O")}


def build(specs: dict, families: list[dict]) -> tuple[list[dict], list[dict]]:
    samples: list[dict] = []
    completed_families: list[dict] = []
    for family in families:
        spec = specs[family["matrix_class"]]["routine"]
        controls = family_controls(family, spec)
        accepted = None
        for attempt in range(500):
            seed = candidate_seed(f"{family['design_family_id']}:background:{attempt}")
            base = design_minerals(spec, 1, seed)["samples"][0]
            rows = []
            for variant_id, control in controls:
                try:
                    if control:
                        used, ledger = apply_controls(base, control)
                        if not within_source_ranges(ledger, spec, set(control)):
                            break
                    else:
                        used = base_composition(base)
                        ledger = {
                            "kind": "unmodified_validated_base_recipe", "controlled_element_ppm": {},
                            "actual_element_ppm": {}, "uncontrolled_mixture_scale": 1.0,
                            "compensation": "none; composition is the direct output of the recorded source range sampler",
                            "element_delta_percentage_points": {e: 0.0 for e in (*TARGET_ELEMENTS, "O")},
                            "conversion": base["provenance"],
                        }
                except (ValueError, ZeroDivisionError):
                    break
                p = base["provenance"]
                sample_id = f"{family['design_family_id']}_{variant_id.upper()}"
                actual_controls = {e: used[e] * 10000.0 for e in control}
                provenance = {
                    "schema": SCHEMA, "candidate_id": sample_id, "member": "A",
                    "design_family_id": family["design_family_id"], "variant_id": variant_id,
                    "design_type": family["design_type"], "matrix_class": family["matrix_class"],
                    "target_element": family["target"], "interferent_element": family["interferent"],
                    "control_role": variant_id, "controlled_element_ppm": actual_controls,
                    "candidate_design_seed": seed, "candidate_background_attempt": attempt,
                    "production_noise_seed": None, "production_condition": None,
                    "original_recipe": {"compounds_percent": p["compounds_percent"], "trace_ppm": p["trace_ppm"]},
                    "original_composition_percent": base_composition(base),
                    "compensation_ledger": ledger,
                    "lineage": "synthetic candidate derived from a sampled oxide/trace background; not a certified sample or measured geological population",
                    "historical_source": "pending nearest-history and cross-member closure",
                    "requested_role": "unassigned_pending_global_freeze",
                    "global_role_status": "pending_all_member_candidate_closure",
                    "eligible_for_training": False,
                }
                rows.append({"id": sample_id, "composition_percent": used, "provenance": provenance})
            if len(rows) == family["variant_count"]:
                accepted = (seed, attempt, base, rows)
                break
        if accepted is None:
            raise ValueError(f"No in-range common background found for {family['design_family_id']}")
        seed, attempt, base, rows = accepted
        samples.extend(rows)
        completed_families.append({
            **family, "candidate_design_seed": seed, "background_attempt": attempt,
            "original_composition_percent": base_composition(base),
            "candidate_ids": [r["id"] for r in rows],
            "requested_role": "unassigned_pending_global_freeze",
            "global_role_status": "pending_all_member_candidate_closure",
        })
    return samples, completed_families


def distance_reports(samples: list[dict], families: list[dict], history: list[dict]) -> tuple[list[dict], list[dict], list[dict], dict]:
    elements = (*TARGET_ELEMENTS, "O")
    hist_matrix = np.asarray([[float(r["composition_percent"].get(e, 0.0)) for e in elements] for r in history], dtype=np.float64)
    sample_matrix = np.asarray([[float(r["composition_percent"].get(e, 0.0)) for e in elements] for r in samples], dtype=np.float64)
    d_hist = cdist(sample_matrix, hist_matrix, metric="cityblock")
    nearest_index = d_hist.argmin(axis=1)
    nearest_rows = []
    for i, (row, j) in enumerate(zip(samples, nearest_index)):
        hist = history[int(j)]
        distance = float(d_hist[i, int(j)])
        nearest_rows.append({
            "candidate_id": row["id"], "design_family_id": row["provenance"]["design_family_id"],
            "nearest_historical_id": hist["id"], "nearest_historical_round": hist["source_round"],
            "nearest_historical_exposure": hist["exposure"], "nearest_historical_L1_percentage_points": distance,
            "history_link_required_at_0_5pp": distance <= THRESHOLD_L1,
            "final_role": "pending_global_freeze",
        })
    background_matrix = np.asarray([[float(f["original_composition_percent"].get(e, 0.0)) for e in elements] for f in families], dtype=np.float64)
    d_background = cdist(background_matrix, hist_matrix, metric="cityblock")
    background_rows = []
    for i, (family, j) in enumerate(zip(families, d_background.argmin(axis=1))):
        hist = history[int(j)]
        distance = float(d_background[i, int(j)])
        background_rows.append({
            "design_family_id": family["design_family_id"], "nearest_historical_id": hist["id"],
            "nearest_historical_round": hist["source_round"], "nearest_historical_exposure": hist["exposure"],
            "nearest_historical_L1_percentage_points": distance,
            "history_link_required_at_0_5pp": distance <= THRESHOLD_L1,
            "final_role": "pending_global_freeze",
        })
    d_self = cdist(sample_matrix, sample_matrix, metric="cityblock")
    family_by_id = {r["id"]: r["provenance"]["design_family_id"] for r in samples}
    i_idx, j_idx = np.where(np.triu(d_self <= THRESHOLD_L1, k=1))
    edges = []
    for i, j in zip(i_idx.tolist(), j_idx.tolist()):
        fa, fb = family_by_id[samples[i]["id"]], family_by_id[samples[j]["id"]]
        if fa != fb:
            edges.append({"candidate_a": samples[i]["id"], "candidate_b": samples[j]["id"],
                          "family_a": fa, "family_b": fb, "L1_percentage_points": float(d_self[i, j]),
                          "status": "pending_global_family_union"})
    mins = {
        "candidate_to_history_min_L1_pp": float(d_hist.min()),
        "background_to_history_min_L1_pp": float(d_background.min()),
        "candidate_history_links_at_0_5pp": sum(r["history_link_required_at_0_5pp"] for r in nearest_rows),
        "background_history_links_at_0_5pp": sum(r["history_link_required_at_0_5pp"] for r in background_rows),
        "cross_family_candidate_edges_at_0_5pp": len(edges),
    }
    return nearest_rows, background_rows, edges, mins


def verify_in_memory(samples: list[dict], families: list[dict], specs: dict) -> list[str]:
    errors: list[str] = []
    if len(samples) != 2000 or len({r["id"] for r in samples}) != 2000:
        errors.append("expected 2000 unique recipes")
    if len(families) != 640 or len({f["design_family_id"] for f in families}) != 640:
        errors.append("expected 640 unique provisional design families")
    category_expected = {"element_gradient": 800, "zero_spike": 400, "matrix_interference": 400, "routine_coverage": 400}
    category_counts = collections.Counter(r["provenance"]["design_type"] for r in samples)
    if dict(category_counts) != category_expected:
        errors.append(f"category counts mismatch: {dict(category_counts)}")
    if len({canonical(r["composition_percent"]) for r in samples}) != len(samples):
        errors.append("duplicate used compositions")
    if set(specs) != set(MATRIX_NAMES):
        errors.append("unexpected matrix design range classes")
    for row in samples:
        comp, p = row["composition_percent"], row["provenance"]
        if set(comp) != set((*TARGET_ELEMENTS, "O")):
            errors.append(f"{row['id']}: composition vector is not 32 targets plus O")
            break
        if not math.isclose(sum(comp.values()), 100.0, rel_tol=0, abs_tol=2e-9) or comp["O"] <= 0:
            errors.append(f"{row['id']}: composition closure/O failed")
            break
        if p["production_noise_seed"] is not None or p["production_condition"] is not None:
            errors.append(f"{row['id']}: production metadata was prematurely assigned")
            break
        if p["requested_role"] != "unassigned_pending_global_freeze" or p["eligible_for_training"]:
            errors.append(f"{row['id']}: role/training state was prematurely assigned")
            break
        if set(p["controlled_element_ppm"]) != set(p["compensation_ledger"]["controlled_element_ppm"]):
            errors.append(f"{row['id']}: control ledger mismatch")
            break
    for family in families:
        rows = [r for r in samples if r["provenance"]["design_family_id"] == family["design_family_id"]]
        if len(rows) != family["variant_count"]:
            errors.append(f"{family['design_family_id']}: incomplete family")
            continue
        if len({canonical(r["provenance"]["original_composition_percent"]) for r in rows}) != 1:
            errors.append(f"{family['design_family_id']}: variants do not share a parent background")
        target = family["target"]
        values = [r["composition_percent"].get(target, 0.0) * 10000 for r in rows] if target else []
        if family["design_type"] == "element_gradient" and (values[0] != 0 or not all(a < b for a, b in zip(values, values[1:]))):
            errors.append(f"{family['design_family_id']}: gradient is not zero plus nine increasing levels")
        if family["design_type"] == "zero_spike" and (values[0] != 0 or not all(v > 0 for v in values[1:]) or not all(a < b for a, b in zip(values[1:], values[2:]))):
            errors.append(f"{family['design_family_id']}: zero/spike levels invalid")
        if family["design_type"] == "matrix_interference":
            other = family["interferent"]
            iv = [r["composition_percent"].get(other, 0.0) * 10000 for r in rows]
            if not (values[0] == values[2] == 0 and values[1] > 0 and values[4] > values[1]
                    and np.isclose(iv[0], iv[1]) and np.isclose(iv[2], iv[3]) and np.isclose(iv[3], iv[4]) and iv[2] > iv[0]):
                errors.append(f"{family['design_family_id']}: matrix-interaction controls invalid")
    return errors


def write_json(path: pathlib.Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path: pathlib.Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / "datasets/round4/member_A/candidates_v1")
    parser.add_argument("--round3-root", type=pathlib.Path, default=ROOT / "datasets/round3")
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite candidate output: {out}")
    ranges_path = INPUTS / "design_ranges.json"
    history_path = INPUTS / "historical_compositions.json"
    specs = read_json(ranges_path)
    families = allocation()
    samples, completed_families = build(specs, families)
    errors = verify_in_memory(samples, completed_families, specs)
    if errors:
        raise ValueError("Candidate construction checks failed: " + "; ".join(errors[:20]))
    history, history_sources = load_history(history_path, args.round3_root.resolve())
    nearest, backgrounds, edges, distance_summary = distance_reports(samples, completed_families, history)
    # A ≤0.5 pp historical neighbor is a required global lineage link and may constrain the future role.
    nearest_by_id = {r["candidate_id"]: r for r in nearest}
    history_by_id = {r["id"]: r for r in history}
    for row in samples:
        match = nearest_by_id[row["id"]]
        row["provenance"]["nearest_historical_source"] = match["nearest_historical_id"]
        row["provenance"]["nearest_historical_L1_percentage_points"] = match["nearest_historical_L1_percentage_points"]
        row["provenance"]["historical_train_only_constraint_pending"] = match["history_link_required_at_0_5pp"]
        row["provenance"]["historical_exposure"] = history_by_id[match["nearest_historical_id"]]["exposure"]
    for family in completed_families:
        group_rows = [r for r in nearest if r["design_family_id"] == family["design_family_id"]]
        family["nearest_historical_source"] = min(group_rows, key=lambda r: r["nearest_historical_L1_percentage_points"])["nearest_historical_id"]
        family["minimum_candidate_history_L1_percentage_points"] = min(r["nearest_historical_L1_percentage_points"] for r in group_rows)
        bg_row = next(r for r in backgrounds if r["design_family_id"] == family["design_family_id"])
        family["nearest_original_background_history_source"] = bg_row["nearest_historical_id"]
        family["minimum_original_background_history_L1_percentage_points"] = bg_row["nearest_historical_L1_percentage_points"]
        family["historical_train_only_constraint_pending"] = (
            family["minimum_candidate_history_L1_percentage_points"] <= THRESHOLD_L1
            or family["minimum_original_background_history_L1_percentage_points"] <= THRESHOLD_L1
        )

    matrix_counts = collections.Counter(r["provenance"]["matrix_class"] for r in samples)
    category_counts = collections.Counter(r["provenance"]["design_type"] for r in samples)
    source_manifest = {
        "schema": "round4-A-candidate-source-manifest/1",
        "status": "candidate_inputs_only_not_production_freeze",
        "inputs": [
            {"path": ranges_path.relative_to(ROOT).as_posix(), "sha256": sha256(ranges_path),
             "bytes": ranges_path.stat().st_size, "role": "Round3 A validated starting ranges; Round4 range proposal only"},
            {"path": history_path.relative_to(ROOT).as_posix(), "sha256": sha256(history_path),
             "bytes": history_path.stat().st_size, "role": "Round1/2 historical composition table with its embedded source list"},
            *history_sources,
            *[{"path": (GENERATOR / f"fp_competition/{name}").relative_to(ROOT).as_posix(),
               "sha256": sha256(GENERATOR / f"fp_competition/{name}"),
               "bytes": (GENERATOR / f"fp_competition/{name}").stat().st_size,
               "role": "Round3 frozen composition conversion/range sampler source"}
              for name in ("core.py", "minerals.py", "version.py")],
        ],
        "coverage_limit": "Known Round1/2 history from the Round3 A input table plus all four Round3 shared candidate registries. Does not prove absence of undocumented material ancestry.",
    }
    input_identity = {
        "schema": "round4-A-candidate-input-identity/1",
        "builder_sha256": sha256(pathlib.Path(__file__).resolve()),
        "source_manifest_sha256": hashlib.sha256(json.dumps(source_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "generator_version": GENERATOR_VERSION,
        "candidate_rng": "sha256-derived NumPy default_rng seed; candidate-design-only, not production or spectrum noise",
        "noise_seeds_allocated": False,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "xraylib": getattr(xl, "__version__", "version_not_exposed")},
    }
    for sample in samples:
        sample["provenance"]["input_source_manifest_sha256"] = input_identity["source_manifest_sha256"]
    for family in completed_families:
        family["input_source_manifest_sha256"] = input_identity["source_manifest_sha256"]
    checks = {
        "schema": "round4-A-candidate-checks/1", "status": "passed_A_local_candidate_checks",
        "errors": [], "candidate_count": len(samples), "design_family_count_before_global_merge": len(completed_families),
        "category_counts": dict(sorted(category_counts.items())), "matrix_counts": dict(sorted(matrix_counts.items())),
        "recipes_by_focus_element": {e: sum(f["target"] == e for f in completed_families) for e in FOCUS},
        "variants": {"element_gradient": "one true zero plus nine strictly increasing positive levels",
                     "zero_spike": "one true zero plus four distinct positive levels",
                     "matrix_interference": "five paired target/interferent controls", "routine_coverage": "one composition per family"},
        "historical_rows_compared": len(history), "historical_source_count": len(history_sources),
        "historical_nearest_threshold_L1_percentage_points": THRESHOLD_L1,
        "distance_summary": distance_summary, "cross_member_confirmation": "pending_B_C_D",
        "global_family_closure": "pending_all_round4_candidates_and_round1_2_3_history",
        "role_and_stage_assignments": "pending_global_freeze", "production_started": False,
        "spectra_generated": 0, "noise_seeds_allocated": False, "eligible_for_training": False,
        "scientific_accuracy_validated": False,
        "range_status": "draft_using_round3_validated_ranges; requires Round4 public scope review and global freeze",
    }
    if not args.round3_root.resolve().is_relative_to(ROOT):
        # Snapshot paths are allowed for local source verification, but only their logical repo paths are recorded.
        checks["round3_candidate_source_mode"] = "verified_local_snapshot"
    else:
        checks["round3_candidate_source_mode"] = "repository_tree"

    out.mkdir(parents=True)
    write_json(out / "A_samples.json", {"schema": SCHEMA, "round_id": "round4", "member": "A",
                                       "status": "candidate_pending_cross_member_global_freeze",
                                       "production_started": False, "eligible_for_training": False,
                                       "samples": samples})
    write_json(out / "family_registry.json", {"schema": "round4-A-family-candidates/1",
                                               "status": "provisional_before_global_family_closure",
                                               "families": completed_families})
    write_json(out / "source_manifest.json", source_manifest)
    write_json(out / "input_identity.json", input_identity)
    write_json(out / "candidate_checks.json", checks)
    write_csv(out / "candidate_registry.csv", [
        "candidate_id", "member", "design_family_id", "parent_family_id", "design_type", "variant_id",
        "matrix_class", "composition_used_json", "original_composition_json", "compensation_ledger_json",
        "historical_source_id", "historical_exposure", "requested_role", "global_role_status",
    ], [{
        "candidate_id": r["id"], "member": "A", "design_family_id": r["provenance"]["design_family_id"],
        "parent_family_id": r["provenance"]["design_family_id"], "design_type": r["provenance"]["design_type"],
        "variant_id": r["provenance"]["variant_id"], "matrix_class": r["provenance"]["matrix_class"],
        "composition_used_json": json.dumps(r["composition_percent"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "original_composition_json": json.dumps(r["provenance"]["original_composition_percent"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "compensation_ledger_json": json.dumps(r["provenance"]["compensation_ledger"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "historical_source_id": r["provenance"]["nearest_historical_source"],
        "historical_exposure": r["provenance"]["historical_exposure"],
        "requested_role": "unassigned_pending_global_freeze",
        "global_role_status": "pending_all_member_candidate_closure",
    } for r in samples])
    write_csv(out / "nearest_history.csv", list(nearest[0]), nearest)
    write_csv(out / "original_background_nearest_history.csv", list(backgrounds[0]), backgrounds)
    write_csv(out / "cross_family_near_edges.csv", ["candidate_a", "candidate_b", "family_a", "family_b", "L1_percentage_points", "status"], edges)
    checks["output_record_files"] = ["A_samples.json", "family_registry.json", "candidate_registry.csv",
                                     "nearest_history.csv", "original_background_nearest_history.csv", "cross_family_near_edges.csv"]
    write_json(out / "candidate_checks.json", checks)
    manifest_rows = []
    for path in sorted(p for p in out.iterdir() if p.is_file() and p.name != "delivery_manifest.json"):
        manifest_rows.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json(out / "delivery_manifest.json", {
        "schema": "round4-A-candidate-delivery/1", "status": "candidate_only_not_production_release",
        "member": "A", "round_id": "round4", "candidate_count": len(samples),
        "design_family_count_before_global_merge": len(completed_families),
        "production_started": False, "eligible_for_training": False, "files": manifest_rows,
    })
    print(json.dumps({"out": str(out), "candidate_count": len(samples), "families": len(completed_families),
                      "category_counts": dict(category_counts), "matrix_counts": dict(matrix_counts),
                      "distance_summary": distance_summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
