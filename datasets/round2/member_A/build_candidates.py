"""Build round-2 A candidate formulas, never spectra or a global approval.

Run using the locked generator environment; output must be a new directory.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from fp_competition.core import TARGET_ELEMENTS
from fp_competition.minerals import components_to_elements, design_minerals


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                   allow_nan=False), encoding='utf-8')


def fingerprint(comp):
    """12-decimal elemental-percent key for conservative duplicate screening."""
    return json.dumps({e: round(float(v), 12) for e, v in sorted(comp.items())
                       if v != 0}, sort_keys=True, separators=(',', ':'))


def construct(specs, seed):
    rng = np.random.default_rng(seed)
    samples = []
    controls = [(0, 0), (1, 0), (0, 1), (1, 1), (10, 1)]
    for mi, (matrix, routine_n, sparse_n, parents_n) in enumerate([
            ('silicate_oxide', 90, 30, 6), ('iron_oxide', 60, 20, 4)]):
        spec = specs[matrix]['routine']
        base = design_minerals(spec, routine_n+sparse_n+parents_n, seed+mi+1)['samples']
        balance = spec['balance_compound']

        def add(c, t, scenario, family, detail):
            c, t = dict(c), dict(t)
            c[balance] = 100-sum(v for k, v in c.items() if k != balance)-sum(t.values())/10000
            elements, ledger = components_to_elements(c, t, closure='strict')
            ledger.update(round_id='round2-20261021', owner='A',
                          matrix_type=matrix, parent_family=family, scenario=scenario,
                          design_detail=detail, design_seed=seed,
                          scope='synthetic homogeneous design, not a geological population',
                          first_round_ancestry='fresh draws; no deliberate reuse of first-round parent',
                          global_status='candidate_pending_cross_member_confirmation')
            samples.append({'id': f'R2_A_{len(samples)+1:04d}',
                            'composition_percent': elements, 'provenance': ledger})

        for i, row in enumerate(base[:routine_n]):
            p = row['provenance']
            add(p['compounds_percent'], p['trace_ppm'], 'routine',
                f'R2_A_{matrix}_R{i:03d}', 'Frozen routine ranges; rejection closure')
        for i, row in enumerate(base[routine_n:routine_n+sparse_n]):
            p = row['provenance']
            c = {k: (float(v) if rng.random() < .5 else 0.)
                 for k, v in p['compounds_percent'].items() if k != balance}
            t = {k: (float(v) if rng.random() < .35 else 0.)
                 for k, v in p['trace_ppm'].items()}
            if i < sparse_n//2:
                t = {k: 0. for k in t}
            else:
                t = {k: (float(spec['trace_ranges_ppm'][k][0])
                         if rng.random() < .5 else 0.) for k in t}
            add(c, t, 'sparse_boundary', f'R2_A_{matrix}_S{i:03d}',
                'Independent compound masks; first half trace-zero, second half trace-floor/zero; balance range explicitly expanded')
        for i, row in enumerate(base[routine_n+sparse_n:]):
            p = row['provenance']
            pair = 'As_Pb' if i < parents_n//2 else 'S_Pb'
            for a, b in controls:
                c, t = dict(p['compounds_percent']), dict(p['trace_ppm'])
                if pair == 'As_Pb':
                    t['As'] = 100.*a
                else:
                    c['CaSO4'] = .1*a
                t['Pb'] = 100.*b
                add(c, t, 'interference', f'R2_A_{matrix}_I{i:03d}',
                    {'pair': pair, 'control': [a, b], 'base_trace_ppm': 100,
                     'base_CaSO4_percent': .1,
                     'caveat': 'S supplied as CaSO4 also changes Ca/O; balance changes; not a single-element intervention'})
    return samples


def verify(samples, specs, previous):
    errors = []
    if len(samples) != 250:
        errors.append('Expected 250 samples')
    if len({s['id'] for s in samples}) != len(samples):
        errors.append('Duplicate formula IDs')
    keys = [fingerprint(s['composition_percent']) for s in samples]
    if len(set(keys)) != len(keys):
        errors.append('Duplicate adopted compositions')
    expected = {('silicate_oxide', 'routine'): 90,
                ('silicate_oxide', 'sparse_boundary'): 30,
                ('silicate_oxide', 'interference'): 30,
                ('iron_oxide', 'routine'): 60,
                ('iron_oxide', 'sparse_boundary'): 20,
                ('iron_oxide', 'interference'): 20}
    counts = Counter((s['provenance']['matrix_type'], s['provenance']['scenario']) for s in samples)
    if dict(counts) != expected:
        errors.append('Incorrect matrix/scenario quotas')
    families = {}
    for s in samples:
        if set(s) != {'id', 'composition_percent', 'provenance'}:
            errors.append('Unsupported sample schema')
        p = s['provenance']; spec = specs[p['matrix_type']][p['scenario']]
        c, t = p['compounds_percent'], p['trace_ppm']
        limits = dict(spec['compound_ranges_percent'])
        limits[spec['balance_compound']] = spec['balance_range_percent']
        for element, bounds in limits.items():
            if not bounds[0]-1e-10 <= c.get(element, 0) <= bounds[1]+1e-10:
                errors.append(s['id']+': compound range '+element)
        for element, value in t.items():
            bounds = spec['trace_ranges_ppm'][element]
            if value != 0 and not bounds[0]-1e-10 <= value <= bounds[1]+1e-10:
                errors.append(s['id']+': trace range '+element)
        try:
            rebuilt, _ = components_to_elements(c, t, closure='strict')
            if fingerprint(rebuilt) != fingerprint(s['composition_percent']):
                errors.append(s['id']+': conversion differs')
        except ValueError as exc:
            errors.append(s['id']+': invalid conversion: '+str(exc))
        if abs(sum(s['composition_percent'].values())-100) > 1e-9:
            errors.append(s['id']+': closure differs')
        families.setdefault(p['parent_family'], []).append(s)
    controls = {(0, 0), (1, 0), (0, 1), (1, 1), (10, 1)}
    interference = [v for v in families.values() if v[0]['provenance']['scenario']=='interference']
    for rows in interference:
        if len(rows) != 5 or {tuple(r['provenance']['design_detail']['control']) for r in rows} != controls:
            errors.append('Incomplete interference family')
    prior_keys = {fingerprint(s['composition_percent']) for s in previous}
    overlaps = [s['id'] for s, k in zip(samples, keys) if k in prior_keys]
    if overlaps:
        errors.append('Exact first-round composition overlap')
    elements = sorted(set().union(*(s['composition_percent'] for s in samples+previous)))
    a = np.array([[s['composition_percent'].get(e, 0) for e in elements] for s in samples])
    d = np.abs(a[:, None, :]-a[None, :, :]).sum(axis=2)
    np.fill_diagonal(d, np.inf)
    nearest = [{'formula_id':s['id'], 'nearest_formula_id':samples[int(np.argmin(d[i]))]['id'],
                'L1_element_mass_percentage_points':float(np.min(d[i])),
                'same_parent_family':s['provenance']['parent_family']==samples[int(np.argmin(d[i]))]['provenance']['parent_family']}
               for i, s in enumerate(samples)]
    historical = []
    if previous:
        b = np.array([[s['composition_percent'].get(e, 0) for e in elements] for s in previous])
        for i, s in enumerate(samples):
            dist = np.abs(a[i]-b).sum(axis=1);j=int(np.argmin(dist))
            historical.append({'formula_id':s['id'],'nearest_first_round_id':previous[j]['id'],
                               'L1_element_mass_percentage_points':float(dist[j])})
    return {'status':'passed' if not errors else 'failed','errors':errors,
            'formulas':len(samples),'unique_compositions_12dp':len(set(keys)),
            'parent_families':len(families),'interference_families':len(interference),
            'matrix_scenario_counts':{m+'/'+s:n for (m,s),n in counts.items()},
            'first_round_compositions_compared':len(previous),'exact_first_round_overlaps':overlaps,
            'nearest_within_member':nearest,'nearest_first_round':historical,
            'distance_caveat':'L1 is descriptive, no scientifically validated near-neighbour threshold is assumed; global connected groups remain pending',
            'cross_member_check':'pending_B_C_D_candidate_files'}, keys


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ranges', type=Path, required=True)
    p.add_argument('--previous-samples', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--seed', type=int, default=20261021011)
    args=p.parse_args()
    if args.out.exists():
        raise ValueError('Refusing to overwrite output directory')
    if args.seed < 0:
        raise ValueError('Seed must be nonnegative')
    specs=read(args.ranges);previous=read(args.previous_samples)['samples']
    samples=construct(specs,args.seed)
    report,keys=verify(samples,specs,previous)
    if report['errors']:
        raise ValueError(report['errors'])
    args.out.mkdir(parents=True,exist_ok=False)
    write(args.out/'A_samples.json',{'round_id':'round2-20261021','owner':'A',
          'status':'candidate_pending_global_confirmation','seed':args.seed,'samples':samples})
    write(args.out/'candidate_checks.json',report)
    write(args.out/'coverage.json',{'bin_definition':'0 < mass percent <= 0.1; not a detection limit',
          'targets':{matrix:{e:{'zero':sum(s['composition_percent'].get(e,0)==0 for s in samples if s['provenance']['matrix_type']==matrix),
                               'positive_le_0_1':sum(0<s['composition_percent'].get(e,0)<=.1 for s in samples if s['provenance']['matrix_type']==matrix),
                               'above_0_1':sum(s['composition_percent'].get(e,0)>.1 for s in samples if s['provenance']['matrix_type']==matrix)}
                            for e in TARGET_ELEMENTS} for matrix in specs}})
    with (args.out/'formula_registry.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['formula_id','owner','matrix_type','scenario','parent_family','composition_key_sha256','global_status'])
        for s,key in zip(samples,keys):
            v=s['provenance'];w.writerow([s['id'],'A',v['matrix_type'],v['scenario'],v['parent_family'],hashlib.sha256(key.encode()).hexdigest(),'pending_global_confirmation'])
    print(json.dumps({k:report[k] for k in ['status','formulas','parent_families','interference_families','exact_first_round_overlaps']},ensure_ascii=False))


if __name__=='__main__':main()
