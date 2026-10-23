"""Run one authorized frozen batch with the unchanged, sealed native generator."""
from __future__ import annotations
import argparse,csv,hashlib,json,pathlib,subprocess,sys,time,zipfile
def read(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):pathlib.Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def validate(freeze,repo,batch_id,heldout=False):
 for rel,digest in read(freeze/'freeze_manifest.json')['files'].items():
  p=(freeze/rel).resolve()
  if not p.is_relative_to(freeze) or not p.is_file() or sha(p)!=digest:raise ValueError('Frozen input missing or changed: '+rel)
 release=read(freeze/'release.json');plan=read(freeze/'batch_plan.json')
 batches=[b for b in plan['batches'] if b['batch_id']==batch_id]
 if len(batches)!=1:raise ValueError('Unknown batch ID')
 batch=batches[0]
 if batch['phase']=='pilot':
  if not release['pilot_authorized'] or batch['member'] not in release['pilot_members']:raise ValueError('Member pilot is not released')
 elif not release['batch_production_approved']:raise ValueError('Bulk production has not been released')
 if batch['profile_id'].startswith('T') and (not heldout or batch['phase']!='challenge'):raise ValueError('T profiles require explicit heldout physical-QC mode')
 identity=read(freeze/'input_identity.json')
 for rel,entry in identity['files'].items():
  p=(repo/rel).resolve()
  if not p.is_relative_to(repo) or not p.is_file() or sha(p)!=entry['sha256']:raise ValueError('Pinned candidate/history source missing or changed: '+rel)
 registry=read(freeze/'profile_registry.json')
 if batch['phase']!='challenge' and batch['profile_id'] not in registry['development_allowlist']:raise ValueError('Model-forbidden profile used for base spectra')
 profile_path=freeze/registry['files'][batch['profile_id']]['path']
 member=batch['member'];folder='candidates_v1' if member=='A' else 'candidates'
 source=repo/f'datasets/round3/member_{member}/{folder}/{member}_samples.json'
 candidates={r['id']:r for r in read(source)['samples']}
 rows=[candidates[i] for i in batch['recipe_ids']]
 assignments={f['design_family_id']:f for f in read(freeze/'family_assignments.json')['families']}
 for row in rows:
  f=assignments[row['provenance']['parent_family']]
  if batch['phase']=='pilot' and f['usage']!='train':raise ValueError('Pilot must use confirmed training families')
  allowed=f['challenge_profiles'] if batch['phase']=='challenge' else f['base_profiles']
  if batch['profile_id'] not in allowed:raise ValueError('Family/profile assignment mismatch')
 return batch,rows,profile_path
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--repository',type=pathlib.Path,required=True);parser.add_argument('--freeze',type=pathlib.Path,required=True);parser.add_argument('--batch',required=True);parser.add_argument('--out',type=pathlib.Path,required=True);parser.add_argument('--qc-out',type=pathlib.Path,required=True);parser.add_argument('--heldout-qc',action='store_true');args=parser.parse_args()
 repo=args.repository.resolve();freeze=args.freeze.resolve();out=args.out.resolve();qc=args.qc_out.resolve()
 if out.exists() or qc.exists():raise ValueError('Use new output and QC directories; never append to sealed data')
 if qc.is_relative_to(out) or out.is_relative_to(qc):raise ValueError('Sealed output and external QC must be disjoint')
 batch,rows,profile_path=validate(freeze,repo,args.batch,args.heldout_qc)
 sys.path.insert(0,str(freeze/'generator'))
 from fp_competition.core import Profile,TARGET_ELEMENTS
 from fp_competition.dataset import generate_dataset,make_plan
 profile=Profile.from_dict(read(profile_path))
 jobs,_,_=make_plan(rows,profile,2,batch['batch_seed'],{},'strict','reject',list(TARGET_ELEMENTS),batch['split_seed'])
 with (freeze/'record_plan.csv').open(encoding='utf-8') as f:records=[r for r in csv.DictReader(f) if r['batch_id']==args.batch]
 assert len(jobs)==batch['spectra']==len(records)
 for job,record in zip(jobs,records):
  row,repeat,_,child,_,_=job
  assert (row['id'],repeat,child)==(record['recipe_id'],int(record['repeat']),int(record['noise_seed']))
 qc.mkdir(parents=True);started=time.monotonic()
 generate_dataset(rows,profile,out,replicates=2,seed=batch['batch_seed'],jitter={},closure='strict',legacy_al='reject',targets=list(TARGET_ELEMENTS),split_seed=batch['split_seed'],source_files={'profile':profile_path})
 generate_seconds=time.monotonic()-started
 budget=read(freeze/'window_budget.json');window_rows=[]
 for path in sorted((out/'full_results').glob('*.json')):
  full=read(path);total=full['detected_signal_before_window_counts'];fraction=sum(full['outside_window_counts'].values())/total if total else 0.
  cap=budget['maximum_lost_fraction_20kV' if full['profile']['voltage_kV']==20 else 'maximum_lost_fraction_49kV']
  window_rows.append({'id':full['record_id'],'lost_fraction':fraction,'budget':cap,'passed':0<=fraction<=cap})
 write(qc/'window_budget.json',{'budget_sha256':sha(freeze/'window_budget.json'),'rows':window_rows,'passed':all(r['passed'] for r in window_rows)})
 if not all(r['passed'] for r in window_rows):raise ValueError('Registered window budget failed; preserve batch and do not pack or release production')
 app=out/'reproducibility/generator/fp_competition/app.py'
 assert sha(out/'reproducibility/generator/fp_competition/core.py')==read(freeze/'input_identity.json')['physics_core_sha256']
 commands=[]
 for name in ['audit','replay','pack']:
  dest=qc/(out.name+'.zip' if name=='pack' else name+'.json')
  cmd=[sys.executable,'-X','utf8','-B',str(app),name,'--dataset',str(out),'--out',str(dest)]
  t=time.monotonic();process=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace')
  (qc/(name+'.txt')).write_text(process.stdout+process.stderr,encoding='utf-8')
  commands.append({'action':name,'command':['python','-X','utf8','-B',f'<sealed>/{app.relative_to(out).as_posix()}',name,'--dataset','<sealed>','--out',dest.name],'exit_code':process.returncode,'seconds':time.monotonic()-t})
  write(qc/'commands.json',commands)
  if process.returncode!=0:raise ValueError(name+' failed; preserve sealed data and QC logs')
  if name!='pack':
   result=read(dest);assert result['status']=='passed',result
   if name=='replay':assert result['complete_physics_recalculation'] and result['spectra_recalculated']==batch['spectra']
 archive=qc/(out.name+'.zip')
 with zipfile.ZipFile(archive) as z:assert z.testzip() is None
 manifest=read(out/'manifest.json');assert manifest['spectrum_count']==batch['spectra']
 mapping=[]
 for rec,native in zip(records,manifest['records']):
  assert rec['native_id']==native['id']
  mapping.append({**rec,'blind_input_sha256':native['blind_input_sha256'],'full_results_sha256':native['full_results_sha256']})
 with (qc/'external_record_index.csv').open('w',encoding='utf-8',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(mapping[0]));writer.writeheader();writer.writerows(mapping)
 write(qc/'summary.json',{'status':'passed_pilot_QC' if batch['phase']=='pilot' else 'passed_batch_QC','batch_id':args.batch,'spectra':batch['spectra'],'generate_seconds':generate_seconds,'all_actions_seconds':time.monotonic()-started,'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive),'zip_crc_checked':True,'audit':'passed','replay':'all_records_passed','freeze_manifest_sha256':sha(freeze/'freeze_manifest.json'),'native_split_ignored_for_research_usage':True,'external_blind_ids':'record_plan opaque IDs; export with these names only','training_inclusion_approved':False,'scientific_accuracy_verified':False})
 print(json.dumps(read(qc/'summary.json'),ensure_ascii=False))
if __name__=='__main__':main()
