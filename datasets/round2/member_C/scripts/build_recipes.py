# -*- coding: utf-8 -*-
"""Round-2 Member C recipe builder.

250 independent recipes:
  - silicate/oxide   150 = 90 routine / 30 sparse-boundary / 30 interference
  - iron-rich oxide  100 = 60 routine / 20 sparse-boundary / 20 interference

Constructions are element-mass-percent, strictly closed to 100.00000000 at 1e-8
granularity (well inside the 1e-6-pp acceptance tolerance).  Every recipe keeps
its full matrix (including O) and a provenance ledger recording the original
compound percents and element ppm -> percent conversions.

Deterministic: a single design seed drives all random draws (rng = SeedSequence).
"""
import json
import hashlib
from decimal import Decimal
from pathlib import Path

import numpy as np
import xraylib

DESIGN_SEED = 2026102101          # recipe-sampling design seed (member C, round 2)
OWNER = "C"
ROUND_ID = "round2"
N_PLACES = 8                       # closure granularity, 1e-8 weight percent

TARGETS = ["Na", "Mg", "Al", "Si", "P", "S", "Cl", "K", "Ca", "Ti", "V", "Cr",
           "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "As", "Se", "Rb", "Sr", "Y", "Zr",
           "Nb", "Mo", "Cd", "Sn", "Sb", "Ba", "W", "Pb"]

AW = {  # IUPAC 2021 conventional standard atomic weights (g/mol)
    "H": 1.008, "C": 12.011, "O": 15.999, "Na": 22.98976928, "Mg": 24.305,
    "Al": 26.9815385, "Si": 28.085, "P": 30.973761998, "S": 32.06,
    "Cl": 35.45, "K": 39.0983, "Ca": 40.078, "Ti": 47.867, "V": 50.9415,
    "Cr": 51.9961, "Mn": 54.938044, "Fe": 55.845, "Co": 58.9331948,
    "Ni": 58.6934, "Cu": 63.546, "Zn": 65.38, "As": 74.921595,
    "Se": 78.971, "Rb": 85.4678, "Sr": 87.62, "Y": 88.90584, "Zr": 91.224,
    "Nb": 92.906372, "Mo": 95.95, "Cd": 112.414, "Sn": 118.71, "Sb": 121.76,
    "Ba": 137.327, "W": 183.84, "Pb": 207.2}


def el_masses(formula):
    """Element mass fractions of a compound, from atomic weights."""
    import re
    counts, i = {}, 0
    for m in re.finditer(r"([A-Z][a-z]?)(\d*)", formula):
        if m.group(1):
            counts[m.group(1)] = counts.get(m.group(1), 0) + int(m.group(2) or 1)
    total = sum(AW[e] * n for e, n in counts.items())
    return {e: AW[e] * n / total for e, n in counts.items()}

COMPOUNDS = {k: el_masses(k) for k in [
    "SiO2", "Al2O3", "Fe2O3", "FeO", "MgO", "CaO", "Na2O", "K2O", "TiO2",
    "MnO", "Cr2O3", "V2O5", "P2O5", "CaCO3", "MgCO3", "FeCO3", "NaCl", "KCl",
    "CaSO4", "NiO", "CoO", "CuO", "PbO", "As2O5", "SeO2", "SrO", "BaO", "WO3",
    "CdO", "SnO2", "Sb2O5", "Y2O3", "Nb2O5", "MoO3", "Rb2O", "ZrO2", "FeS2"]}


def q(name, *args):
    return {"name": name, "args": args}

