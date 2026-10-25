"""Execute a complete approved member quota; --dry-run never calculates spectra."""
from __future__ import annotations
import argparse, collections, concurrent.futures, csv, dataclasses, gzip, hashlib, json, os, pathlib, shutil, sys, time, zipfile
for _key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[_key]='1'
from prepare_global import read,write,sha,key

def rows_csv(path):
    with pathlib.Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def safe_file(root,relative):
    if not isinstance(relative,str) or '\\' in relative or ':' in relative:raise ValueError('Invalid relative POSIX path')
    p=(root/relative).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():raise ValueError('Missing or unsafe file: '+relative)
    return p

def validate_freeze(repo,freeze,release,member,production=False,include_sealed=False):
    if member not in 'ABCD' or len(member)!=1:raise ValueError('Unknown member')
    fm=read(freeze/'freeze_manifest.json')
    if fm['status']!='frozen_inputs_prepared_for_review' or fm['spectra']!=100000:raise ValueError('Wrong Round4 freeze schema/count')
    for rel,digest in fm['files'].items():
        if sha(safe_file(freeze,rel))!=digest:raise ValueError('Frozen file changed: '+rel)
    re=read(release)
    if re['freeze_manifest_sha256']!=sha(freeze/'freeze_manifest.json'):raise ValueError('Release targets a different freeze')
    for name,digest in re['production_tool_sha256'].items():
        if sha(safe_file(pathlib.Path(__file__).resolve().parent,name))!=digest:raise ValueError('Production tool changed: '+name)
    if production and (re.get('production_approved') is not True or member not in re.get('members',[])):raise ValueError('Complete production release is not approved for this member')
    if production:
        review=re.get('review_evidence')
        if not isinstance(review,dict) or any(not review.get(k) for k in ('pull_request_url','merged_commit','reviewed_by')):raise ValueError('Approved release must bind the collaborator review/merge evidence')
    if production and not include_sealed:raise ValueError('Full member quota includes sealed-QC records; pass --include-sealed-qc')
    for rel,entry in read(freeze/'input_identity.json')['sources'].items():
        if sha(safe_file(repo,rel))!=entry['sha256']:raise ValueError('Pinned candidate/history source changed: '+rel)
    import importlib.metadata
    pinned=read(freeze/'scope.json')['environment']['packages']
    for package in ('numpy','scipy','xraylib'):
        if importlib.metadata.version(package)!=pinned[package]:raise ValueError('Core numerical dependency differs from freeze: '+package)
    return re

def load_member(repo,freeze,member):
    sys.path.insert(0,str(freeze/'generator'))
    from fp_competition.core import Profile,TARGET_ELEMENTS
    from fp_competition.dataset import make_plan
    scope=read(freeze/'scope.json');source=scope['source_candidate_files'][member];p=safe_file(repo,source['path'])
    if sha(p)!=source['sha256']:raise ValueError('Candidate source hash mismatch')
    samples={s['id']:s for s in read(p)['samples']};profiles={}
    registry=read(freeze/'profile_registry.json')
    for rel,entry in registry['condition_files'].items():
        if pathlib.PurePosixPath(rel).name.startswith(member+'_'):
            with gzip.open(safe_file(freeze,rel),'rt',encoding='utf-8') as f:
                for line in f:
                    r=json.loads(line);cid=r['condition_instance_id']
                    if cid in profiles:raise ValueError('Duplicate condition ID')
                    profiles[cid]=r
    plan=[b for b in read(freeze/'batch_plan.json')['batches'] if b['member']==member]
    records=rows_csv(freeze/f'record_plan_{member}.csv');by_batch=collections.defaultdict(list)
    for r in records:by_batch[r['batch_id']].append(r)
    assigned={f['design_family_id']:f for f in read(freeze/'family_assignments.json')['families']}
    fallback=Profile.from_dict(registry['fallback_profile'])
    return samples,profiles,plan,by_batch,assigned,fallback,make_plan,TARGET_ELEMENTS

