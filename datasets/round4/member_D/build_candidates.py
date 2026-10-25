"""Build D's round-four composition candidates only; never generate spectra.

D's theme is measurement-condition and sample-state variation: gain/zero,
resolution, low-energy response, background/counting level and matrix state.
At the candidate stage only compositions are fixed; actual gain/zero,
resolution, background and counting-condition instances stay pending the
public round-four profile freeze.  The builder intentionally keeps every
candidate in the candidate stage: no production conditions, noise seeds,
train/validation/sealed approval or round-four runner command is assigned.

The construction logic follows the already-reviewed Round3 composition
conversion and the Round4 A/C candidate patterns so that D's recipes can be
compared directly during A's global family closure.
"""
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

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUTS = ROOT / "datasets/round3/member_A/inputs"
GENERATOR = INPUTS / "generator"
sys.path.insert(0, str(GENERATOR))
from fp_competition.core import TARGET_ELEMENTS  # noqa: E402
from fp_competition.minerals import components_to_elements, design_minerals  # noqa: E402
from fp_competition.version import VERSION as GENERATOR_VERSION  # noqa: E402

SCHEMA = "round4-D-candidate-compositions/1"
THRESHOLD_L1 = 0.5
LINE_WINDOW_EV = 150.0
FOCUS = ("Na", "Mg", "Al", "Si", "P", "S", "Cl", "K")
CARRIERS = {
    "Na": "Na2O", "Mg": "MgO", "Al": "Al2O3", "Si": "SiO2", "Fe": "Fe2O3T",
    "P": "P2O5", "K": "K2O", "Ca": "CaO", "Ti": "TiO2", "Mn": "MnO",
}
REGISTRY_FIELDS = [
    "candidate_id", "member", "design_family_id", "parent_family_id",
    "design_type", "variant_id", "matrix_class", "composition_used_json",
    "original_composition_json", "compensation_ledger_json",
    "historical_source_id", "historical_exposure", "requested_role",
    "global_role_status",
]

# All 32 targets once, then eight D-theme repeats.  The repeats cover the
# low-energy analytical lines most sensitive to gain/zero, resolution and
# low-energy response; the gradient is the only category that deliberately
# spans trace to major concentrations.
LADDER_TARGETS = list(TARGET_ELEMENTS) + list(FOCUS)

# All 32 targets once, then the same eight low-energy repeats near zero and
# detection thresholds, where background and counting level dominate.
ZERO_TARGETS = list(TARGET_ELEMENTS) + list(FOCUS)

# Every pair is checked against the xraylib line table below.  The target is
# the low-level analyte whose analytical line is screened against the named
# interferent; all are inside the 150 eV candidate window.
INTERFERENCE_PAIRS = [
    ("Na", "Cu"), ("Mg", "Se"), ("Al", "Se"), ("Si", "Rb"),
    ("P", "Zr"), ("S", "Mo"), ("Cl", "Mo"), ("K", "Sn"),
    ("Ca", "Sn"), ("Ti", "V"), ("V", "Cr"), ("Cr", "Mn"),
    ("Mn", "Fe"), ("Fe", "Co"), ("Co", "Ni"), ("Ni", "Cu"),
    ("Cu", "Zn"), ("Zn", "Na"), ("As", "Pb"), ("Se", "Pb"),
    ("Rb", "Y"), ("Sr", "Zr"), ("Y", "W"), ("Zr", "Nb"),
    ("Nb", "Mo"), ("Mo", "Pb"), ("Cd", "Sn"), ("Sn", "Sb"),
    ("Sb", "Ca"), ("Ba", "V"), ("W", "Sr"), ("Pb", "Nb"),
    ("Mg", "As"), ("Al", "Rb"), ("Si", "W"), ("Fe", "Cr"),
    ("Ca", "Sb"), ("Cd", "Sb"), ("As", "Se"), ("Pb", "S"),
]

LINE_DEFS = {
    "KA1": xl.KA1_LINE, "KA2": xl.KA2_LINE, "KB1": xl.KB1_LINE,
    "LA1": xl.LA1_LINE, "LA2": xl.LA2_LINE, "LB1": xl.LB1_LINE,
    "LB2": xl.LB2_LINE, "MA1": xl.MA1_LINE, "MB": xl.MB_LINE,
}


def read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: pathlib.Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: dict) -> str:
    return json.dumps(
        {k: round(float(v), 12) for k, v in sorted(value.items()) if round(float(v), 12) != 0},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )


def candidate_seed(key: str) -> int:
    """Deterministic composition-design seed; never a production/noise seed."""
    raw = hashlib.sha256(("round4-D-candidate-only-v1:" + key).encode("utf-8")).digest()
    return int.from_bytes(raw[:4], "big")


def formula_fraction(formula: str, element: str) -> float:
    parsed = xl.CompoundParser("Fe2O3" if formula == "Fe2O3T" else formula)
    return sum(
        float(w) for z, w in zip(parsed["Elements"], parsed["massFractions"])
        if xl.AtomicNumberToSymbol(z) == element
    )


def formula_has(formula: str, element: str) -> bool:
    parsed = xl.CompoundParser("Fe2O3" if formula == "Fe2O3T" else formula)
    return any(xl.AtomicNumberToSymbol(z) == element for z in parsed["Elements"])


def element_max_ppm(spec: dict, element: str) -> float:
    """Upper feasible concentration from the source range file, not a detection limit."""
    carrier = CARRIERS.get(element)
    if carrier is not None:
        if carrier in spec["compound_ranges_percent"]:
            oxide_max = spec["compound_ranges_percent"][carrier][1]
        elif carrier == spec["balance_compound"]:
            oxide_max = spec["balance_range_percent"][1]
        else:
            oxide_max = None
        if oxide_max is not None:
            return float(oxide_max) * formula_fraction(carrier, element) * 10000.0
    if element in spec["trace_ranges_ppm"]:
        return float(spec["trace_ranges_ppm"][element][1])
    totals = []
    for formula, bounds in spec["compound_ranges_percent"].items():
        fraction = formula_fraction(formula, element)
        if fraction > 0:
            totals.append(float(bounds[1]) * fraction * 10000.0)
    fraction = formula_fraction(spec["balance_compound"], element)
    if fraction > 0:
        totals.append(float(spec["balance_range_percent"][1]) * fraction * 10000.0)
    if totals:
        return max(totals)
    raise ValueError(f"No supported source range for {element}")


def unique_levels(values, count: int, maximum: float) -> list[float]:
    vals = sorted({
        round(float(v), 10) for v in values
        if math.isfinite(float(v)) and 0 < float(v) <= maximum
    })
    if len(vals) < count:
        lo = max(0.01, maximum * 1e-5)
        vals = sorted({
            round(float(v), 10) for v in np.geomspace(lo, maximum, max(count * 4, 20))
            if 0 < float(v) <= maximum
        })
    if len(vals) < count:
        raise ValueError(f"Cannot form {count} distinct levels below {maximum}")
    indices = np.linspace(0, len(vals) - 1, count).round().astype(int)
    picked = [vals[int(i)] for i in indices]
    if len(set(picked)) != count:
        raise ValueError(f"Duplicate levels selected below {maximum}")
    return picked


