"""Rebuild member D candidates and check failure paths, shared hashes and readiness.

Runs the candidate construction twice from a fresh process and refuses any drift in
the published artifacts, the shared preparation inputs or the frozen generator copies.
Nothing here generates spectra.
"""
from __future__ import annotations
import collections, copy, json, os, pathlib, platform, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import build_candidates as build

def main():
    compiled = []
    for path in [HERE/'build_candidates.py', pathlib.Path(__file__), ROOT/'datasets/round3/shared/prepare_inputs.py'] + sorted((HERE/'inputs/generator/fp_competition').rglob('*.py')):
        compile(path.read_text(encoding='utf-8-sig'), str(path), 'exec'); compiled.append(path.relative_to(ROOT).as_posix())
    saved = build.read(HERE/'candidates/D_samples.json')['samples']
    families = build.read(HERE/'candidates/family_registry.json')['design_families']
    manifest = build.read(HERE/'inputs/source_manifest.json')
    for relative, digest in manifest['files'].items():
        if build.sha(HERE/'inputs'/relative) != digest: raise ValueError('Source input changed: '+relative)
    specs = build.read(HERE/'inputs/design_ranges.json'); history, sources, archive = build.historical()
    rebuilt, rebuilt_families = build.construct(specs, build.assignment('D'))
    if saved != rebuilt or families != rebuilt_families: raise ValueError('Deterministic candidate rebuild differs')
    report = build.verify(saved, families, specs, history)
    report['cross_member_checks'] = {owner: build.cross_member(saved, ROOT/f'datasets/round3/member_{owner}/candidates{"_v1" if owner=="A" else ""}/{owner}_samples.json', owner) for owner in 'ABC'}
    if report['errors']: raise ValueError(report['errors'])
    published = build.assignment('D'); derived = build.allocation()
    if [f['design_family_id'] for f in published] != [f['design_family_id'] for f in derived if f['owner']=='D']:
        raise ValueError('Published allocation ordering differs')
    allocation_checks = {}
    for member in 'ABCD':
        assigned = [f for f in derived if f['owner']==member]
        by_category = collections.Counter(f['category'] for f in assigned)
        by_matrix = collections.Counter(f['matrix'] for f in assigned)
        assert by_category == {'ladder':15,'interference':10,'paired_negative_spike':30,'routine':50}, member
        assert by_matrix == {'silicate_oxide':63,'iron_oxide':42}, member
        assert sum(f['variants'] for f in assigned) == 250, member
        allocation_checks[member] = {'families':len(assigned),'recipes':sum(f['variants'] for f in assigned),'category_families':dict(by_category),'matrix_families':dict(by_matrix)}
    assert len({f['design_seed'] for f in derived}) == 420
    for e in build.FOCUS:
        group = [f for f in derived if f['category']=='ladder' and f['target']==e]
        assert len(group)==10 and sum(f['matrix']=='silicate_oxide' for f in group)==6
    for a,b in build.PAIRS:
        group = [f for f in derived if f['category']=='interference' and f['target']==a and f['interferent']==b]
        assert len(group)==5 and sum(f['matrix']=='silicate_oxide' for f in group)==3
    cases = {}
    def reject(name, mutate):
        rows = copy.deepcopy(saved); fs = copy.deepcopy(families); mutate(rows, fs)
        result = build.verify(rows, fs, specs, history)
        if not result['errors']: raise ValueError('Failure case accepted: '+name)
        cases[name] = {'rejected':True,'errors':result['errors'][:6]}
    reject('missing_variant', lambda rows, fs: rows.pop(0))
    reject('duplicate_ID_and_composition', lambda rows, fs: rows.__setitem__(1, copy.deepcopy(rows[0])))
    def contaminate(rows, fs):
        row = next(r for r in rows if r['provenance']['target']=='Na' and r['provenance']['control_role']=='zero')
        row['composition_percent']['Na'] = .001; row['composition_percent']['O'] -= .001
    reject('Na_zero_contaminated_by_unrecorded_source', contaminate)
    def wrong_delta(rows, fs):
        rows[0]['provenance']['conversion']['intervention']['element_delta_percentage_points']['O'] += .1
    reject('mass_compensation_ledger_tampered', wrong_delta)
    def wrong_background(rows, fs):
        rows[1]['provenance']['original_compounds_percent']['NaCl'] += .01
        rows[1]['provenance']['original_compounds_percent']['SiO2'] -= .01
    reject('paired_original_background_tampered', wrong_background)
    def split_family(rows, fs):
        target = next(f for f in fs if f['category']=='ladder')
        row = next(r for r in rows if r['id']==target['sample_ids'][-1])
        row['provenance']['parent_family'] = target['design_family_id']+'_SPLIT'
        row['id'] = row['provenance']['parent_family']+'_V01'
    reject('family_split_moves_a_matched_variant_out', split_family)
    prep = ROOT/'datasets/round3/shared/preparation_v1'; premanifest = build.read(prep/'preparation_manifest.json')
    for relative, digest in premanifest['files'].items():
        if build.sha(prep/relative) != digest: raise ValueError('Prepared input changed: '+relative)
    assert premanifest['production_approved'] is False
    registry = build.read(prep/'profile_registry.json')
    assert set(registry['development_allowlist']).isdisjoint(registry['model_forbidden'])
    assert len(registry['development_allowlist'])==9 and len(registry['model_forbidden'])==3
    numeric = build.read(prep/'profile_numeric_checks.json'); assert not numeric['errors'] and numeric['forward_calculations']==24
    source = build.read(prep/'source_identity.json')
    for name, digest in source['generator_source_sha256'].items():
        if build.sha(HERE/'inputs/generator/fp_competition'/name) != digest: raise ValueError('Generator source differs: '+name)
    budget = build.read(prep/'window_budget.json')
    repository = build.read(HERE/'inputs/repository_source.json')
    ready = {'status':'pending_global_freeze','production_approved':False,'production_started':False,'actual_training_spectra':0,
        'D_candidates_checked':True,'repository_snapshot':repository['main'],
        'other_member_candidates_in_snapshot':{m:any(p.startswith(f'datasets/round3/member_{m}/candidates') for p in repository['round3_paths']) for m in 'ABC'},
        'pending':['global historical-family connected closure and final use split','per-family profile mapping (1 anchor + 2 development conditions) and long-exposure ladder coverage','all count-noise sub-seeds and global collision check','formal production source/dependency snapshot, exact commands and profile freeze','D 15-recipe x 6 = 90-spectrum pilot from confirmed training families','assigned held-out T1/T2/T3 challenge spectra','full-batch audit, full physical replay and pack'],
        'window_budget_carried_forward':budget,'note':'No spectra were generated; candidate-stage checks only. 24 probe forward checks in shared preparation are parameter QA, not the D pilot.'}
    build.write(HERE/'reports/production_readiness.json', ready)
    build.write(HERE/'candidates/candidate_checks.json', report)
    identity = build.read(HERE/'candidates/input_identity.json')
    identity['builder_sha256'] = build.sha(HERE/'build_candidates.py')
    identity['ranges'] = {'path':'datasets/round3/member_D/inputs/design_ranges.json','sha256':build.sha(HERE/'inputs/design_ranges.json')}
    identity['rebuilt_exactly_with_final_builder'] = True
    build.write(HERE/'candidates/input_identity.json', identity)
    import numpy, scipy, xraylib
    result = {'status':'passed_candidate_and_preparation_checks_pending_global_freeze','round_id':'round3','owner':'D',
        'compiled_sources':compiled,'candidate_rebuild_exact':True,'D_recipes':len(saved),'D_design_families':len(families),
        'global_design_assignments':allocation_checks,'design_seeds_unique':420,'failure_cases':cases,
        'prepared_files_hash_checked':len(premanifest['files']),'profile_numeric_checks':24,
        'generator_source_hash_checked':len(source['generator_source_sha256']),
        'historical_rows_compared':len(history),
        'historical_minimum_L1_percentage_points':min(r['minimum_L1_percentage_points'] for r in report['historical_nearest']),
        'historical_L1_le_0_5_matches':sum(r['requires_train_only'] for r in report['historical_nearest']),
        'cross_design_family_near_edges':len(report['cross_design_family_near_edges']),
        'cross_member_checks':{owner:{k:v for k,v in check.items() if k not in ['near_duplicate_edges']} for owner,check in report['cross_member_checks'].items()},
        'exact_zero_labels_verified':report['exact_zero_labels_verified'],
        'environment':{'python':sys.version.split()[0],'implementation':platform.python_implementation(),'system':platform.system(),'machine':platform.machine(),
            'numpy':numpy.__version__,'scipy':scipy.__version__,'xraylib':getattr(xraylib,'__version__','unknown'),
            'bit_generator': numpy.random.PCG64.__name__+' (numpy.random.default_rng default)',
            'thread_environment':{k:os.environ.get(k) for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']}},
        'physics_source_unchanged':True,'production_started':False,'training_spectra_generated':0,'eligible_for_training':False,
        'scientific_accuracy_verified':False}
    build.write(HERE/'reports/verification.json', result)
    print(json.dumps({k: result[k] for k in ['status','D_recipes','D_design_families','candidate_rebuild_exact','historical_minimum_L1_percentage_points','historical_L1_le_0_5_matches','cross_design_family_near_edges','exact_zero_labels_verified','failure_cases']}, ensure_ascii=False))
    print(json.dumps({owner:{k:check[k] for k in ['status','minimum_L1_percentage_points','pairs_within_L1_0_5']} for owner,check in result['cross_member_checks'].items()}, ensure_ascii=False))

if __name__=='__main__': main()
