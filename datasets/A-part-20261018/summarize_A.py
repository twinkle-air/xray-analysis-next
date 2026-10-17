"""Build the external member-A delivery index after both full checks."""
import csv,json,hashlib,sys,zipfile
from pathlib import Path
from collections import Counter
OUT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(name,d): (OUT/name).write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
samples=read(OUT/'A_samples.json')['samples']
assert len(samples)==2500 and len({s['id'] for s in samples})==2500
keys=[tuple(sorted((k,round(v,12)) for k,v in s['composition_percent'].items() if v)) for s in samples]
assert len(set(keys))==2500
assert Counter(s['provenance']['scenario'] for s in samples)==dict(routine=1500,sparse_boundary=500,interference=500)
for s in samples:
    assert abs(sum(s['composition_percent'].values())-100)<1e-10
    p=s['provenance']; c=p['conversion_original_percent']
    assert all(abs(c.get(k,0)-v)<1e-10 for k,v in s['composition_percent'].items())
families={}
for s in samples: families.setdefault(s['provenance']['parent_family'],[]).append(s)
assert Counter(len(v) for v in families.values())=={1:2000,5:100}
for members in families.values():
    if len(members)!=5:continue
    assert [s['provenance']['design_detail']['control'] for s in members]==[[0,0],[1,0],[0,1],[1,1],[10,1]]
    for s in members:
        p=s['provenance'];d=p['design_detail'];a,b=d['control']
        assert abs(p['trace_ppm']['Pb']-100*b)<1e-10
        if d['pair'][0]=='As':assert abs(p['trace_ppm']['As']-100*a)<1e-10
        else:assert abs(p['compounds_percent']['CaSO4']-.1*a)<1e-10
summary={'owner':'A','formula_count':2500,'unique_compositions_rounded_12_decimals':2500,'parent_families':len(families),'formula_checks':'passed','cross_person_review':'pending','global_split':'pending_B_C_master','formal_20000_spectra':'not_generated','pilots':{}}
rows=[]
for profile in ('P1','P2'):
    root=OUT/('pilot_'+profile);m=read(root/'manifest.json')
    audit=read(OUT/(profile+'_audit.json'));replay=read(OUT/(profile+'_replay.json'))
    assert audit['status']=='passed' and replay['status'] in ('passed','passed_with_environment_differences')
    assert not replay['errors']
    env=read(OUT/(profile+'_replay_environment.json'))
    assert {k:v for k,v in env['generation'].items() if k!='thread_environment'}=={k:v for k,v in env['replay'].items() if k!='thread_environment'}
    assert replay['spectra_recalculated']==200 and replay['complete_physics_recalculation']
    archive=OUT/(profile+'_pack.zip')
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==(archive.with_suffix('.zip.sha256').read_text().split()[0])
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    truth=[json.loads(x) for x in (root/'truth.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(truth)==200 and len({x['original_sample_id'] for x in truth})==100
    assert m['jitter_ranges']=={} and m['replicates']==2
    totals=[];line_pairs=Counter()
    for record,label in zip(m['records'],truth):
        assert record['id']==label['id']
        p=label['source_provenance']
        rows.append([profile,record['id'],profile+'-'+record['id'],label['original_sample_id'],p['parent_family'],p['matrix'],p['scenario'],label['split'],'workflow_pilot_only',record['blind_input_sha256'],record['full_results_sha256']])
        full=read(root/record['full_results']);totals.append(sum(full['counts']))
        lines=full['lines']; present={l['element'] for l in lines if m['window_summary']['lower_edge_range'][0]<=l['energy_keV']<=m['window_summary']['upper_edge_range'][0]}
        for a,b in [('As','Pb'),('S','Pb')]:
            if a in present and b in present:line_pairs[a+'/'+b]+=1
    summary['pilots'][profile]=dict(spectra=200,formulas=100,audit=audit['status'],full_replay=replay['status'],same_environment=replay['same_environment'],environment_difference='Thread limits only; complete difference record in replay_environment JSON',maximum_absolute_array_difference=replay['maximum_absolute_array_difference'],total_observed_counts_range=[min(totals),max(totals)],candidate_pairs_with_both_line_centers_in_window=dict(line_pairs),raw_bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),check_timings=read(OUT/(profile+'_check_timings.json')))
with (OUT/'pilot_index.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['profile_id','local_id','global_id','formula_id','parent_family','matrix','scenario','generator_split','benchmark_split','blind_sha256','full_sha256']);w.writerows(rows)
save('A_acceptance_summary.json',summary)
save('A_delivery_hashes.json',{str(p.relative_to(OUT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='A_delivery_hashes.json'})
print(json.dumps(summary,ensure_ascii=False,indent=2))