# ---------------------------------------------------------------- families ---
# Each family: template of compounds with per-arg range tuples (min,max).
# Balance compound absorbs the rounding residual so the compound sum is exact.
SIL_FAMILIES = {
    "quartz-arenite": dict(compounds=[("SiO2", 74, 95), ("Al2O3", 1, 8),
        ("Fe2O3", 0.2, 3), ("K2O", 0.5, 4), ("Na2O", 0.2, 3), ("CaO", 0.1, 4),
        ("MgO", 0.1, 2), ("TiO2", 0.05, 1.2)], balance="SiO2"),
    "granite": dict(compounds=[("SiO2", 66, 76), ("Al2O3", 11, 15.5),
        ("Fe2O3", 1, 4.5), ("CaO", 0.5, 3), ("Na2O", 2, 4.5), ("K2O", 2.5, 5.5),
        ("MgO", 0.2, 1.6), ("TiO2", 0.1, 0.9)], balance="SiO2"),
    "granodiorite": dict(compounds=[("SiO2", 62, 70), ("Al2O3", 13, 17),
        ("Fe2O3", 1.5, 5), ("CaO", 2, 6), ("Na2O", 2, 4.5), ("K2O", 0.8, 3),
        ("MgO", 0.5, 2.5), ("TiO2", 0.3, 1.4)], balance="SiO2"),
    "diorite-basalt": dict(compounds=[("SiO2", 45, 56), ("Al2O3", 12, 18),
        ("Fe2O3", 8, 18), ("CaO", 6, 12), ("MgO", 3, 11), ("Na2O", 0.5, 4),
        ("K2O", 0.05, 2), ("TiO2", 0.5, 4)], balance="SiO2"),
    "andesite": dict(compounds=[("SiO2", 54, 64), ("Al2O3", 13, 19),
        ("Fe2O3", 3, 9), ("CaO", 3, 8), ("MgO", 1, 6), ("Na2O", 1.5, 5),
        ("K2O", 0.3, 3.5), ("TiO2", 0.4, 2.4)], balance="SiO2"),
    "kaolinite-clay": dict(compounds=[("SiO2", 43, 55), ("Al2O3", 25, 36),
        ("Fe2O3", 0.2, 4), ("TiO2", 0.1, 1.5), ("CaO", 0.05, 2.5),
        ("MgO", 0.05, 2), ("K2O", 0.1, 2.5), ("Na2O", 0.05, 1.5)], balance="SiO2"),
    "illite-clay": dict(compounds=[("SiO2", 50, 62), ("Al2O3", 18, 28),
        ("Fe2O3", 3, 10), ("K2O", 4, 10), ("MgO", 0.8, 3.5), ("CaO", 0.2, 3),
        ("Na2O", 0.1, 1.5), ("TiO2", 0.3, 1.6)], balance="SiO2"),
    "montmorillonite": dict(compounds=[("SiO2", 52, 64), ("Al2O3", 17, 27),
        ("Fe2O3", 1.5, 8), ("MgO", 1.5, 6), ("CaO", 0.5, 4), ("Na2O", 0.3, 3),
        ("K2O", 0.1, 1.2), ("TiO2", 0.1, 1)], balance="SiO2"),
    "limestone": dict(compounds=[("CaCO3", 72, 95), ("SiO2", 0.3, 12),
        ("Al2O3", 0.05, 3), ("Fe2O3", 0.05, 2.5), ("MgCO3", 0.1, 6),
        ("CaSO4", 0.02, 2), ("TiO2", 0.01, 0.5), ("K2O", 0.01, 0.8)],
        balance="CaCO3"),
    "dolomite-marl": dict(compounds=[("CaCO3", 40, 68), ("MgCO3", 18, 40),
        ("SiO2", 0.5, 14), ("Al2O3", 0.05, 4), ("Fe2O3", 0.05, 3),
        ("CaSO4", 0.02, 2.5), ("NaCl", 0.01, 1.2), ("TiO2", 0.01, 0.7)],
        balance="CaCO3"),
    "bauxite": dict(compounds=[("Al2O3", 44, 68), ("SiO2", 1, 14),
        ("Fe2O3", 2, 25), ("TiO2", 1, 5), ("CaCO3", 0.1, 3), ("MgCO3", 0.05, 1.5),
        ("K2O", 0.02, 0.8), ("Na2O", 0.02, 0.8)], balance="Al2O3"),
    "laterite-residual": dict(compounds=[("Fe2O3", 30, 62), ("Al2O3", 8, 30),
        ("SiO2", 3, 28), ("TiO2", 0.8, 5), ("MgO", 0.05, 2), ("CaO", 0.05, 2.5),
        ("K2O", 0.02, 1), ("Na2O", 0.02, 1)], balance="Fe2O3"),
    "feldspar-arkose": dict(compounds=[("SiO2", 55, 78), ("Al2O3", 9, 16),
        ("Na2O", 2, 8), ("K2O", 2, 9), ("CaO", 0.5, 5), ("Fe2O3", 0.5, 6),
        ("MgO", 0.1, 2), ("TiO2", 0.1, 1.4)], balance="SiO2"),
    "gneiss-mica-schist": dict(compounds=[("SiO2", 58, 72), ("Al2O3", 12, 22),
        ("Fe2O3", 2, 12), ("K2O", 2, 8), ("MgO", 0.4, 6), ("CaO", 0.2, 5),
        ("Na2O", 0.3, 4), ("TiO2", 0.2, 2.2)], balance="SiO2"),
}

