"""Independent exhaustive checks of the frozen record/config plans; no forward spectra."""
from __future__ import annotations
import argparse, collections, dataclasses, gzip, hashlib, json, pathlib, subprocess, sys
from prepare_global import read,write,sha,key
from prepare_conditions import physical_sha
from run_member import rows_csv

def check(condition,message):
    if not condition:raise ValueError(message)

def compatibility_digest(generator):
    code="""import sys,json,hashlib,dataclasses
sys.path.insert(0,sys.argv[1])
from fp_competition.core import Profile
from fp_competition.dataset import make_plan
samples=[{'id':'a','composition_percent':{'Fe':100.}},{'id':'b','composition_percent':{'O':50.,'Si':50.}},{'id':'c','composition_percent':{'Na':1.,'O':49.,'Si':50.}}]
alljobs=[]
for seed in (0,20261025,202610240702):
 jobs,targets,splitseed=make_plan(samples,Profile(),2,seed,{'gain_keV_channel':[.0137,.0139]},'strict','reject',['Fe','O','Si','Na'],2026102501)
 alljobs += [(s['id'],r,dataclasses.asdict(p),child,family,split) for s,r,p,child,family,split in jobs]
print(hashlib.sha256(json.dumps(alljobs,sort_keys=True,separators=(',',':')).encode()).hexdigest())
"""
    p=subprocess.run([sys.executable,'-B','-',str(generator)],input=code,text=True,encoding='utf-8',capture_output=True,check=True)
    return p.stdout.strip()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repository',type=pathlib.Path,required=True);p.add_argument('--freeze',type=pathlib.Path,required=True);args=p.parse_args()
    repo=args.repository.resolve();freeze=args.freeze.resolve();sys.path.insert(0,str(freeze/'generator'))
    from fp_competition.core import Profile
    from fp_competition.dataset import make_plan
    original=repo/'datasets/round3/shared/freeze_v1/generator';new=freeze/'generator'
    check(sha(original/'fp_competition/core.py')==sha(new/'fp_competition/core.py'),'Physics core changed')
    check(sha(original/'fp_competition/minerals.py')==sha(new/'fp_competition/minerals.py'),'Composition conversion changed')
    old_digest=compatibility_digest(original);new_digest=compatibility_digest(new)
    check(old_digest==new_digest,'Existing batch sampling changed')
    base=dataclasses.asdict(Profile());custom={**base,'gain_keV_channel':base['gain_keV_channel']*1.003}
    sample={'id':'explicit_condition','composition_percent':{'Fe':100.},'profile_override':custom}
    jobs,_,_=make_plan([sample],Profile(),2,20261025,{},'strict','reject',['Fe'],2026102501)
    check(dataclasses.asdict(jobs[0][2])==custom==dataclasses.asdict(jobs[1][2]) and jobs[0][3]!=jobs[1][3],'Explicit condition repeats changed profile or repeated seed')
    invalid=[({**sample,'profile_override':{'gain_keV_channel':.01}},{}),({**sample,'profile_override':{**custom,'gain_keV_channel':-1}},{}),(sample,{'zero_keV':[0.,.1]}),({**sample,'composition_percent':{'Fe':90.}}, {})]
    for s,jitter in invalid:
        try:make_plan([s],Profile(),2,1,jitter,'strict','reject',['Fe'],1)
        except ValueError:pass
        else:raise ValueError('An invalid explicit-profile plan was accepted')
    registry=read(freeze/'profile_registry.json');dist=read(freeze/'profile_distribution_development.json');dev=dist['ranges'];held=read(freeze/'profiles/sealed_QC_only/distribution.json')['challenge_ranges']
    anchors={k:read(repo/v['path']) for k,v in dist['anchors'].items() if k.startswith('P')}
    forbidden=set()
    for t in ('T1','T2','T3'):
        q=repo/f'datasets/round3/shared/preparation_v1/heldout_profiles_qc_only/{t}.json'
        forbidden.add(physical_sha(read(q)))
    conditions={};recipes=collections.defaultdict(list);groups=collections.Counter();maximum_profile_error=0.
    for rel,entry in registry['condition_files'].items():
        check(sha(freeze/rel)==entry['sha256'],'Condition file hash changed')
        count=0
        with gzip.open(freeze/rel,'rt',encoding='utf-8') as f:
            for line in f:
                c=json.loads(line);cid=c['condition_instance_id'];pr=Profile.from_dict(c['profile']);coords=c['design_coordinates'];anchor=anchors[c['anchor']]
                check(cid not in conditions,'Repeated condition ID');conditions[cid]=c;recipes[c['candidate_id']].append(c);groups[c['condition_group']]+=1;count+=1
                check(physical_sha(c['profile'])==c['physical_profile_sha256'] and physical_sha(c['profile']) not in forbidden,'Physical profile digest/old T isolation failed')
                expected={'gain_keV_channel':anchor['gain_keV_channel']*(1+coords['gain_relative']),'zero_keV':anchor['zero_keV']+coords['zero_offset_keV'],'noise_fwhm_eV':anchor['noise_fwhm_eV']*coords['noise_fwhm_multiplier'],'live_time_s':anchor['live_time_s']*coords['live_time_multiplier'],'exit_air_path_cm':anchor['exit_air_path_cm']+coords['exit_air_offset_cm']}
                for field,value in expected.items():
                    maximum_profile_error=max(maximum_profile_error,abs(c['profile'][field]-value));check(c['profile'][field]==value,'Condition coordinates do not reconstruct the profile')
                for field in dist['fixed_fields']:check(c['profile'][field]==anchor[field],'An unsupported/fixed field was varied')
                if c['condition_group']!='sealed_challenge':check(all(bounds[0]<=coords[k]<=bounds[1] for k,bounds in dev.items()),'Development condition entered a reserved response band')
                else:
                    outside=not all(bounds[0]<=coords[k]<=bounds[1] for k,bounds in dev.items());check(outside,'Sealed challenge is inside all development ranges')
                    check(abs(coords['gain_relative'])<=.005 and 0<=coords['zero_offset_keV']<=.03 and 1<=coords['noise_fwhm_multiplier']<=1.15 and 0<=coords['exit_air_offset_cm']<=.5,'Challenge response outside inherited sensitivity ranges')
        check(count==entry['conditions'],'Condition-file record count mismatch')
    for recipe,rr in recipes.items():
        check(len(rr)==10 and len({r['physical_profile_sha256'] for r in rr})==10,'A recipe lacks 10 distinct physical conditions')
        counts=collections.Counter(c['condition_group'] for c in rr)
        check(counts in ({'development':10},{'sealed_in_distribution':5,'sealed_challenge':5}),'Condition groups per recipe differ from plan')
    seeds=set();opaque=set();globalids=set();repeat_counts=collections.Counter();family_roles=collections.defaultdict(set);rolecounts=collections.Counter();source_history=set()
    for rel in ('datasets/round2/member_A/actual_record_index.csv','datasets/round3/shared/freeze_v1/record_plan.csv'):
        for row in rows_csv(repo/rel):
            for field in ('noise_seed','seed'):
                if row.get(field):source_history.add(int(row[field]))
    for member in 'ABCD':
        rr=rows_csv(freeze/f'record_plan_{member}.csv')
        check(len(rr)==(40000 if member=='A' else 20000),'Member quota changed')
        for r in rr:
            seed=int(r['noise_seed']);oid=r['opaque_blind_id'];gid=r['global_record_id'];cid=r['condition_instance_id'];c=conditions[cid]
            check(seed not in seeds and seed not in source_history and oid not in opaque and gid not in globalids,'Global or historical seed/ID collision')
            check(oid==key('blind:'+str(seed))[:24],'Opaque ID reconstruction failed')
            check(c['candidate_id']==r['candidate_id'] and c['condition_group']==r['condition_group'] and c['physical_profile_sha256']==r['profile_physical_sha256'],'Record/condition join mismatch')
            check((r['research_usage']=='sealed_test')==(r['condition_group'].startswith('sealed_')),'Sealed/development usage isolation failed')
            seeds.add(seed);opaque.add(oid);globalids.add(gid);repeat_counts[cid]+=1;family_roles[r['unified_family_id']].add((r['research_usage'],r['training_stage']));rolecounts[r['research_usage']]+=1
    check(len(seeds)==100000 and len(conditions)==50000 and set(repeat_counts.values())=={2},'Global records/condition repeats differ')
    check(all(len(v)==1 for v in family_roles.values()) and len(family_roles)==1600,'Unified family crossed role/stage')
    check(rolecounts=={'train':80000,'validation':10000,'sealed_test':10000},'Global roles differ')
    with gzip.open(freeze/'historical_compositions.jsonl.gz','rt',encoding='utf-8') as stream:
        history=[json.loads(line) for line in stream]
    historical_tokens={str(a[k]) for h in history for a in h['aliases'] for k in ('id','parent') if a.get(k)}
    current_families=set(family_roles)
    for member in 'ABCD':
        path=repo/f'datasets/round4/member_{member}'/('candidates_v1' if member=='A' else 'candidates')/f'{member}_samples.json'
        for row in read(path)['samples']:
            prov=row['provenance'];claims=[prov.get(k) for k in ('parent_family','historical_parent_id','root_parent','root_parent_id','generator_family')]
            if isinstance(prov.get('lineage'),dict):claims.extend(prov['lineage'].get(k) for k in ('parent_family','historical_parent_id','root_parent','root_parent_id'))
            for value in claims:
                if value is None:continue
                check(str(value) not in historical_tokens,'An explicit historical parent was not closed')
                check(str(value) not in current_families or str(value)==prov['design_family_id'],'An explicit current cross-family parent was not closed')
    result={'status':'passed_independent_no_spectrum_verification','records':len(seeds),'conditions':len(conditions),'families':len(family_roles),'recipes':len(recipes),'roles':dict(rolecounts),'conditions_by_group':dict(groups),'legacy_plan_compatibility_sha256':old_digest,'explicit_profile_negative_cases_rejected':len(invalid),'same_profile_two_distinct_noise_seeds':True,'known_historical_noise_seeds_checked':len(source_history),'explicit_current_and_historical_parent_claims_checked':True,'maximum_profile_coordinate_rebuild_error':maximum_profile_error,'physics_core_unchanged':True,'old_T_profiles_reused':False,'pilot_spectra':0,'spectra_generated':0,'production_approved':False,'forward_physics_and_window_QC':'must execute on every actual generated record during the full production job'}
    write(freeze/'independent_static_verification.json',result);print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
