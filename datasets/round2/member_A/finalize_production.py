"""Summarize actual A native shard artifacts without editing sealed bundles."""
from __future__ import annotations
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
FROZEN=HERE/'production_inputs_v2'
DATA=HERE/'production_v2'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def main():
    status=read(DATA/'run_status.json')
    if status['status']!='selfcheck_passed' or status['spectra_selfchecked']!=1500:
        raise ValueError('All 30 full audit/replay/package tasks must finish first')
    frozen=read(FROZEN/'freeze_manifest.json')
    if any(sha(FROZEN/p)!=h for p,h in frozen['files'].items()):
        raise ValueError('Frozen input changed')
    config=read(FROZEN/'A_run_config.json')
    samples=read(FROZEN/'A_samples.json')['samples'];samplemap={s['id']:s for s in samples}
    rows=[];archive_rows=[];pairs=defaultdict(list);seeds=set();conditions=Counter();replays=[]
    for batch,task in config['batches'].items():
        root=DATA/(batch+'_dataset');m=read(root/'manifest.json');state=read(DATA/(batch+'_state.json'))
        audit=read(DATA/(batch+'_audit.json'));replay=read(DATA/(batch+'_replay.json'))
        if state['status']!='selfcheck_passed' or audit['status']!='passed' or audit['errors']:
            raise ValueError(batch+': selfcheck/audit failed')
        if replay['status'] not in ('passed','passed_with_environment_differences') or replay['errors']:
            raise ValueError(batch+': replay failed')
        if replay['scope']!='all_records' or not replay['complete_physics_recalculation'] or replay['spectra_recalculated']!=50:
            raise ValueError(batch+': replay coverage incomplete')
        if m['status']!='complete' or m['spectrum_count']!=50 or len(m['records'])!=50:
            raise ValueError(batch+': incomplete records')
        if m['jitter_ranges']!={} or m['replicates']!=2 or m['seed']!=task['seed']:
            raise ValueError(batch+': condition/seed differs')
        if read(root/'configs/profile.json')!=read(FROZEN/'profiles'/(task['profile_id']+'.json')):
            raise ValueError(batch+': profile differs')
        for role,source in [('samples',FROZEN/task['samples']),('profile',FROZEN/'profiles'/(task['profile_id']+'.json')),('design_ranges',FROZEN/'design_ranges.json')]:
            if m['original_inputs'][role]['sha256']!=sha(source):raise ValueError(batch+': source input hash differs')
        truths={r['id']:r for r in map(json.loads,(root/'truth.jsonl').read_text(encoding='utf-8').splitlines())}
        for record in m['records']:
            t=truths[record['id']];sample=samplemap[t['original_sample_id']];p=sample['provenance']
            if t['source_provenance']!=p:raise ValueError('Provenance differs')
            if t['seed'] in seeds:raise ValueError('Duplicate child seed')
            seeds.add(t['seed']);conditions[task['profile_id']]+=1
            if sha(root/record['file'])!=record['blind_input_sha256'] or sha(root/record['full_results'])!=record['full_results_sha256']:
                raise ValueError('Record hash mismatch')
            full=read(root/record['full_results']);blind=read(root/record['file'])
            if set(blind)!={'axis','signal_unit','synthetic','x','counts'}:
                raise ValueError('Unexpected blind fields')
            for e,v in sample['composition_percent'].items():
                if abs(full['composition']['used_percent'].get(e,0)-v)>1e-10:
                    raise ValueError('Adopted composition differs')
            key=(sample['id'],task['profile_id']);pairs[key].append((t['repeat'],full['expected_counts']))
            public_id='XR2_'+hashlib.sha256(('R2_A_'+batch+'/'+record['id']).encode()).hexdigest()[:24]
            rows.append({'global_id':'R2_A_'+batch+'/'+record['id'],'blind_public_id':public_id,
                'owner':'A','round_id':'round2-20261021',
                'batch_id':batch,'local_id':record['id'],'formula_id':sample['id'],
                'parent_family':p['parent_family'],'matrix_type':p['matrix_type'],
                'scenario':p['scenario'],'profile_id':task['profile_id'],'repeat':t['repeat'],
                'seed':t['seed'],'generator_family':t['family'],'generator_split':t['split'],
                'benchmark_split':'pending_global_family_split','eligible_for_training':False,
                'blind_file':str((root/record['file']).relative_to(HERE)).replace('\\','/'),
                'full_file':str((root/record['full_results']).relative_to(HERE)).replace('\\','/'),
                'blind_sha256':record['blind_input_sha256'],'full_sha256':record['full_results_sha256']})
        archive=DATA/(batch+'_dataset.zip');digest=sha(archive)
        if not archive.with_suffix('.zip.sha256').read_text(encoding='utf-8').startswith(digest):
            raise ValueError('External archive hash mismatch')
        archive_rows.append({'batch':batch,'profile_id':task['profile_id'],'spectra':50,
            'zip':archive.name,'sha256':digest,'bytes':archive.stat().st_size,
            'audit':batch+'_audit.json','audit_sha256':sha(DATA/(batch+'_audit.json')),
            'replay':batch+'_replay.json','replay_sha256':sha(DATA/(batch+'_replay.json')),
            'replay_seconds':next(c['seconds'] for c in state['completed_commands'] if c['stage']=='replay'),
            'generation_seconds':next(c['seconds'] for c in state['completed_commands'] if c['stage']=='generation')})
        replays.append(replay)
    if len(rows)!=1500 or len({r['global_id'] for r in rows})!=1500 or len(pairs)!=750:
        raise ValueError('Wrong complete sample/profile/record coverage')
    if len({r['blind_public_id'] for r in rows})!=1500:
        raise ValueError('Opaque blind IDs collide')
    for key,reps in pairs.items():
        if len(reps)!=2 or len({r[0] for r in reps})!=2 or reps[0][1]!=reps[1][1]:
            raise ValueError('Replicates do not differ only in count noise: '+str(key))
    if dict(conditions)!={'P1':500,'P2':500,'P3':500}:raise ValueError('Condition quotas differ')
    with (HERE/'actual_record_index.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with (HERE/'actual_record_index.jsonl').open('w',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
    write(HERE/'package_manifest.json',{'round_id':'round2-20261021','owner':'A','packages':archive_rows})
    verification={'status':'passed','actual_records':1500,'formulas':250,'parent_families':210,
        'sealed_shards':30,'profiles':dict(conditions),'noise_pairs_checked':len(pairs),
        'pairs_expected_arrays_exactly_equal':True,'child_seeds_unique':len(seeds),
        'actual_blind_and_full_hashes_checked':1500,'frozen_inputs_byte_identity':True,
        'all_replays_full':True,'replay_total':sum(r['spectra_recalculated'] for r in replays),
        'replay_same_environment':all(r['same_environment'] for r in replays),
        'replay_maximum_absolute_array_difference':max(r['maximum_absolute_array_difference'] for r in replays),
        'sealed_bundles_modified':False,'cross_member_checks':'pending','scientific_accuracy_verified':False}
    write(HERE/'final_artifact_checks.json',verification)
    summary={'round_id':'round2-20261021','owner':'A','version':'A-sharded-production-v2',
        'status':'selfcheck_passed_pending_global_inclusion','actual_formulas':250,
        'parent_families':210,'complete_interference_families':10,'actual_spectra':1500,
        'profile_counts':dict(conditions),'sealed_shards':30,'candidate_checks':'passed',
        'audit':'30/30 passed','full_physics_replay':'1500/1500 passed',
        'maximum_absolute_array_difference':verification['replay_maximum_absolute_array_difference'],
        'same_environment':verification['replay_same_environment'],
        'independent_person_review':False,'cross_member_deduplication':'pending_B_C_D_candidates',
        'global_family_split':'pending','eligible_for_training':False,'concentration_accuracy_verified':False,
        'archive_bytes':sum(r['bytes'] for r in archive_rows),
        'raw_dataset_bytes':sum(read(DATA/(batch+'_state.json'))['dataset_bytes'] for batch in config['batches']),
        'cancelled_v1':read(HERE/'production_v1/run_status.json'),
        'candidate_errors':[],'production_errors':[]}
    write(HERE/'selfcheck_summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