def positive_ladder(spec: dict, element: str) -> list[float]:
    maximum = element_max_ppm(spec, element)
    lo = max(0.01, maximum * 1e-5)
    if lo >= maximum:
        lo = maximum * 0.01
    return unique_levels(np.geomspace(lo, maximum, 24), 9, maximum)


def spike_levels(spec: dict, element: str) -> list[float]:
    maximum = element_max_ppm(spec, element)
    lo = max(0.01, maximum * 1e-3)
    hi = max(lo * 1.5, maximum * 0.3)
    if hi >= maximum:
        hi = maximum * 0.9
    if hi <= lo:
        values = np.linspace(maximum * 0.05, maximum * 0.9, 4)
    else:
        values = np.geomspace(lo, hi, 4)
    return unique_levels(values, 4, maximum)


def interference_levels(spec: dict, target: str, interferent: str) -> dict:
    tmax = element_max_ppm(spec, target)
    imax = element_max_ppm(spec, interferent)
    t_low = min(max(0.05, tmax * 0.001), tmax * 0.1)
    t_high = max(tmax * 0.3, t_low * 3.0)
    t_high = min(t_high, tmax * 0.8)
    i_low = min(max(0.05, imax * 0.1), imax * 0.2)
    i_high = max(imax * 0.35, i_low * 2.0)
    i_high = min(i_high, imax * 0.8)
    if not (0 < t_low < t_high <= tmax):
        raise ValueError(f"Invalid target levels for {target}/{interferent}")
    if not (0 < i_low < i_high <= imax):
        raise ValueError(f"Invalid interferent levels for {target}/{interferent}")
    return {"target_low_ppm": t_low, "target_high_ppm": t_high,
            "interferent_low_ppm": i_low, "interferent_high_ppm": i_high}


def element_lines(element: str) -> list[tuple[str, float, float]]:
    z = xl.SymbolToAtomicNumber(element)
    rows = []
    for name, line in LINE_DEFS.items():
        try:
            energy = float(xl.LineEnergy(z, line)) * 1000.0
            rate = float(xl.RadRate(z, line))
        except Exception:
            continue
        if 500.0 <= energy <= 25000.0 and rate >= 0.003:
            rows.append((name, energy, rate))
    return rows


def line_evidence(target: str, interferent: str) -> dict:
    """Closest strong line pair inside the candidate screening window."""
    candidates = []
    for tname, tenergy, trate in element_lines(target):
        for iname, ienergy, irate in element_lines(interferent):
            delta = abs(tenergy - ienergy)
            if delta <= LINE_WINDOW_EV:
                candidates.append((min(trate, irate), -delta, tname, tenergy, trate,
                                   iname, ienergy, irate))
    if not candidates:
        raise ValueError(f"No line pair within {LINE_WINDOW_EV} eV for {target}/{interferent}")
    strength, neg_delta, tname, tenergy, trate, iname, ienergy, irate = max(candidates)
    return {
        "schema": "round4-D-line-interference-evidence/1",
        "target_element": target,
        "interferent_element": interferent,
        "window_eV": LINE_WINDOW_EV,
        "target_line": tname,
        "target_line_energy_eV": round(tenergy, 3),
        "target_rad_rate": round(trate, 6),
        "interferent_line": iname,
        "interferent_line_energy_eV": round(ienergy, 3),
        "interferent_rad_rate": round(irate, 6),
        "delta_eV": round(-neg_delta, 3),
        "mechanism": "overlapping_analytical_line_within_candidate_energy_window",
        "status": "candidate_screen_using_xraylib_line_table; detector profile and public round4 window not frozen",
        "strength": round(strength, 6),
    }


def nominal_role(index: int) -> str:
    position = index % 10
    if position < 8:
        return "train_nominal"
    if position == 8:
        return "validation_nominal"
    return "sealed_test_nominal"


def allowed_matrices(family: dict) -> list[str]:
    controlled = {family["target"]}
    if family.get("interferent"):
        controlled.add(family["interferent"])
    out = []
    for matrix, balance in (("silicate_oxide", "Si"), ("iron_oxide", "Fe")):
        if balance not in controlled:
            out.append(matrix)
    if not out:
        raise ValueError(f"No matrix leaves the balance element uncontrolled: {family}")
    return out


def assign_matrices(families: list[dict]) -> None:
    total = sum(int(f["variant_count"]) for f in families)
    target_silicate = total // 2
    silicate = 0
    for index, family in enumerate(families):
        options = allowed_matrices(family)
        if len(options) == 1:
            chosen = options[0]
        else:
            ranked = []
            for matrix in options:
                new_silicate = silicate + (int(family["variant_count"])
                                           if matrix == "silicate_oxide" else 0)
                preference = 0 if (index % 2 == 0) == (matrix == "silicate_oxide") else 1
                ranked.append((abs(new_silicate - target_silicate), preference, matrix))
            chosen = min(ranked)[2]
        family["matrix_class"] = chosen
        if chosen == "silicate_oxide":
            silicate += int(family["variant_count"])
    guard = 0
    while silicate != target_silicate and guard < 10000:
        guard += 1
        difference = silicate - target_silicate
        flipped = False
        for family in families:
            if len(allowed_matrices(family)) < 2:
                continue
            amount = int(family["variant_count"])
            if family["matrix_class"] == "silicate_oxide":
                new_silicate = silicate - amount
            else:
                new_silicate = silicate + amount
            if abs(new_silicate - target_silicate) < abs(difference):
                family["matrix_class"] = (
                    "iron_oxide" if family["matrix_class"] == "silicate_oxide" else "silicate_oxide"
                )
                silicate = new_silicate
                flipped = True
                break
        if not flipped:
            break
    if silicate != target_silicate:
        raise ValueError(f"Could not balance matrix recipes: {silicate} vs {target_silicate}")


