"""Rebuild A candidates and check failure paths, shared hashes and current readiness."""
from __future__ import annotations
import collections, copy, importlib.util, pathlib, sys
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
import build_candidates as build

def main():
    compiled=[]
    for path in [HERE/'build_candidates.py',pathlib.Path(__file__),ROOT/'datasets/round3/shared/prepare_inputs.py']+sorted((HERE/'inputs/generator/fp_competition').rglob('*.py')):
        compile(path.read_text(encoding='utf-8-sig'),str(path),'exec');compiled.append(path.relative_to(ROOT).as_posix())
    saved=build.read(HERE/'candidates_v1/A_samples.json')['samples'];families=build.read(HERE/'candidates_v1/family_registry.json')['design_families']
    source_manifest=build.read(HERE/'inputs/source_manifest.json')
    for relative,digest in source_manifest['files'].items():
        if build.sha(HERE/'inputs'/relative)!=digest:raise ValueError('Source input changed: '+relative)
    specs=build.read(HERE/'inputs/design_ranges.json');history,sources=build.historical()
    rebuilt,rebuilt_families=build.construct(specs,build.allocation())
    if saved!=rebuilt or families!=rebuilt_families:raise ValueError('Deterministic candidate rebuild differs')
    report=build.verify(saved,families,specs,history)
    if report['errors']:raise ValueError(report['errors'])
    assignments=build.allocation();allocation_checks={}
    for member in 'ABCD':
        assigned=[f for f in assignments if f['owner']==member]
        by_category=collections.Counter(f['category'] for f in assigned)
        by_matrix=collections.Counter(f['matrix'] for f in assigned)
        assert by_category=={'ladder':15,'interference':10,'paired_negative_spike':30,'routine':50}
        assert by_matrix=={'silicate_oxide':63,'iron_oxide':42}
        assert sum(f['variants'] for f in assigned)==250
        allocation_checks[member]={'families':len(assigned),'recipes':sum(f['variants'] for f in assigned),'category_families':dict(by_category),'matrix_families':dict(by_matrix)}
    assert len({f['design_seed'] for f in assignments})==420
    for e in build.FOCUS:
        group=[f for f in assignments if f['category']=='ladder' and f['target']==e]
        assert len(group)==10 and sum(f['matrix']=='silicate_oxide' for f in group)==6
    for a,b in build.PAIRS:
        group=[f for f in assignments if f['category']=='interference' and f['target']==a and f['interferent']==b]
        assert len(group)==5 and sum(f['matrix']=='silicate_oxide' for f in group)==3
    cases={}
    def reject(name,mutate):
        rows=copy.deepcopy(saved);fs=copy.deepcopy(families);mutate(rows,fs)
        result=build.verify(rows,fs,specs,history)
        if not result['errors']:raise ValueError('Failure case accepted: '+name)
        cases[name]={'rejected':True,'errors':result['errors'][:6]}
    reject('missing_variant',lambda rows,fs:rows.pop(0))
    reject('duplicate_ID_and_composition',lambda rows,fs:rows.__setitem__(1,copy.deepcopy(rows[0])))
    def contaminate(rows,fs):
        row=next(r for r in rows if r['provenance']['target']=='Na' and r['provenance']['control_role']=='zero')
        row['composition_percent']['Na']=.001;row['composition_percent']['O']-=.001
    reject('Na_zero_contaminated_by_unrecorded_source',contaminate)
    def wrong_delta(rows,fs):
        rows[0]['provenance']['conversion']['intervention']['element_delta_percentage_points']['O']+=.1
    reject('mass_compensation_ledger_tampered',wrong_delta)
    def wrong_background(rows,fs):
        rows[1]['provenance']['original_compounds_percent']['NaCl']+=.01
        rows[1]['provenance']['original_compounds_percent']['SiO2']-=.01
    reject('paired_original_background_tampered',wrong_background)
    prep=ROOT/'datasets/round3/shared/preparation_v1';manifest=build.read(prep/'preparation_manifest.json')
    for relative,digest in manifest['files'].items():
        if build.sha(prep/relative)!=digest:raise ValueError('Prepared input changed: '+relative)
    assert manifest['production_approved'] is False
    profile_registry=build.read(prep/'profile_registry.json')
    assert set(profile_registry['development_allowlist']).isdisjoint(profile_registry['model_forbidden'])
    assert len(profile_registry['development_allowlist'])==9 and len(profile_registry['model_forbidden'])==3
    numeric=build.read(prep/'profile_numeric_checks.json');assert not numeric['errors'] and numeric['forward_calculations']==24
    source=build.read(prep/'source_identity.json')
    for name,digest in source['generator_source_sha256'].items():assert build.sha(HERE/'inputs/generator/fp_competition'/name)==digest
    remote=build.read(HERE/'inputs/repository_source.json')
    paths=set(remote['round3_blob_paths'])
    members_with_candidates={m:any(p.startswith(f'datasets/round3/member_{m}/') and ('samples' in p.lower() or 'candidates/' in p) for p in paths) for m in 'BCD'}
    ready={'status':'pending_global_freeze','production_approved':False,'production_started':False,'actual_training_spectra':0,'A_candidates_checked':True,'repository_snapshot':remote['plan_ref'],'B_C_D_candidates_in_snapshot':members_with_candidates,'pending':['B/C/D actual candidate recipes and provenance','global historical-family connected closure and final use split','family/profile mapping with long-exposure ladder coverage','all count-noise seeds and global collision check','formal production source/dependency snapshots, exact commands and profile freeze','full candidate profile window QC and 90-spectrum A training pilot','final frozen count and measured runtime/disk budget'],'note':'24 deterministic probe forward checks are parameter QA, not production spectra or the required 90-spectrum pilot.'}
    build.write(HERE/'reports/production_readiness.json',ready)
    build.write(HERE/'candidates_v1/candidate_checks.json',report)
    identity=build.read(HERE/'candidates_v1/input_identity.json');identity['builder_sha256']=build.sha(HERE/'build_candidates.py');identity['ranges']={'path':'datasets/round3/member_A/inputs/design_ranges.json','sha256':build.sha(HERE/'inputs/design_ranges.json')};identity['rebuilt_exactly_with_final_builder']=True;build.write(HERE/'candidates_v1/input_identity.json',identity)
    result={'status':'passed_candidate_and_preparation_checks_pending_global_freeze','compiled_sources':compiled,'candidate_rebuild_exact':True,'A_recipes':len(saved),'A_design_families':len(families),'global_design_assignments':allocation_checks,'design_seeds_unique':420,'failure_cases':cases,'prepared_files_hash_checked':len(manifest['files']),'profile_numeric_checks':24,'historical_rows_compared':len(history),'historical_minimum_L1_percentage_points':min(r['minimum_L1_percentage_points'] for r in report['historical_nearest']),'historical_L1_le_0_5_matches':sum(r['requires_train_only'] for r in report['historical_nearest']),'cross_design_family_near_edges':len(report['cross_design_family_near_edges']),'physics_source_unchanged':True,'production_started':False,'training_spectra_generated':0,'eligible_for_training':False}
    build.write(HERE/'reports/verification.json',result)
    print(__import__('json').dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