FE_FAMILIES = {
    "hematite-magnetite": dict(compounds=[("Fe2O3", 55, 88), ("SiO2", 1, 18),
        ("Al2O3", 0.3, 8), ("CaO", 0.05, 4), ("MgO", 0.05, 3), ("TiO2", 0.1, 5),
        ("MnO", 0.02, 2.5), ("K2O", 0.01, 1)], balance="Fe2O3"),
    "goethite-limonite": dict(compounds=[("Fe2O3", 48, 72), ("SiO2", 3, 25),
        ("Al2O3", 1, 10), ("CaCO3", 0.1, 6), ("MgO", 0.05, 2.5),
        ("P2O5", 0.02, 1.5), ("TiO2", 0.1, 2), ("K2O", 0.02, 1.2)],
        balance="Fe2O3"),
    "carbonate-siderite-ox": dict(compounds=[("Fe2O3", 38, 66), ("FeCO3", 8, 34),
        ("CaCO3", 2, 16), ("MgCO3", 0.5, 8), ("SiO2", 0.5, 9), ("Al2O3", 0.2, 4),
        ("MnO", 0.1, 3.5), ("CaSO4", 0.02, 1.5)], balance="Fe2O3"),
    "fe-ti-oxide": dict(compounds=[("Fe2O3", 45, 70), ("TiO2", 6, 22),
        ("SiO2", 1, 12), ("Al2O3", 0.5, 7), ("MgO", 0.2, 4), ("CaO", 0.1, 4),
        ("Cr2O3", 0.02, 2), ("V2O5", 0.01, 1.4)], balance="Fe2O3"),
    "manganese-iron": dict(compounds=[("Fe2O3", 30, 62), ("MnO", 12, 38),
        ("SiO2", 1, 12), ("Al2O3", 0.5, 7), ("CaO", 0.2, 6), ("MgO", 0.2, 5),
        ("FeCO3", 0.5, 8), ("K2O", 0.02, 1.4)], balance="MnO"),
    "ni-laterite": dict(compounds=[("Fe2O3", 22, 48), ("SiO2", 18, 40),
        ("Al2O3", 2, 12), ("MgO", 4, 16), ("NiO", 0.8, 4.5), ("CoO", 0.02, 0.8),
        ("Cr2O3", 0.05, 1.6), ("CaO", 0.05, 2)], balance="SiO2"),
    "chromite-sand": dict(compounds=[("Fe2O3", 30, 55), ("Cr2O3", 18, 42),
        ("Al2O3", 4, 14), ("MgO", 2, 12), ("SiO2", 1, 10), ("TiO2", 0.3, 4),
        ("V2O5", 0.05, 2.2), ("CaO", 0.05, 2)], balance="Cr2O3"),
    "fe-skarn-mixed": dict(compounds=[("Fe2O3", 30, 58), ("CaCO3", 12, 30),
        ("SiO2", 8, 26), ("Al2O3", 0.5, 6), ("MgCO3", 0.5, 8), ("MnO", 0.1, 3),
        ("Na2O", 0.05, 2), ("K2O", 0.02, 1.5)], balance="Fe2O3"),
}

# trace spike element pools (ppm) per matrix class
SIL_TRACE_POOL = ["V", "Cr", "Ni", "Cu", "Zn", "As", "Se", "Rb", "Sr", "Y",
                  "Zr", "Nb", "Mo", "Cd", "Sn", "Sb", "Ba", "W", "Pb", "P",
                  "S", "Cl", "Co"]
FE_TRACE_POOL = ["Zn", "Cu", "Ni", "Co", "Cr", "V", "As", "Se", "Pb", "Cd",
                 "Sn", "Sb", "Ba", "W", "Sr", "Y", "Zr", "Nb", "Mo", "Rb",
                 "P", "S"]