def native_inputs(batch,state):
    samples,profiles,_,by_batch,assignments,fallback,make_plan,targets=state;ss=[]
    for cid in batch['condition_ids']:
        c=profiles[cid];candidate=samples[c['candidate_id']];f=assignments[candidate['provenance']['design_family_id']]
        if c['candidate_id'] not in batch['candidate_ids'] or f['member']!=batch['member'] or f['usage']!=batch['usage'] or f['training_stage']!=batch['training_stage'] or c['condition_group']!=batch['condition_group']:raise ValueError('Family/condition/role/stage plan mismatch')
        # Full candidate provenance is retained in the sealed input, never in the blind file.
        ss.append({'id':cid,'composition_percent':candidate['composition_percent'],'profile_override':c['profile'],'provenance':{'round_id':'round4','original_candidate_id':c['candidate_id'],'design_family_id':f['design_family_id'],'unified_family_id':f['unified_family_id'],'condition_instance_id':cid,'condition_group':batch['condition_group'],'research_usage':batch['usage'],'training_stage':batch['training_stage'],'source_candidate_provenance':candidate['provenance']}})
    jobs,_,_=make_plan(ss,fallback,2,batch['batch_seed'],{},'strict','reject',list(targets),batch['split_seed']);rr=by_batch[batch['batch_id']]
    if len(rr)!=len(jobs) or len(jobs)!=batch['spectra']:raise ValueError('Record count mismatch')
    for i,(job,r) in enumerate(zip(jobs,rr),1):
        s,repeat,p,child,_,native_split=job
        if (r['native_id'],r['condition_instance_id'],int(r['repeat']),int(r['noise_seed']),r['native_split_not_authoritative'])!=(f'S{i:06d}',s['id'],repeat,child,native_split):raise ValueError('Seed/condition/native ID mismatch')
    return ss,jobs,rr

def dry_run(repo,freeze,release,member):
    validate_freeze(repo,freeze,release,member);state=load_member(repo,freeze,member)
    seeds=set();opaque=set();roles=collections.Counter();families={};conditions=collections.Counter()
    for batch in state[2]:
        _,jobs,records=native_inputs(batch,state)
        for r in records:
            seed=int(r['noise_seed']);bid=r['opaque_blind_id']
            if seed in seeds or bid in opaque:raise ValueError('Duplicated seed/opaque ID')
            seeds.add(seed);opaque.add(bid);roles[r['research_usage']]+=1;conditions[r['condition_instance_id']]+=1
            family=r['unified_family_id'];families.setdefault(family,set()).add((r['research_usage'],r['training_stage']))
    expected=40000 if member=='A' else 20000
    if len(seeds)!=expected or set(conditions.values())!={2} or any(len(v)!=1 for v in families.values()):raise ValueError('Incomplete quota/condition repeats or family leakage')
    return {'status':'passed_no_spectrum_preflight','member':member,'records':len(seeds),'batches':len(state[2]),'conditions':len(conditions),'roles':dict(roles),'pilot_spectra':0,'spectra_generated':0,'freeze_manifest_sha256':sha(freeze/'freeze_manifest.json'),'release_production_approved':read(release)['production_approved']}

def worker_init(repo,freeze,release,member,out,minimum_free_gib):
    global W_REPO,W_FREEZE,W_OUT,W_STATE,W_MIN,W_HASH
    W_REPO=pathlib.Path(repo);W_FREEZE=pathlib.Path(freeze);W_OUT=pathlib.Path(out);W_MIN=minimum_free_gib*1024**3
    validate_freeze(W_REPO,W_FREEZE,pathlib.Path(release),member,production=True,include_sealed=True)
    W_STATE=load_member(W_REPO,W_FREEZE,member);W_HASH=sha(W_FREEZE/'freeze_manifest.json')

