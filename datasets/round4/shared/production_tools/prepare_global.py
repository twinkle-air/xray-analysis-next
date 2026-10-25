"""Close Round4 candidate lineage and allocate whole families; never calculate spectra."""
from __future__ import annotations
import argparse, collections, csv, gzip, hashlib, json, math, pathlib, sys
import numpy as np
from scipy.spatial.distance import cdist

CATEGORIES = ('element_gradient','zero_spike','matrix_interference','routine_coverage')
HISTORY_LIMIT = ('All registered Round1 full/pilot sample pools, the inherited Round1/2 history table, '
                 'Round2 C current/superseded and D current/backup compositions, and Round3 ABCD candidates '
                 'with available original backgrounds. Undocumented ancestry and unavailable historical noise seeds remain unknown.')

def read(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def write(p,v):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def key(v): return hashlib.sha256(('round4-global-v1:'+str(v)).encode()).hexdigest()
def canonical(c): return json.dumps({e:round(float(v),10) for e,v in sorted(c.items()) if round(float(v),10)},sort_keys=True,separators=(',',':'))
def save_csv(p,rows,fields):
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def jsonl_gz(p,rows):
    with p.open('wb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as z:
            for r in rows:z.write((json.dumps(r,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode())

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--repository',type=pathlib.Path,required=True);a.add_argument('--out',type=pathlib.Path,required=True);a.add_argument('--source-commit',required=True);args=a.parse_args()
    repo=args.repository.resolve();out=args.out.resolve()
    if out.exists():raise FileExistsError('Refusing to overwrite preparation')
    sys.path.insert(0,str(repo/'datasets/round3/member_A/inputs/generator'))
    from fp_competition.core import TARGET_ELEMENTS
    from fp_competition.minerals import components_to_elements
    rows=[];families=[];sources={};notes=[];errors=[];members={};by_family={}
    def source(p):
        rel=p.relative_to(repo).as_posix()
        if rel not in sources:sources[rel]={'sha256':sha(p),'bytes':p.stat().st_size}
        return rel
    for m in 'ABCD':
        folder=repo/f'datasets/round4/member_{m}'/('candidates_v1' if m=='A' else 'candidates')
        sp=folder/f'{m}_samples.json';fp=folder/'family_registry.json';vp=folder/'independent_verification.json';cp=folder/'candidate_checks.json'
        for p in (sp,fp,vp,cp):source(p)
        doc=read(sp);ss=doc['samples'];fd=read(fp);fs=fd.get('families',fd.get('design_families'));v=read(vp)
        if v.get('status')!='passed' or v.get('errors'):errors.append(m+': member self-check has unresolved errors')
        if doc.get('production_started') is not False or doc.get('eligible_for_training') is not False:errors.append(m+': invalid candidate state')
        if len(ss)!=(2000 if m=='A' else 1000) or len(fs)!=(640 if m=='A' else 320):errors.append(m+': count mismatch')
        manifest=folder/'delivery_manifest.json'
        if manifest.exists():
            source(manifest)
            for x in read(manifest)['files']:
                p=folder/x['path']
                if not p.is_file() or sha(p)!=x['sha256'] or p.stat().st_size!=x['bytes']:errors.append(m+': delivery hash mismatch '+x['path'])
        else:notes.append(m+': merged candidate package has no delivery_manifest.json; coordinator receipt hashes bind every used source')
        for s in ss:
            p=s['provenance'];fid=p['design_family_id'];comp=s['composition_percent'];ledger=p['compensation_ledger']
            if set(comp)!=set((*TARGET_ELEMENTS,'O')) or any(not math.isfinite(float(x)) or x<0 for x in comp.values()) or abs(sum(comp.values())-100)>1e-7 or comp['O']<=0:errors.append(s['id']+': composition closure')
            conversion=ledger.get('conversion',{})
            compounds=conversion.get('compounds_percent',ledger.get('final_compounds_percent'))
            traces=conversion.get('trace_ppm',ledger.get('final_trace_ppm'))
            if compounds is None or traces is None:errors.append(s['id']+': no reconstructible compound/trace ledger');continue
            rebuilt,_=components_to_elements(compounds,traces,closure='strict')
            delta=max(abs(comp[e]-rebuilt.get(e,0)) for e in comp)
            if delta>1e-8 or any(comp[e]==0 and rebuilt.get(e,0)!=0 for e in comp):errors.append(s['id']+': reconstructed labels or true zero mismatch')
            if p.get('production_noise_seed') is not None or p.get('production_condition') is not None:errors.append(s['id']+': premature production metadata')
            row={'id':s['id'],'member':m,'family':fid,'category':p['design_type'],'matrix':p['matrix_class'],'target':p.get('target_element'),'interferent':p.get('interferent_element'),'composition_percent':comp,'original_composition_percent':p['original_composition_percent'],'source':source(sp),'provenance':p}
            rows.append(row);by_family.setdefault(fid,[]).append(row)
        for f in fs:
            fid=f['design_family_id'];rr=by_family[fid]
            if len({canonical(r['original_composition_percent']) for r in rr})!=1:errors.append(fid+': parent backgrounds differ')
            n={'element_gradient':10,'zero_spike':5,'matrix_interference':5,'routine_coverage':1}[rr[0]['category']]
            if len(rr)!=n:errors.append(fid+': incomplete family')
            families.append({'design_family_id':fid,'member':m,'category':rr[0]['category'],'matrix':rr[0]['matrix'],'target':rr[0]['target'],'interferent':rr[0]['interferent'],'recipes':len(rr),'candidate_ids':[r['id'] for r in rr],'nominal_role':f.get('requested_role')})
        members[m]={'recipes':len(ss),'families':len(fs),'selfcheck_status':v['status']}
    if len({r['id'] for r in rows})!=5000 or len({f['design_family_id'] for f in families})!=1600:errors.append('global candidate/family IDs not unique')
    if len({canonical(r['composition_percent']) for r in rows})!=5000:errors.append('exact candidate compositions repeated')
    if errors:
        out.mkdir(parents=True);write(out/'candidate_receipt_failed.json',{'errors':errors,'sources':sources});raise ValueError(errors[:10])
    # All retained provenance sources enter the history table, including unused/failed/superseded pools.
    hist={}
    def add_hist(identity,comp,path,parent=None,kind='used_composition'):
        ck=canonical(comp);entry=hist.setdefault(ck,{'id':identity,'composition_percent':comp,'aliases':[]})
        entry['aliases'].append({'id':identity,'source':path,'parent':parent,'kind':kind,'exposure':'prior_round_registered_or_visible'})
    hp=repo/'datasets/round3/member_A/inputs/historical_compositions.json';source(hp)
    for h in read(hp)['rows']:add_hist(h['id'],h['composition_percent'],hp.relative_to(repo).as_posix(),h.get('parent_family'))
    paths=list((repo/'datasets/round1').rglob('*_samples.json'))
    paths += [repo/p for p in ('datasets/round2/member_C/C_r2_samples.json','datasets/round2/member_C/qc/superseded_v1/C_r2_samples.json','datasets/round2/member_D/design/backup_samples_D.json','datasets/round2/member_D/design/candidate_samples_D.json')]
    paths += [repo/f'datasets/round3/member_{m}'/('candidates_v1/A_samples.json' if m=='A' else f'candidates/{m}_samples.json') for m in 'ABCD']
    for p in paths:
        if not p.is_file():continue
        rel=source(p)
        for s in read(p).get('samples',[]):
            prov=s.get('provenance',{});parent=prov.get('design_family_id',prov.get('parent_family',prov.get('root_parent')))
            add_hist(rel+'#'+s['id'],s['composition_percent'],rel,parent)
            if prov.get('original_composition_percent'):add_hist(rel+'#'+s['id']+'/original',prov['original_composition_percent'],rel,parent,'original_background')
    history=list(hist.values());boards=[{'id':f['design_family_id']+'/original','family':f['design_family_id'],'member':f['member'],'composition_percent':by_family[f['design_family_id']][0]['original_composition_percent'],'kind':'original_background'} for f in families]
    current=[{'id':r['id'],'family':r['family'],'member':r['member'],'composition_percent':r['composition_percent'],'kind':'used_composition'} for r in rows]+boards
    elements=sorted(set().union(*(x['composition_percent'] for x in current+history)))
    matrix=lambda rr:np.asarray([[r['composition_percent'].get(e,0) for e in elements] for r in rr],dtype=np.float64)
    a_cur=matrix(current);a_hist=matrix(history);parent={f['design_family_id']:f['design_family_id'] for f in families}
    def find(f):
        while parent[f]!=f:parent[f]=parent[parent[f]];f=parent[f]
        return f
    def union(f,g):
        f,g=find(f),find(g)
        if f!=g:parent[max(f,g)]=min(f,g)
    edges=[];history_edges=[];nearest=[];pairmin={};historymin=float('inf')
    for start in range(0,len(current),128):
        block=current[start:start+128];d=cdist(a_cur[start:start+128],a_cur,'cityblock');dh=cdist(a_cur[start:start+128],a_hist,'cityblock')
        for k,r in enumerate(block):
            i=start+k;j=int(dh[k].argmin());distance=float(dh[k,j]);historymin=min(historymin,distance)
            nearest.append({'id':r['id'],'family':r['family'],'member':r['member'],'kind':r['kind'],'history_id':history[j]['id'],'L1_percentage_points':distance,'history_link_required':distance<=.5})
            for j in np.flatnonzero(d[k]<=.5):
                if int(j)<=i:continue
                q=current[int(j)]
                if q['family']!=r['family']:
                    union(r['family'],q['family']);edges.append({'a':r['id'],'b':q['id'],'family_a':r['family'],'family_b':q['family'],'L1_percentage_points':float(d[k,j])})
            for j in np.flatnonzero(dh[k]<=.5):history_edges.append({'id':r['id'],'family':r['family'],'history_id':history[int(j)]['id'],'L1_percentage_points':float(dh[k,j])})
            for m in 'ABCD':
                if m<=r['member']:continue
                jj=[x for x,q in enumerate(current) if q['member']==m]
                value=float(d[k,jj].min());pairmin[r['member']+m]=min(pairmin.get(r['member']+m,float('inf')),value)
    historical_tokens={str(a[k]) for h in history for a in h['aliases'] for k in ('id','parent') if a.get(k)}
    explicit_links=[]
    for row in rows:
        prov=row['provenance'];claims={k:prov.get(k) for k in ('parent_family','historical_parent_id','root_parent','root_parent_id','generator_family')}
        if isinstance(prov.get('lineage'),dict):claims.update({'lineage.'+k:prov['lineage'].get(k) for k in ('parent_family','historical_parent_id','root_parent','root_parent_id')})
        for field,value in claims.items():
            if value is None:continue
            token=str(value)
            if token in historical_tokens:
                link={'id':row['id'],'family':row['family'],'historical_parent':token,'field':field,'kind':'explicit_ancestry'};history_edges.append(link);explicit_links.append(link)
            elif token in parent and token!=row['family']:
                union(row['family'],token);link={'a':row['id'],'family_a':row['family'],'family_b':token,'field':field,'kind':'explicit_ancestry'};edges.append(link);explicit_links.append(link)
    groups=collections.defaultdict(list)
    for f in families:groups[find(f['design_family_id'])].append(f['design_family_id'])
    out.mkdir(parents=True)
    closure={'status':'passed_global_candidate_lineage_checks' if not edges and not history_edges else 'blocked_connected_allocation_required','source_main':args.source_commit,'candidate_count':len(rows),'design_families':len(families),'original_backgrounds':len(boards),'registered_history_distinct_compositions':len(history),'registered_history_aliases':sum(len(h['aliases']) for h in history),'distance_elements':elements,'threshold_L1_percentage_points':.5,'cross_family_edges':edges,'history_edges':history_edges,'explicit_ancestry_links':explicit_links,'unified_components':list(groups.values()),'minimum_current_or_background_history_L1_pp':historymin,'pairwise_member_minimum_L1_including_backgrounds':pairmin,'history_coverage_limit':HISTORY_LIMIT,'external_independent_blindness':False,'notes':notes}
    if sum(r['provenance'].get('historical_train_only_constraint_pending') is True for r in rows if r['member']=='B')==1000:
        closure['notes'].append('B sets historical_train_only_constraint_pending=true unconditionally; coordinator independently derives actual history links from the registered composition table instead of treating this pending flag as an assigned role.')
    write(out/'global_closure.json',closure);write(out/'input_identity.json',{'source_main':args.source_commit,'sources':sources,'member_receipts':members,'spectra_generated':0})
    save_csv(out/'global_nearest_history.csv',nearest,list(nearest[0]));jsonl_gz(out/'historical_compositions.jsonl.gz',history)
    if edges or history_edges:raise ValueError('Connected family/history allocation needs review; no production release created')
    def select_balanced(pool,n,domain):
        selected=[];target_counts=collections.Counter()
        for _ in range(n):
            f=min(pool,key=lambda f:(target_counts[str(f['target'])],key(domain+f['design_family_id'])));pool.remove(f);selected.append(f);target_counts[str(f['target'])]+=1
        return selected
    def matrix_quota(pool,n):
        counts=collections.Counter(f['matrix'] for f in pool);keys=sorted(counts);q={k:int(n*counts[k]/len(pool)) for k in keys}
        while sum(q.values())<n:
            k=max(keys,key=lambda k:(n*counts[k]/len(pool)-q[k],key(k)));q[k]+=1
        if n>=len(keys) and all(counts[k]>=3 for k in keys):
            for k in keys:
                if q[k]==0:
                    donor=max(keys,key=lambda x:q[x]);q[donor]-=1;q[k]=1
        return q
    assigned=[]
    for m in 'ABCD':
        for category in CATEGORIES:
            pool=[dict(f) for f in families if f['member']==m and f['category']==category]
            n_eval=len(pool)//10
            for role in ('sealed_test','validation'):
                quotas=matrix_quota(pool,n_eval)
                for mat,n in quotas.items():
                    sub=[f for f in pool if f['matrix']==mat]
                    for f in select_balanced(sub,n,m+category+role+mat):
                        pool.remove(f);assigned.append({**f,'unified_family_id':find(f['design_family_id']),'usage':role,'training_stage':'none'})
            original_train=len(pool)
            for stage,n in [('stage1',original_train//4),('stage2',original_train//4),('stage3',original_train-original_train//2)]:
                quotas=matrix_quota(pool,n)
                for mat,k in quotas.items():
                    sub=[f for f in pool if f['matrix']==mat]
                    for f in select_balanced(sub,k,m+category+stage+mat):
                        pool.remove(f);assigned.append({**f,'unified_family_id':find(f['design_family_id']),'usage':'train','training_stage':stage})
    actual=collections.Counter();stages=collections.Counter()
    for f in assigned:
        actual[f['member'],f['usage']]+=f['recipes']*20
        if f['usage']=='train':stages[f['member'],f['training_stage']]+=f['recipes']*20
    for m in 'ABCD':
        factor=2 if m=='A' else 1
        for role,n in [('train',16000),('validation',2000),('sealed_test',2000)]:
            if actual[m,role]!=n*factor:raise ValueError('Role quota mismatch '+str((m,role,actual[m,role])))
        if [stages[m,s] for s in ('stage1','stage2','stage3')]!=[4000*factor,4000*factor,8000*factor]:raise ValueError('Stage quota mismatch')
    write(out/'family_assignments.json',{'status':'prepared_for_freeze_review','source_main':args.source_commit,'assignment_rule':'whole family; exact member/category quotas; feasible matrix representation; deterministic target-balanced selection; submitted requested_role is nominal only','production_release_approved':False,'families':assigned,'role_spectra_counts':{m:{role:actual[m,role] for role in ('train','validation','sealed_test')} for m in 'ABCD'},'training_stage_increment_spectra':{m:{s:stages[m,s] for s in ('stage1','stage2','stage3')} for m in 'ABCD'},'nominal_role_changes':sum(f['nominal_role'] not in (None,'unassigned_pending_global_freeze',f['usage']+'_nominal') for f in assigned)})
    write(out/'candidate_receipt.json',{'status':'passed_coordinator_candidate_receipt','source_main':args.source_commit,'members':members,'candidate_count':len(rows),'family_count':len(families),'source_files':sources,'production_approved':False,'spectra_generated':0,'notes':closure['notes']})
    print(json.dumps({'status':'prepared_global_closure_and_family_roles','candidates':len(rows),'families':len(families),'history_distinct':len(history),'current_history_min_L1':historymin,'cross_family_edges':len(edges),'history_edges':len(history_edges),'role_spectra_counts':{m:{role:actual[m,role] for role in ('train','validation','sealed_test')} for m in 'ABCD'}},ensure_ascii=False))

if __name__=='__main__':main()