# interference pairs: (elemA, elemB, note) -- classic spectral overlaps
PAIRS = [
    ("As", "Pb", "As Ka 10.544 / Pb La 10.551"),
    ("Ti", "Ba", "Ti Ka 4.511 / Ba La 4.466"),
    ("P", "Zr", "P Ka 2.013 / Zr La 2.043"),
    ("Ti", "V", "Ti Kb 4.932 / V Ka 4.952"),
    ("Cr", "Mn", "Cr Kb 5.839 / Mn Ka 5.899"),
    ("Se", "Pb", "Se Kb 12.598 / Pb Lb 12.614"),
    ("W", "Cu", "W La 8.397 / Cu Kb 8.401"),
    ("Sr", "Zr", "Sr Kb 15.688 / Zr Ka 15.775"),
    ("Rb", "Mo", "Rb Ka 13.395 / Mo Lb 17.378? use Rb K vs Mo L region"),
    ("Sn", "Nb", "Sn La 3.444 / Nb L-series low-energy tail"),
]


def sample_family(rng, fam, lo_factor=1.0):
    """Uniform draw of compound percents inside the family ranges."""
    comp = {}
    for name, lo, hi in fam["compounds"]:
        span = (hi - lo) * lo_factor
        c = lo + rng.uniform(0, span) if span > 0 else lo
        comp[name] = c
    total = sum(comp.values())
    return comp, total


def exact_scale(comp, total, target=100.0):
    """Scale compound dict so Decimal sum == target exactly at 1e-N."""
    f = Decimal(target) / Decimal(str(total))
    quant = Decimal(1).scaleb(-N_PLACES)
    out, acc = {}, Decimal(0)
    items = sorted(comp.items(), key=lambda kv: -kv[1])
    for i, (k, v) in enumerate(items):
        if i == len(items) - 1:
            out[k] = (Decimal(target) - acc)
        else:
            x = (Decimal(str(v)) * f).quantize(quant)
            out[k] = x
            acc += x
    return {k: float(v) for k, v in out.items()}


def compound_to_elements(comp):
    els = {}
    for c, w in comp.items():
        for e, fr in COMPOUNDS[c].items():
            els[e] = els.get(e, 0.0) + w * fr
    return els


def add_ppm_spikes(els, spikes):
    """spikes: {element: ppm}. Element percents added; matrix rescaled."""
    add = {e: ppm / 10000.0 for e, ppm in spikes.items()}
    add_total = sum(add.values())
    matrix_total = sum(els.values())
    scale = (100.0 - add_total) / matrix_total
    out = {e: w * scale for e, w in els.items()}
    for e, v in add.items():
        out[e] = out.get(e, 0.0) + v
    return out, scale


def close_exact(els):
    quant = Decimal(1).scaleb(-N_PLACES)
    items = sorted(els.items(), key=lambda kv: -kv[1])
    out, acc = {}, Decimal(0)
    for i, (k, v) in enumerate(items):
        if i == len(items) - 1:
            out[k] = Decimal(100) - acc
            # last entry must stay nonnegative & near target
        else:
            x = Decimal(str(v)).quantize(quant)
            out[k] = x
            acc += x
    total = sum(out.values())
    if abs(total - Decimal(100)) > Decimal("1e-12"):
        raise AssertionError(f"closure fail {total}")
    for v in out.values():
        if v < 0:
            raise AssertionError("negative component")
    return {k: float(v) for k, v in out.items()}


