"""Prepare 50,000 explicit conditions and 100,000 records without calculating spectra."""
from __future__ import annotations
import argparse, collections, csv, dataclasses, gzip, hashlib, json, math, pathlib, shutil, sys
import numpy as np
from prepare_global import read, write, sha, key, jsonl_gz

def physical_sha(profile):
    return hashlib.sha256(json.dumps({k:v for k,v in profile.items() if k not in ('name','calibration_status')},sort_keys=True,separators=(',',':')).encode()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repository',type=pathlib.Path,required=True);ap.add_argument('--freeze',type=pathlib.Path,required=True);args=ap.parse_args()
    repo=args.repository.resolve();freeze=args.freeze.resolve();tools=pathlib.Path(__file__).resolve().parent
    if (freeze/'record_plan_A.csv').exists():raise FileExistsError('Record plans already exist')
    if read(freeze/'global_closure.json')['status']!='passed_global_candidate_lineage_checks':raise ValueError('Global closure has not passed')
    source=repo/'datasets/round3/shared/freeze_v1/generator'
    dest=freeze/'generator';shutil.copytree(source,dest,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    dataset=dest/'fp_competition/dataset.py';original=dataset.read_text(encoding='utf-8')
    needle="            values=asdict(profile);values.update({k:float(rng.uniform(*v)) for k,v in jitter.items()})"
    replacement="""            if 'profile_override' in sample:
                if jitter: raise ValueError('Explicit condition profiles cannot be combined with jitter')
                override=sample['profile_override']
                if not isinstance(override,dict) or set(override)!=set(asdict(profile)):
                    raise ValueError('profile_override must contain the complete Profile schema')
                values=asdict(Profile.from_dict(override))
            else:
                values=asdict(profile)
            values.update({k:float(rng.uniform(*v)) for k,v in jitter.items()})"""
    if original.count(needle)!=1:raise ValueError('Pinned dataset source no longer matches the reviewed extension point')
    amended=original.replace(needle,replacement)
    note=('Each input row may carry a complete profile_override for one frozen condition. '
          'Two replicates of that row share the identical response and use different child seeds. '
          'configs/profile.json is only the fallback for rows without profile_override. '
          'Authoritative family/usage/stage assignments are external to the native batch split.\\n')
    amended=amended.replace('inputs/samples.json 是本批采用的完整输入；',note+'inputs/samples.json 是本批采用的完整输入；')
    dataset.write_text(amended,encoding='utf-8')
    (dest/'fp_competition/version.py').write_text('"""Round4 explicit-condition dataset wrapper; physics core remains 0.2.0."""\nVERSION = "0.2.2"\n',encoding='utf-8')
    for p in dest.rglob('*.py'):compile(p.read_text(encoding='utf-8-sig'),str(p),'exec')
    if sha(dest/'fp_competition/core.py')!=sha(source/'fp_competition/core.py'):raise ValueError('Physics core changed')
    sys.path.insert(0,str(dest))
    from fp_competition.core import Profile,TARGET_ELEMENTS,line_data
    from fp_competition.dataset import make_plan,environment
    import xraylib as xl
    prep=repo/'datasets/round3/shared/preparation_v1/development_profiles'
    anchors={p:read(prep/f'{p}.json') for p in ('P1','P2','P3')}
    source_profiles={p:{'path':(prep/f'{p}.json').relative_to(repo).as_posix(),'sha256':sha(prep/f'{p}.json')} for p in ('P1','P2','P3','D1','D2','D3','D4','D5','D6')}
    # These widths are inherited engineering sensitivities, not a fitted instrument population.
    dev={'gain_relative':[-.004,.004],'zero_offset_keV':[0.,.024],'noise_fwhm_multiplier':[1.,1.12],'live_time_multiplier':[1.,3.],'exit_air_offset_cm':[0.,.4]}
    held={'gain_outer_abs_relative':[.0045,.005],'zero_offset_keV':[.027,.03],'noise_fwhm_multiplier':[1.135,1.15],'exit_air_offset_cm':[.45,.5]}
    write(freeze/'profile_distribution_development.json',{'status':'frozen_design_proposal_for_review','ranges':dev,'anchors':source_profiles,'anchor_slots':2,'internal_slots':6,'boundary_slots':2,'source':'P1/P2/P3 regimes and D1/D2 gain +/-0.5%, D3 noise +15%, D4 zero +0.03keV, D5 exposure x3, D6 exit air +0.5cm; development deliberately reserves outer bands for sealed response challenge','fixed_fields':['filter_Al_um','background_counts_channel','detector_be_um','detector_si_um','mass_thickness_g_cm2','detector_distance_cm','incident_angle_deg','exit_angle_deg','scatter_angle_deg','source_step_keV','secondary_layers'],'scope_limit':'No newly calibrated response, grain/moisture/container effects or inferred real-device parameter distribution. Background/filter/sample geometry and detector window thickness remain at inherited anchor values.'})
    write(freeze/'profiles/sealed_QC_only/distribution.json',{'scope':'QC/final evaluation only; excluded from model fitting, dictionary construction and selection','challenge_ranges':held,'five_challenge_types':['negative_gain_outer_band','positive_gain_outer_band','zero_upper_band','noise_upper_band','joint_outer_gain_zero_noise_air'],'within_distribution_conditions_per_recipe':5,'challenge_conditions_per_recipe':5,'old_T1_T2_T3_reused':False,'external_blindness':False})
    # Use all known prior record seeds; preserve the incomplete-history boundary.
    historical_seeds=set();historical_opaque=set();seed_sources=[]
    for rel in ('datasets/round2/member_A/actual_record_index.csv','datasets/round3/shared/freeze_v1/record_plan.csv'):
        p=repo/rel
        with p.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                for k in ('noise_seed','seed'):
                    if r.get(k):historical_seeds.add(int(r[k]))
                if r.get('opaque_blind_id'):historical_opaque.add(r['opaque_blind_id'])
        seed_sources.append({'path':rel,'sha256':sha(p)})
    assigned=read(freeze/'family_assignments.json')['families'];fmap={f['design_family_id']:f for f in assigned}
    samples={};sample_sources={}
    for m in 'ABCD':
        p=repo/f'datasets/round4/member_{m}'/('candidates_v1' if m=='A' else 'candidates')/f'{m}_samples.json'
        sample_sources[m]={'path':p.relative_to(repo).as_posix(),'sha256':sha(p)}
        for s in read(p)['samples']:samples[s['id']]=s
    profile_records={};condition_tables={};all_records={m:[] for m in 'ABCD'};buckets=collections.defaultdict(list);static_rows=[];seen_physical=set();seen_condition=set()
    def condition(recipe,slot,group):
        cid='q'+key('condition:'+recipe+':'+str(slot))[:24]
        rng=np.random.default_rng(int(key(cid)[:16],16));anchor=tuple(anchors)[int(rng.integers(3))]
        if group=='development' and slot<2:anchor=tuple(anchors)[(int(key(recipe)[:8],16)+slot)%3]
        p=dict(anchors[anchor]);physical={k:float(rng.uniform(*bounds)) for k,bounds in dev.items()}
        mode='internal'
        if group=='development' and slot<2:physical={k:(1. if 'multiplier' in k else 0.) for k in dev};mode='anchor'
        elif group=='development' and slot>=8:
            high=slot==9;physical={k:bounds[1 if high else 0] for k,bounds in dev.items()};mode='boundary'
        elif group=='sealed_challenge':
            challenge=slot-5;mode=('negative_gain_outer_band','positive_gain_outer_band','zero_upper_band','noise_upper_band','joint_outer_gain_zero_noise_air')[challenge]
            if challenge in (0,1,4):physical['gain_relative']=float(rng.uniform(*held['gain_outer_abs_relative']))*(-1 if challenge==0 or challenge==4 and rng.random()<.5 else 1)
            if challenge in (2,4):physical['zero_offset_keV']=float(rng.uniform(*held['zero_offset_keV']))
            if challenge in (3,4):physical['noise_fwhm_multiplier']=float(rng.uniform(*held['noise_fwhm_multiplier']))
            if challenge==4:physical['exit_air_offset_cm']=float(rng.uniform(*held['exit_air_offset_cm']))
        p.update(name='round4_assumed_'+cid,gain_keV_channel=p['gain_keV_channel']*(1+physical['gain_relative']),zero_keV=p['zero_keV']+physical['zero_offset_keV'],noise_fwhm_eV=p['noise_fwhm_eV']*physical['noise_fwhm_multiplier'],live_time_s=p['live_time_s']*physical['live_time_multiplier'],exit_air_path_cm=p['exit_air_path_cm']+physical['exit_air_offset_cm'])
        pr=Profile.from_dict(p);energy=pr.zero_keV+pr.gain_keV_channel*np.arange(pr.channels);width=pr.fwhm_keV(np.array([1.,5.9,pr.voltage_kV]))
        if pr.channels!=2048 or not np.all(np.diff(energy)>0) or not np.isfinite(width).all() or np.min(width)/pr.gain_keV_channel<2:raise ValueError('Condition numerical consistency failed')
        if cid in seen_condition:raise ValueError('Condition ID collision')
        seen_condition.add(cid);digest=physical_sha(p);seen_physical.add(digest)
        result={'condition_instance_id':cid,'candidate_id':recipe,'slot':slot,'condition_group':group,'design_mode':mode,'anchor':anchor,'design_coordinates':physical,'physical_profile_sha256':digest,'profile':p}
        profile_records[cid]=result
        static_rows.append({'condition_instance_id':cid,'voltage_kV':pr.voltage_kV,'minimum_fwhm_bins':float(np.min(width)/pr.gain_keV_channel),'lower_edge_keV':float(energy[0]-.5*pr.gain_keV_channel),'upper_edge_keV':float(energy[-1]+.5*pr.gain_keV_channel),'status':'passed_static_config_no_spectrum'})
        return result
    for f in sorted(assigned,key=lambda x:x['design_family_id']):
        for recipe in f['candidate_ids']:
            rr=[]
            for slot in range(10):
                group='sealed_challenge' if f['usage']=='sealed_test' and slot>=5 else ('sealed_in_distribution' if f['usage']=='sealed_test' else 'development')
                c=condition(recipe,slot,group);rr.append(c)
                location='profiles/sealed_QC_only' if f['usage']=='sealed_test' else 'profiles/development'
                path=f'{location}/{f["member"]}_{f["usage"]}.jsonl.gz'
                condition_tables.setdefault(path,[]).append(c)
            if len({x['physical_profile_sha256'] for x in rr})!=10:raise ValueError('Ten conditions are not physically distinct: '+recipe)
            # Sealed ID and challenge are packed separately to preserve access boundaries.
            for group in (('sealed_in_distribution','sealed_challenge') if f['usage']=='sealed_test' else ('development',)):
                buckets[f['member'],f['usage'],f['training_stage'],group].append((recipe,[c for c in rr if c['condition_group']==group]))
    seen_seeds=set();seen_opaque=set();batches=[]
    for (member,usage,stage,group),recipes in sorted(buckets.items()):
        per_batch=10 if usage=='sealed_test' else 5
        for i,start in enumerate(range(0,len(recipes),per_batch),1):
            chunk=recipes[start:start+per_batch];bid=f'R4_{member}_{usage}_{stage}_{group}_{i:04d}';native_samples=[]
            for recipe,conditions in chunk:
                f=fmap[samples[recipe]['provenance']['design_family_id']]
                for c in conditions:native_samples.append({'id':c['condition_instance_id'],'composition_percent':samples[recipe]['composition_percent'],'profile_override':c['profile'],'provenance':{'round_id':'round4','original_candidate_id':recipe,'design_family_id':f['design_family_id'],'unified_family_id':f['unified_family_id'],'condition_instance_id':c['condition_instance_id'],'condition_group':group,'source_candidate_path':sample_sources[member]['path'],'source_candidate_file_sha256':sample_sources[member]['sha256'],'research_usage':usage,'training_stage':stage,'source_candidate_provenance':samples[recipe]['provenance']}})
            nonce=0
            while True:
                seed=int(key('batch-seed:'+bid+':'+str(nonce))[:16],16)%(2**63-1)
                jobs,_,split_seed=make_plan(native_samples,Profile.from_dict(anchors['P1']),2,seed,{},'strict','reject',list(TARGET_ELEMENTS),2026102501)
                children=[j[3] for j in jobs]
                if len(set(children))==len(children) and not (set(children)&(seen_seeds|historical_seeds)):break
                nonce+=1
                if nonce>100:raise ValueError('Could not resolve noise seed collision')
            seen_seeds.update(children)
            batch={'batch_id':bid,'member':member,'usage':usage,'training_stage':stage,'condition_group':group,'candidate_ids':[x[0] for x in chunk],'condition_ids':[s['id'] for s in native_samples],'batch_seed':seed,'seed_collision_nonce':nonce,'split_seed':split_seed,'spectra':len(jobs)}
            batches.append(batch)
            for k,(sample,repeat,profile,child,native_family,native_split) in enumerate(jobs,1):
                opaque=key('blind:'+str(child))[:24]
                if opaque in seen_opaque or opaque in historical_opaque:raise ValueError('Opaque ID collision')
                seen_opaque.add(opaque);prov=sample['provenance']
                all_records[member].append({'global_record_id':bid+f'/S{k:06d}','batch_id':bid,'native_id':f'S{k:06d}','opaque_blind_id':opaque,'candidate_id':prov['original_candidate_id'],'unified_family_id':prov['unified_family_id'],'member':member,'research_usage':usage,'training_stage':stage,'condition_instance_id':sample['id'],'condition_group':group,'repeat':repeat,'noise_seed':child,'profile_physical_sha256':physical_sha(dataclasses.asdict(profile)),'native_split_not_authoritative':native_split,'eligible_for_training':False,'exposure_status':'synthetic_production_not_yet_generated'})
    if sum(map(len,all_records.values()))!=100000 or len(profile_records)!=50000 or len(seen_seeds)!=100000:raise ValueError('Full plan count mismatch')
    for path,conditions in condition_tables.items():
        target=freeze/path;target.parent.mkdir(parents=True,exist_ok=True);jsonl_gz(target,conditions)
    for m,records in all_records.items():
        with (freeze/f'record_plan_{m}.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    write(freeze/'batch_plan.json',{'source_main':read(freeze/'input_identity.json')['source_main'],'spectra':100000,'conditions':50000,'noise_repeats':2,'pilot_spectra':0,'production_mode':'full_member_quota_once','batches':batches})
    write(freeze/'profile_registry.json',{'condition_files':{p:{'sha256':sha(freeze/p),'conditions':len(rr),'usage':'sealed_QC_only' if '/sealed_QC_only/' in p else 'development'} for p,rr in condition_tables.items()},'conditions':len(profile_records),'distinct_physical_profile_values':len(seen_physical),'sealed_test_requires_explicit_QC_mode':True,'old_T1_T2_T3_excluded_from_training_dictionary_and_selection':True,'fallback_profile':anchors['P1']})
    write(freeze/'scope.json',{'targets':list(TARGET_ELEMENTS),'target_unit':'elemental_mass_percent','ppm_per_percent':10000,'matrix_elements':['O'],'oxygen_is_prediction_target':False,'composition_labels':'full normalized used_percent, never normalize the 32 targets alone','source_candidate_files':sample_sources,'generator_version':'0.2.2','physical_model_version':'0.2.0','physics_core_unchanged':True,'physics_core_sha256':sha(dest/'fp_competition/core.py'),'dataset_wrapper_source_diff':'make_plan accepts a complete profile_override for each input condition; both repeats retain it; native audit/replay reconstruct those explicit jobs','atomic_library':'xraylib','environment':environment(),'coverage_limit':'Inherited homogeneous FP model, source >=1keV line cutoff, no newly validated real-device calibration or grain/moisture/container model'})
    lines={}
    for e in TARGET_ELEMENTS:
        lines[e]=[{'transition':name,'energy_keV':energy} for name,code,energy in line_data(xl.SymbolToAtomicNumber(e))]
    write(freeze/'target_line_table.json',{'provider':'installed_xraylib','version':getattr(xl,'__version__',None),'minimum_modeled_line_keV':1.,'elements':lines,'scope':'structural modeled transitions only, not a concentration/LOD claim'})
    budget=read(repo/'datasets/round3/shared/preparation_v1/window_budget.json');budget['round_id']='round4';budget['policy']='Inherited preregistered numeric window guardrails; apply to every actual record in full production and full QC. Failed records are retained, not deleted or post-hoc budget-relaxed.';write(freeze/'window_budget.json',budget)
    write(freeze/'static_preflight.json',{'status':'passed_no_spectrum_preflight','conditions_checked':len(static_rows),'planned_records':sum(map(len,all_records.values())),'batch_count':len(batches),'pilot_spectra_generated':0,'spectra_generated':0,'checks':['Profile schema/positive parameters','2048 increasing channel-energy axis','Fano/noise width positive and at least 2 channels at modeled >=1keV energies','10 distinct physical conditions per candidate excluding profile names','same condition retained in both noise repeats','100000 unique child seeds and opaque IDs','exact whole-family roles/stage quotas'],'minimum_fwhm_bins':min(x['minimum_fwhm_bins'] for x in static_rows),'actual_window_and_full_physics_QC':'required per actual generated record; not executed by static preflight','historical_seed_sources':seed_sources,'known_historical_noise_seeds':len(historical_seeds),'historical_noise_registry_limit':'Round3 complete frozen noise plan plus available Round2 A index. Round1 and unavailable Round2 member record seeds are not claimed as exhaustively checked.'})
    report={}
    for m,records in all_records.items():report[m]={'records':len(records),'roles':dict(collections.Counter(r['research_usage'] for r in records)),'batches':sum(b['member']==m for b in batches),'sealed_condition_groups':dict(collections.Counter(r['condition_group'] for r in records if r['research_usage']=='sealed_test'))}
    write(freeze/'plan_summary.json',{'status':'prepared_pending_review','members':report,'production_approved':False,'spectra_generated':0,'no_pilot':True})
    identity=read(freeze/'input_identity.json')
    extra=[repo/e['path'] for e in seed_sources]+[repo/e['path'] for e in source_profiles.values()]
    extra += [p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    for path in extra:identity['sources'][path.relative_to(repo).as_posix()]={'sha256':sha(path),'bytes':path.stat().st_size}
    write(freeze/'input_identity.json',identity)
    print(json.dumps({'status':'prepared_no_spectrum_full_plan','members':report,'conditions':len(profile_records),'batches':len(batches),'spectra_generated':0},ensure_ascii=False))

if __name__=='__main__':main()
