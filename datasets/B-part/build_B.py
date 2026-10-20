"""Deterministic member B iron-rich oxide recipe design.

The delivered FP generator is used read-only: compound/trace conversion comes from
``fp_competition.minerals.components_to_elements`` and the routine/parent pool from the
shipped ``design-mineral`` CLI. The sparse and interference blocks are built by this
reproducible preprocessing script. Nothing here changes A's directory, the PDFs or sealed
batches, and no XRF physics solver is rewritten.

Run with the isolated environment recorded in B_environment.json:

    <venv>/Scripts/python.exe -B build_B.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent                       # datasets/B-part
ROOT = HERE.parents[1]                                       # workspace root
GEN = ROOT / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition'
WORK = HERE / 'work'
A_DIR = ROOT / 'datasets' / 'A-part-20261018'
sys.path.insert(0, str(GEN.parent))                          # importable package root

from fp_competition.core import TARGET_ELEMENTS                      # noqa: E402
from fp_competition.minerals import components_to_elements, design_minerals  # noqa: E402

# ---------------------------------------------------------------------- fixed identities
DESIGN_SEED = 2026101820           # construction RNG for the built blocks
POOL_SEED = 2026101821             # design-mineral CLI seed
POOL_COUNT = 1000                  # 900 routine + 60 interference parents + 40 reserve
QUOTA = {'routine': 900, 'sparse_boundary': 300, 'interference': 300}
MATRIX = 'iron_rich_oxide'
OWNER = 'B'
LOW_UPPER = 0.1                    # initial low bin: 0 < element percent <= 0.1
MID_RELATIVE = 0.5                 # mid/high split at 0.5 * declared maximum of the element
NEAR_LINF = 0.1                    # near-neighbour merge threshold, absolute element points
TRACE_LOW_UPPER = 1000.0           # ppm; 1000 ppm = 0.1 element percent
ROUND_DECIMALS = 12
CANON_ELEMENTS = tuple(sorted(set(TARGET_ELEMENTS) | {'O'}))          # 33 symbols, fixed order

# ---------------------------------------------------------------------- design ranges
# Fe2O3T is the balance compound, i.e. iron oxides are the main balancing component.
# Every bound is a human-set experimental-design value for label coverage inside an
# iron-rich oxide matrix, not a certified, measured or population distribution.
SPEC = {
    'compound_ranges_percent': {
        'SiO2': [0.0, 25.0], 'Al2O3': [0.0, 20.0], 'CaO': [0.0, 14.0], 'MgO': [0.0, 12.0],
        'TiO2': [0.0, 3.0], 'MnO': [0.0, 4.0], 'P2O5': [0.0, 1.0], 'K2O': [0.0, 2.0],
        'Na2O': [0.0, 2.0], 'CaSO4': [0.0, 3.0], 'NaCl': [0.0, 0.5],
    },
    'balance_compound': 'Fe2O3T',
    'balance_range_percent': [40.0, 75.0],
    'trace_ranges_ppm': {
        'V': [1.0, 3000.0], 'Cr': [1.0, 2500.0], 'Co': [1.0, 1500.0], 'Ni': [1.0, 2000.0],
        'Cu': [1.0, 2000.0], 'Zn': [1.0, 3000.0], 'As': [1.0, 2000.0], 'Se': [1.0, 1500.0],
        'Rb': [1.0, 2000.0], 'Sr': [1.0, 3000.0], 'Y': [1.0, 1500.0], 'Zr': [1.0, 4000.0],
        'Nb': [1.0, 2000.0], 'Mo': [1.0, 1500.0], 'Cd': [1.0, 1200.0], 'Sn': [1.0, 1500.0],
        'Sb': [1.0, 1500.0], 'Ba': [1.0, 4000.0], 'W': [1.0, 2000.0], 'Pb': [1.0, 3000.0],
    },
    'trace_absence_probability': {symbol: 0.25 for symbol in (
        'V', 'Cr', 'Co', 'Ni', 'Cu', 'Zn', 'As', 'Se', 'Rb', 'Sr',
        'Y', 'Zr', 'Nb', 'Mo', 'Cd', 'Sn', 'Sb', 'Ba', 'W', 'Pb')},
}
OPTIONAL = tuple(SPEC['compound_ranges_percent'])
CAP = {formula: SPEC['compound_ranges_percent'][formula][1] for formula in OPTIONAL}
GANGUE_MIN, GANGUE_MAX = 100.0 - SPEC['balance_range_percent'][1], 100.0 - SPEC['balance_range_percent'][0]

COMPOUND_ELEMENT = {'SiO2': 'Si', 'Al2O3': 'Al', 'CaO': 'Ca', 'MgO': 'Mg', 'TiO2': 'Ti',
                    'MnO': 'Mn', 'P2O5': 'P', 'K2O': 'K', 'Na2O': 'Na', 'CaSO4': 'S',
                    'NaCl': 'Cl', 'Fe2O3T': 'Fe'}
CARRIERS = {'Si': ('SiO2',), 'Al': ('Al2O3',), 'Ca': ('CaO', 'CaSO4'), 'Mg': ('MgO',),
            'Ti': ('TiO2',), 'Mn': ('MnO',), 'P': ('P2O5',), 'K': ('K2O',),
            'Na': ('Na2O', 'NaCl'), 'S': ('CaSO4',), 'Cl': ('NaCl',), 'Fe': ('Fe2O3T',)}
TRACE_ELEMENTS = tuple(SPEC['trace_ranges_ppm'])
COMPOUND_NONFE = ('Cl', 'Na', 'S', 'Ca', 'Si', 'Al', 'Mg', 'Ti', 'Mn', 'P', 'K')
APPLICABLE = tuple(e for e in TARGET_ELEMENTS if e != 'Fe')            # 31 non-iron targets
# Rotated closure pairs for the sparse zero/low families. Each pair must be able to absorb
# the whole gangue floor (>= GANGUE_MIN) or the row could not stay inside the iron band.
PAIRS = (('SiO2', 'Al2O3'), ('SiO2', 'CaO'), ('SiO2', 'MgO'),
         ('Al2O3', 'CaO'), ('Al2O3', 'MgO'), ('CaO', 'MgO'))
PAIR_CAP = {pair: CAP[pair[0]] + CAP[pair[1]] for pair in PAIRS}
SL_ROWS_PER_PAIR = 22                        # 6 x 22 = 132 two-member families = 264 rows
SPIKE_ROWS = len(APPLICABLE)                 # 31 declared-maximum spike rows
BOUNDARY_ROWS = 5                            # explicit band-edge and all-trace constructions
assert SL_ROWS_PER_PAIR * 2 * len(PAIRS) + SPIKE_ROWS + BOUNDARY_ROWS == QUOTA['sparse_boundary']
BASE = {'As': 200.0, 'Pb': 200.0, 'CaSO4': 0.2}      # ppm for As/Pb, mass percent for CaSO4
CONTROLS = ((0, 0), (1, 0), (0, 1), (1, 1), (10, 1))
BASIS = ('Member B experimental design for a synthetic iron-rich oxide matrix. Ranges, '
         'sampling distributions, the iron-rich criterion and the exact-zero mechanism are '
         'human-set for label coverage; they do not represent all iron ores and are not a '
         'measured, certified or population distribution.')


def convert(compounds, traces):
    """Element percents plus provenance, using the shipped converter with strict closure."""
    used, provenance = components_to_elements(compounds, traces, closure='strict')
    return used, provenance


FRACTION = {}
for _formula in tuple(OPTIONAL) + ('Fe2O3T',):
    _used, _ = convert({_formula: 100.0}, None)
    # components_to_elements returns element mass percents of the 100 mass percent compound,
    # so the true conversion factor is percent/100.
    FRACTION[_formula] = {k: v / 100.0 for k, v in _used.items()}
DECLARED_MAX = {element: sum(CAP[f] * FRACTION[f].get(element, 0.0) for f in CARRIERS[element])
                for element in COMPOUND_NONFE}
DECLARED_MAX.update({element: SPEC['trace_ranges_ppm'][element][1] / 10000.0
                     for element in TRACE_ELEMENTS})
DECLARED_MAX['Fe'] = SPEC['balance_range_percent'][1] * FRACTION['Fe2O3T']['Fe']


def save(name, data, directory=HERE):
    path = Path(directory) / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return path


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def a_rule_hash(composition):
    """A build_A.py rule: non-zero element dict, json.dumps(sort_keys=True), SHA256."""
    return sha256_bytes(json.dumps({k: v for k, v in composition.items() if v != 0},
                                   sort_keys=True).encode())


def numeric_vector(composition):
    unknown = set(composition) - set(CANON_ELEMENTS)
    if unknown:
        raise ValueError('element outside the canonical order: ' + str(sorted(unknown)))
    return [round(float(composition.get(s, 0.0)), ROUND_DECIMALS) for s in CANON_ELEMENTS]


def numeric_hash(composition):
    return sha256_bytes(json.dumps(numeric_vector(composition)).encode())


samples = []
audit_rows = []


def make_row(compounds, traces, scenario, family, detail):
    """Close the mass on Fe2O3T, convert, and verify every declared numerical rule."""
    compounds = {key: float(value) for key, value in compounds.items()}
    traces = {key: float(value) for key, value in traces.items()}
    gangue = sum(v for k, v in compounds.items() if k != 'Fe2O3T') + sum(traces.values()) / 10000.0
    compounds['Fe2O3T'] = 100.0 - gangue
    used, provenance = convert(compounds, traces)
    checks = {
        'Fe2O3T_percent': compounds['Fe2O3T'],
        'Fe_percent': used.get('Fe', 0.0),
        'gangue_percent': gangue,
        'Fe2O3T_in_declared_balance_band': SPEC['balance_range_percent'][0] - 1e-9 <=
                                          compounds['Fe2O3T'] <= SPEC['balance_range_percent'][1] + 1e-9,
        'iron_is_largest_candidate_target': used.get('Fe', 0.0) > max(
            (used.get(e, 0.0) for e in TARGET_ELEMENTS if e != 'Fe'), default=0.0),
        'every_compound_within_declared_range': all(
            SPEC['compound_ranges_percent'].get(k, [0.0, 100.0])[0] - 1e-12 <= v <=
            SPEC['compound_ranges_percent'].get(k, [0.0, 100.0])[1] + 1e-12
            for k, v in compounds.items()),
        'every_trace_zero_or_within_declared_range': all(
            v == 0.0 or SPEC['trace_ranges_ppm'][k][0] - 1e-12 <= v <=
            SPEC['trace_ranges_ppm'][k][1] + 1e-12 for k, v in traces.items()),
        'composition_sum_minus_100': sum(used.values()) - 100.0,
        'closure_policy': provenance['closure']['closure_policy'],
    }
    failed = [k for k, v in checks.items() if isinstance(v, bool) and not v]
    if failed or abs(checks['composition_sum_minus_100']) > 1e-9:
        raise ValueError('design rule violated in family %s: %s %s' % (family, failed, checks))
    provenance.update(basis=BASIS, matrix=MATRIX, owner=OWNER, scenario=scenario,
                      parent_family=family, design_detail=detail, iron_rich_check=checks)
    return compounds, traces, used, provenance


def add(compounds, traces, scenario, family, detail):
    compounds, traces, used, provenance = make_row(compounds, traces, scenario, family, detail)
    index = len(samples) + 1
    samples.append({'id': f'B{index:05d}', 'composition_percent': used, 'provenance': provenance})
    audit_rows.append({'id': f'B{index:05d}', 'parent_family': family, 'scenario': scenario,
                       'compounds_percent': compounds, 'trace_ppm': traces,
                       'used_percent': used, 'checks': checks_of(provenance)})
    return provenance


def checks_of(provenance):
    return provenance['iron_rich_check']


def log_draw(rng, low, high):
    return float(np.exp(rng.uniform(np.log(low), np.log(high))))


def to_band(compounds, traces, rng, protected=(), filler_order=('SiO2', 'Al2O3', 'CaO', 'MgO')):
    """Adjust non-iron compounds so Fe2O3T lands inside the declared iron band."""
    compounds = dict(compounds)
    trace_percent = sum(traces.values()) / 10000.0

    def total():
        return sum(v for k, v in compounds.items() if k != 'Fe2O3T') + trace_percent

    flexible = [k for k in compounds if k not in protected and k != 'Fe2O3T' and compounds[k] > 0]
    if total() > GANGUE_MAX:
        target = float(rng.uniform(GANGUE_MIN + 2.0, GANGUE_MAX - 2.0))
        excess = total() - target
        pool = sum(compounds[k] for k in flexible)
        if pool <= excess:
            raise ValueError('cannot reach the iron band; protected mass already exceeds the floor')
        for k in flexible:
            compounds[k] *= (pool - excess) / pool
    if total() < GANGUE_MIN:
        for formula in filler_order:
            if total() >= GANGUE_MIN + 0.5:
                break
            if formula in protected:
                continue
            room = CAP[formula] - compounds.get(formula, 0.0)
            if room > 0:
                compounds[formula] = compounds.get(formula, 0.0) + min(room, GANGUE_MIN + 1.0 - total())
    if not GANGUE_MIN - 1e-9 <= total() <= GANGUE_MAX + 1e-9:
        raise ValueError('constructed recipe outside the gangue band: %.6f' % total())
    return compounds


# ---------------------------------------------------------------------- pool (design-mineral CLI)
def get_pool():
    """Produce the routine/parent pool with the shipped design-mineral CLI and keep the file."""
    ranges_path = save('B_design_ranges.json', SPEC)
    pool_path = WORK / 'B_design_mineral_pool.json'
    pool_path.parent.mkdir(parents=True, exist_ok=True)
    if pool_path.exists():
        pool_path.unlink()                       # always regenerate so the recorded seed reproduces
    command = [sys.executable, '-B', 'app.py', 'design-mineral', '--ranges', str(ranges_path),
               '--count', str(POOL_COUNT), '--out', str(pool_path), '--seed', str(POOL_SEED)]
    done = subprocess.run(command, cwd=GEN, capture_output=True, text=True)
    (WORK / 'design_mineral_cli.log').write_text(
        'command: ' + ' '.join(command) + '\ncwd: ' + str(GEN) +
        '\nexit_code: %d\nstdout:\n%s\nstderr:\n%s\n' % (done.returncode, done.stdout, done.stderr),
        encoding='utf-8')
    if done.returncode != 0:
        raise RuntimeError('design-mineral failed, see work/design_mineral_cli.log')
    pool = json.loads(pool_path.read_text(encoding='utf-8'))
    if pool['seed'] != POOL_SEED or len(pool['samples']) != POOL_COUNT:
        raise RuntimeError('pool seed/count mismatch')
    in_process = design_minerals(SPEC, POOL_COUNT, POOL_SEED)['samples']
    if in_process[:3] != pool['samples'][:3]:
        raise RuntimeError('in-process design_minerals disagrees with the CLI pool output')
    return pool, ranges_path, pool_path


# ---------------------------------------------------------------------- blocks
def build_routine(pool):
    for i, sample in enumerate(pool[:QUOTA['routine']]):
        prov = sample['provenance']
        add(prov['compounds_percent'], prov['trace_ppm'], 'routine', 'B-R%04d' % i,
            {'block': 'routine', 'pool_sample_id': sample['id'], 'design_seed': POOL_SEED,
             'mechanism': 'design-mineral uniform compound draws over the declared ranges, '
                          'log-uniform positive traces with 25% exact-absence probability, '
                          'Fe2O3T as balance accepted only inside 40-75%'})


def low_spikes(carrier_elements, rng):
    """Compound amounts putting every non-carrier oxide element in 0 < x <= 0.1 percent.

    A compound can carry two tracked elements (CaSO4 -> Ca+S, NaCl -> Na+Cl), so each new
    amount is capped by the remaining low-bin room of every co-element it touches, not only
    by the element it is meant to spike. verify_blocks() re-checks the resulting percents.
    """
    spikes = {}

    def already(element):
        return sum(amount * FRACTION[key].get(element, 0.0) for key, amount in spikes.items())

    for element in COMPOUND_NONFE:
        if element in carrier_elements:
            continue
        target = float(np.exp(rng.uniform(np.log(0.001), np.log(LOW_UPPER))))
        for formula in CARRIERS[element]:
            if COMPOUND_ELEMENT[formula] in carrier_elements:
                continue                       # that compound is a closure carrier
            fraction = FRACTION[formula]
            value = target
            for tracked in COMPOUND_NONFE:
                if tracked in carrier_elements or fraction.get(tracked, 0.0) <= 0.0:
                    continue                   # O is stoichiometric bookkeeping, never binned here
                # room in this element's units: the compound mass added also carries the
                # co-element in the ratio fraction[tracked] / fraction[element]
                room = ((LOW_UPPER - already(tracked)) * 0.999
                        * fraction[element] / fraction[tracked])
                value = min(value, room)
            if value <= 0.0:
                continue                       # this element already fills the low bin
            spikes[formula] = spikes.get(formula, 0.0) + value / fraction[element]
    return spikes


def build_sparse_zero_low(rng):
    """132 two-member families: an all-optional-zero row and its low-spiked sibling.

    The sibling keeps Fe2O3T and the zero-row closure pair identical by paying the spike
    mass out of the larger carrier, so the pair is a real near-neighbour inside one family.
    """
    count = 0
    for pair in PAIRS:
        carrier_elements = {COMPOUND_ELEMENT[f] for f in pair}
        for _ in range(SL_ROWS_PER_PAIR):
            gangue = float(rng.uniform(GANGUE_MIN, min(PAIR_CAP[pair], 58.0)))
            low_a, high_a = max(0.0, gangue - CAP[pair[1]]), min(CAP[pair[0]], gangue)
            amount_a = float(rng.uniform(low_a, high_a))
            carriers = {pair[0]: amount_a, pair[1]: gangue - amount_a}
            family = 'B-S%04d' % count
            count += 1
            add(carriers, {e: 0.0 for e in TRACE_ELEMENTS}, 'sparse_boundary', family,
                {'block': 'sparse_exact_zero', 'closure_pair': list(pair),
                 'gangue_percent_target': gangue,
                 'mechanism': 'exact zero for every optional oxide and every trace; only the '
                              'rotated closure pair carries gangue mass'})
            spikes = low_spikes(carrier_elements, rng)
            traces = {e: log_draw(rng, SPEC['trace_ranges_ppm'][e][0], TRACE_LOW_UPPER)
                      for e in TRACE_ELEMENTS}
            budget = sum(spikes.values()) + sum(traces.values()) / 10000.0
            carriers = dict(carriers)
            larger = pair[0] if carriers[pair[0]] >= carriers[pair[1]] else pair[1]
            carriers[larger] -= budget
            if carriers[larger] < 1.0:
                raise RuntimeError('closure carrier exhausted in family ' + family)
            compounds = dict(carriers)
            compounds.update(spikes)
            add(compounds, traces, 'sparse_boundary', family,
                {'block': 'sparse_low', 'closure_pair': list(pair), 'reduced_carrier': larger,
                 'spike_budget_percent': budget,
                 'mechanism': 'same Fe2O3T and closure pair as the zero sibling; each other '
                              'oxide element drawn into 0 < percent <= 0.1 and each trace into '
                              '1-1000 ppm (= 0.0001-0.1 percent)'})


def build_spike_boundary(rng):
    """Declared-maximum spike per applicable element, plus explicit boundary constructions."""
    for element in APPLICABLE:
        compounds = {f: float(rng.uniform(0.25, 0.60) * CAP[f]) for f in OPTIONAL}
        traces = {e: log_draw(rng, SPEC['trace_ranges_ppm'][e][0], SPEC['trace_ranges_ppm'][e][1])
                  for e in TRACE_ELEMENTS}
        protected = []
        if element in TRACE_ELEMENTS:
            traces[element] = SPEC['trace_ranges_ppm'][element][1]
            spike = {'unit': 'ppm', 'value': traces[element]}
        else:
            formulas = [f for f in CARRIERS[element] if f in CAP]
            for formula in formulas:
                compounds[formula] = CAP[formula]
                protected.append(formula)
            if element == 'S':
                traces.pop('S', None)
            spike = {'unit': 'compound mass percent',
                     'values': {f: CAP[f] for f in formulas}}
        compounds = to_band(compounds, traces, rng, protected=tuple(protected))
        add(compounds, traces, 'sparse_boundary', 'B-H-' + element,
            {'block': 'declared_maximum_spike', 'spiked_element': element, 'spike': spike,
             'mechanism': 'one target pinned at its declared design maximum with a normal '
                          'multi-oxide background; stresses the high end of the label range, '
                          'it is not a certified concentration'})
    # five explicit boundary constructions
    weights = np.array([CAP[f] for f in OPTIONAL])
    for name, iron_target in (('balance_upper', 75.0), ('balance_lower', 40.0)):
        gangue = 100.0 - iron_target
        traces = {e: log_draw(rng, 1.0, 300.0) for e in TRACE_ELEMENTS}
        shift = sum(traces.values()) / 10000.0
        shares = weights / weights.sum() * (gangue - shift)
        compounds = dict(zip(OPTIONAL, shares.tolist()))
        compounds = to_band(compounds, traces, rng)
        add(compounds, traces, 'sparse_boundary', 'B-H-' + name,
            {'block': 'boundary', 'Fe2O3T_target_percent': iron_target,
             'mechanism': 'Fe2O3T pinned at a declared band edge, gangue distributed in '
                          'proportion to the declared maxima, traces drawn 1-300 ppm'})
    traces_max = {e: SPEC['trace_ranges_ppm'][e][1] for e in TRACE_ELEMENTS}
    add(to_band({'SiO2': 15.0, 'Al2O3': 13.0}, traces_max, rng), traces_max,
        'sparse_boundary', 'B-H-all_traces_max',
        {'block': 'boundary', 'total_trace_ppm': sum(traces_max.values()),
         'mechanism': 'all 20 traces simultaneously at their declared maximum with a '
                      'SiO2+Al2O3 closure; tests simultaneous weak-line records'})
    boundary_low = {e: 1.0 for e in TRACE_ELEMENTS}
    add(to_band({'SiO2': 20.0, 'Al2O3': 10.0, 'CaO': 3.0, 'MgO': 2.0, 'TiO2': 1.0, 'MnO': 1.0,
                 'P2O5': 0.3, 'K2O': 0.5, 'Na2O': 0.5, 'CaSO4': 0.4, 'NaCl': 0.1},
                boundary_low, rng), boundary_low, 'sparse_boundary', 'B-H-all_traces_min',
        {'block': 'boundary', 'mechanism': 'every trace at its declared minimum 1 ppm above a '
                                          'full mid-level oxide background'})
    widest = PAIRS[0]
    ceiling = {widest[0]: CAP[widest[0]], widest[1]: CAP[widest[1]]}
    add(to_band(ceiling, {e: 0.0 for e in TRACE_ELEMENTS}, rng),
        {e: 0.0 for e in TRACE_ELEMENTS}, 'sparse_boundary', 'B-H-two_carrier_ceiling',
        {'block': 'boundary', 'closure_pair': list(PAIRS[0]),
         'mechanism': 'both members of the widest closure pair simultaneously at their declared '
                      'compound maxima with every trace explicitly absent; the sparsest possible '
                      'multi-oxide iron-rich record'})


def build_interference(pool):
    for j, sample in enumerate(pool[QUOTA['routine']:QUOTA['routine'] + 60]):
        prov = sample['provenance']
        pair = ('As', 'Pb') if j < 30 else ('S', 'Pb')
        family = 'B-I%04d' % j
        for a, b in CONTROLS:
            compounds = dict(prov['compounds_percent'])
            traces = {k: v for k, v in prov['trace_ppm'].items() if k not in ('As', 'Pb', 'S')}
            if pair[0] == 'As':
                traces['As'] = BASE['As'] * a
            else:
                compounds['CaSO4'] = BASE['CaSO4'] * a
            traces['Pb'] = BASE['Pb'] * b
            add(compounds, traces, 'interference', family,
                {'block': 'interference_control', 'candidate_pair': list(pair),
                 'control_multipliers': [a, b], 'basis_values': dict(BASE),
                 'basis_units': {'As': 'ppm', 'Pb': 'ppm', 'CaSO4': 'compound mass percent'},
                 'parent_pool_sample_id': sample['id'],
                 'sulfur_note': 'S enters as CaSO4, so Ca and O change with it; this is not a '
                                'strict single-variable sulfur control' if pair[0] == 'S' else
                               'As added as an elemental trace',
                 'mechanism': 'same parent oxide background, Fe2O3T re-closes the mass'})


# ---------------------------------------------------------------------- construction proofs
def verify_blocks():
    """Re-derive every block claim from the adopted compositions instead of assuming they held."""
    blocks = defaultdict(list)
    for sample in samples:
        blocks[sample['provenance']['design_detail']['block']].append(sample)
    per_block = {}
    for name, rows in sorted(blocks.items()):
        per_block[name] = {
            'rows': len(rows),
            'scenarios': sorted({r['provenance']['scenario'] for r in rows}),
            'element_zero_low_counts': {
                element: {'zero': sum(r['composition_percent'].get(element, 0.0) == 0.0
                                      for r in rows),
                          'low_0_to_0_1_percent':
                              sum(0.0 < r['composition_percent'].get(element, 0.0) <= LOW_UPPER
                                  for r in rows)}
                for element in APPLICABLE}}
    violations = []
    for sample in samples:
        detail = sample['provenance']['design_detail']
        used = sample['composition_percent']
        block = detail['block']
        if block == 'sparse_exact_zero':
            allowed = {'Fe', 'O'} | {COMPOUND_ELEMENT[f] for f in detail['closure_pair']}
            extra = sorted(e for e, value in used.items() if value != 0 and e not in allowed)
            if extra:
                violations.append({'id': sample['id'], 'block': block,
                                   'claim': 'only the closure pair plus Fe and O carry mass',
                                   'unexpected_nonzero_elements': extra})
        elif block == 'sparse_low':
            carriers = {COMPOUND_ELEMENT[f] for f in detail['closure_pair']}
            outside = {element: used.get(element, 0.0) for element in APPLICABLE
                       if element not in carriers
                       and not 0.0 < used.get(element, 0.0) <= LOW_UPPER}
            if outside:
                violations.append({'id': sample['id'], 'block': block,
                                   'claim': 'every non-carrier applicable element in 0 < x <= 0.1',
                                   'outside_the_low_bin': outside})
        elif block == 'declared_maximum_spike':
            element = detail['spiked_element']
            if abs(used.get(element, 0.0) - DECLARED_MAX[element]) > 1e-9:
                violations.append({'id': sample['id'], 'block': block,
                                   'claim': 'spiked element at its declared design maximum',
                                   'element': element, 'percent': used.get(element, 0.0),
                                   'declared_maximum_percent': DECLARED_MAX[element]})
    return {'per_block': per_block, 'violations': violations, 'violation_count': len(violations),
            'note': 'per-block zero/low counts are the arithmetic evidence behind the gap list in '
                    'B_coverage.json; the routine and interference blocks are randomly drawn or '
                    'control-structured, so no per-element zero/low quota is claimed for them'}


# ---------------------------------------------------------------------- grouping and reports
def merge_near_neighbours():
    """Union-find grouping of near-identical compositions so neighbours share parent_family."""
    vectors = np.array([[s['composition_percent'].get(e, 0.0) for e in CANON_ELEMENTS]
                        for s in samples])
    families = [s['provenance']['parent_family'] for s in samples]
    parent = list(range(len(samples)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cross_family = []
    block = 200
    for start in range(0, len(samples), block):
        left = vectors[start:start + block]
        distance = np.max(np.abs(vectors[None, :, :] - left[:, None, :]), axis=2)
        rows, columns = np.where(distance <= NEAR_LINF)
        for row, column in zip(rows, columns):
            i, j = start + int(row), int(column)
            if i >= j:
                continue
            if families[i] != families[j]:
                cross_family.append({'ids': [samples[i]['id'], samples[j]['id']],
                                     'families': [families[i], families[j]],
                                     'linfinity_percent': float(distance[row][column]),
                                     'scenarios': [samples[i]['provenance']['scenario'],
                                                   samples[j]['provenance']['scenario']]})
            root_i, root_j = find(i), find(j)
            if root_i != root_j:
                parent[max(root_i, root_j)] = min(root_i, root_j)
    renamed = 0
    for index, sample in enumerate(samples):
        canonical = min(families[m] for m in range(len(samples)) if find(m) == find(index))
        if sample['provenance']['parent_family'] != canonical:
            sample['provenance']['parent_family'] = canonical
            sample['provenance']['near_neighbour_merge'] = {
                'rule': 'L-inf over the unified 33-element vector <= %.2f element points' % NEAR_LINF,
                'canonical_family': canonical}
            renamed += 1
    groups = defaultdict(list)
    for index in range(len(samples)):
        groups[find(index)].append(index)
    return {'rule': 'two distinct recipes are near-neighbours when the maximum absolute '
                    'difference over the unified 33-element vector is <= %.2f absolute element '
                    'percent points; near-neighbours are merged into one parent_family '
                    '(deterministic: smallest family label wins)' % NEAR_LINF,
            'cross_family_near_neighbour_pairs': cross_family,
            'cross_family_pair_count': len(cross_family),
            'family_renamed_rows': renamed,
            'family_count_after_merge': len(groups),
            'largest_family_after_merge': max(len(v) for v in groups.values())}


def resolve_duplicates():
    """Fixed rule if the adopted compositions are not all independent: perturb and reconvert."""
    seen = {}
    repairs = []
    for index, sample in enumerate(samples):
        digest = a_rule_hash(sample['composition_percent'])
        while digest in seen:
            previous = seen[digest]
            prov = sample['provenance']
            compounds = dict(prov['compounds_percent'])
            traces = dict(prov['trace_ppm'])
            step = 0.0001 * (len(repairs) + 1)
            compounds['MgO'] = compounds.get('MgO', 0.0) + step
            if traces.get('Cd', 0) > 0:
                traces['Cd'] = traces['Cd'] + 1.0
            new_compounds, new_traces, used, provenance = make_row(
                compounds, traces, prov['scenario'], prov['parent_family'],
                {**prov['design_detail'], 'duplicate_resolution':
                    'MgO +%.4f mass percent%s, Fe2O3T re-balanced' %
                    (step, ', Cd +1 ppm' if traces.get('Cd', 0) > 1 else '')})
            provenance['basis'] = prov['basis']
            sample['composition_percent'] = used
            sample['provenance'] = provenance
            audit_rows[index] = {'id': sample['id'], 'parent_family': prov['parent_family'],
                                 'scenario': prov['scenario'], 'compounds_percent': new_compounds,
                                 'trace_ppm': new_traces, 'used_percent': used,
                                 'checks': provenance['iron_rich_check']}
            repairs.append({'id': sample['id'], 'duplicate_of': samples[previous]['id'],
                            'step': step})
            digest = a_rule_hash(used)
        seen[digest] = index
    return repairs


def build_registry():
    path = HERE / 'B_formula_registry.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['formula_id', 'parent_family', 'matrix', 'scenario',
                         'composition_sha256_a_rule', 'composition_sha256_unified12',
                         'used_element_count', 'Fe2O3T_percent', 'split_status'])
        for sample in samples:
            prov = sample['provenance']
            writer.writerow([sample['id'], prov['parent_family'], prov['matrix'], prov['scenario'],
                             a_rule_hash(sample['composition_percent']),
                             numeric_hash(sample['composition_percent']),
                             sum(v != 0 for v in sample['composition_percent'].values()),
                             prov['iron_rich_check']['Fe2O3T_percent'],
                             'pending_global_5000_family_split'])
    return path


def build_coverage(merge_report, checks, block_proof):
    coverage = {}
    for element in TARGET_ELEMENTS:
        values = [s['composition_percent'].get(element, 0.0) for s in samples]
        maximum = DECLARED_MAX[element]
        mid_edge = maximum * MID_RELATIVE
        low_values = [v for v in values if 0.0 < v <= LOW_UPPER]
        coverage[element] = {
            'zero': sum(v == 0.0 for v in values),
            'low_0_to_0_1_percent': sum(0.0 < v <= LOW_UPPER for v in values),
            'low_bin_spread_percent': {'min': min(low_values, default=None),
                                       'max': max(low_values, default=None)},
            'mid_above_0_1_to_declared_half_max': sum(LOW_UPPER < v <= max(mid_edge, LOW_UPPER)
                                                      for v in values),
            'high_above_declared_half_max': sum(v > max(mid_edge, LOW_UPPER) for v in values),
            'min_percent': min(values), 'max_percent': max(values),
            'declared_maximum_percent': maximum,
            'declared_maximum_reached': max(values) >= maximum - 1e-9,
            'by_scenario': {scenario: {
                'zero': sum(s['composition_percent'].get(element, 0.0) == 0.0
                            and s['provenance']['scenario'] == scenario for s in samples),
                'low_0_to_0_1_percent': sum(0.0 < s['composition_percent'].get(element, 0.0) <=
                                            LOW_UPPER and s['provenance']['scenario'] == scenario
                                            for s in samples),
                'rows': sum(s['provenance']['scenario'] == scenario for s in samples)}
                for scenario in QUOTA}}
    gaps = {}
    for element in APPLICABLE:
        row = coverage[element]
        maximum = row['declared_maximum_percent']
        degenerate = maximum * MID_RELATIVE <= LOW_UPPER
        shortfalls = {bin_name: row[bin_name] for bin_name in
                      ('zero', 'low_0_to_0_1_percent') if row[bin_name] < 50}
        notes = []
        if shortfalls:
            if element in ('Si', 'Al', 'Ca', 'Mg'):
                notes.append('this element is a closure carrier in %d of the 6 sparse pairs, so '
                             'it can only be zero/low in the remaining pairs; recorded rather '
                             'than padded' % sum(1 for pair in PAIRS if element in
                                                 {COMPOUND_ELEMENT[f] for f in pair}))
            else:
                notes.append('not reachable with the declared carriers; recorded rather than padded')
        if row['high_above_declared_half_max'] == 0:
            notes.append('high bin empty: declared maximum %.6g percent does not exceed the '
                         'low-bin ceiling by enough margin under the sampling scheme'
                         % maximum)
        if row['mid_above_0_1_to_declared_half_max'] == 0:
            if degenerate:
                notes.append('mid band is degenerate by definition, not a coverage failure: half of '
                             'the declared maximum %.6g percent is %.6g, at or below the low-bin '
                             'ceiling 0.1, so every value above the low bin is counted as high'
                             % (maximum, maximum * MID_RELATIVE))
            else:
                notes.append('mid bin empty at the declared split %.6g percent'
                             % (maximum * MID_RELATIVE))
        if shortfalls or notes:
            gaps[element] = {'shortfall_counts': shortfalls,
                             'band_definition_degenerate': degenerate,
                             'notes': notes,
                             'target': '>= 50 exact-zero and >= 50 low recipes per applicable element'}
    families = defaultdict(list)
    family_scenarios = defaultdict(set)
    for sample in samples:
        families[sample['provenance']['parent_family']].append(sample['id'])
        family_scenarios[sample['provenance']['parent_family']].add(
            sample['provenance']['scenario'])
    interference = {k: len(v) for k, v in families.items() if k.startswith('B-I')}
    iron = [s['provenance']['iron_rich_check'] for s in samples]
    by_id = {s['id']: s for s in samples}
    largest_key = max(families, key=lambda key: (len(families[key]), key))
    largest_family = {
        'parent_family': largest_key,
        'row_ids': families[largest_key],
        'blocks': sorted({by_id[i]['provenance']['design_detail']['block']
                          for i in families[largest_key]}),
        'note': 'near-neighbour merging is transitive (union-find), so a chain of individually '
                'close constructed families can end up under one label; this only ever makes the '
                'global family split more conservative, it never splits one constructed control '
                'group across folds'}
    return {
        'total_recipes': len(samples),
        'unique_by_a_rule_hash': len({a_rule_hash(s['composition_percent']) for s in samples}),
        'unique_by_unified_12_decimal_key': len({numeric_hash(s['composition_percent'])
                                                for s in samples}),
        'scenario_counts': dict(Counter(s['provenance']['scenario'] for s in samples)),
        'scenario_quota': QUOTA,
        'low_bin_definition': '0 < element mass percent <= 0.1; an initial statistical reporting '
                              'convention of this design, not a detection limit and not a claim '
                              'about real samples',
        'mid_high_definition': 'mid = 0.1 < x <= 0.5 * declared maximum element percent for that '
                               'element; high = x > that half-maximum. Declared maxima come from '
                               'B_design_ranges.json (compound maxima converted to elements, trace '
                               'maxima in ppm/10000), so unreachable bins stay visible',
        'exact_zero_definition': 'the recipe adds no compound or trace carrying that element; it '
                                 'is not a claim that a physical sample is non-detect',
        'applicable_elements': list(APPLICABLE),
        'candidate_target_count': len(TARGET_ELEMENTS),
        'canonical_vector_element_count': len(CANON_ELEMENTS),
        'exempt': {'Fe': 'required iron matrix of the iron-rich oxide design; never asked to be zero',
                   'O': 'stoichiometric matrix bookkeeping, not a direct fluorescence target of '
                        'this model version'},
        'coverage': coverage,
        'gaps': gaps,
        'family_integrity': {
            'family_count': len(families),
            'family_size_histogram': dict(Counter(len(v) for v in families.values())),
            'interference_family_count': len(interference),
            'interference_family_sizes': sorted(set(interference.values())),
            'interference_families_of_size_5': sum(1 for v in interference.values() if v == 5),
            'families_spanning_scenarios': sorted(k for k, v in family_scenarios.items()
                                                  if len(v) > 1),
            'largest_family_evidence': largest_family},
        'iron_rich_criterion_verification': {
            'criterion': 'Fe2O3T in [40,75] mass percent (elemental Fe in [27.977,52.458] percent '
                         'under the Fe2O3 stoichiometry assumption) AND Fe strictly larger than '
                         'every other candidate target AND strict closure of the element sum to '
                         '100 percent within 1e-6 points',
            'rows_passing_all_boolean_checks': sum(
                all(v for k, v in row.items() if isinstance(v, bool)) for row in iron),
            'rows_total': len(iron),
            'Fe2O3T_min': min(r['Fe2O3T_percent'] for r in iron),
            'Fe2O3T_max': max(r['Fe2O3T_percent'] for r in iron),
            'Fe_min': min(r['Fe_percent'] for r in iron),
            'Fe_max': max(r['Fe_percent'] for r in iron),
            'gangue_min': min(r['gangue_percent'] for r in iron),
            'gangue_max': max(r['gangue_percent'] for r in iron),
            'max_abs_closure_error': max(abs(r['composition_sum_minus_100']) for r in iron)},
        'near_neighbour_grouping': merge_report,
        'block_construction_proof': block_proof,
        'design_checks': checks,
    }


def cross_A():
    a_samples = json.loads((A_DIR / 'A_samples.json').read_text(encoding='utf-8'))['samples']
    a_vectors = np.array([numeric_vector(s['composition_percent']) for s in a_samples])
    a_a_rule = {a_rule_hash(s['composition_percent']): s['id'] for s in a_samples}
    a_unified = {numeric_hash(s['composition_percent']): s['id'] for s in a_samples}
    b_vectors = np.array([numeric_vector(s['composition_percent']) for s in samples])
    exact_a_rule, exact_unified, nearest, counts = [], [], [], {}
    thresholds = [0.0, 0.05, NEAR_LINF, 0.5, 1.0, 5.0]
    counts = {'%.2f' % t: 0 for t in thresholds}
    for index, sample in enumerate(samples):
        digest = a_rule_hash(sample['composition_percent'])
        if digest in a_a_rule:
            exact_a_rule.append({'b_id': sample['id'], 'a_id': a_a_rule[digest]})
        unified = numeric_hash(sample['composition_percent'])
        if unified in a_unified:
            exact_unified.append({'b_id': sample['id'], 'a_id': a_unified[unified]})
        distance = np.max(np.abs(a_vectors - b_vectors[index]), axis=1)
        position = int(distance.argmin())
        nearest.append({'b_id': sample['id'], 'closest_a_id': a_samples[position]['id'],
                        'linfinity_percent': float(distance.min())})
        for threshold in thresholds:
            if distance.min() <= threshold:
                counts['%.2f' % threshold] += 1
    nearest.sort(key=lambda row: row['linfinity_percent'])
    a_ids = {s['id'] for s in a_samples}
    a_families = {s['provenance']['parent_family'] for s in a_samples}
    return {
        'a_master_file': str(A_DIR / 'A_samples.json'),
        'a_recipe_count': len(a_samples),
        'b_recipe_count': len(samples),
        'duplicate_criterion_1_a_rule': 'SHA256 of json.dumps({element: percent for nonzero '
                                        'elements}, sort_keys=True), identical to build_A.py',
        'duplicate_criterion_2_unified_numeric': 'unified 33-symbol element order (32 targets + O) '
                                                 'with values rounded to 12 decimals, then SHA256; '
                                                 'this also matches compositions that differ only by '
                                                 'which elements happen to be zero',
        'near_neighbour_rule': 'L-inf distance over the unified 33-element vector, nearest '
                               'neighbour reported for every B recipe; merge threshold %.2f points'
                               % NEAR_LINF,
        'exact_overlap_a_rule': exact_a_rule,
        'exact_overlap_unified_numeric': exact_unified,
        'nearest_neighbour_counts_by_threshold': counts,
        'closest_pairs_top10': nearest[:10],
        'matrix_separation_note': 'A balances on SiO2 with Fe2O3T 1-20 percent while B balances on '
                                  'Fe2O3T 40-75 percent, so an exact or near collision would itself '
                                  'be a design error; the distances are recorded anyway',
        'formula_id_collisions': sorted(set(s['id'] for s in samples) & a_ids),
        'parent_family_collisions': sorted({s['provenance']['parent_family'] for s in samples} &
                                          a_families),
        'action_for_A': 'this list is handed to A for the 5,000-row master merge; B does not '
                        'modify any A recipe'}


def main():
    pool, ranges_path, pool_path = get_pool()
    rng = np.random.default_rng(DESIGN_SEED)
    build_routine(pool['samples'])
    build_sparse_zero_low(rng)
    build_spike_boundary(rng)
    build_interference(pool['samples'])
    scenario_counts = dict(Counter(s['provenance']['scenario'] for s in samples))
    if len(samples) != sum(QUOTA.values()) or scenario_counts != QUOTA:
        raise RuntimeError('quota mismatch: %d rows %s' % (len(samples), scenario_counts))
    merge_report = merge_near_neighbours()
    repairs = resolve_duplicates()
    block_proof = verify_blocks()
    a_unique = len({a_rule_hash(s['composition_percent']) for s in samples})
    n_unique = len({numeric_hash(s['composition_percent']) for s in samples})
    if a_unique != 1500 or n_unique != 1500:
        raise RuntimeError('dedup failed: a_rule=%d unified=%d' % (a_unique, n_unique))
    mismatched = []
    for sample in samples:
        rebuilt, _ = convert(sample['provenance']['compounds_percent'],
                             sample['provenance']['trace_ppm'])
        if rebuilt != sample['composition_percent']:
            mismatched.append(sample['id'])
    checks = {
        'nonnegative_and_finite': all(np.isfinite(v) and v >= 0 for s in samples
                                      for v in s['composition_percent'].values()),
        'sum_is_100_within_strict_tolerance': max(
            abs(sum(s['composition_percent'].values()) - 100.0) for s in samples) <= 1e-6,
        'max_abs_composition_sum_error': max(abs(sum(s['composition_percent'].values()) - 100.0)
                                             for s in samples),
        'scenario_quota_met': scenario_counts == QUOTA,
        'unique_by_a_rule_hash': a_unique,
        'unique_by_unified_12_decimal': n_unique,
        'duplicate_repairs': repairs,
        'id_format_stable_and_unique': all(len(s['id']) == 6 and s['id'].startswith('B')
                                           for s in samples) and
                                       len({s['id'] for s in samples}) == 1500,
        'provenance_reconversion_matches': not mismatched,
        'provenance_reconversion_mismatches': mismatched,
        'closure_policy_used': sorted({s['provenance']['closure']['closure_policy']
                                       for s in samples}),
        'matrix_owner': sorted({s['provenance']['matrix'] for s in samples} |
                               {s['provenance']['owner'] for s in samples}),
        'elements_outside_canonical_order': sorted({e for s in samples
                                                    for e in s['composition_percent']} -
                                                   set(CANON_ELEMENTS)),
        'block_construction_violation_count': block_proof['violation_count'],
        'block_construction_violations': block_proof['violations'],
    }
    coverage = build_coverage(merge_report, checks, block_proof)
    overlap = cross_A()
    manifest = {
        'design_ranges': {'file': 'B_design_ranges.json', 'sha256': sha256_bytes(ranges_path.read_bytes())},
        'design_mineral_pool': {'file': pool_path.relative_to(HERE).as_posix(),
                                'sha256': sha256_bytes(pool_path.read_bytes()),
                                'seed': POOL_SEED, 'count': POOL_COUNT,
                                'command_log': 'work/design_mineral_cli.log'},
        'construction_seed': DESIGN_SEED,
        'strict_closure_tolerance_points': 1e-6,
    }
    coverage['design_manifest'] = manifest
    save('B_samples.json', {'synthetic_design': True, 'matrix': MATRIX, 'owner': OWNER,
                            'construction_seed': DESIGN_SEED, 'pool_seed': POOL_SEED,
                            'pool_file': manifest['design_mineral_pool']['file'],
                            'purpose': 'member B iron-rich oxide recipes; composition_percent is '
                                       'the adopted element mass percent actually fed to the model, '
                                       'not a measured concentration',
                            'samples': samples})
    save('B_coverage.json', coverage)
    save('B_cross_A_overlap.json', overlap)
    build_registry()
    (HERE / 'B_design_ranges.json').write_text(
        json.dumps(SPEC, ensure_ascii=False, indent=2), encoding='utf-8')
    save('B_recipe_checks.json', checks, WORK)
    print(json.dumps({'recipes': len(samples), 'scenarios': scenario_counts,
                      'unique_a_rule': a_unique, 'unique_unified': n_unique,
                      'families': coverage['family_integrity']['family_count'],
                      'cross_family_near_neighbours': merge_report['cross_family_pair_count'],
                      'gap_elements': sorted(coverage['gaps']),
                      'shortfall_elements': sorted(e for e, g in coverage['gaps'].items()
                                                   if g['shortfall_counts']),
                      'block_construction_violations': block_proof['violation_count'],
                      'min_zero': min(coverage['coverage'][e]['zero'] for e in APPLICABLE),
                      'min_low': min(coverage['coverage'][e]['low_0_to_0_1_percent']
                                     for e in APPLICABLE),
                      'exact_overlap_with_A': len(overlap['exact_overlap_a_rule']),
                      'checks_failed': [k for k, v in checks.items()
                                        if isinstance(v, bool) and not v]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