def run_batch(batch):
    from fp_competition.dataset import generate_dataset,audit_dataset,replay_dataset,pack_dataset
    bid=batch['batch_id'];out=W_OUT/'sealed_batches'/bid;qc=W_OUT/'reports'/bid;archive=W_OUT/'archives'/(bid+'.zip')
    summary=qc/'summary.json'
    if summary.exists():
        saved=read(summary)
        if saved.get('status')=='passed_all_records' and saved['freeze_manifest_sha256']==W_HASH and archive.is_file() and sha(archive)==saved['archive_sha256']:
            required={'audit.json','replay.json','window_budget.json','commands.json','actual_record_index.csv'}
            if set(saved.get('qc_files_sha256',{}))!=required:raise ValueError('Resume requires the complete pinned QC inventory')
            for name,digest in saved['qc_files_sha256'].items():
                if not (qc/name).is_file() or sha(qc/name)!=digest:raise ValueError('Resume QC evidence changed: '+name)
            replay=read(qc/'replay.json');audit=read(qc/'audit.json')
            if replay.get('status')!='passed' or replay.get('scope')!='all_records' or replay.get('spectra_recalculated')!=batch['spectra'] or replay.get('errors') or audit.get('status')!='passed' or audit.get('spectra_checked')!=batch['spectra']:raise ValueError('Resume requires exact all-record audit/replay coverage')
            with zipfile.ZipFile(archive) as z:
                if z.testzip() is not None:raise ValueError('Resume archive CRC failure')
            return saved
        raise ValueError('Existing incomplete/failed batch retained: '+bid+'; review before an explicit new revision')
    if out.exists() or qc.exists() or archive.exists():raise ValueError('Refusing to overwrite a partial or unindexed batch '+bid)
    if shutil.disk_usage(W_OUT).free<W_MIN:raise ValueError('Free disk reserve threshold reached; preserve completed batches and resume after capacity review')
    qc.mkdir(parents=True);out.parent.mkdir(parents=True,exist_ok=True);archive.parent.mkdir(parents=True,exist_ok=True)
    t=time.monotonic();ss,jobs,records=native_inputs(batch,W_STATE);commands=[]
    try:
        samples,profiles,plan,by_batch,assigned,fallback,make_plan,targets=W_STATE
        generate_dataset(ss,fallback,out,replicates=2,seed=batch['batch_seed'],jitter={},closure='strict',legacy_al='reject',targets=list(targets),split_seed=batch['split_seed'])
        commands.append({'action':'generate_dataset','seconds':time.monotonic()-t,'status':'complete'})
        budget=read(W_FREEZE/'window_budget.json');window=[]
        for r in records:
            full=read(out/'full_results'/f"{r['native_id']}.json");total=full['detected_signal_before_window_counts'];loss=sum(full['outside_window_counts'].values());fraction=loss/total if total else 0.
            cap=budget['maximum_lost_fraction_20kV' if full['profile']['voltage_kV']==20 else 'maximum_lost_fraction_49kV']
            window.append({'native_id':r['native_id'],'lost_fraction':fraction,'budget':cap,'passed':0<=fraction<=cap})
        write(qc/'window_budget.json',{'records':window,'status':'passed' if all(x['passed'] for x in window) else 'failed'})
        if not all(x['passed'] for x in window):raise ValueError('Preregistered window budget failed; retain original data and record failure')
        a=audit_dataset(out);write(qc/'audit.json',a)
        if a['status']!='passed' or a['spectra_checked']!=len(records):raise ValueError('Full audit failed')
        r=replay_dataset(out);write(qc/'replay.json',r)
        if r['status']!='passed' or r['scope']!='all_records' or r['spectra_recalculated']!=len(records) or r['errors']:raise ValueError('Full physical replay failed or environment differs')
        p=pack_dataset(out,archive);commands.append({'action':'audit_replay_pack','scope':'all_records','status':'passed'})
        native=read(out/'manifest.json')['records'];actual=[]
        for rr,m in zip(records,native):
            actual.append({**rr,'blind_path':m['file'],'blind_sha256':m['blind_input_sha256'],'full_path':m['full_results'],'full_sha256':m['full_results_sha256'],'archive_path':archive.relative_to(W_OUT).as_posix(),'archive_sha256':p['sha256'],'qc_status':'passed','eligible_for_training':False})
        with (qc/'actual_record_index.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(actual[0]));w.writeheader();w.writerows(actual)
        result={'status':'passed_all_records','batch_id':bid,'records':len(records),'freeze_manifest_sha256':W_HASH,'archive_sha256':p['sha256'],'archive_bytes':archive.stat().st_size,'seconds':time.monotonic()-t,'audit':'all_records_passed','replay':'all_records_passed','window_budget':'all_records_passed','ZIP_CRC':'passed','eligible_for_training':False}
        write(qc/'commands.json',commands)
        result['qc_files_sha256']={name:sha(qc/name) for name in ('audit.json','replay.json','window_budget.json','commands.json','actual_record_index.csv')}
        write(summary,result);return result
    except BaseException as exc:
        write(qc/'commands.json',commands);write(qc/'failure.json',{'batch_id':bid,'error_type':type(exc).__name__,'error':str(exc),'freeze_manifest_sha256':W_HASH,'partial_data_preserved':True,'eligible_for_training':False});raise

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repository',type=pathlib.Path,required=True);p.add_argument('--freeze',type=pathlib.Path,required=True);p.add_argument('--release',type=pathlib.Path,required=True);p.add_argument('--member',choices=list('ABCD'),required=True);p.add_argument('--out',type=pathlib.Path);p.add_argument('--workers',type=int,default=4);p.add_argument('--minimum-free-gib',type=float,default=10.);p.add_argument('--include-sealed-qc',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--preflight-report',type=pathlib.Path);args=p.parse_args()
    repo=args.repository.resolve();freeze=args.freeze.resolve();release=args.release.resolve()
    if not 1<=args.workers<=8 or args.minimum_free_gib<1:raise ValueError('workers 1..8 and a positive >=1GiB free-space reserve required')
    preflight=dry_run(repo,freeze,release,args.member)
    if args.preflight_report:
        if args.preflight_report.resolve().is_relative_to(freeze):raise ValueError('Write preflight reports outside the immutable freeze')
        write(args.preflight_report,preflight)
    if args.dry_run:print(json.dumps(preflight,ensure_ascii=False));return
    validate_freeze(repo,freeze,release,args.member,production=True,include_sealed=args.include_sealed_qc)
    if args.out is None:raise ValueError('--out is required for production')
    out=args.out.resolve()
    if out.is_relative_to(freeze) or freeze.is_relative_to(out):raise ValueError('Production output and frozen inputs must be disjoint')
    out.mkdir(parents=True,exist_ok=True);state=load_member(repo,freeze,args.member);results=[];failures=[]
    completed=0
    for b in state[2]:
        p=out/'reports'/b['batch_id']/'summary.json'
        if p.is_file():
            r=read(p)
            if r.get('status')=='passed_all_records' and r.get('freeze_manifest_sha256')==sha(freeze/'freeze_manifest.json'):completed+=b['spectra']
    resource=read(freeze/'resource_budget.json');remaining=max(0,(40000 if args.member=='A' else 20000)-completed)
    estimated=remaining*resource['estimated_total_bytes_per_record_including_blind_export']
    available=shutil.disk_usage(out).free
    write(out/'resource_preflight.json',{'remaining_records':remaining,'estimated_remaining_bytes':estimated,'available_bytes':available,'reserved_free_bytes':args.minimum_free_gib*1024**3,'reference':resource['reference_archive'],'performance_guarantee':False})
    if available<estimated+args.minimum_free_gib*1024**3:raise ValueError('Available disk is below historical full-quota estimate plus reserved free space')
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers,initializer=worker_init,initargs=(str(repo),str(freeze),str(release),args.member,str(out),args.minimum_free_gib)) as pool:
        future={pool.submit(run_batch,b):b for b in state[2]}
        for task in concurrent.futures.as_completed(future):
            try:result=task.result();results.append(result);print(json.dumps({'completed_batches':len(results),'total_batches':len(state[2]),'batch_id':result['batch_id'],'status':result['status']},ensure_ascii=False),flush=True)
            except BaseException as exc:failures.append({'batch_id':future[task]['batch_id'],'error':str(exc)})
    actual=[]
    for b in state[2]:
        path=out/'reports'/b['batch_id']/'actual_record_index.csv'
        if path.is_file() and any(r['batch_id']==b['batch_id'] for r in results):actual.extend(rows_csv(path))
    if actual:
        with (out/'actual_record_index.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(actual[0]));w.writeheader();w.writerows(actual)
    expected=40000 if args.member=='A' else 20000
    passed=not failures and len(actual)==expected and len({r['global_record_id'] for r in actual})==expected
    member_summary={'status':'all_batch_QC_passed_packaging_pending' if passed else 'failed_partial_retained','packaging_status':'pending','member':args.member,'expected_records':expected,'actual_records':len(actual),'roles':dict(collections.Counter(r['research_usage'] for r in actual)),'complete_batches':len(results),'failures':failures,'full_audit_and_replay_performed':passed,'pilot_spectra':0,'freeze_manifest_sha256':sha(freeze/'freeze_manifest.json'),'eligible_for_training':False,'scientific_accuracy_verified':False}
    write(out/'selfcheck_summary.json',member_summary)
    if passed:
        blind=out/(args.member+'_round4_blind_inputs.zip')
        blind_preexisting=blind.exists()
        if not blind.exists():
            by_archive=collections.defaultdict(list)
            for row in actual:by_archive[row['archive_path']].append(row)
            with zipfile.ZipFile(blind,'x',zipfile.ZIP_DEFLATED) as target:
                for rel,rr in by_archive.items():
                    with zipfile.ZipFile(out/rel) as source:
                        for row in rr:
                            raw=source.read(row['blind_path'])
                            if hashlib.sha256(raw).hexdigest()!=row['blind_sha256']:raise ValueError('Blind archive source hash mismatch')
                            target.writestr(row['opaque_blind_id']+'.json',raw)
        with zipfile.ZipFile(blind) as z:
            if z.testzip() is not None or len(z.namelist())!=expected or set(z.namelist())!={r['opaque_blind_id']+'.json' for r in actual}:raise ValueError('Blind-only export is incomplete or has non-opaque names')
            if blind_preexisting:
                for r in actual:
                    if hashlib.sha256(z.read(r['opaque_blind_id']+'.json')).hexdigest()!=r['blind_sha256']:raise ValueError('Existing blind export has changed content')
        blind.with_suffix('.zip.sha256').write_text(sha(blind)+'  '+blind.name+'\n',encoding='ascii')
        qcpack=out/'reports'/(args.member+'_all_batch_QC.zip')
        if not qcpack.exists():
            with zipfile.ZipFile(qcpack,'x',zipfile.ZIP_DEFLATED) as z:
                for b in state[2]:
                    for name in ('audit.json','replay.json','window_budget.json','commands.json','summary.json','actual_record_index.csv'):
                        path=out/'reports'/b['batch_id']/name;z.write(path,b['batch_id']+'/'+name)
        with zipfile.ZipFile(qcpack) as z:
            if z.testzip() is not None:raise ValueError('QC ZIP CRC failed')
            for b in state[2]:
                for name in ('audit.json','replay.json','window_budget.json','commands.json','summary.json','actual_record_index.csv'):
                    if hashlib.sha256(z.read(b['batch_id']+'/'+name)).hexdigest()!=sha(out/'reports'/b['batch_id']/name):raise ValueError('QC archive content differs from complete batch evidence')
        write(out/'archive_index.json',{'records':expected,'native_archives':results,'blind_only_archive':{'path':blind.name,'sha256':sha(blind),'records':expected},'QC_archive':{'path':qcpack.relative_to(out).as_posix(),'sha256':sha(qcpack)},'expanded_sealed_batches':'local reproducibility working copies; not additional spectra or duplicate delivery records'})
        member_summary.update(status='passed_member_full_QC_pending_coordinator_acceptance',packaging_status='complete');write(out/'selfcheck_summary.json',member_summary)
        deliver=[out/'actual_record_index.csv',out/'selfcheck_summary.json',out/'archive_index.json',out/'resource_preflight.json',blind,blind.with_suffix('.zip.sha256'),qcpack]
        deliver += [out/'archives'/(b['batch_id']+suffix) for b in state[2] for suffix in ('.zip','.zip.sha256')]
        write(out/'delivery_manifest.json',{'status':'complete_member_delivery_pending_coordinator_acceptance','member':args.member,'records':expected,'freeze_manifest_sha256':sha(freeze/'freeze_manifest.json'),'eligible_for_training':False,'files':[{'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in deliver]})
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