def allocation() -> list[dict]:
    families: list[dict] = []
    for index, target in enumerate(LADDER_TARGETS):
        families.append({
            "design_family_id": f"R4_D_ELEMENT_GRADIENT_{index + 1:04d}",
            "member": "D", "design_type": "element_gradient",
            "target": target, "interferent": None, "variant_count": 10,
            "requested_role": nominal_role(index),
            "global_role_status": "pending_global_freeze",
        })
    for index, target in enumerate(ZERO_TARGETS):
        families.append({
            "design_family_id": f"R4_D_ZERO_SPIKE_{index + 1:04d}",
            "member": "D", "design_type": "zero_spike",
            "target": target, "interferent": None, "variant_count": 5,
            "requested_role": nominal_role(index),
            "global_role_status": "pending_global_freeze",
        })
    for index, (target, interferent) in enumerate(INTERFERENCE_PAIRS):
        families.append({
            "design_family_id": f"R4_D_MATRIX_INTERFERENCE_{index + 1:04d}",
            "member": "D", "design_type": "matrix_interference",
            "target": target, "interferent": interferent, "variant_count": 5,
            "line_interference_evidence": line_evidence(target, interferent),
            "requested_role": nominal_role(index),
            "global_role_status": "pending_global_freeze",
        })
    for index in range(200):
        families.append({
            "design_family_id": f"R4_D_ROUTINE_{index + 1:04d}",
            "member": "D", "design_type": "routine_coverage",
            "target": None, "interferent": None, "variant_count": 1,
            "requested_role": nominal_role(index),
            "global_role_status": "pending_global_freeze",
        })
    assign_matrices(families)
    return families


def base_composition(sample: dict) -> dict:
    return {e: float(sample["composition_percent"].get(e, 0.0)) for e in (*TARGET_ELEMENTS, "O")}


def apply_controls(base: dict, controls_ppm: dict[str, float]) -> tuple[dict, dict]:
    """Replace controlled elements with explicit carriers/traces, then scale the rest."""
    source = base["provenance"]
    compounds = {k: float(v) for k, v in source["compounds_percent"].items()}
    traces = {k: float(v) for k, v in source["trace_ppm"].items()}
    removed_compounds: dict[str, float] = {}
    removed_traces: dict[str, float] = {}
    fixed_compounds: dict[str, float] = {}
    fixed_traces: dict[str, float] = {}
    for element, ppm in controls_ppm.items():
        value = float(ppm)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid concentration for {element}: {ppm}")
        for formula in list(compounds):
            if formula_has(formula, element):
                removed_compounds[formula] = compounds.pop(formula)
        if element in traces:
            removed_traces[element] = traces.pop(element)
        if element in CARRIERS:
            formula = CARRIERS[element]
            amount = value / 10000.0 / formula_fraction(formula, element)
            if amount:
                fixed_compounds[formula] = fixed_compounds.get(formula, 0.0) + amount
        elif value:
            fixed_traces[element] = value

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
        raise ValueError(f"Unexpected non-target elements after conversion: {sorted(set(used) - set(full_used))}")
    actual_ppm = {e: full_used[e] * 10000.0 for e in controls_ppm}
    if any(not np.isclose(actual_ppm[e], float(v), rtol=1e-10, atol=1e-9)
           for e, v in controls_ppm.items()):
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
        "compensation": (
            "replace every source compound containing a controlled element; add the declared "
            "oxide/trace level; proportionally scale all remaining compounds and traces; record "
            "resulting elemental deltas"
        ),
        "controlled_range_override": True,
        "range_caveat": (
            "The original source ranges describe the sampled background.  Controlled zero/low/high "
            "levels may intentionally lie outside those ranges to cover detection-threshold and "
            "spike behaviour; every non-controlled compound and trace must remain inside its range."
        ),
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


def family_controls(family: dict, spec: dict) -> list[tuple[str, dict[str, float]]]:
    target = family["target"]
    if family["design_type"] == "element_gradient":
        return [(f"gradient_{i + 1:02d}", {target: v})
                for i, v in enumerate([0.0, *positive_ladder(spec, target)])]
    if family["design_type"] == "zero_spike":
        return [("true_zero", {target: 0.0})] + [
            (f"spike_{i + 1:02d}", {target: v})
            for i, v in enumerate(spike_levels(spec, target))
        ]
    if family["design_type"] == "matrix_interference":
        other = family["interferent"]
        levels = interference_levels(spec, target, other)
        tl, th = levels["target_low_ppm"], levels["target_high_ppm"]
        il, ih = levels["interferent_low_ppm"], levels["interferent_high_ppm"]
        return [
            ("target_zero_interferent_low", {target: 0.0, other: il}),
            ("target_low_interferent_low", {target: tl, other: il}),
            ("target_zero_interferent_high", {target: 0.0, other: ih}),
            ("target_low_interferent_high", {target: tl, other: ih}),
            ("target_high_interferent_high", {target: th, other: ih}),
        ]
    return [("routine", {})]


def positive_sources(row: dict) -> dict[str, list[str]]:
    conversion = row["provenance"]["compensation_ledger"]["conversion"]
    carried: dict[str, list[str]] = collections.defaultdict(list)
    for formula, amount in conversion["compounds_percent"].items():
        if amount <= 0:
            continue
        parsed = xl.CompoundParser("Fe2O3" if formula == "Fe2O3T" else formula)
        for z in parsed["Elements"]:
            symbol = xl.AtomicNumberToSymbol(z)
            if symbol in TARGET_ELEMENTS or symbol == "O":
                carried[symbol].append(formula)
    for symbol, amount in conversion["trace_ppm"].items():
        if amount > 0:
            carried[symbol].append("trace_ppm")
    return carried


def exact_zero_conflicts(rows: list[dict]) -> tuple[list[tuple], int]:
    conflicts = []
    verified = 0
    for row in rows:
        carried = positive_sources(row)
        for symbol, value in row["composition_percent"].items():
            if value == 0:
                verified += 1
                if carried.get(symbol):
                    conflicts.append((row["id"], symbol, carried[symbol]))
    return conflicts, verified


