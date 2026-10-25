"""Build B's round-four composition candidates only; never generate spectra.

B's theme is overlapping peaks and absorption/enhancement interferences
(V/Cr, Mn/Fe, Co/Ni, As/Pb and further real line overlaps).  Every interference
pair is screened against the xraylib line table inside a 150 eV candidate
window; that window is a screening assumption, not a frozen detector profile.

Nothing here is a production release: no measurement conditions, no noise
seeds, no final train/validation/sealed assignment and no spectra.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import platform
import pathlib
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

SCHEMA = "round4-B-candidate-compositions/1"
THRESHOLD_L1 = 0.5
LINE_WINDOW_EV = 150.0

FOCUS_PAIRS = (("V", "Cr"), ("Mn", "Fe"), ("Co", "Ni"), ("As", "Pb"))

CARRIERS = {
    "Na": "Na2O", "Mg": "MgO", "Al": "Al2O3", "Si": "SiO2", "P": "P2O5",
    "K": "K2O", "Ca": "CaO", "Ti": "TiO2", "Mn": "MnO", "Fe": "Fe2O3T",
}
TRACE_ELEMENTS = (
    "V", "Cr", "Co", "Ni", "Cu", "Zn", "As", "Se", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Cd", "Sn", "Sb", "Ba", "W", "Pb", "S", "Cl",
)

REGISTRY_FIELDS = [
    "candidate_id", "member", "design_family_id", "parent_family_id",
    "design_type", "variant_id", "matrix_class", "composition_used_json",
    "original_composition_json", "compensation_ledger_json",
    "historical_source_id", "historical_exposure", "requested_role",
    "global_role_status",
]

CATEGORY = collections.OrderedDict(
    (
        ("element_gradient", {"prefix": "ELEMENT_GRADIENT", "families": 40, "variants": 10}),
        ("zero_spike", {"prefix": "ZERO_SPIKE", "families": 40, "variants": 5}),
        ("matrix_interference", {"prefix": "MATRIX_INTERFERENCE", "families": 40, "variants": 5}),
        ("routine_coverage", {"prefix": "ROUTINE", "families": 200, "variants": 1}),
    )
)

LINE_DEFS = {
    "KA1": xl.KA1_LINE, "KA2": xl.KA2_LINE, "KB1": xl.KB1_LINE,
    "LA1": xl.LA1_LINE, "LA2": xl.LA2_LINE, "LB1": xl.LB1_LINE,
    "LB2": xl.LB2_LINE, "MA1": xl.MA1_LINE, "MB": xl.MB_LINE,
}

COMPENSATION_NOTE = (
    "replace every source compound containing a controlled element; add the declared "
    "oxide/trace level; proportionally scale all remaining compounds and traces; "
    "record resulting elemental deltas"
)
RANGE_CAVEAT = (
    "The original source ranges describe the sampled background. Controlled zero/low/high "
    "levels may intentionally lie outside those ranges to cover detection-threshold and "
    "spike behaviour; every non-controlled compound and trace must remain inside its range."
)


# --------------------------------------------------------------------------- io
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
    raw = hashlib.sha256(("round4-B-candidate-only-v1:" + key).encode("utf-8")).digest()
    return int.from_bytes(raw[:8], "big")


# --------------------------------------------------------------------- chemistry
def formula_fraction(formula: str, element: str) -> float:
    parsed = xl.CompoundParser("Fe2O3" if formula == "Fe2O3T" else formula)
    for z, weight in zip(parsed["Elements"], parsed["massFractions"]):
        if xl.AtomicNumberToSymbol(z) == element:
            return float(weight)
    return 0.0


def spec_element_max(spec: dict, element: str) -> float:
    if element in spec["trace_ranges_ppm"]:
        return spec["trace_ranges_ppm"][element][1] / 10000.0
    if element == "S":
        return spec["compound_ranges_percent"]["CaSO4"][1] * formula_fraction("CaSO4", "S")
    if element == "Cl":
        return spec["compound_ranges_percent"]["NaCl"][1] * formula_fraction("NaCl", "Cl")
    carrier = CARRIERS[element]
    ranges = spec["compound_ranges_percent"]
    if carrier == spec["balance_compound"]:
        return spec["balance_range_percent"][1] * formula_fraction(carrier, element)
    if carrier in ranges:
        return ranges[carrier][1] * formula_fraction(carrier, element)
    return 0.0


def spec_element_min(spec: dict, element: str) -> float:
    if element in spec["trace_ranges_ppm"]:
        return spec["trace_ranges_ppm"][element][0] / 10000.0
    if element == "S":
        return spec["compound_ranges_percent"]["CaSO4"][0] * formula_fraction("CaSO4", "S")
    if element == "Cl":
        return spec["compound_ranges_percent"]["NaCl"][0] * formula_fraction("NaCl", "Cl")
    carrier = CARRIERS[element]
    ranges = spec["compound_ranges_percent"]
    if carrier == spec["balance_compound"]:
        return spec["balance_range_percent"][0] * formula_fraction(carrier, element)
    if carrier in ranges:
        return ranges[carrier][0] * formula_fraction(carrier, element)
    return 0.0


def balance_element(spec: dict) -> str:
    for element, carrier in CARRIERS.items():
        if carrier == spec["balance_compound"]:
            return element
    raise ValueError("balance compound has no carrier mapping")


# ------------------------------------------------------------------- line table
def element_lines(element: str) -> list[tuple[str, float, float]]:
    z = xl.SymbolToAtomicNumber(element)
    rows = []
    for name, code in LINE_DEFS.items():
        try:
            energy = xl.LineEnergy(z, code)
            rate = xl.RadRate(z, code)
        except Exception:
            continue
        if not energy or energy <= 0 or not rate or rate <= 0:
            continue
        rows.append((name, float(energy) * 1000.0, float(rate)))
    return rows


def best_overlap(target: str, interferent: str) -> dict | None:
    best = None
    for t_name, t_e, t_i in element_lines(target):
        for i_name, i_e, i_i in element_lines(interferent):
            delta = abs(t_e - i_e)
            if best is None or delta < best["delta_eV"]:
                best = {
                    "target_line": t_name, "target_line_energy_eV": round(t_e, 1),
                    "target_rad_rate": round(t_i, 5),
                    "interferent_line": i_name, "interferent_line_energy_eV": round(i_e, 1),
                    "interferent_rad_rate": round(i_i, 5),
                    "delta_eV": round(delta, 1),
                }
    return best


def line_evidence(target: str, interferent: str) -> dict:
    overlap = best_overlap(target, interferent)
    return {
        "schema": "round4-B-line-interference-evidence/1",
        "target_element": target,
        "interferent_element": interferent,
        "window_eV": LINE_WINDOW_EV,
        "target_line": overlap["target_line"],
        "target_line_energy_eV": overlap["target_line_energy_eV"],
        "target_rad_rate": overlap["target_rad_rate"],
        "interferent_line": overlap["interferent_line"],
        "interferent_line_energy_eV": overlap["interferent_line_energy_eV"],
        "interferent_rad_rate": overlap["interferent_rad_rate"],
        "delta_eV": overlap["delta_eV"],
        "mechanism": "overlapping_analytical_line_within_candidate_energy_window",
        "status": "candidate_screen_using_xraylib_line_table; detector profile and public round4 window not frozen",
        "strength": max(overlap["target_rad_rate"], overlap["interferent_rad_rate"]),
    }


def interference_pairs() -> list[tuple[str, str]]:
    candidates = []
    for i, a in enumerate(TARGET_ELEMENTS):
        for b in TARGET_ELEMENTS[i + 1:]:
            overlap = best_overlap(a, b)
            if overlap and overlap["delta_eV"] <= LINE_WINDOW_EV:
                candidates.append((overlap["delta_eV"], a, b))
    candidates.sort()
    chosen: list[tuple[str, str]] = []
    used = collections.Counter()
    for pair in FOCUS_PAIRS:
        if pair not in chosen:
            chosen.append(pair)
            used[pair[0]] += 1
            used[pair[1]] += 1
    for cap in (2, 3, 99):
        for _, a, b in candidates:
            if len(chosen) >= 40:
                break
            if (a, b) in chosen or (b, a) in chosen:
                continue
            if used[a] >= cap or used[b] >= cap:
                continue
            chosen.append((a, b))
            used[a] += 1
            used[b] += 1
        if len(chosen) >= 40:
            break
    if len(chosen) < 40:  # pragma: no cover - defensive
        raise ValueError("fewer than 40 qualifying interference pairs")
    return chosen[:40]


# ------------------------------------------------------------------ allocation
INTERFERENCE_ROLES = (
    "target_zero_interferent_low",
    "target_low_interferent_low",
    "target_zero_interferent_high",
    "target_low_interferent_high",
    "target_high_interferent_high",
)


def nominal_role(index: int) -> str:
    if index % 10 == 0:
        return "sealed_test_nominal"
    if index % 10 == 1:
        return "validation_nominal"
    return "train_nominal"


def allocate(specs: dict) -> tuple[list[dict], list[tuple[str, str]]]:
    pairs = interference_pairs()
    gradient_targets = list(TARGET_ELEMENTS) + ["V", "Cr", "Mn", "Fe", "Co", "Ni", "As", "Pb"]
    zero_targets = list(TARGET_ELEMENTS) + ["Cd", "Pb", "As", "Se", "Co", "Ni", "Rb", "Sr"]
    families: list[dict] = []
    for design_type, meta in CATEGORY.items():
        for index in range(meta["families"]):
            target = interferent = None
            if design_type == "element_gradient":
                target = gradient_targets[index]
            elif design_type == "zero_spike":
                target = zero_targets[index]
            elif design_type == "matrix_interference":
                target, interferent = pairs[index]
            forbidden = {e for e in (target, interferent) if e}
            families.append({
                "family_id": f"R4_B_{meta['prefix']}_{index + 1:04d}",
                "design_type": design_type,
                "prefix": meta["prefix"],
                "variant_count": meta["variants"],
                "target": target,
                "interferent": interferent,
                "forbidden": forbidden,
                "scenario": "routine",
                "nominal_role": nominal_role(index),
                "index": index,
            })
    totals = collections.Counter()
    for family in families:
        options = []
        for matrix in ("silicate_oxide", "iron_oxide"):
            if balance_element(specs[matrix][family["scenario"]]) in family["forbidden"]:
                continue
            options.append(matrix)
        if not options:
            raise ValueError(f"no matrix available for {family['family_id']}")
        options.sort(key=lambda m: (totals[m],
                                    0 if (m == "silicate_oxide") == (family["index"] % 2 == 0) else 1))
        family["matrix_type"] = options[0]
        totals[options[0]] += 1
    return families, pairs


# ------------------------------------------------------------------- background
def detach_s_and_cl(compounds: dict, traces: dict) -> tuple[dict, dict, dict]:
    """Express sulfate/chloride as element traces so one element can be controlled alone."""
    compounds = dict(compounds)
    traces = dict(traces)
    ledger = {}
    if compounds.get("CaSO4", 0.0) > 0:
        mass = compounds.pop("CaSO4")
        ca = mass * formula_fraction("CaSO4", "Ca")
        s_ppm = mass * formula_fraction("CaSO4", "S") * 10000.0
        compounds["CaO"] = compounds.get("CaO", 0.0) + ca / formula_fraction("CaO", "Ca")
        traces["S"] = traces.get("S", 0.0) + s_ppm
        ledger["CaSO4"] = {"removed_compound_percent": mass,
                           "element_reinstated": "Ca", "via": "CaO",
                           "element_reinstated_percent": ca,
                           "trace_added_ppm": {"S": s_ppm}}
    if compounds.get("NaCl", 0.0) > 0:
        mass = compounds.pop("NaCl")
        na = mass * formula_fraction("NaCl", "Na")
        cl_ppm = mass * formula_fraction("NaCl", "Cl") * 10000.0
        compounds["Na2O"] = compounds.get("Na2O", 0.0) + na / formula_fraction("Na2O", "Na")
        traces["Cl"] = traces.get("Cl", 0.0) + cl_ppm
        ledger["NaCl"] = {"removed_compound_percent": mass,
                          "element_reinstated": "Na", "via": "Na2O",
                          "element_reinstated_percent": na,
                          "trace_added_ppm": {"Cl": cl_ppm}}
    return compounds, traces, ledger


def make_background(spec: dict, key: str, salt: int = 0) -> dict | None:
    base_seed = (candidate_seed("background:" + key) + salt * 7919) % (2 ** 63)
    for attempt in range(64):
        seed = base_seed + attempt
        try:
            design = design_minerals(spec, 1, seed)
        except ValueError:
            continue
        sample = design["samples"][0]
        provenance = sample["provenance"]
        raw_compounds = {k: float(v) for k, v in provenance["compounds_percent"].items()}
        raw_traces = {k: float(v) for k, v in provenance["trace_ppm"].items()}
        working, traces, detached = detach_s_and_cl(raw_compounds, raw_traces)
        balance = spec["balance_compound"]
        residual = 100.0 - (sum(working.values()) + sum(traces.values()) / 10000.0)
        working[balance] = working.get(balance, 0.0) + residual
        if not (spec["balance_range_percent"][0] - 1e-9 <= working[balance]
                <= spec["balance_range_percent"][1] + 1e-9):
            continue
        if any(v < -1e-12 for v in working.values()):
            continue
        overflow = any(
            value > spec["compound_ranges_percent"].get(formula, [0.0, 0.0])[1] + 1e-9
            for formula, value in working.items() if formula != balance)
        if overflow:
            continue
        try:
            composition, _ = components_to_elements(working, traces)
            original_composition, _ = components_to_elements(raw_compounds, raw_traces)
        except ValueError:
            continue
        return {
            "seed": seed,
            "attempt": attempt,
            "original_recipe": {"compounds_percent": raw_compounds, "trace_ppm": raw_traces},
            "original_composition_percent": original_composition,
            "working_compounds": working,
            "working_traces": traces,
            "detached": detached,
        }
    return None


# ---------------------------------------------------------------------- levels
def geometric(first: float, last: float, count: int) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [first]
    ratio = (last / first) ** (1.0 / (count - 1))
    return [first * ratio ** i for i in range(count)]


def level_plan(family: dict, spec: dict) -> list[dict]:
    if family["design_type"] == "routine_coverage":
        return [{"role": "routine", "controls": {}}]

    if family["design_type"] == "element_gradient":
        element = family["target"]
        high = 0.9 * spec_element_max(spec, element)
        low = max(spec_element_min(spec, element), high / 1e4)
        if high <= 0 or low >= high:
            return []
        levels = geometric(low, high, 10)
        return [{"role": f"gradient_{i:02d}", "controls": {element: level}}
                for i, level in enumerate(levels, start=1)]

    if family["design_type"] == "zero_spike":
        element = family["target"]
        high = 0.9 * spec_element_max(spec, element)
        threshold = max(spec_element_min(spec, element), high / 1000.0)
        if threshold * 15.0 <= high:
            levels = [threshold * f for f in (1.0, 2.5, 6.0, 15.0)]
        else:
            levels = geometric(threshold, 0.6 * high, 4)
        levels = sorted(dict.fromkeys(round(v, 12) for v in levels))
        if high <= 0 or len(levels) < 4:
            return []
        plan = [{"role": "true_zero", "controls": {element: 0.0}}]
        for index, level in enumerate(levels[:4], start=1):
            plan.append({"role": f"spike_{index:02d}", "controls": {element: level}})
        return plan

    target, interferent = family["target"], family["interferent"]
    t_max = spec_element_max(spec, target)
    i_max = spec_element_max(spec, interferent)
    if t_max <= 0 or i_max <= 0:
        return []
    t_low, t_high = 0.05 * t_max, 0.6 * t_max
    i_low, i_high = 0.1 * i_max, 0.8 * i_max
    levels = {
        "target_zero_interferent_low": {target: 0.0, interferent: i_low},
        "target_low_interferent_low": {target: t_low, interferent: i_low},
        "target_zero_interferent_high": {target: 0.0, interferent: i_high},
        "target_low_interferent_high": {target: t_low, interferent: i_high},
        "target_high_interferent_high": {target: t_high, interferent: i_high},
    }
    return [{"role": role, "controls": levels[role]} for role in INTERFERENCE_ROLES]


# -------------------------------------------------------------------- controls
def within_source_ranges(compounds: dict, traces: dict, spec: dict,
                         controlled_compounds: set[str],
                         controlled_traces: set[str]) -> bool:
    """Non-controlled components must stay inside the validated source envelope."""
    for formula, value in compounds.items():
        if value < -1e-12:
            return False
        if formula in controlled_compounds:
            continue
        ceiling = (spec["balance_range_percent"][1] if formula == spec["balance_compound"]
                   else spec["compound_ranges_percent"].get(formula, [0.0, 0.0])[1])
        if value > ceiling + 1e-6:
            return False
    for element, value in traces.items():
        if element in controlled_traces:
            continue
        if value <= 0.0:
            continue
        if element in spec["trace_ranges_ppm"]:
            ceiling = spec["trace_ranges_ppm"][element][1]
        elif element == "S":
            ceiling = (spec["compound_ranges_percent"]["CaSO4"][1]
                       * formula_fraction("CaSO4", "S") * 10000.0)
        elif element == "Cl":
            ceiling = (spec["compound_ranges_percent"]["NaCl"][1]
                       * formula_fraction("NaCl", "Cl") * 10000.0)
        else:
            return False
        if value > ceiling + 1e-6:
            return False
    return True


def apply_controls(background: dict, controls: dict[str, float], spec: dict) -> dict:
    compounds = dict(background["working_compounds"])
    traces = dict(background["working_traces"])
    removed_compounds, added_compounds = {}, {}
    removed_traces, added_traces = {}, {}
    for element, value in controls.items():
        value = float(value)
        if element in TRACE_ELEMENTS:
            removed_traces[element] = traces.get(element, 0.0)
            traces[element] = value * 10000.0
            added_traces[element] = value * 10000.0
        else:
            carrier = CARRIERS[element]
            fraction = formula_fraction(carrier, element)
            removed_compounds[carrier] = compounds.get(carrier, 0.0)
            compounds[carrier] = value / fraction
            added_compounds[carrier] = value / fraction

    fixed_compounds = sum(compounds[c] for c in removed_compounds)
    fixed_traces = sum(traces[e] for e in removed_traces)
    rest_compounds = sum(v for k, v in compounds.items() if k not in removed_compounds)
    rest_traces = sum(v for k, v in traces.items() if k not in removed_traces)
    rest_total = rest_compounds + rest_traces / 10000.0
    free_mass = 100.0 - fixed_compounds - fixed_traces / 10000.0
    scale = free_mass / rest_total if rest_total > 0 else 1.0
    for formula in compounds:
        if formula not in removed_compounds:
            compounds[formula] *= scale
    for element in traces:
        if element not in removed_traces:
            traces[element] *= scale

    composition, _ = components_to_elements(compounds, traces)
    original = background["original_composition_percent"]
    deltas = {element: round(composition.get(element, 0.0) - original.get(element, 0.0), 9)
              for element in set(composition) | set(original)}
    ledger = {
        "kind": "round4_explicit_element_control_and_mass_compensation",
        "controlled_element_ppm": {k: round(float(v) * 10000.0, 9) for k, v in controls.items()},
        "actual_element_ppm": {k: round(float(composition.get(k, 0.0)) * 10000.0, 9)
                               for k in controls},
        "removed_compounds_percent": {k: round(v, 12) for k, v in removed_compounds.items()},
        "removed_trace_ppm": {k: round(v, 12) for k, v in removed_traces.items()},
        "added_carrier_compounds_percent": {k: round(v, 12) for k, v in added_compounds.items()},
        "added_trace_ppm": {k: round(v, 12) for k, v in added_traces.items()},
        "uncontrolled_mixture_scale": round(scale, 12),
        "compensation": COMPENSATION_NOTE,
        "controlled_range_override": True,
        "range_caveat": RANGE_CAVEAT,
        "element_delta_percentage_points": deltas,
        "detached_carriers": background["detached"],
        "final_compounds_percent": {k: round(v, 12) for k, v in compounds.items() if v != 0},
        "final_trace_ppm": {k: round(v, 12) for k, v in traces.items() if v != 0},
    }
    return {
        "compounds": compounds,
        "traces": traces,
        "composition": composition,
        "ledger": ledger,
        "controlled_compounds": set(removed_compounds),
        "controlled_traces": set(removed_traces),
    }


# ---------------------------------------------------------------------- build
def build() -> tuple[list[dict], list[dict], dict]:
    specs = read_json(INPUTS / "design_ranges.json")
    families, pairs = allocate(specs)
    samples: list[dict] = []
    family_rows: list[dict] = []
    dropped: list[dict] = []
    for family in families:
        spec = specs[family["matrix_type"]][family["scenario"]]
        plan = level_plan(family, spec)
        if not plan:
            dropped.append({"family_id": family["family_id"], "reason": "no_feasible_levels"})
            continue
        background = None
        built = []
        for salt in range(64):
            background = make_background(spec, family["family_id"], salt)
            if background is None:
                continue
            built = []
            feasible = True
            for variant in plan:
                controlled = apply_controls(background, variant["controls"], spec)
                if not within_source_ranges(controlled["compounds"], controlled["traces"], spec,
                                            controlled["controlled_compounds"],
                                            controlled["controlled_traces"]):
                    feasible = False
                    break
                built.append((variant, controlled))
            if feasible:
                break
        if background is None or not built:
            dropped.append({"family_id": family["family_id"], "reason": "no_feasible_background"})
            continue

        evidence = None
        if family["design_type"] == "matrix_interference":
            evidence = line_evidence(family["target"], family["interferent"])

        variant_ids = []
        for variant, controlled in built:
            role = variant["role"]
            candidate_id = f"{family['family_id']}_{role.upper()}"
            variant_ids.append(candidate_id)
            sample = {
                "id": candidate_id,
                "composition_percent": controlled["composition"],
                "provenance": {
                    "schema": SCHEMA,
                    "candidate_id": candidate_id,
                    "member": "B",
                    "design_family_id": family["family_id"],
                    "variant_id": role,
                    "design_type": family["design_type"],
                    "matrix_class": family["matrix_type"],
                    "target_element": family["target"],
                    "interferent_element": family["interferent"],
                    "control_role": role,
                    "controlled_element_ppm": {
                        k: round(float(v) * 10000.0, 9) for k, v in variant["controls"].items()},
                    "candidate_design_seed": candidate_seed(candidate_id) % (2 ** 31),
                    "candidate_background_attempt": background["attempt"],
                    "production_noise_seed": None,
                    "production_condition": None,
                    "original_recipe": background["original_recipe"],
                    "original_composition_percent": background["original_composition_percent"],
                    "compensation_ledger": controlled["ledger"],
                    "line_interference_evidence": evidence,
                    "lineage": {
                        "kind": "synthetic_round4_family_background",
                        "parent_family": family["family_id"],
                        "background_seed": background["seed"],
                        "background_attempt": background["attempt"],
                        "background_composition_sha256": hashlib.sha256(
                            canonical(background["original_composition_percent"]).encode("utf-8")
                        ).hexdigest(),
                    },
                    "historical_source": "none_known_in_registered_history",
                    "historical_exposure": "new_round4_design_not_in_history",
                    "nearest_historical_L1_percentage_points": None,
                    "historical_train_only_constraint_pending": True,
                    "requested_role": family["nominal_role"],
                    "global_role_status": "pending_global_freeze",
                    "eligible_for_training": False,
                    "input_source_manifest_sha256": None,
                },
            }
            samples.append(sample)

        family_rows.append({
            "schema": "round4-B-candidate-family/1",
            "design_family_id": family["family_id"],
            "member": "B",
            "design_type": family["design_type"],
            "matrix_class": family["matrix_type"],
            "scenario": family["scenario"],
            "target_element": family["target"],
            "interferent_element": family["interferent"],
            "requested_role": family["nominal_role"],
            "global_role_status": "pending_global_freeze",
            "variant_ids": variant_ids,
            "recipe_count": len(variant_ids),
            "spectra_target_per_recipe": 20,
            "background_seed": background["seed"],
            "background_attempt": background["attempt"],
            "line_interference_evidence": evidence,
            "original_recipe": background["original_recipe"],
            "original_composition_percent": background["original_composition_percent"],
        })
    return samples, family_rows, {"pairs": pairs, "dropped": dropped, "specs": specs}


# ---------------------------------------------------------------------- history
def load_history() -> tuple[list[dict], dict]:
    history = read_json(INPUTS / "historical_compositions.json")
    rows = [{"id": row["id"], "composition": row["composition_percent"],
             "source": row["id"].split("/")[0]} for row in history["rows"]]
    round3 = []
    for member in ("A", "B", "C", "D"):
        candidates = [ROOT / f"datasets/round3/member_{member}/candidates/{member}_samples.json",
                      ROOT / f"datasets/round3/member_{member}/candidates_v1/{member}_samples.json"]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            continue
        for row in read_json(path)["samples"]:
            rows.append({"id": row["id"], "composition": row["composition_percent"],
                         "source": f"round3_{member}"})
            round3.append(member)
    return rows, {
        "history_rows": len(history["rows"]),
        "history_sources": len(history.get("sources", [])),
        "round3_candidate_rows": len(round3),
        "round3_members": sorted(set(round3)),
    }


def to_matrix(rows: list[dict], elements: list[str]) -> np.ndarray:
    def composition_of(row: dict) -> dict:
        return row.get("composition_percent", row.get("composition", {}))
    return np.array([[float(composition_of(s).get(e, 0.0)) for e in elements] for s in rows],
                    dtype=float)


def nearest_rows(samples: list[dict], history: list[dict]) -> tuple[list[dict], list[dict], float]:
    elements = sorted({e for s in samples for e in s["composition_percent"]} |
                      {e for h in history for e in h["composition"]})
    mine = to_matrix(samples, elements)
    theirs = to_matrix(history, elements)
    distances = cdist(mine, theirs, metric="cityblock")
    per_sample, per_family = [], []
    seen = set()
    for index, sample in enumerate(samples):
        column = int(np.argmin(distances[index]))
        value = float(distances[index, column])
        family = sample["provenance"]["design_family_id"]
        per_sample.append({
            "candidate_id": sample["id"],
            "family_id": family,
            "design_type": sample["provenance"]["design_type"],
            "nearest_history_id": history[column]["id"],
            "nearest_history_source": history[column]["source"],
            "l1_percentage_points": value,
        })
        if family not in seen:
            seen.add(family)
            per_family.append({
                "family_id": family,
                "nearest_history_id": history[column]["id"],
                "l1_percentage_points": value,
            })
    return per_sample, per_family, float(distances.min())


def cross_family_edges(samples: list[dict]) -> list[dict]:
    elements = sorted({e for s in samples for e in s["composition_percent"]})
    matrix = to_matrix(samples, elements)
    family = [s["provenance"]["design_family_id"] for s in samples]
    edges = []
    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            if family[i] == family[j]:
                continue
            value = float(cdist(matrix[i:i + 1], matrix[j:j + 1], metric="cityblock")[0, 0])
            if value <= THRESHOLD_L1:
                edges.append({"candidate_a": samples[i]["id"], "candidate_b": samples[j]["id"],
                              "l1_percentage_points": value})
    return edges


def cross_member_edges(samples: list[dict], paths: list[tuple[str, pathlib.Path]]) -> tuple[list[dict], dict]:
    elements = sorted({e for s in samples for e in s["composition_percent"]})
    mine = to_matrix(samples, elements)
    edges, summary = [], {}
    for member, path in paths:
        relative = str(path.relative_to(ROOT)).replace("\\", "/") if path.is_relative_to(ROOT) else str(path)
        if not path.exists():
            summary[member] = {"path": relative, "status": "not_available_in_workspace"}
            continue
        other = read_json(path)["samples"]
        wide = sorted({e for s in other for e in s["composition_percent"]} | set(elements))
        distances = cdist(to_matrix(samples, wide), to_matrix(other, wide), metric="cityblock")
        other_keys = {canonical(s["composition_percent"]) for s in other}
        exact = sum(1 for s in samples if canonical(s["composition_percent"]) in other_keys)
        for i, j in zip(*np.nonzero(distances <= THRESHOLD_L1)):
            edges.append({"member": member, "candidate_a": samples[i]["id"],
                          "other_id": other[j]["id"],
                          "l1_percentage_points": float(distances[i, j])})
        summary[member] = {
            "path": relative,
            "other_candidate_count": len(other),
            "minimum_L1_percentage_points": float(distances.min()),
            "pairs_at_0_5pp": int((distances <= THRESHOLD_L1).sum()),
            "exact_composition_matches": exact,
            "status": "pairwise_screen_only; global four-member closure pending",
        }
    return edges, summary


# ---------------------------------------------------------------------- checks
def coverage(samples: list[dict]) -> dict:
    per_element = {}
    for element in TARGET_ELEMENTS:
        values = [s["composition_percent"].get(element, 0.0) for s in samples]
        positive = [v for v in values if v > 0]
        per_element[element] = {
            "records": len(values),
            "positive_records": len(positive),
            "zero_records": len(values) - len(positive),
            "min_percent": min(values),
            "max_percent": max(values),
            "median_positive_percent": float(np.median(positive)) if positive else 0.0,
        }
    by_type = collections.Counter(s["provenance"]["design_type"] for s in samples)
    return {
        "schema": "round4-B-candidate-coverage/1",
        "per_element": per_element,
        "design_type_counts": dict(by_type),
        "matrix_counts": dict(collections.Counter(s["provenance"]["matrix_class"] for s in samples)),
        "requested_role_counts": dict(collections.Counter(
            s["provenance"]["requested_role"] for s in samples)),
    }


def write_csv(path: pathlib.Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def readme_text(checks: dict) -> str:
    lines = [
        "B 部分候选配方 v1",
        "",
        "状态：B 本地候选校核已完成；尚未完成 A/C/D 汇总、全局亲缘闭环、最终用途/阶段分配或生产冻结。此目录中的内容是组成候选，不是能谱数据。",
        "",
        "本次候选规模",
        f"{checks['candidate_count']} 个唯一组成，{checks['design_family_count_before_global_merge']} 个合并前设计族。",
        "元素梯度：40 族 × 10 个配方 = 400。",
        "零/加标配对：40 族 × 5 个配方 = 200（1 个真零 + 4 个正水平）。",
        "矩阵干扰控制：40 族 × 5 个配方 = 200（目标零/低 × 干扰低/高 的配对设计）。",
        "常规覆盖：200 族 × 1 个配方 = 200。",
        "基体按硅酸盐/氧化物与富铁氧化物各半配置：500 / 500 个配方。",
        "名义用途预算（仅候选阶段，A 全局冻结后才生效）：训练 800、验证 100、封存测试 100 个配方；对应 256/32/32 个完整族。",
        "",
        "每个配方记录完整 used composition、原始氧化物/痕量背景（original_recipe）、换算结果、受控元素值（ppm）、移除/加入的载体、未受控部分的整体缩放因子和逐元素差值。B 的主题是重叠峰与吸收/增强干扰：V/Cr、Mn/Fe、Co/Ni、As/Pb 等组合逐族用 xraylib 实际线表核对。真实标签是实际 used_percent，保留完整 32 个目标元素标签与 O 基体闭合。",
        "",
        "干扰控制的线表证据",
        "",
        f"{checks['line_interference_pairs']} 个低含量干扰族全部用 xraylib 实际线表核对：目标元素线与干扰元素线在 {checks['line_window_eV']:.0f} eV 候选能窗内的最近组合逐族记录线名、能量、RadRate 和差值（每族同时写入 B_samples.json 的 line_interference_evidence 与 line_interference_evidence.csv）。能窗是候选筛选假设，不是已冻结的第四轮探测器响应或公共 profile；最终能窗和响应须由 A 的公共范围/条件冻结确认。",
        "",
        "历史近邻边界",
        "",
        f"候选与第三轮 A 输入表中的第一/二轮已知历史组成（3,800 条）以及仓库中第三轮 A/B/C/D 候选组成（{checks['round3_candidate_rows']} 条）比较 L1 距离。nearest_history.csv 与 original_background_nearest_history.csv 保存逐条近邻。最小候选—历史 L1 为 {checks['distance_summary']['candidate_to_history_min_L1_pp']:.4f} 个百分点；≤0.5 连接 {checks['distance_summary']['candidate_history_links_at_0_5pp']} 条；B 候选跨设计族 ≤0.5 近邻边 {checks['distance_summary']['cross_family_candidate_edges_at_0_5pp']} 条。",
    ]
    for member, block in checks.get("cross_member_round4", {}).items():
        if block.get("status", "").startswith("not_available"):
            lines.append(f"与第四轮 {member} 候选的逐对比较：当前工作区没有该成员样本文件，登记为 pending，不能声称已比对。")
        else:
            lines.append(
                f"与第四轮 {member} 的 {block['other_candidate_count']} 个候选做逐对比较："
                f"最小 L1 {block['minimum_L1_percentage_points']:.4f} 个百分点，"
                f"≤0.5 对 {block['pairs_at_0_5pp']} 个，精确重复 {block['exact_composition_matches']} 个。")
    lines += [
        "",
        "所有候选的 requested_role 只是 train_nominal/validation_nominal/sealed_test_nominal 预算，global_role_status 仍为 pending_global_freeze；没有最终 train/test 分配、条件实例、生产噪声种子或训练资格。候选设计种子仅用于可复现地构造配方，不是测谱噪声子种子或批量生成种子。",
        "",
        "下一步与生产口径",
        "",
        "当前生产被前置条件阻塞：A 尚未发布第四轮公共范围、条件/profile、freeze_v1 和完整生产 release，仓库状态仍为 usable_for_generation=false、production_started=false。因此本目录不含运行器、条件实例、噪声种子或能谱，也不能复用第三轮命令出谱。",
        "",
        "B 不安排 400 谱试片。待 A 的公共冻结和完整生产 release 通过后，按冻结 release 一次生成全部 20,000 条谱（1,000 配方 × 10 个真实条件 × 2 个独立计数噪声），随后做一次全量 audit/replay/QC，再打包交付。封存部分保持 eligible_for_training=false。",
        "",
        "复核与重建",
        "",
        "在协作仓库根目录执行：",
        "",
        "```powershell",
        "python datasets/round4/member_B/build_candidates.py",
        "python datasets/round4/member_B/verify_candidates.py",
        "```",
        "",
        "build_candidates.py 默认拒绝覆盖已有输出。verify_candidates.py 独立检查数量、闭合、补偿重建、范围、名义用途计数、线表证据、历史距离和交付哈希，并写出 independent_verification.json。当前没有可执行的第四轮生产命令；本目录不含任何能谱。",
        "",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------------ main
def main() -> int:
    parser = argparse.ArgumentParser(description="Build B round-four composition candidates")
    parser.add_argument("--out", default=str(HERE / "candidates"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    out = pathlib.Path(args.out)
    if out.exists() and any(out.iterdir()) and not args.force:
        raise SystemExit(f"refusing to overwrite non-empty {out}")
    out.mkdir(parents=True, exist_ok=True)

    samples, families, meta = build()
    specs = meta["specs"]
    history, history_meta = load_history()
    nearest, family_nearest, history_min = nearest_rows(samples, history)
    by_id = {row["candidate_id"]: row for row in nearest}
    for sample in samples:
        sample["provenance"]["nearest_historical_L1_percentage_points"] = round(
            by_id[sample["id"]]["l1_percentage_points"], 9)

    family_edges = cross_family_edges(samples)
    member_paths = [
        ("A", ROOT / "datasets/round4/member_A/candidates_v1/A_samples.json"),
        ("C", ROOT / "datasets/round4/member_C/candidates/C_samples.json"),
        ("D", ROOT / "datasets/round4/member_D/candidates/D_samples.json"),
    ]
    member_edges, member_summary = cross_member_edges(samples, member_paths)

    zero_controlled = sum(
        1 for s in samples for value in s["provenance"]["controlled_element_ppm"].values()
        if value == 0.0)
    zero_conflicts = sum(
        1 for s in samples
        for element, value in s["provenance"]["controlled_element_ppm"].items()
        if value == 0.0 and s["composition_percent"].get(element, 0.0) != 0.0)
    zero_entries = sum(1 for s in samples for v in s["composition_percent"].values() if v == 0.0)

    role_recipes = collections.Counter()
    role_families = collections.Counter()
    for family in families:
        role_families[family["requested_role"]] += 1
        role_recipes[family["requested_role"]] += family["recipe_count"]

    distance_summary = {
        "candidate_to_history_min_L1_pp": history_min,
        "background_to_history_min_L1_pp": min(r["l1_percentage_points"] for r in family_nearest),
        "candidate_history_links_at_0_5pp": sum(1 for r in nearest
                                                if r["l1_percentage_points"] <= THRESHOLD_L1),
        "background_history_links_at_0_5pp": sum(1 for r in family_nearest
                                                 if r["l1_percentage_points"] <= THRESHOLD_L1),
        "cross_family_candidate_edges_at_0_5pp": len(family_edges),
    }

    checks = {
        "schema": "round4-B-candidate-checks/1",
        "status": "failed_B_local_candidate_checks" if zero_conflicts else "passed_B_local_candidate_checks",
        "errors": [f"{zero_conflicts} zero-label conflicts"] if zero_conflicts else [],
        "candidate_count": len(samples),
        "design_family_count_before_global_merge": len(families),
        "category_counts": dict(collections.Counter(s["provenance"]["design_type"] for s in samples)),
        "matrix_counts": dict(collections.Counter(s["provenance"]["matrix_class"] for s in samples)),
        "nominal_role_recipe_counts": dict(role_recipes),
        "nominal_role_family_counts": dict(role_families),
        "variants": {
            "element_gradient": "ten strictly increasing positive levels spanning trace to major",
            "zero_spike": "one true zero plus four distinct positive levels near detection thresholds",
            "matrix_interference": "five paired target/interferent controls with xraylib line-table evidence",
            "routine_coverage": "one composition per family",
        },
        "line_interference_pairs": len(meta["pairs"]),
        "line_window_eV": LINE_WINDOW_EV,
        "line_evidence_file": "line_interference_evidence.csv",
        "line_window_status": "candidate_screen_only; detector profile and public round4 energy window not frozen",
        "matrix_status": "draft_50_50_silicate_iron; requires Round4 public scope review",
        "exact_zero_labels_verified": zero_entries,
        "controlled_zero_labels": zero_controlled,
        "exact_zero_label_conflicts": zero_conflicts,
        "historical_rows_compared": len(history),
        "historical_source_count": len(history_meta["round3_members"]) + history_meta["history_sources"],
        "round3_candidate_rows": history_meta["round3_candidate_rows"],
        "historical_nearest_threshold_L1_percentage_points": THRESHOLD_L1,
        "distance_summary": distance_summary,
        "cross_member_round4": member_summary,
        "cross_member_confirmation": "pending_A_global_closure_with_B_C_D_round4_candidates",
        "global_family_closure": "pending_all_round4_candidates_and_round1_2_3_history",
        "role_and_stage_assignments": "pending_global_freeze",
        "production_started": False,
        "spectra_generated": 0,
        "noise_seeds_allocated": False,
        "eligible_for_training": False,
        "scientific_accuracy_validated": False,
        "range_status": "draft_using_round3_validated_ranges; requires Round4 public scope review and global freeze",
        "round3_candidate_source_mode": "repository_tree",
        "dropped_records": meta["dropped"],
    }

    source_manifest = {
        "schema": "round4-B-candidate-source-manifest/1",
        "status": "candidate_inputs_only_not_production_freeze",
        "inputs": [
            {"path": "datasets/round3/member_A/inputs/design_ranges.json",
             "sha256": sha256(INPUTS / "design_ranges.json"),
             "bytes": (INPUTS / "design_ranges.json").stat().st_size,
             "role": "Round3 A validated starting ranges; Round4 range proposal only"},
            {"path": "datasets/round3/member_A/inputs/historical_compositions.json",
             "sha256": sha256(INPUTS / "historical_compositions.json"),
             "bytes": (INPUTS / "historical_compositions.json").stat().st_size,
             "records": history_meta["history_rows"],
             "role": "Round1/2 historical composition table with its embedded source list"},
            {"path": "datasets/round3/member_A/inputs/generator/fp_competition/core.py",
             "sha256": sha256(GENERATOR / "fp_competition/core.py"),
             "bytes": (GENERATOR / "fp_competition/core.py").stat().st_size,
             "role": "Round3 frozen composition conversion source"},
            {"path": "datasets/round3/member_A/inputs/generator/fp_competition/minerals.py",
             "sha256": sha256(GENERATOR / "fp_competition/minerals.py"),
             "bytes": (GENERATOR / "fp_competition/minerals.py").stat().st_size,
             "role": "Round3 frozen range sampler source"},
            {"path": "datasets/round3/member_A/inputs/generator/fp_competition/version.py",
             "sha256": sha256(GENERATOR / "fp_competition/version.py"),
             "bytes": (GENERATOR / "fp_competition/version.py").stat().st_size,
             "role": "Frozen generator version identity"},
        ],
        "coverage_limit": "Known Round1/2 history from the Round3 A input table plus all four Round3 shared candidate registries. Does not prove absence of undocumented material ancestry.",
    }
    for member in ("A", "C", "D"):
        path = dict(member_paths)[member]
        if path.exists():
            source_manifest["inputs"].append({
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "role": f"Round4 {member} candidate recipes for the pairwise B-vs-{member} screen; not a role or family freeze",
            })
    write_json(out / "source_manifest.json", source_manifest)
    manifest_sha = sha256(out / "source_manifest.json")
    for sample in samples:
        sample["provenance"]["input_source_manifest_sha256"] = manifest_sha

    write_json(out / "B_samples.json", {
        "schema": SCHEMA,
        "round_id": "round4",
        "member": "B",
        "status": "candidate_compositions_only_not_production",
        "production_started": False,
        "eligible_for_training": False,
        "spectra_generated": 0,
        "noise_seeds_allocated": False,
        "samples": samples,
    })

    registry_rows = []
    for sample in samples:
        provenance = sample["provenance"]
        registry_rows.append({
            "candidate_id": sample["id"],
            "member": "B",
            "design_family_id": provenance["design_family_id"],
            "parent_family_id": provenance["design_family_id"],
            "design_type": provenance["design_type"],
            "variant_id": provenance["variant_id"],
            "matrix_class": provenance["matrix_class"],
            "composition_used_json": canonical(sample["composition_percent"]),
            "original_composition_json": canonical(provenance["original_composition_percent"]),
            "compensation_ledger_json": json.dumps(provenance["compensation_ledger"],
                                                   ensure_ascii=False, sort_keys=True,
                                                   separators=(",", ":")),
            "historical_source_id": "",
            "historical_exposure": provenance["historical_exposure"],
            "requested_role": provenance["requested_role"],
            "global_role_status": provenance["global_role_status"],
        })
    write_csv(out / "candidate_registry.csv", REGISTRY_FIELDS, registry_rows)

    write_json(out / "family_registry.json", {
        "schema": "round4-B-candidate-family-registry/1",
        "status": "candidate_only_not_global_freeze",
        "design_families": families,
    })
    write_json(out / "coverage.json", coverage(samples))
    write_csv(out / "nearest_history.csv",
              ["candidate_id", "family_id", "design_type", "nearest_history_id",
               "nearest_history_source", "l1_percentage_points"], nearest)
    write_csv(out / "original_background_nearest_history.csv",
              ["family_id", "nearest_history_id", "l1_percentage_points"], family_nearest)
    write_csv(out / "cross_family_near_edges.csv",
              ["candidate_a", "candidate_b", "l1_percentage_points"], family_edges)
    write_csv(out / "cross_member_near_edges.csv",
              ["member", "candidate_a", "other_id", "l1_percentage_points"], member_edges)

    evidence_rows = []
    for family in families:
        block = family.get("line_interference_evidence")
        if not block:
            continue
        evidence_rows.append({
            "family_id": family["design_family_id"],
            "target": block["target_element"],
            "interferent": block["interferent_element"],
            "matrix_class": family["matrix_class"],
            "window_eV": block["window_eV"],
            "target_line": block["target_line"],
            "target_energy_eV": block["target_line_energy_eV"],
            "target_rad_rate": block["target_rad_rate"],
            "interferent_line": block["interferent_line"],
            "interferent_energy_eV": block["interferent_line_energy_eV"],
            "interferent_rad_rate": block["interferent_rad_rate"],
            "delta_eV": block["delta_eV"],
            "verdict": block["mechanism"],
            "note": block["status"],
        })
    write_csv(out / "line_interference_evidence.csv",
              ["family_id", "target", "interferent", "matrix_class", "window_eV",
               "target_line", "target_energy_eV", "target_rad_rate",
               "interferent_line", "interferent_energy_eV", "interferent_rad_rate",
               "delta_eV", "verdict", "note"], evidence_rows)

    write_json(out / "candidate_checks.json", checks)
    write_json(out / "input_identity.json", {
        "schema": "round4-B-candidate-input-identity/1",
        "member": "B",
        "builder_sha256": sha256(HERE / "build_candidates.py"),
        "source_manifest_sha256": manifest_sha,
        "generator_version": GENERATOR_VERSION,
        "candidate_rng": "sha256-derived NumPy default_rng seed; candidate-design-only, not production or spectrum noise",
        "noise_seeds_allocated": False,
        "range_status": "draft_using_round3_validated_ranges; requires Round4 public scope review and global freeze",
        "historical_archive": {
            "path": "datasets/round3/member_A/inputs/historical_compositions.json",
            "sha256": sha256(INPUTS / "historical_compositions.json"),
            "bytes": (INPUTS / "historical_compositions.json").stat().st_size,
            "status": "available_historical_evidence_snapshot",
            "coverage_limit": "Accepted round2 plus known local round1 candidate/pilot/research records; undocumented or unavailable lineage cannot be ruled out.",
        },
        "spectra_generated": 0,
        "production_started": False,
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "xraylib": getattr(xl, "__version__", "unknown"),
        },
    })
    (out / "README.md").write_text(readme_text(checks), encoding="utf-8")

    files = []
    for path in sorted(out.iterdir()):
        if path.name in ("delivery_manifest.json", "independent_verification.json"):
            continue
        files.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json(out / "delivery_manifest.json", {
        "schema": "round4-B-candidate-delivery/1",
        "status": "candidate_only_not_production_release",
        "member": "B",
        "round_id": "round4",
        "candidate_count": len(samples),
        "design_family_count_before_global_merge": len(families),
        "production_started": False,
        "eligible_for_training": False,
        "files": files,
    })

    print(json.dumps({
        "candidates": len(samples),
        "families": len(families),
        "categories": checks["category_counts"],
        "matrices": checks["matrix_counts"],
        "roles": checks["nominal_role_recipe_counts"],
        "controlled_zero_labels": zero_controlled,
        "zero_entries": zero_entries,
        "history_min_L1_pp": round(history_min, 4),
        "cross_member": {k: v.get("minimum_L1_percentage_points") for k, v in member_summary.items()},
        "dropped": len(meta["dropped"]),
        "out": str(out),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