def sha_comp(els):
    s = json.dumps({k: round(v, N_PLACES) for k, v in sorted(els.items())},
                   sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()


def build():
    rng = np.random.default_rng(DESIGN_SEED)
    recipes = []
    seen = set()

    def new_recipe(rid, matrix, fam, scenario, comp, spikes, note=""):
        els = compound_to_elements(comp)
        if spikes:
            els, scale = add_ppm_spikes(els, spikes)
        else:
            scale = None
        els = close_exact(els)
        h = sha_comp(els)
        if h in seen:
            return None
        seen.add(h)
        prov = {
            "round_id": ROUND_ID,
            "owner": OWNER,
            "matrix_type": matrix,
            "parent_family": fam,
            "scenario": scenario,
            "design_seed": DESIGN_SEED,
            "original_compounds_percent": comp,
            "trace_ppm": spikes,
            "ppm_to_percent_rule": "1 ppm = 1e-4 wt% element; matrix rescaled",
            "matrix_rescale_factor": scale,
            "basis": "C 第二轮人工设计配方；不代表实际矿床/牌号分布或认证值",
            "composition_semantic_sha256": h,
            "note": note,
        }
        return {"id": rid, "composition_percent": els, "provenance": prov}

    # ---- silicates: 90 routine ----
    fams = list(SIL_FAMILIES)
    n = 0
    i = 0
    while n < 90:
        fam = SIL_FAMILIES[fams[i % len(fams)]]
        i += 1
        comp, total = sample_family(rng, fam)
        comp = exact_scale(comp, total)
        spikes = {}
        k = rng.integers(3, 10)
        for e in rng.choice(SIL_TRACE_POOL, size=k, replace=False):
            spikes[e] = float(np.round(10 ** rng.uniform(0.3, 3.3), 3))
        r = new_recipe(f"C-S-{n+1:03d}", "silicate-oxide", fams[(i-1) % len(fams)], "routine",
                       comp, spikes)
        if r:
            recipes.append(r)
            n += 1

    # ---- silicates: 30 sparse/boundary ----
    boundaries = [
        ("boundary", "near-pure quartz", {"SiO2": 99.4}, {"Fe": 80, "Al": 120, "Ti": 30}),
        ("boundary", "pure calcite", {"CaCO3": 99.5}, {"Mg": 60, "Sr": 40}),
        ("boundary", "pure dolomite", {"CaCO3": 54.0, "MgCO3": 45.5}, {"Fe": 50}),
        ("boundary", "halite-rich", {"NaCl": 78.0, "CaCO3": 19.0, "SiO2": 2.5}, {"K": 300, "Sr": 20}),
        ("boundary", "Fe-total high", {"Fe2O3": 86.0, "SiO2": 8.0, "Al2O3": 5.0}, {"Ti": 500, "V": 120}),
        ("boundary", "Mg-rich forsteritic", {"MgO": 42.0, "SiO2": 43.0, "Fe2O3": 14.0}, {"Ni": 90, "Cr": 60}),
        ("boundary", "Na-K feldspar endmember", {"Na2O": 11.5, "Al2O3": 18.4, "SiO2": 70.0}, {"K": 400, "Ca": 900}),
        ("boundary", "apatite-rich P high", {"P2O5": 38.0, "CaCO3": 52.0, "SiO2": 9.0}, {"Sr": 800, "Y": 150}),
        ("boundary", "Ti high ilmenite mix", {"TiO2": 42.0, "Fe2O3": 40.0, "SiO2": 17.0}, {"Cr": 120, "V": 400, "Nb": 25}),
        ("sparse", "quartz no traces", {"SiO2": 94.0, "Al2O3": 2.0, "K2O": 1.0, "Fe2O3": 0.6, "TiO2": 0.3, "CaO": 0.4, "MgO": 0.5, "Na2O": 0.4}, {}),
        ("sparse", "kaolinite minimal", {"SiO2": 52.0, "Al2O3": 30.0, "TiO2": 0.8, "Fe2O3": 1.2, "CaO": 0.5, "MgO": 0.8, "K2O": 1.4, "Na2O": 0.7}, {"Zr": 40}),
        ("sparse", "marble minimal", {"CaCO3": 95.0, "SiO2": 2.0, "MgCO3": 1.6, "Al2O3": 0.9, "Fe2O3": 0.5}, {"Sr": 30}),
        ("sparse", "basalt minimal", {"SiO2": 48.0, "Al2O3": 14.0, "Fe2O3": 12.0, "CaO": 10.0, "MgO": 7.0, "Na2O": 2.5, "TiO2": 2.0, "K2O": 0.6}, {}),
        ("sparse", "sandstone clean", {"SiO2": 91.0, "CaCO3": 4.0, "K2O": 1.2, "Al2O3": 2.0, "Fe2O3": 1.0}, {}),
        ("sparse", "bentonite dry", {"SiO2": 60.0, "Al2O3": 18.0, "Fe2O3": 2.0, "MgO": 2.5, "CaO": 3.0, "Na2O": 2.0, "K2O": 1.0, "TiO2": 0.5}, {}),
    ]
    made = 0
    extra_i = 0
    while made < 30:
        if made < len(boundaries):
            kind, name, comp, spikes = boundaries[made]
            tot = sum(comp.values())
            comp = exact_scale(comp, tot)
            r = new_recipe(f"C-S-{90+made+1:03d}", "silicate-oxide",
                           f"boundary-{kind}-{made+1}", "sparse_boundary",
                           comp, spikes, note=name)
        else:
            fam = SIL_FAMILIES[fams[extra_i % len(fams)]]
            extra_i += 1
            comp, total = sample_family(rng, fam, lo_factor=0.15)
            comp = exact_scale(comp, total)
            r = new_recipe(f"C-S-{90+made+1:03d}", "silicate-oxide", fams[(extra_i-1) % len(fams)],
                           "sparse_boundary", comp, {"Rb": float(np.round(10**rng.uniform(0,1.2),3))})
        if r:
            recipes.append(r)
            made += 1

    # ---- silicates: 30 interference ----
    made = 0
    pi = 0
    while made < 30:
        a, b, note = PAIRS[pi % len(PAIRS)]
        pi += 1
        famidx = (made * 7 + 3) % len(SIL_FAMILIES)
        famname = fams[famidx]
        comp, total = sample_family(rng, SIL_FAMILIES[famname])
        comp = exact_scale(comp, total)
        ratio = [0.2, 1.0, 5.0][(made // len(PAIRS)) % 3]
        base = float(np.round(10 ** rng.uniform(1.4, 2.6), 3))  # 25..400 ppm
        spikes = {a: base, b: base * ratio}
        if rng.random() < 0.5:
            spikes[a], spikes[b] = base * ratio, base
        for e in rng.choice([x for x in SIL_TRACE_POOL if x not in (a, b)],
                            size=int(rng.integers(2, 6)), replace=False):
            spikes[e] = float(np.round(10 ** rng.uniform(0.3, 2.3), 3))
        r = new_recipe(f"C-S-{120+made+1:03d}", "silicate-oxide", famname,
                       "interference", comp, spikes, note=f"{a}/{b}: {note}")
        if r:
            recipes.append(r)
            made += 1

    # ---- iron-rich: 60 routine ----
    ffams = list(FE_FAMILIES)
    n = 0
    i = 0
    while n < 60:
        fam = FE_FAMILIES[ffams[i % len(ffams)]]
        i += 1
        comp, total = sample_family(rng, fam)
        comp = exact_scale(comp, total)
        spikes = {}
        for e in rng.choice(FE_TRACE_POOL, size=int(rng.integers(3, 10)), replace=False):
            spikes[e] = float(np.round(10 ** rng.uniform(0.3, 3.1), 3))
        r = new_recipe(f"C-F-{n+1:03d}", "iron-rich-oxide", ffams[(i-1) % len(ffams)], "routine",
                       comp, spikes)
        if r:
            recipes.append(r)
            n += 1

    # ---- iron-rich: 20 sparse/boundary ----
    fe_bound = [
        ("boundary", "hematite endmember", {"Fe2O3": 98.5}, {"Ti": 200, "Al": 1500}),
        ("boundary", "magnetite route FeO rich", {"Fe2O3": 92.0, "MgO": 3.0, "SiO2": 4.0}, {"V": 250}),
        ("boundary", "Fe-Carbonate high", {"FeCO3": 90.0, "CaCO3": 5.0, "MgCO3": 3.0}, {"Mn": 8000}),
        ("boundary", "Fe-Ni laterite extreme", {"SiO2": 40.0, "Fe2O3": 35.0, "MgO": 14.0, "NiO": 6.0}, {"Co": 250, "Cr": 900}),
        ("boundary", "Fe-Cr extreme", {"Fe2O3": 45.0, "Cr2O3": 40.0, "Al2O3": 9.0, "MgO": 5.0}, {"V": 1400}),
        ("boundary", "Fe-Mn extreme", {"Fe2O3": 30.0, "MnO": 60.0, "SiO2": 7.0}, {"Ba": 900, "P": 1200}),
        ("boundary", "Fe-Ti extreme", {"TiO2": 55.0, "Fe2O3": 40.0}, {"Nb": 90, "V": 600}),
        ("boundary", "W-rich ferruginous", {"Fe2O3": 78.0, "SiO2": 14.0, "Al2O3": 6.0}, {"W": 4800, "Sn": 260, "As": 140}),
        ("boundary", "Pb-Zn in Fe matrix", {"Fe2O3": 60.0, "SiO2": 18.0, "CaCO3": 15.0, "MgO": 5.0}, {"Pb": 3200, "Zn": 5100, "Cd": 310, "Ba": 90}),
        ("sparse", "pure hematite", {"Fe2O3": 99.9}, {}),
        ("sparse", "hematite siliceous", {"Fe2O3": 66.0, "SiO2": 33.0}, {}),
        ("sparse", "banded iron formation", {"Fe2O3": 50.0, "SiO2": 47.5, "CaCO3": 2.0}, {}),
        ("sparse", "bog ore simple", {"Fe2O3": 40.0, "CaCO3": 30.0, "SiO2": 26.0, "P2O5": 2.0}, {}),
        ("sparse", "red clay simple", {"Fe2O3": 22.0, "SiO2": 45.0, "Al2O3": 20.0, "CaCO3": 8.0, "MgO": 3.0, "K2O": 2.0}, {}),
    ]
    made = 0
    extra_i = 0
    while made < 20:
        if made < len(fe_bound):
            kind, name, comp, spikes = fe_bound[made]
            comp = exact_scale(comp, sum(comp.values()))
            r = new_recipe(f"C-F-{made+1+60:03d}", "iron-rich-oxide",
                           f"boundary-{kind}-{made+1}", "sparse_boundary",
                           comp, spikes, note=name)
        else:
            fam = FE_FAMILIES[ffams[extra_i % len(ffams)]]
            extra_i += 1
            comp, total = sample_family(rng, fam, lo_factor=0.12)
            comp = exact_scale(comp, total)
            r = new_recipe(f"C-F-{60+made+1:03d}", "iron-rich-oxide",
                           ffams[(extra_i-1) % len(ffams)], "sparse_boundary",
                           comp, {"Cs" and "Zn": 25.0})
        if r:
            recipes.append(r)
            made += 1

    # ---- iron-rich: 20 interference ----
    made = 0
    pi = 0
    while made < 20:
        a, b, note = PAIRS[pi % len(PAIRS)]
        pi += 1
        fam = FE_FAMILIES[ffams[made % len(ffams)]]
        comp, total = sample_family(rng, fam)
        comp = exact_scale(comp, total)
        ratio = [0.25, 1.0, 4.0][(made // len(PAIRS)) % 3]
        base = float(np.round(10 ** rng.uniform(1.5, 2.8), 3))
        spikes = {a: base, b: base * ratio}
        if rng.random() < 0.5:
            spikes[a], spikes[b] = base * ratio, base
        for e in rng.choice([x for x in FE_TRACE_POOL if x not in (a, b)],
                            size=int(rng.integers(2, 7)), replace=False):
            spikes[e] = float(np.round(10 ** rng.uniform(0.3, 2.5), 3))
        r = new_recipe(f"C-F-{80+made+1:03d}", "iron-rich-oxide",
                       ffams[made % len(ffams)], "interference", comp, spikes,
                       note=f"{a}/{b}: {note}")
        if r:
            recipes.append(r)
            made += 1

    # ---- outputs ----
    out = Path(__file__).parent / "build"
    out.mkdir(exist_ok=True)
    samples = {"samples": recipes}
    p = out / "C_r2_samples.json"
    p.write_text(json.dumps(samples, ensure_ascii=False, indent=1), encoding="utf-8")

    reg_rows = []
    for r in recipes:
        pr = r["provenance"]
        reg_rows.append({
            "id": r["id"], "matrix_type": pr["matrix_type"],
            "parent_family": pr["parent_family"], "scenario": pr["scenario"],
            "owner": OWNER, "round_id": ROUND_ID,
            "composition_semantic_sha256": pr["composition_semantic_sha256"],
            "n_elements": len(r["composition_percent"]),
            "compounds": json.dumps(pr["original_compounds_percent"], sort_keys=True),
            "trace_ppm": json.dumps(pr["trace_ppm"], sort_keys=True),
            "matrix_rescale_factor": pr["matrix_rescale_factor"],
            "note": pr["note"],
        })
    import csv
    with open(out / "C_r2_formula_registry.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(reg_rows[0].keys()))
        w.writeheader()
        w.writerows(reg_rows)

    # quota & closure summary
    from collections import Counter
    cnt = Counter((r["provenance"]["matrix_type"], r["provenance"]["scenario"])
                  for r in recipes)
    maxerr = max(abs(sum(r["composition_percent"].values()) - 100.0) for r in recipes)
    print(json.dumps({
        "recipes": len(recipes),
        "quota": {f"{k[0]}/{k[1]}": v for k, v in sorted(cnt.items())},
        "max_closure_abs_err": maxerr,
        "design_seed": DESIGN_SEED,
    }, ensure_ascii=False))


if __name__ == "__main__":
    build()