def build(specs: dict, families: list[dict]) -> tuple[list[dict], list[dict]]:
    samples: list[dict] = []
    completed: list[dict] = []
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
                            "kind": "unmodified_validated_base_recipe",
                            "controlled_element_ppm": {},
                            "actual_element_ppm": {},
                            "uncontrolled_mixture_scale": 1.0,
                            "compensation": "none; composition is the direct output of the recorded source range sampler",
                            "controlled_range_override": False,
                            "element_delta_percentage_points": {e: 0.0 for e in (*TARGET_ELEMENTS, "O")},
                            "conversion": base["provenance"],
                        }
                except (ValueError, ZeroDivisionError):
                    break
                provenance_base = base["provenance"]
                sample_id = f"{family['design_family_id']}_{variant_id.upper()}"
                actual_controls = {e: used[e] * 10000.0 for e in control}
                provenance = {
                    "schema": SCHEMA,
                    "candidate_id": sample_id,
                    "member": "D",
                    "design_family_id": family["design_family_id"],
                    "variant_id": variant_id,
                    "design_type": family["design_type"],
                    "matrix_class": family["matrix_class"],
                    "target_element": family["target"],
                    "interferent_element": family["interferent"],
                    "control_role": variant_id,
                    "controlled_element_ppm": actual_controls,
                    "candidate_design_seed": seed,
                    "candidate_background_attempt": attempt,
                    "production_noise_seed": None,
                    "production_condition": None,
                    "original_recipe": {
                        "compounds_percent": provenance_base["compounds_percent"],
                        "trace_ppm": provenance_base["trace_ppm"],
                    },
                    "original_composition_percent": base_composition(base),
                    "compensation_ledger": ledger,
                    "line_interference_evidence": family.get("line_interference_evidence"),
                    "lineage": (
                        "synthetic candidate derived from a sampled oxide/trace background; "
                        "not a certified sample or measured geological population"
                    ),
                    "historical_source": "pending nearest-history and cross-member closure",
                    "historical_exposure": "pending",
                    "nearest_historical_L1_percentage_points": None,
                    "historical_train_only_constraint_pending": None,
                    "requested_role": family["requested_role"],
                    "global_role_status": "pending_global_freeze",
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
        completed.append({
            **family,
            "candidate_design_seed": seed,
            "background_attempt": attempt,
            "original_composition_percent": base_composition(base),
            "candidate_ids": [r["id"] for r in rows],
            "requested_role": family["requested_role"],
            "global_role_status": "pending_global_freeze",
        })
    return samples, completed


def load_history(history_path: pathlib.Path, round3_root: pathlib.Path) -> tuple[list[dict], list[dict]]:
    history_doc = read_json(history_path)
    rows = []
    for item in history_doc["rows"]:
        rows.append({
            "id": str(item["id"]),
            "composition_percent": item["composition_percent"],
            "parent_family": item.get("parent_family"),
            "exposure": item.get("exposure", "prior_round_exposed"),
            "source_round": str(item["id"]).split("/", 1)[0],
            "source_path": history_path.relative_to(ROOT).as_posix(),
        })
    sources = [{
        "path": history_path.relative_to(ROOT).as_posix(),
        "sha256": sha256(history_path),
        "bytes": history_path.stat().st_size,
        "records": len(history_doc["rows"]),
        "coverage": "Round1/2 history prepared for Round3 A; see embedded source manifest and coverage limit",
    }]
    for member in "ABCD":
        relative = (
            pathlib.Path("member_A/candidates_v1/A_samples.json") if member == "A"
            else pathlib.Path(f"member_{member}/candidates/{member}_samples.json")
        )
        path = round3_root / relative
        doc = read_json(path)
        if doc.get("production_started") is not False:
            raise ValueError(f"Round3 source is not a candidate-only record: {path}")
        for item in doc["samples"]:
            rows.append({
                "id": f"round3/{item['id']}",
                "composition_percent": item["composition_percent"],
                "parent_family": item.get("provenance", {}).get("parent_family"),
                "exposure": "prior_round_candidate_visible_in_shared_repository",
                "source_round": "round3",
                "source_path": f"datasets/round3/{relative.as_posix()}",
            })
        sources.append({
            "path": f"datasets/round3/{relative.as_posix()}",
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "records": len(doc["samples"]),
            "coverage": f"Round3 member {member} candidate compositions; all were visible in the shared repository",
        })
    return rows, sources


def distance_reports(samples: list[dict], families: list[dict], history: list[dict]) -> tuple[list[dict], list[dict], list[dict], dict]:
    elements = (*TARGET_ELEMENTS, "O")
    history_matrix = np.asarray(
        [[float(r["composition_percent"].get(e, 0.0)) for e in elements] for r in history],
        dtype=np.float64,
    )
    sample_matrix = np.asarray(
        [[float(r["composition_percent"].get(e, 0.0)) for e in elements] for r in samples],
        dtype=np.float64,
    )
    distances = cdist(sample_matrix, history_matrix, metric="cityblock")
    nearest_index = distances.argmin(axis=1)
    nearest_rows = []
    for i, (row, j) in enumerate(zip(samples, nearest_index)):
        hist = history[int(j)]
        distance = float(distances[i, int(j)])
        nearest_rows.append({
            "candidate_id": row["id"],
            "design_family_id": row["provenance"]["design_family_id"],
            "nearest_historical_id": hist["id"],
            "nearest_historical_round": hist["source_round"],
            "nearest_historical_exposure": hist["exposure"],
            "nearest_historical_L1_percentage_points": distance,
            "history_link_required_at_0_5pp": distance <= THRESHOLD_L1,
            "final_role": "pending_global_freeze",
        })
    background_matrix = np.asarray(
        [[float(f["original_composition_percent"].get(e, 0.0)) for e in elements] for f in families],
        dtype=np.float64,
    )
    background_distances = cdist(background_matrix, history_matrix, metric="cityblock")
    background_rows = []
    for i, (family, j) in enumerate(zip(families, background_distances.argmin(axis=1))):
        hist = history[int(j)]
        distance = float(background_distances[i, int(j)])
        background_rows.append({
            "design_family_id": family["design_family_id"],
            "nearest_historical_id": hist["id"],
            "nearest_historical_round": hist["source_round"],
            "nearest_historical_exposure": hist["exposure"],
            "nearest_historical_L1_percentage_points": distance,
            "history_link_required_at_0_5pp": distance <= THRESHOLD_L1,
            "final_role": "pending_global_freeze",
        })
    self_distances = cdist(sample_matrix, sample_matrix, metric="cityblock")
    family_by_id = {r["id"]: r["provenance"]["design_family_id"] for r in samples}
    i_idx, j_idx = np.where(np.triu(self_distances <= THRESHOLD_L1, k=1))
    edges = []
    for i, j in zip(i_idx.tolist(), j_idx.tolist()):
        family_a = family_by_id[samples[i]["id"]]
        family_b = family_by_id[samples[j]["id"]]
        if family_a != family_b:
            edges.append({
                "candidate_a": samples[i]["id"],
                "candidate_b": samples[j]["id"],
                "family_a": family_a,
                "family_b": family_b,
                "L1_percentage_points": float(self_distances[i, j]),
                "status": "pending_global_family_union",
            })
    summary = {
        "candidate_to_history_min_L1_pp": float(distances.min()),
        "background_to_history_min_L1_pp": float(background_distances.min()),
        "candidate_history_links_at_0_5pp": int(sum(r["history_link_required_at_0_5pp"] for r in nearest_rows)),
        "background_history_links_at_0_5pp": int(sum(r["history_link_required_at_0_5pp"] for r in background_rows)),
        "cross_family_candidate_edges_at_0_5pp": len(edges),
    }
    return nearest_rows, background_rows, edges, summary


def cross_member_round4(samples: list[dict], other_path: pathlib.Path,
                        other_member: str) -> tuple[list[dict], dict]:
    """Pairwise D-vs-one-member screen; global closure remains A's freeze step."""
    doc = read_json(other_path)
    if doc.get("production_started") is not False:
        raise ValueError(f"Cross-member source is not a candidate-only record: {other_path}")
    other = doc["samples"]
    path_key = f"{other_member.lower()}_candidate_id"
    elements = (*TARGET_ELEMENTS, "O")
    sample_matrix = np.asarray(
        [[float(r["composition_percent"].get(e, 0.0)) for e in elements] for r in samples],
        dtype=np.float64,
    )
    other_matrix = np.asarray(
        [[float(r["composition_percent"].get(e, 0.0)) for e in elements] for r in other],
        dtype=np.float64,
    )
    distances = cdist(sample_matrix, other_matrix, metric="cityblock")
    edges = []
    for i, j in zip(*np.where(distances <= THRESHOLD_L1)):
        edges.append({
            "d_candidate_id": samples[int(i)]["id"],
            "other_member": other_member,
            "other_candidate_id": other[int(j)]["id"],
            path_key: other[int(j)]["id"],
            "L1_percentage_points": float(distances[i, j]),
            "status": "pending_global_family_union",
        })
    return edges, {
        "member": other_member,
        "path": other_path.relative_to(ROOT).as_posix(),
        "other_candidate_count": len(other),
        "minimum_L1_percentage_points": float(distances.min()),
        "pairs_at_0_5pp": len(edges),
        "exact_composition_matches": sum(edge["L1_percentage_points"] == 0.0 for edge in edges),
        "status": "pairwise_screen_only; global four-member closure pending",
    }


def verify_in_memory(samples: list[dict], families: list[dict], specs: dict) -> list[str]:
    errors: list[str] = []
    if len(samples) != 1000 or len({r["id"] for r in samples}) != 1000:
        errors.append("expected 1000 unique recipes")
    if len(families) != 320 or len({f["design_family_id"] for f in families}) != 320:
        errors.append("expected 320 unique provisional design families")
    category_expected = {
        "element_gradient": 400, "zero_spike": 200,
        "matrix_interference": 200, "routine_coverage": 200,
    }
    category_counts = collections.Counter(r["provenance"]["design_type"] for r in samples)
    if dict(category_counts) != category_expected:
        errors.append(f"category counts mismatch: {dict(category_counts)}")
    role_counts = collections.Counter(r["provenance"]["requested_role"] for r in samples)
    if dict(role_counts) != {"train_nominal": 800, "validation_nominal": 100, "sealed_test_nominal": 100}:
        errors.append(f"nominal role counts mismatch: {dict(role_counts)}")
    if len({canonical(r["composition_percent"]) for r in samples}) != len(samples):
        errors.append("duplicate used compositions")
    if set(specs) != {"silicate_oxide", "iron_oxide"}:
        errors.append("unexpected matrix design range classes")
    for row in samples:
        comp = row["composition_percent"]
        provenance = row["provenance"]
        if set(comp) != set((*TARGET_ELEMENTS, "O")):
            errors.append(f"{row['id']}: composition vector is not 32 targets plus O")
            break
        if not math.isclose(sum(comp.values()), 100.0, rel_tol=0, abs_tol=2e-9) or comp["O"] <= 0:
            errors.append(f"{row['id']}: composition closure/O failed")
            break
        if provenance["production_noise_seed"] is not None or provenance["production_condition"] is not None:
            errors.append(f"{row['id']}: production metadata was prematurely assigned")
            break
        if provenance["global_role_status"] != "pending_global_freeze" or provenance["eligible_for_training"]:
            errors.append(f"{row['id']}: role/training state was prematurely assigned")
            break
        if set(provenance["controlled_element_ppm"]) != set(provenance["compensation_ledger"]["controlled_element_ppm"]):
            errors.append(f"{row['id']}: control ledger mismatch")
            break
        if not within_source_ranges(provenance["compensation_ledger"], specs[provenance["matrix_class"]]["routine"],
                                    set(provenance["controlled_element_ppm"])):
            errors.append(f"{row['id']}: uncontrolled components left the source ranges")
            break
    by_family = collections.defaultdict(list)
    for row in samples:
        by_family[row["provenance"]["design_family_id"]].append(row)
    for family in families:
        rows = by_family[family["design_family_id"]]
        if len(rows) != family["variant_count"]:
            errors.append(f"{family['design_family_id']}: incomplete family")
            continue
        if len({canonical(r["provenance"]["original_composition_percent"]) for r in rows}) != 1:
            errors.append(f"{family['design_family_id']}: variants do not share a parent background")
        target = family["target"]
        values = [r["composition_percent"].get(target, 0.0) * 10000 for r in rows] if target else []
        if family["design_type"] == "element_gradient":
            if values[0] != 0 or not all(a < b for a, b in zip(values, values[1:])):
                errors.append(f"{family['design_family_id']}: gradient is not zero plus nine increasing levels")
        if family["design_type"] == "zero_spike":
            if values[0] != 0 or not all(v > 0 for v in values[1:]) or not all(
                    a < b for a, b in zip(values[1:], values[2:])):
                errors.append(f"{family['design_family_id']}: zero/spike levels invalid")
        if family["design_type"] == "matrix_interference":
            other = family["interferent"]
            interferent_values = [r["composition_percent"].get(other, 0.0) * 10000 for r in rows]
            if not (values[0] == values[2] == 0 and values[1] > 0 and values[4] > values[3] > 0
                    and np.isclose(values[1], values[3])
                    and np.isclose(interferent_values[0], interferent_values[1])
                    and np.isclose(interferent_values[2], interferent_values[3])
                    and np.isclose(interferent_values[3], interferent_values[4])
                    and interferent_values[2] > interferent_values[0]):
                errors.append(f"{family['design_family_id']}: matrix-interaction controls invalid")
            evidence = family.get("line_interference_evidence")
            if not evidence or evidence["delta_eV"] > LINE_WINDOW_EV:
                errors.append(f"{family['design_family_id']}: line evidence missing or outside window")
    conflicts, _ = exact_zero_conflicts(samples)
    if conflicts:
        errors.append(f"exact-zero label conflicts: {conflicts[:3]}")
    return errors


def write_csv(path: pathlib.Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def readme_text(checks: dict) -> str:
    counts = checks["category_counts"]
    roles = checks["nominal_role_recipe_counts"]
    distance = checks["distance_summary"]
    return f"""# D 部分候选配方 v1

状态：D 本地候选校核已完成，并完成与已合并 A、C 第四轮候选的逐对筛分；B 第四轮候选尚未发布，四人全局亲缘闭环、最终用途/阶段分配和生产冻结均未完成。此目录中的内容是组成候选，不是能谱数据。

## 本次候选规模

- {checks['candidate_count']:,} 个唯一组成，{checks['design_family_count_before_global_merge']} 个合并前设计族。
- 元素梯度：40 族 × 10 个配方 = {counts['element_gradient']}。
- 零/加标配对：40 族 × 5 个配方 = {counts['zero_spike']}（1 个真零 + 4 个正水平）。
- 低含量干扰控制：40 族 × 5 个配方 = {counts['matrix_interference']}。
- 常规覆盖：200 族 × 1 个配方 = {counts['routine_coverage']}。
- 基体按硅酸盐/氧化物与富铁氧化物各半配置：{checks['matrix_counts']['silicate_oxide']} / {checks['matrix_counts']['iron_oxide']} 个配方。
- 名义用途预算（仅候选阶段，A 全局冻结后才生效）：训练 {roles['train_nominal']}、验证 {roles['validation_nominal']}、封存测试 {roles['sealed_test_nominal']} 个配方；对应 256/32/32 个完整族。

每个配方记录完整 used composition、原始氧化物/痕量背景、换算结果、受控元素值、移除/加入的载体和质量补偿比例。受控 S 和 Cl 以痕量形式加入，避免通过 CaSO4/NaCl 载体同时引入未受控的 Ca/Na；移除的载体与缩放比例逐条记录在补偿账目中。D 的主题是测量条件与样品状态变化（增益/零点、分辨率、低能响应、本底与计数水平、允许的基体状态），但候选阶段只固定组成：真实增益/零点、分辨率、本底和计数条件实例必须等 A 的公共第四轮 profile 冻结后再分配。为支撑该主题，梯度和零/加标族在覆盖全部 32 个目标元素之外，重点复测 Na、Mg、Al、Si、P、S、Cl、K 这些低能分析线元素；全部配方保留完整 32 个目标元素标签和 O 基体闭合，真实标签是实际 used_percent。

## 干扰控制的线表证据

40 个低含量干扰族全部用 xraylib 实际线表核对：目标元素分析线与干扰元素线在 {checks['line_window_eV']:.0f} eV 候选能窗内，逐族记录线名、能量、相对强度和差值，见 `line_interference_evidence.csv`。能窗是候选筛选假设，不是已冻结的第四轮探测器响应或公共 profile；最终能窗和响应须由 A 的公共范围/条件冻结确认。

## 历史近邻边界

候选与第三轮 A 输入表中的第一/二轮已知历史组成（{checks['historical_rows_compared'] - 1000:,} 条）以及仓库中第三轮 A/B/C/D 候选组成（1,000 条）比较 L1 距离。`nearest_history.csv` 与 `original_background_nearest_history.csv` 保存逐条近邻。最小候选—历史 L1 为 {distance['candidate_to_history_min_L1_pp']:.4f} 个百分点；≤0.5 连接 {distance['candidate_history_links_at_0_5pp']} 条；D 候选跨设计族 ≤0.5 近邻边 {distance['cross_family_candidate_edges_at_0_5pp']} 条。

第四轮成员间逐对比较结果：与已合并 A 的 {checks['cross_member_round4_A']['other_candidate_count']:,} 个候选，最小 L1 {checks['cross_member_round4_A']['minimum_L1_percentage_points']:.4f} 个百分点，≤0.5 对 {checks['cross_member_round4_A']['pairs_at_0_5pp']} 个，精确重复 {checks['cross_member_round4_A']['exact_composition_matches']} 个；与已合并 C 的 {checks['cross_member_round4_C']['other_candidate_count']:,} 个候选，最小 L1 {checks['cross_member_round4_C']['minimum_L1_percentage_points']:.4f} 个百分点，≤0.5 对 {checks['cross_member_round4_C']['pairs_at_0_5pp']} 个，精确重复 {checks['cross_member_round4_C']['exact_composition_matches']} 个。B 的第四轮候选尚未发布，四人全局闭环仍待 A 在 B 合并后完成。候选范围只覆盖已登记来源，不能证明不存在未记录的历史亲缘。

所有候选的 requested role 只是 `train_nominal`/`validation_nominal`/`sealed_test_nominal` 预算，`global_role_status` 仍为 `pending_global_freeze`；没有最终 train/test 分配、条件实例、生产噪声种子或训练资格。脚本生成的候选设计 RNG 值仅用于可复现地构造配方，不是测谱噪声子种子或批量生成种子。

## 下一步与生产口径

当前生产被前置条件阻塞：A 尚未发布第四轮公共范围、条件/profile、`freeze_v1` 和完整生产 release，仓库状态仍为 `usable_for_generation=false`、`production_started=false`。因此本目录不含运行器、条件实例、噪声种子或能谱，也不能复用第三轮命令出谱。

D 不安排 400 谱试片。待 A 的公共冻结和完整生产 release 通过后，按冻结 release 一次生成全部 20,000 条谱（1,000 配方 × 10 个真实条件 × 2 个独立计数噪声），随后做一次全量 audit/replay/QC，再打包交付。封存部分保持 `eligible_for_training=false`。

## 复核与重建

在协作仓库根目录执行：

```powershell
python datasets/round4/member_D/build_candidates.py
python datasets/round4/member_D/verify_candidates.py
```

`build_candidates.py` 默认拒绝覆盖已有输出。`verify_candidates.py` 独立检查数量、闭合、补偿重建、范围、名义用途计数、线表证据、历史距离、A/C 成员间距离和交付哈希，并写出 `independent_verification.json`。当前没有可执行的第四轮生产命令；本目录不含任何能谱。
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, default=HERE / "candidates")
    parser.add_argument("--round3-root", type=pathlib.Path, default=ROOT / "datasets/round3")
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite candidate output: {out}")
    ranges_path = INPUTS / "design_ranges.json"
    history_path = INPUTS / "historical_compositions.json"
    specs = read_json(ranges_path)

    families = allocation()
    samples, completed = build(specs, families)
    errors = verify_in_memory(samples, completed, specs)
    if errors:
        raise ValueError("Candidate construction checks failed: " + "; ".join(errors[:20]))

    history, history_sources = load_history(history_path, args.round3_root.resolve())
    nearest, backgrounds, edges, distance_summary = distance_reports(samples, completed, history)
    a_round4_path = ROOT / "datasets/round4/member_A/candidates_v1/A_samples.json"
    c_round4_path = ROOT / "datasets/round4/member_C/candidates/C_samples.json"
    a_edges, a_summary = cross_member_round4(samples, a_round4_path, "A")
    c_edges, c_summary = cross_member_round4(samples, c_round4_path, "C")
    cross_edges = a_edges + c_edges
    nearest_by_id = {r["candidate_id"]: r for r in nearest}
    history_by_id = {r["id"]: r for r in history}
    for row in samples:
        match = nearest_by_id[row["id"]]
        row["provenance"]["historical_source"] = match["nearest_historical_id"]
        row["provenance"]["nearest_historical_L1_percentage_points"] = match["nearest_historical_L1_percentage_points"]
        row["provenance"]["historical_train_only_constraint_pending"] = match["history_link_required_at_0_5pp"]
        row["provenance"]["historical_exposure"] = history_by_id[match["nearest_historical_id"]]["exposure"]
    for family in completed:
        group = [r for r in nearest if r["design_family_id"] == family["design_family_id"]]
        family["nearest_historical_source"] = min(
            group, key=lambda r: r["nearest_historical_L1_percentage_points"]
        )["nearest_historical_id"]
        family["minimum_candidate_history_L1_percentage_points"] = min(
            r["nearest_historical_L1_percentage_points"] for r in group
        )
        background_row = next(r for r in backgrounds if r["design_family_id"] == family["design_family_id"])
        family["nearest_original_background_history_source"] = background_row["nearest_historical_id"]
        family["minimum_original_background_history_L1_percentage_points"] = (
            background_row["nearest_historical_L1_percentage_points"]
        )
        family["historical_train_only_constraint_pending"] = (
            family["minimum_candidate_history_L1_percentage_points"] <= THRESHOLD_L1
            or family["minimum_original_background_history_L1_percentage_points"] <= THRESHOLD_L1
        )

    matrix_counts = collections.Counter(r["provenance"]["matrix_class"] for r in samples)
    category_counts = collections.Counter(r["provenance"]["design_type"] for r in samples)
    role_recipe_counts = collections.Counter(r["provenance"]["requested_role"] for r in samples)
    role_family_counts = collections.Counter(f["requested_role"] for f in completed)
    zero_conflicts, zero_verified = exact_zero_conflicts(samples)

    source_manifest = {
        "schema": "round4-D-candidate-source-manifest/1",
        "status": "candidate_inputs_only_not_production_freeze",
        "inputs": [
            {"path": ranges_path.relative_to(ROOT).as_posix(), "sha256": sha256(ranges_path),
             "bytes": ranges_path.stat().st_size,
             "role": "Round3 A validated starting ranges; Round4 range proposal only"},
            {"path": history_path.relative_to(ROOT).as_posix(), "sha256": sha256(history_path),
             "bytes": history_path.stat().st_size,
             "role": "Round1/2 historical composition table with its embedded source list"},
            *history_sources,
            *[{"path": (GENERATOR / f"fp_competition/{name}").relative_to(ROOT).as_posix(),
               "sha256": sha256(GENERATOR / f"fp_competition/{name}"),
               "bytes": (GENERATOR / f"fp_competition/{name}").stat().st_size,
               "role": "Round3 frozen composition conversion/range sampler source"}
              for name in ("core.py", "minerals.py", "version.py")],
            {"path": a_round4_path.relative_to(ROOT).as_posix(),
             "sha256": sha256(a_round4_path),
             "bytes": a_round4_path.stat().st_size,
             "records": a_summary["other_candidate_count"],
             "role": "Round4 A candidate recipes for the D-vs-A pairwise screen; not a role or family freeze"},
            {"path": c_round4_path.relative_to(ROOT).as_posix(),
             "sha256": sha256(c_round4_path),
             "bytes": c_round4_path.stat().st_size,
             "records": c_summary["other_candidate_count"],
             "role": "Round4 C candidate recipes for the D-vs-C pairwise screen; not a role or family freeze"},
        ],
        "coverage_limit": (
            "Known Round1/2 history from the Round3 A input table plus all four Round3 shared "
            "candidate registries. Does not prove absence of undocumented material ancestry."
        ),
    }
    source_manifest_hash = hashlib.sha256(
        json.dumps(source_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    input_identity = {
        "schema": "round4-D-candidate-input-identity/1",
        "member": "D",
        "builder_sha256": sha256(pathlib.Path(__file__).resolve()),
        "source_manifest_sha256": source_manifest_hash,
        "generator_version": GENERATOR_VERSION,
        "candidate_rng": "sha256-derived NumPy default_rng seed; candidate-design-only, not production or spectrum noise",
        "noise_seeds_allocated": False,
        "range_status": "draft_using_round3_validated_ranges; requires Round4 public scope review and global freeze",
        "historical_archive": {
            "path": history_path.relative_to(ROOT).as_posix(),
            "sha256": sha256(history_path),
            "bytes": history_path.stat().st_size,
            "status": read_json(history_path)["status"],
            "coverage_limit": read_json(history_path)["coverage_limit"],
        },
        "round3_candidate_sources": history_sources[1:],
        "spectra_generated": 0,
        "production_started": False,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": __import__("scipy").__version__,
            "xraylib": getattr(xl, "__version__", "version_not_exposed"),
        },
    }
    for sample in samples:
        sample["provenance"]["input_source_manifest_sha256"] = source_manifest_hash
    for family in completed:
        family["input_source_manifest_sha256"] = source_manifest_hash

    checks = {
        "schema": "round4-D-candidate-checks/1",
        "status": "passed_D_local_candidate_checks",
        "errors": [],
        "candidate_count": len(samples),
        "design_family_count_before_global_merge": len(completed),
        "category_counts": dict(sorted(category_counts.items())),
        "matrix_counts": dict(sorted(matrix_counts.items())),
        "nominal_role_recipe_counts": dict(sorted(role_recipe_counts.items())),
        "nominal_role_family_counts": dict(sorted(role_family_counts.items())),
        "variants": {
            "element_gradient": "one true zero plus nine strictly increasing positive levels spanning trace to major",
            "zero_spike": "one true zero plus four distinct positive levels near detection thresholds",
            "matrix_interference": "five paired low-level target/interferent controls with xraylib line-table evidence",
            "routine_coverage": "one composition per family",
        },
        "line_interference_pairs": len(INTERFERENCE_PAIRS),
        "line_window_eV": LINE_WINDOW_EV,
        "line_evidence_file": "line_interference_evidence.csv",
        "line_window_status": "candidate_screen_only; detector profile and public round4 energy window not frozen",
        "matrix_status": "draft_50_50_silicate_iron; requires Round4 public scope review",
        "exact_zero_labels_verified": zero_verified,
        "exact_zero_label_conflicts": len(zero_conflicts),
        "historical_rows_compared": len(history),
        "historical_source_count": len(history_sources),
        "historical_nearest_threshold_L1_percentage_points": THRESHOLD_L1,
        "distance_summary": distance_summary,
        "cross_member_round4_A": a_summary,
        "cross_member_round4_C": c_summary,
        "cross_member_round4_B": {
            "status": "pending_B_round4_candidate_publication_and_A_global_closure",
        },
        "cross_member_confirmation": "pairwise_A_and_C_screens_done; pending_B_round4_merge_and_A_global_closure",
        "global_family_closure": "pending_all_round4_candidates_and_round1_2_3_history",
        "role_and_stage_assignments": "pending_global_freeze",
        "production_started": False,
        "spectra_generated": 0,
        "noise_seeds_allocated": False,
        "eligible_for_training": False,
        "scientific_accuracy_validated": False,
        "range_status": "draft_using_round3_validated_ranges; requires Round4 public scope review and global freeze",
        "round3_candidate_source_mode": (
            "repository_tree" if args.round3_root.resolve().is_relative_to(ROOT)
            else "verified_local_snapshot"
        ),
    }

    out.mkdir(parents=True)
    write_json(out / "D_samples.json", {
        "schema": SCHEMA,
        "round_id": "round4",
        "member": "D",
        "status": "candidate_pending_cross_member_global_freeze",
        "production_started": False,
        "eligible_for_training": False,
        "spectra_generated": 0,
        "noise_seeds_allocated": False,
        "samples": samples,
    })
    write_json(out / "family_registry.json", {
        "schema": "round4-D-family-candidates/1",
        "status": "provisional_before_global_family_closure",
        "families": completed,
    })
    write_json(out / "original_backgrounds.json", {
        "status": "candidate_pending_global_freeze",
        "note": "one fresh independent background board per design family; every variant of a family shares it",
        "backgrounds": {
            family["design_family_id"]: {
                "matrix_class": family["matrix_class"],
                "background_seed": family["candidate_design_seed"],
                "background_attempt": family["background_attempt"],
                "compounds_percent": next(
                    r["provenance"]["original_recipe"]["compounds_percent"]
                    for r in samples if r["provenance"]["design_family_id"] == family["design_family_id"]
                ),
                "trace_ppm": next(
                    r["provenance"]["original_recipe"]["trace_ppm"]
                    for r in samples if r["provenance"]["design_family_id"] == family["design_family_id"]
                ),
                "composition_percent": family["original_composition_percent"],
            }
            for family in completed
        },
    })
    write_json(out / "source_manifest.json", source_manifest)
    write_json(out / "input_identity.json", input_identity)
    write_json(out / "candidate_checks.json", checks)

    write_csv(out / "candidate_registry.csv", REGISTRY_FIELDS, [{
        "candidate_id": row["id"],
        "member": "D",
        "design_family_id": row["provenance"]["design_family_id"],
        "parent_family_id": row["provenance"]["design_family_id"],
        "design_type": row["provenance"]["design_type"],
        "variant_id": row["provenance"]["variant_id"],
        "matrix_class": row["provenance"]["matrix_class"],
        "composition_used_json": json.dumps(row["composition_percent"], ensure_ascii=False,
                                            sort_keys=True, separators=(",", ":")),
        "original_composition_json": json.dumps(row["provenance"]["original_composition_percent"],
                                                ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "compensation_ledger_json": json.dumps(row["provenance"]["compensation_ledger"],
                                               ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "historical_source_id": row["provenance"]["historical_source"],
        "historical_exposure": row["provenance"]["historical_exposure"],
        "requested_role": row["provenance"]["requested_role"],
        "global_role_status": row["provenance"]["global_role_status"],
    } for row in samples])
    write_csv(out / "nearest_history.csv", list(nearest[0]), nearest)
    write_csv(out / "original_background_nearest_history.csv", list(backgrounds[0]), backgrounds)
    write_csv(out / "cross_family_near_edges.csv",
              ["candidate_a", "candidate_b", "family_a", "family_b", "L1_percentage_points", "status"],
              edges)
    write_csv(out / "cross_member_near_edges.csv",
              ["d_candidate_id", "other_member", "other_candidate_id",
               "L1_percentage_points", "status"],
              cross_edges)
    write_csv(out / "line_interference_evidence.csv", [
        "design_family_id", "target_element", "interferent_element", "matrix_class", "window_eV",
        "target_line", "target_line_energy_eV", "target_rad_rate", "interferent_line",
        "interferent_line_energy_eV", "interferent_rad_rate", "delta_eV", "mechanism", "status",
    ], [{
        "design_family_id": family["design_family_id"],
        "target_element": family["target"],
        "interferent_element": family["interferent"],
        "matrix_class": family["matrix_class"],
        "window_eV": family["line_interference_evidence"]["window_eV"],
        "target_line": family["line_interference_evidence"]["target_line"],
        "target_line_energy_eV": family["line_interference_evidence"]["target_line_energy_eV"],
        "target_rad_rate": family["line_interference_evidence"]["target_rad_rate"],
        "interferent_line": family["line_interference_evidence"]["interferent_line"],
        "interferent_line_energy_eV": family["line_interference_evidence"]["interferent_line_energy_eV"],
        "interferent_rad_rate": family["line_interference_evidence"]["interferent_rad_rate"],
        "delta_eV": family["line_interference_evidence"]["delta_eV"],
        "mechanism": family["line_interference_evidence"]["mechanism"],
        "status": family["line_interference_evidence"]["status"],
    } for family in completed if family["design_type"] == "matrix_interference"])

    coverage = {}
    for element in TARGET_ELEMENTS:
        values = [row["composition_percent"].get(element, 0.0) * 10000 for row in samples]
        coverage[element] = {
            "zero": sum(v == 0 for v in values),
            "positive_below_1ppm": sum(0 < v < 1 for v in values),
            "positive_1_to_10ppm": sum(1 <= v < 10 for v in values),
            "positive_10_to_100ppm": sum(10 <= v < 100 for v in values),
            "positive_100_to_1000ppm": sum(100 <= v < 1000 for v in values),
            "positive_at_least_1000ppm": sum(v >= 1000 for v in values),
            "max_used_ppm": max(values),
            "families_as_gradient_target": sum(f["target"] == element and f["design_type"] == "element_gradient" for f in completed),
            "families_as_zero_spike_target": sum(f["target"] == element and f["design_type"] == "zero_spike" for f in completed),
            "families_as_interference_target": sum(f["target"] == element and f["design_type"] == "matrix_interference" for f in completed),
        }
    write_json(out / "coverage.json", {
        "schema": "round4-D-candidate-coverage/1",
        "scope": "composition labels, not measured detection limits",
        "target_elements_tracked": len(TARGET_ELEMENTS),
        "elements": coverage,
    })
    (out / "README.md").write_text(readme_text(checks), encoding="utf-8")

    manifest_rows = []
    for path in sorted(p for p in out.iterdir() if p.is_file() and p.name != "delivery_manifest.json"):
        manifest_rows.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json(out / "delivery_manifest.json", {
        "schema": "round4-D-candidate-delivery/1",
        "status": "candidate_only_not_production_release",
        "member": "D",
        "round_id": "round4",
        "candidate_count": len(samples),
        "design_family_count_before_global_merge": len(completed),
        "production_started": False,
        "eligible_for_training": False,
        "files": manifest_rows,
    })
    print(json.dumps({
        "out": str(out),
        "candidate_count": len(samples),
        "families": len(completed),
        "category_counts": dict(category_counts),
        "matrix_counts": dict(matrix_counts),
        "role_recipe_counts": dict(role_recipe_counts),
        "role_family_counts": dict(role_family_counts),
        "exact_zero_labels_verified": zero_verified,
        "exact_zero_label_conflicts": len(zero_conflicts),
        "distance_summary": distance_summary,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
