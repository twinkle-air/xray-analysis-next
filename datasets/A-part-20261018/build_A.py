"""Deterministic member A design; existing FP generator remains unchanged."""
import sys, json, csv, hashlib, collections
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from fp_competition.minerals import design_minerals, components_to_elements
from fp_competition.core import TARGET_ELEMENTS
OUT=Path(__file__).resolve().parent
def save(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
spec=json.loads((ROOT/'fp_competition/mineral_design_ranges.json').read_text(encoding='utf-8'))
rng=np.random.default_rng(2026101810)
base=design_minerals(spec,2100,2026101811)['samples']
samples=[]
def add(compounds,traces,scenario,family,detail):
    compounds=dict(compounds);traces=dict(traces)
    compounds['SiO2']=100-sum(v for k,v in compounds.items() if k!='SiO2')-sum(traces.values())/10000
    assert 25<=compounds['SiO2']<=100
    used,provenance=components_to_elements(compounds,traces)
    provenance.update(basis='Explicit synthetic experimental design; not real population or certified material',matrix='silicate_oxide',owner='A',scenario=scenario,parent_family=family,design_detail=detail)
    samples.append(dict(id=f'A{len(samples)+1:05d}',composition_percent=used,provenance=provenance))
for i,s in enumerate(base[:1500]):
    p=s['provenance'];add(p['compounds_percent'],p['trace_ppm'],'routine',f'A-R{i:04d}','Existing mineral ranges, uniform compounds and log-uniform positive traces; 25% trace absence')
# Ten 50-recipe blocks remove all optional components, set them low, then
# cover progressively higher component fractions. Si/O remain required matrix.
for i,s in enumerate(base[1500:2000]):
    p=s['provenance'];c=dict(p['compounds_percent']);t=dict(p['trace_ppm']);block=i//50
    if block==0:
        c={k:0. for k in c if k!='SiO2'};t={k:0. for k in t}
        # Distinct Al-bearing backgrounds preserve all optional zero targets
        # except Al, which has its own exact-zero block below.
        c['Al2O3']=5+i*.1
    elif block==1:
        c={k:0. for k in c if k!='SiO2'};c['Fe2O3T']=1+(i-50)*.05;t={k:0. for k in t}
    elif block==2:
        c={k:float(v[0])*.01 for k,v in spec['compound_ranges_percent'].items()};t={k:float(v[0]) for k,v in spec['trace_ranges_ppm'].items()}
        c['Al2O3']*=1+(i-100)*.01
    else:
        # A single common scale preserves feasibility and spans low to high
        # mixtures; extra zeros improve sparse-element coverage.
        scale=[.02,.05,.1,.25,.5,.75,1.][block-3]
        c={k:v*scale for k,v in c.items() if k!='SiO2'}
        t={k:(v*scale if rng.random()>.5 else 0.) for k,v in t.items()}
    add(c,t,'sparse_boundary',f'A-S{i:04d}',f'Boundary block {block}; designed rather than measured distribution')
# 100 parents x 5 controls. Each family stays together downstream.
controls=[(0,0),(1,0),(0,1),(1,1),(10,1)]
for j,s in enumerate(base[2000:2100]):
    p=s['provenance'];pair=('As','Pb') if j<50 else ('S','Pb')
    for a,b in controls:
        c=dict(p['compounds_percent']);t=dict(p['trace_ppm'])
        if pair[0]=='As':t['As']=100.*a
        else:c['CaSO4']=.1*a
        t['Pb']=100.*b
        add(c,t,'interference',f'A-I{j:04d}',dict(pair=pair,control=[a,b],As_or_Pb_unit='ppm',S_carrier='CaSO4 mass percent 0.1 x control'))
assert len(samples)==2500
fingerprints=[hashlib.sha256(json.dumps({k:v for k,v in s['composition_percent'].items() if v!=0},sort_keys=True).encode()).hexdigest() for s in samples]
assert len(set(fingerprints))==2500
assert max(abs(sum(s['composition_percent'].values())-100) for s in samples)<1e-10
save('A_samples.json',dict(synthetic_design=True,seed=2026101810,samples=samples))
save('A_design_ranges.json',spec)
coverage={e:dict(zero=sum(s['composition_percent'].get(e,0)==0 for s in samples),low_0_to_0_1_percent=sum(0<s['composition_percent'].get(e,0)<=.1 for s in samples),above_0_1_percent=sum(s['composition_percent'].get(e,0)>.1 for s in samples)) for e in TARGET_ELEMENTS}
save('A_coverage.json',dict(total=2500,unique=2500,scenario_counts=dict(collections.Counter(s['provenance']['scenario'] for s in samples)),low_definition='0 < elemental mass percent <= 0.1; operational design bin, not detection limit',coverage=coverage,gaps={e:v for e,v in coverage.items() if v['zero']<50 or v['low_0_to_0_1_percent']<50},required_matrix=['Si','O']))
with (OUT/'A_formula_registry.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['formula_id','parent_family','matrix','scenario','composition_sha256','split_status'])
    for s,h in zip(samples,fingerprints):
        p=s['provenance'];w.writerow([s['id'],p['parent_family'],p['matrix'],p['scenario'],h,'pending_global_5000_family_split'])
# Pilot: 20 routine, 20 sparse, 12 complete interference families = 100.
pilot=samples[:20]+[samples[1500+i] for i in range(0,500,25)]+samples[2000:2030]+samples[2250:2280]
assert len(pilot)==100
save('A_pilot_samples.json',dict(synthetic_design=True,purpose='Workflow pilot only; no authoritative train/test split',samples=pilot))
print('Designed 2500 unique recipes; selected 100 pilot recipes')
