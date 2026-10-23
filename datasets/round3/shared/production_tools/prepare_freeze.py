"""Freeze round-three plans outside the unchanged FP solver; no spectra are saved."""
from __future__ import annotations
import argparse,collections,concurrent.futures,csv,hashlib,itertools,json,pathlib,shutil,sys,time
import numpy as np
from scipy.spatial.distance import cdist

SPLIT_SEED=202610240701
NOISE_SEED=202610240702
FOCUS=('Na','Cu','Zn','Cd','Co','Rb')
def read(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def key(text,seed=SPLIT_SEED):return hashlib.sha256(f'{seed}:{text}'.encode()).hexdigest()
def load_physics(generator):
 sys.path.insert(0,str(generator))
 from fp_competition.core import Profile,simulate,TARGET_ELEMENTS
 from fp_competition.dataset import make_plan,environment
 return Profile,simulate,TARGET_ELEMENTS,make_plan,environment
def qc_init(generator,profiles,budget):
 global Q_Profile,Q_simulate,Q_profiles,Q_budget
 Q_Profile,Q_simulate,_,_,_=load_physics(generator);Q_profiles=profiles;Q_budget=budget
def qc_one(job):
 sample,profile_id=job;p=Q_Profile.from_dict(Q_profiles[profile_id])
 try:
  r=Q_simulate(sample['composition_percent'],p,seed=0,poisson=False)
  expected=np.asarray(r['expected_counts']);components=np.asarray(list(r['components_expected_counts'].values()))
  total=r['detected_signal_before_window_counts'];lost=sum(r['outside_window_counts'].values());fraction=lost/total if total else 0.
  cap=Q_budget['maximum_lost_fraction_20kV' if p.voltage_kV==20 else 'maximum_lost_fraction_49kV'];errors=[]
  if not np.isfinite(expected).all() or (expected < -Q_budget['nonnegative_tolerance']).any():errors.append('invalid_expectation')
  if len(components)!=6 or not np.allclose(components.sum(axis=0),expected,rtol=Q_budget['conservation_rtol'],atol=Q_budget['conservation_atol']):errors.append('six_component_closure')
  residual=total-float((expected-p.background_counts_channel).sum())-lost
  if not np.isclose(total,total-residual,rtol=Q_budget['conservation_rtol'],atol=Q_budget['conservation_atol']):errors.append('window_conservation')
  if not 0<=fraction<=cap:errors.append('preregistered_window_budget')
  return {'recipe_id':sample['id'],'profile_id':profile_id,'window_lost_fraction':fraction,'budget':cap,'conservation_residual_counts':residual,'errors':errors}
 except Exception as e:return {'recipe_id':sample['id'],'profile_id':profile_id,'errors':[type(e).__name__+': '+str(e)]}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--repository',type=pathlib.Path,required=True);parser.add_argument('--out',type=pathlib.Path,required=True);parser.add_argument('--workers',type=int,default=4);parser.add_argument('--full-forward-qc',action='store_true');args=parser.parse_args()
 repo=args.repository.resolve();out=args.out.resolve();r3=repo/'datasets/round3';prep=r3/'shared/preparation_v1'
 if out.exists():raise ValueError('Refusing to overwrite a freeze directory')
 if not 1<=args.workers<=8:raise ValueError('workers must be 1..8')
 samples=[];families=[];sources={};by_member={};family_samples={}
 allocation=read(prep/'design_allocation.json')['families']
 for owner in 'ABCD':
  folder='candidates_v1' if owner=='A' else 'candidates';base=r3/f'member_{owner}'/folder
  rows=read(base/f'{owner}_samples.json')['samples'];fs=read(base/'family_registry.json')['design_families']
  assert len(rows)==250 and len(fs)==105
  assert collections.Counter(r['provenance']['scenario'] for r in rows)=={'ladder':90,'interference':50,'paired_negative_spike':60,'routine':50}
  assert collections.Counter(r['provenance']['matrix_type'] for r in rows)=={'silicate_oxide':150,'iron_oxide':100}
  for path in [base/f'{owner}_samples.json',base/'family_registry.json']:sources[path.relative_to(repo).as_posix()]={'sha256':sha(path),'bytes':path.stat().st_size}
  for f in fs:
   expected=next(x for x in allocation if x['design_family_id']==f['design_family_id'])
   assert all(f[k]==v for k,v in expected.items())
   group=[r for r in rows if r['provenance']['parent_family']==f['design_family_id']]
   assert len(group)==f['variants'] and {r['id'] for r in group}==set(f['sample_ids'])
   assert len({json.dumps(r['provenance']['original_composition_percent'],sort_keys=True) for r in group})==1
   family_samples[f['design_family_id']]=group
  by_member[owner]=rows;samples+=rows;families+=fs
 assert len({r['id'] for r in samples})==1000 and len({f['design_family_id'] for f in families})==420
 history_path=r3/'member_A/inputs/historical_compositions.json';history_doc=read(history_path);history=history_doc['rows'];assert len(history)==3800
 sources[history_path.relative_to(repo).as_posix()]={'sha256':sha(history_path),'bytes':history_path.stat().st_size}
 # Include used compositions, original boards and explicit family claims before splitting.
 boards=[{'id':f['design_family_id']+'/original','composition_percent':family_samples[f['design_family_id']][0]['provenance']['original_composition_percent'],'family':f['design_family_id']} for f in families]
 elements=sorted(set().union(*(r['composition_percent'] for r in samples+boards+history)))
 arr=lambda rows:np.asarray([[r['composition_percent'].get(e,0) for e in elements] for r in rows])
 current=samples+boards;matrix=arr(current);hist_matrix=arr(history);d=cdist(matrix,matrix,'cityblock');dh=cdist(matrix,hist_matrix,'cityblock')
 family_of=lambda r:r.get('family') or r['provenance']['parent_family']
 cross_edges=[];history_edges=[];explicit_links=[]
 historical_tokens={str(r[k]) for r in history for k in ('id','parent_family','root_parent','root_parent_id','generator_family') if r.get(k)}
 for i,j in zip(*np.where(np.triu(d<=.5,1))):
  if family_of(current[i])!=family_of(current[j]):cross_edges.append({'a':current[i]['id'],'b':current[j]['id'],'L1':float(d[i,j])})
 for i,j in zip(*np.where(dh<=.5)):history_edges.append({'candidate':current[i]['id'],'historical':history[j]['id'],'L1':float(dh[i,j])})
 for r in samples:
  for k in ('parent_family','root_parent','root_parent_id','historical_parent_id','generator_family'):
   if r['provenance'].get(k) and str(r['provenance'][k]) in historical_tokens:explicit_links.append({'candidate':r['id'],'field':k,'value':r['provenance'][k]})
 # This version stops for any merge/train-only case rather than silently splitting components.
 if cross_edges or history_edges or explicit_links:
  out.mkdir(parents=True);write(out/'closure_blocked.json',{'cross_edges':cross_edges,'history_edges':history_edges,'explicit_links':explicit_links,'production_approved':False})
  raise ValueError('Kinship links require explicit connected-component allocation before freeze')
 prep_manifest=read(prep/'preparation_manifest.json')
 for rel,digest in prep_manifest['files'].items():assert sha(prep/rel)==digest,rel
 profiles={};profile_sources={}
 for item in read(prep/'profile_registry.json')['profiles']:
  p=prep/item['path'];assert sha(p)==item['sha256'];profiles[item['profile_id']]=read(p);profile_sources[item['profile_id']]=p
 assert set(profiles)==set(['P1','P2','P3']+[f'D{i}' for i in range(1,7)]+['T1','T2','T3'])
 generator=r3/'member_A/inputs/generator';Profile,simulate,targets,make_plan,environment=load_physics(generator)
 for p in profiles.values():Profile.from_dict(p)
 def ordered(rows,domain):return sorted(rows,key=lambda f:key(domain+f['design_family_id']))
 assigned={};usage={}
 def split_group(rows,nval,nhold,domain,preserve_owner=False):
  order=ordered(rows,domain);counts=collections.Counter(f['owner'] for f in rows)
  for use,n in [('internal_holdout',nhold),('validation',nval)]:
   if n==0:continue
   chosen=0
   for f in order:
    fid=f['design_family_id']
    if fid in usage or (preserve_owner and counts[f['owner']]<=1):continue
    usage[fid]=use;counts[f['owner']]-=1;chosen+=1
    if chosen==n:break
   assert chosen==n,(domain,use,chosen,n)
  for f in rows:usage.setdefault(f['design_family_id'],'train')
 for i,target in enumerate(FOCUS):
  split_group([f for f in families if f['category']=='ladder' and f['target']==target],1 if i<3 else 2,2 if i<3 else 1,'ladder:'+target,True)
 pairs=[]
 for f in families:
  pair=(f['target'],f['interferent'])
  if f['category']=='interference' and pair not in pairs:pairs.append(pair)
 for i,pair in enumerate(pairs):split_group([f for f in families if f['category']=='interference' and (f['target'],f['interferent'])==pair],int(i<6),int(i>=2),'pair:'+str(pair))
 for target,nval,nhold in zip(FOCUS,[6,4,3,1,2,2],[6,5,3,2,1,1]):split_group([f for f in families if f['category']=='paired_negative_spike' and f['target']==target],nval,nhold,'spike:'+target)
 for matrix_type,n in [('silicate_oxide',18),('iron_oxide',12)]:split_group([f for f in families if f['category']=='routine' and f['matrix']==matrix_type],n,n,'routine:'+matrix_type)
 assert collections.Counter(usage.values())=={'train':294,'validation':63,'internal_holdout':63}
 assert collections.Counter(usage[r['provenance']['parent_family']] for r in samples)=={'train':700,'validation':150,'internal_holdout':150}
 forced_long=set()
 for target in FOCUS:
  for owner in 'ABCD':
   group=ordered([f for f in families if f['category']=='ladder' and f['target']==target and f['owner']==owner and usage[f['design_family_id']]=='train'],'long:'+target+owner)
   assert group;forced_long.add(group[0]['design_family_id'])
 counters=collections.Counter();anchor_counts=collections.Counter()
 for f in ordered(families,'profile'):
  fid=f['design_family_id'];use=usage[fid]
  if use=='internal_holdout':base=['P1','P2','P3'];challenge=['T1','T2','T3']
  else:
   anchor=min(['P1','P2','P3'],key=lambda p:(anchor_counts[(f['owner'],use,p)],key(fid+p)));anchor_counts[f['owner'],use,anchor]+=1
   choices=list(itertools.combinations([f'D{i}' for i in range(1,7)],2))
   if fid in forced_long:choices=[c for c in choices if 'D5' in c]
   choice=min(choices,key=lambda c:(sum(counters[f['owner'],use,p] for p in c),max(counters[f['owner'],use,p] for p in c),key(fid+str(c))))
   for p in choice:counters[f['owner'],use,p]+=1
   base=[anchor,*choice];challenge=[]
  assigned[fid]={**f,'usage':use,'base_profiles':base,'challenge_profiles':challenge,'historical_scope':'known_snapshot_only_not_independently_blinded'}
 pilot_families={}
 for owner in 'ABCD':
  own=[f for f in families if f['owner']==owner and usage[f['design_family_id']]=='train']
  ladder=next(f for f in own if f['category']=='ladder' and f['target']=='Na' and f['design_family_id'] in forced_long)
  selected=[ladder]+[ordered([f for f in own if f['category']==cat],'pilot:'+owner+cat)[0] for cat in ['interference','paired_negative_spike']]+ordered([f for f in own if f['category']=='routine'],'pilot:'+owner+'routine')[:2]
  pilot_families[owner]=[f['design_family_id'] for f in selected];assert sum(f['variants'] for f in selected)==15
 pilot_set=set(sum(pilot_families.values(),[]));buckets=collections.defaultdict(list)
 for f in families:
  fid=f['design_family_id'];a=assigned[fid];phase='pilot' if fid in pilot_set else 'base'
  for profile in a['base_profiles']:buckets[f['owner'],phase,profile].append(fid)
  for profile in a['challenge_profiles']:buckets[f['owner'],'challenge',profile].append(fid)
 batches=[];noise=[];seen_seeds=set();seen_ids=set();all_jobs=[]
 for (owner,phase,pid),fids in sorted(buckets.items()):
  chunks=[];chunk=[];size=0
  for fid in sorted(fids):
   n=len(family_samples[fid])
   if size+n>25:chunks.append(chunk);chunk=[];size=0
   chunk.append(fid);size+=n
  if chunk:chunks.append(chunk)
  for index,chunk in enumerate(chunks,1):
   bid=f'R3_{owner}_{phase}_{pid}_{index:03d}';batch_seed=int(key('batch:'+bid,NOISE_SEED)[:16],16)%(2**63-1)
   rows=sum((family_samples[fid] for fid in chunk),[])
   jobs,_,_=make_plan(rows,Profile.from_dict(profiles[pid]),2,batch_seed,{},'strict','reject',list(targets),SPLIT_SEED)
   batches.append({'batch_id':bid,'member':owner,'phase':phase,'profile_id':pid,'families':chunk,'recipe_ids':[r['id'] for r in rows],'recipes':len(rows),'spectra':len(jobs),'batch_seed':batch_seed,'split_seed':SPLIT_SEED,'replicates':2,'jitter':{},'closure':'strict','legacy_al':'reject'})
   for i,(row,repeat,variant,child,native_family,native_split) in enumerate(jobs,1):
    fid=row['provenance']['parent_family'];opaque=key('opaque:'+str(child),NOISE_SEED)[:24]
    assert child not in seen_seeds and opaque not in seen_ids;seen_seeds.add(child);seen_ids.add(opaque)
    noise.append({'batch_id':bid,'native_id':f'S{i:06d}','opaque_blind_id':opaque,'member':owner,'recipe_id':row['id'],'design_family_id':fid,'usage':usage[fid],'profile_id':pid,'repeat':repeat,'noise_seed':child,'native_split_not_authoritative':native_split})
   all_jobs.extend((row,pid) for row in rows)
 assert len(noise)==6900 and len(seen_seeds)==6900
 assert sum(b['spectra'] for b in batches if b['phase']=='challenge')==900
 assert all(sum(b['spectra'] for b in batches if b['member']==o and b['phase']=='pilot')==90 for o in 'ABCD')
 out.mkdir(parents=True)
 write(out/'input_identity.json',{'files':sources,'history_coverage_limit':history_doc['coverage_limit'],'candidate_count':1000,'design_families':420,'physics_core_sha256':sha(generator/'fp_competition/core.py'),'environment':environment()})
 write(out/'global_closure.json',{'used_compositions':1000,'original_backgrounds':420,'historical_rows':3800,'threshold_L1_percentage_points':.5,'cross_design_edges':cross_edges,'historical_edges':history_edges,'explicit_history_links':explicit_links,'known_components':[[f['design_family_id']] for f in families],'scope':'all_four_current_members_and_available_history_only','history_coverage_limit':history_doc['coverage_limit'],'external_independent_blindness':False,'minimum_candidate_history_L1':float(dh[:1000].min()),'minimum_original_background_history_L1':float(dh[1000:].min())})
 write(out/'family_assignments.json',{'split_seed':SPLIT_SEED,'families':list(assigned.values()),'pilot_families':pilot_families,'forced_long_exposure_families':sorted(forced_long),'whole_family_roles_frozen':True,'role_counts_families':dict(collections.Counter(usage.values()))})
 write(out/'batch_plan.json',{'noise_master_seed':NOISE_SEED,'split_seed':SPLIT_SEED,'batches':batches,'expected_base_spectra':6000,'expected_challenge_spectra':900,'expected_total_spectra':6900,'pilot_included_in_base':True,'native_generator_split_is_authoritative':False})
 with (out/'record_plan.csv').open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(noise[0]));w.writeheader();w.writerows(noise)
 for pid,path in profile_sources.items():
  target=out/'profiles'/('heldout_qc_only' if pid.startswith('T') else 'development')/(pid+'.json');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
 shutil.copytree(generator,out/'generator',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copyfile(prep/'window_budget.json',out/'window_budget.json')
 write(out/'profile_registry.json',{'development_allowlist':['P1','P2','P3']+[f'D{i}' for i in range(1,7)],'model_forbidden':['T1','T2','T3'],'files':{pid:{'path':f'profiles/{"heldout_qc_only" if pid.startswith("T") else "development"}/{pid}.json','sha256':sha(path)} for pid,path in profile_sources.items()},'T_access':'physical_QC_only_not_model_fit_dictionary_or_selection'})
 budget=read(prep/'window_budget.json');results=[];started=time.monotonic()
 print('Plan fixed:',len(batches),'batches,',len(noise),'records;',len(all_jobs),'candidate/profile QC pairs',flush=True)
 if args.full_forward_qc:
  with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers,initializer=qc_init,initargs=(str(generator),profiles,budget)) as pool:
   for i,row in enumerate(pool.map(qc_one,all_jobs,chunksize=4),1):
    results.append(row)
    if i%100==0:print('Full candidate window QC',i,'/',len(all_jobs),'errors',sum(bool(x['errors']) for x in results),flush=True)
 else:
  for row,pid in all_jobs:
   comp=row['composition_percent'];assert all(np.isfinite(v) and v>=0 for v in comp.values()) and abs(sum(comp.values())-100)<1e-9 and comp.get('O',0)>0
   Profile.from_dict(profiles[pid])
  probes=read(prep/'profile_numeric_checks.json');assert not probes['errors'] and probes['forward_calculations']==24
 errors=[r for r in results if r['errors']]
 write(out/'candidate_profile_qc.json',{'status':('passed_full_forward_QC' if args.full_forward_qc else 'passed_static_and_pinned_probe_preflight_only') if not errors else 'failed','static_candidate_profile_pairs_checked':len(all_jobs),'forward_pairs_checked':len(results),'full_candidate_forward_QC_complete':args.full_forward_qc and not errors,'prior_probe_checks_verified':24,'prior_probe_source_sha256':sha(prep/'profile_numeric_checks.json'),'rows':results,'errors':errors,'seconds':time.monotonic()-started,'spectra_saved':0,'T_scope':'physical_QC_only','budget_sha256':sha(out/'window_budget.json'),'remaining_QC':'Pilot checks every saved spectrum; bulk producer must check each batch without loosening the registered window budget.'})
 write(out/'release.json',{'status':'pilot_only_after_owner_global_freeze' if not errors else 'blocked_candidate_QC','pilot_authorized':not errors,'batch_production_approved':False,'training_inclusion_approved':False,'pilot_members':['A'],'member_B_C_D_pilots':'pending_A_pilot_QC_and_owner_release','formal_total_spectra':6900,'external_independent_blindness':False,'note':'A global known-lineage split/profile/noise plan fixed before pilot. This release permits only A pilot; bulk production requires a later explicit versioned owner release.'})
 write(out/'freeze_manifest.json',{'schema':'round3-production-input-freeze/1','files':{p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='freeze_manifest.json'},'pilot_only':True,'production_approved':False})
 if errors:raise ValueError(f'{len(errors)} candidate/profile QC failures; no pilot allowed; keep artifacts, no budget changes')
 print('Preflight passed; A pilot only authorized; full candidate forward QC:',args.full_forward_qc,flush=True)
if __name__=='__main__':main()
