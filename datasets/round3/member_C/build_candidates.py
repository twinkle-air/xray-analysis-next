"""Round-three C candidate construction. Does not generate spectra or approve a split.

The construction logic is the reference implementation published by member A
(`datasets/round3/member_A/build_candidates.py`), reproduced so that C's recipes are
directly comparable to A's for the global dedup/freeze. The only intentional
differences are: the assignment comes from A's published
`shared/preparation_v1/design_allocation.json` (filtered to owner C and cross-checked
against the local re-derivation), provenance records owner C, and the delivery
artifacts add a template-conformant candidate registry plus one original background
board per design family. Nothing here produces spectra.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, math, pathlib, sys
import numpy as np
import xraylib as xl
from scipy.spatial.distance import cdist

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUTS = HERE/'inputs'
if (INPUTS/'generator/fp_competition').is_dir(): sys.path.insert(0, str(INPUTS/'generator'))
from fp_competition.core import TARGET_ELEMENTS
from fp_competition.minerals import components_to_elements, design_minerals

SEED = 202610230301
FOCUS = ('Na', 'Cu', 'Zn', 'Cd', 'Co', 'Rb')
PAIRS = (('Na','Zn'),('Cu','Ni'),('Zn','W'),('Cd','K'),('Co','Fe'),('Rb','Y'),('As','Pb'),('Ti','Ba'))
CARRIERS = {'Na':'Na2O','K':'K2O','Fe':'Fe2O3T','Ti':'TiO2'}
VARIANTS = {'ladder':6,'interference':5,'paired_negative_spike':2,'routine':1}
ALLOCATION = ROOT/'datasets/round3/shared/preparation_v1/design_allocation.json'

def read(path): return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))
def write(path, value):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
def sha(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def canonical(comp): return json.dumps({e:round(float(v),12) for e,v in sorted(comp.items()) if round(float(v),12)!=0}, sort_keys=True, separators=(',',':'))
def recipe_sha(comp): return hashlib.sha256(canonical(comp).encode()).hexdigest()
def stable_seed(text): return int.from_bytes(hashlib.sha256((str(SEED)+':'+text).encode()).digest()[:8],'big')%(2**63-1)
def logdraw(rng, lo, hi): return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
def fraction(formula, element):
    d = xl.CompoundParser('Fe2O3' if formula=='Fe2O3T' else formula)
    return sum(w for z,w in zip(d['Elements'], d['massFractions']) if xl.AtomicNumberToSymbol(z)==element)

def allocation():
    """Independent re-derivation of the global 420-family design assignment."""
    rows=[]; counts=collections.Counter()
    def add(category, target, pair, n_sil, n_iron):
        for matrix, n in [('silicate_oxide',n_sil),('iron_oxide',n_iron)]:
            for _ in range(n):
                owner='ABCD'[counts[category,matrix]%4]; counts[category,matrix]+=1
                fid=f'R3_{owner}_{category}_{len(rows)+1:04d}'
                rows.append({'design_family_id':fid,'owner':owner,'category':category,'matrix':matrix,'target':target,'interferent':pair,'variants':VARIANTS[category],'design_seed':stable_seed(fid),'status':'assigned_design_pending_candidates_and_global_freeze'})
    for e in FOCUS: add('ladder',e,None,6,4)
    for a,b in PAIRS: add('interference',a,b,3,2)
    for e,n in zip(FOCUS,[40,30,20,10,10,10]):
        add('paired_negative_spike',e,dict(Na='Zn',Cu='Ni',Zn='W',Cd='K',Co='Zn',Rb='Y')[e],n*3//5,n*2//5)
    add('routine',None,None,120,80)
    return rows

def assignment(owner='C'):
    """A's published allocation, cross-checked against the local re-derivation."""
    doc = read(ALLOCATION); families = doc['families']
    if doc['production_approved'] is not False or doc['status']!='design_assigned_pending_actual_candidates':
        raise ValueError('Shared allocation is not in the expected pending state')
    keys = ['design_family_id','owner','category','matrix','target','interferent','variants','design_seed']
    derived = allocation()
    if len(families)!=420 or len(derived)!=420: raise ValueError('420 design families expected')
    for published, local in zip(families, derived):
        if {k:(published.get(k) if k!='design_family_id' else published[k]) for k in keys} != {k:local[k] for k in keys}:
            raise ValueError('Published allocation differs from re-derivation: '+str(published.get('design_family_id')))
    mine = [dict(f) for f in families if f['owner']==owner]
    if len(mine)!=105 or sum(f['variants'] for f in mine)!=250: raise ValueError('C must own 105 families and 250 recipes')
    return mine

def modify(base, controls):
    """Fix controlled elemental ppm via explicit carriers, scale remaining mixture."""
    c=dict(base['provenance']['compounds_percent']); t=dict(base['provenance']['trace_ppm'])
    removed={}; fixed_c={}; fixed_t={}
    for element,ppm in controls.items():
        if not math.isfinite(ppm) or ppm<0: raise ValueError('Invalid controlled concentration')
        for formula in list(c):
            if fraction(formula,element)>0: removed[formula]=c.pop(formula)
        t.pop(element,None)
        if element in CARRIERS:
            carrier=CARRIERS[element]; fixed_c[carrier]=ppm/10000/fraction(carrier,element)
        else: fixed_t[element]=ppm
    remaining=sum(c.values())+sum(t.values())/10000
    fixed_mass=sum(fixed_c.values())+sum(fixed_t.values())/10000
    if remaining<=0 or fixed_mass>=100: raise ValueError('Infeasible fixed concentrations')
    scale=(100-fixed_mass)/remaining
    adopted_c={k:v*scale for k,v in c.items()}; adopted_c.update(fixed_c)
    adopted_t={k:v*scale for k,v in t.items()}; adopted_t.update(fixed_t)
    used,conversion=components_to_elements(adopted_c,adopted_t,closure='strict')
    actual={e:used.get(e,0)*10000 for e in controls}
    if any(not np.isclose(actual[e],v,rtol=1e-10,atol=1e-9) for e,v in controls.items()): raise ValueError('Target changed during conversion')
    delta={e:used.get(e,0)-base['composition_percent'].get(e,0) for e in set(used)|set(base['composition_percent'])}
    conversion['intervention']={'controlled_element_ppm':controls,'actual_element_ppm':actual,'removed_carrier_compounds_percent':removed,'fixed_carriers_percent':fixed_c,'uncontrolled_mixture_scale':scale,'compensation':'proportional scaling of all remaining compounds and traces; controlled carriers replaced; no hidden normalization','element_delta_percentage_points':delta,'controlled_range_override':True,'caveat':'Original ranges describe the initial background. Controlled target-zero/ladder levels intentionally override its ranges; noncontrolled compounds must retain original bounds.'}
    return used, conversion

def variants(family, rng):
    e,b,category=family['target'],family['interferent'],family['category']
    if category=='ladder':
        intervals=[(10,50),(50,200),(200,1000),(1000,5000),(5000,30000)] if e=='Na' else [(.5,2),(2,5),(5,15),(15,50),(50,200)]
        return [('zero',{e:0},None)]+[(f'level_{i+1}',{e:logdraw(rng,*limits)},list(limits)) for i,limits in enumerate(intervals)]
    if category in ('interference','paired_negative_spike'):
        matrix=family['matrix']; iron=matrix=='iron_oxide'
        if b in ('K','Fe'):
            if b=='Fe': low_c,high_c=((42,48),(65,73)) if iron else ((2,5),(12,18))
            else: low_c,high_c=((.1,.3),(1.2,1.8)) if iron else ((.1,.5),(3,4.5))
            low=float(rng.uniform(*low_c))*fraction(CARRIERS[b],b)*10000
            high=float(rng.uniform(*high_c))*fraction(CARRIERS[b],b)*10000
        else:
            bounds={'Zn':(1000,2000) if not iron else (2000,3000),'Ni':(500,1000) if not iron else (1000,2000),'W':(500,1000) if not iron else (1000,2000),'Y':(200,500) if not iron else (700,1500),'Pb':(1000,2000) if not iron else (2000,3000),'Ba':(1500,3000) if not iron else (2500,4000)}
            low=0.; high=logdraw(rng,*bounds[b])
        if category=='paired_negative_spike':
            levels=(1000,10000) if e=='Na' else ((20,200) if e in ('Cu','Zn') else (10,100))
            positive=logdraw(rng,*levels)
            return [('negative',{e:0,b:high},None),('spike',{e:positive,b:high},list(levels))]
        tl=logdraw(rng,100,500) if e=='Na' else logdraw(rng,3,15)
        th=logdraw(rng,5000,20000) if e=='Na' else (logdraw(rng,2000,10000) if e=='Ti' else logdraw(rng,100,200))
        return [(role,{e:a,b:v},None) for role,a,v in [('target0_interferent_low',0,low),('target_low_interferent_low',tl,low),('target0_interferent_high',0,high),('target_low_interferent_high',tl,high),('target_high_interferent_high',th,high)]]
    return [('routine',{},None)]

def in_bounds(ledger, spec, controlled):
    c=ledger['compounds_percent']; t=ledger['trace_ppm']; bounds={**spec['compound_ranges_percent'],spec['balance_compound']:spec['balance_range_percent']}
    removed=set(ledger['intervention']['removed_carrier_compounds_percent'])
    for formula,limits in bounds.items():
        if formula in removed or any(fraction(formula,e)>0 for e in controlled): continue
        if not limits[0]-1e-9<=c.get(formula,0)<=limits[1]+1e-9: return False
    for e,value in t.items():
        if e not in controlled and value!=0 and not spec['trace_ranges_ppm'][e][0]-1e-7<=value<=spec['trace_ranges_ppm'][e][1]+1e-7: return False
    # Material identity is retained even when Fe is the controlled interferent.
    balance=spec['balance_compound']; lo,hi=spec['balance_range_percent']
    return lo-1e-9<=c.get(balance,0)<=hi+1e-9

def positive_sources(row):
    """Elements carried by any compound with positive amount, plus positive traces."""
    conv=row['provenance']['conversion']; carried=collections.defaultdict(list)
    for formula,amount in conv['compounds_percent'].items():
        if amount<=0: continue
        d=xl.CompoundParser('Fe2O3' if formula=='Fe2O3T' else formula)
        for z in d['Elements']:
            symbol=xl.AtomicNumberToSymbol(z)
            if symbol in TARGET_ELEMENTS or symbol=='O': carried[symbol].append(formula)
    for symbol,amount in conv['trace_ppm'].items():
        if amount>0: carried[symbol].append('trace_ppm')
    return carried

def exact_zero_conflicts(rows):
    """Task rule: an exact-zero label must have no other compound or trace source."""
    conflicts=[]; verified=0
    for row in rows:
        carried=positive_sources(row)
        for symbol,value in row['composition_percent'].items():
            if value==0:
                verified+=1
                if carried.get(symbol): conflicts.append((row['id'],symbol,carried[symbol]))
    return conflicts, verified

def construct(specs, families):
    samples=[]; built=[]
    for family in families:
        spec=specs[family['matrix']]['routine']; rng=np.random.default_rng(family['design_seed'])
        design=variants(family,rng)
        # Other target zero states are drawn independently, not all-zero masks.
        extra={e:0. for e in FOCUS if e not in (family['target'],family['interferent']) and rng.random()<.25}
        if family['category']=='routine' and rng.random()<.25: extra['Na']=0.
        for attempt in range(500):
            background_seed=stable_seed(family['design_family_id']+f':background:{attempt}')
            base=design_minerals(spec,1,background_seed)['samples'][0]
            rows=[]
            for index,(role,control,interval) in enumerate(design):
                controls={**extra,**control}; used,ledger=modify(base,controls)
                if not in_bounds(ledger,spec,controls): break
                provenance={'kind':'round3_matched_compound_design','round_id':'round3','owner':'C','parent_family':family['design_family_id'],'matrix_type':family['matrix'],'scenario':family['category'],'control_role':role,'target':family['target'],'interferent':family['interferent'],'target_bin_ppm':interval,'design_seed':family['design_seed'],'background_seed':background_seed,'background_attempt':attempt,'original_compounds_percent':base['provenance']['compounds_percent'],'original_trace_ppm':base['provenance']['trace_ppm'],'original_composition_percent':base['composition_percent'],'conversion':ledger,'lineage':'fresh independent background draw; not derived from a historical error example','global_status':'candidate_pending_global_freeze','scope':'synthetic homogeneous compound design; not certified material or measured geological population'}
                rows.append({'id':f"{family['design_family_id']}_V{index+1:02d}",'composition_percent':used,'provenance':provenance})
            if len(rows)==family['variants']:
                conflicts,_=exact_zero_conflicts(rows)
                if conflicts: raise ValueError('Exact zero has another source: '+str(conflicts[:4]))
                samples.extend(rows); built.append({**family,'background_seed':background_seed,'background_attempt':attempt,'sample_ids':[r['id'] for r in rows]}); break
        else: raise ValueError('No feasible background: '+family['design_family_id'])
    return samples, built

def historical():
    """Historical comparison snapshot: C reuses the archive already published in the repository.

    No duplicate copy is committed (the bytes are identical to member A's published
    snapshot), so the archive is read from its repository path and its SHA-256 is
    recorded in candidates/input_identity.json.
    """
    for candidate in (INPUTS/'historical_compositions.json', ROOT/'datasets/round3/member_A/inputs/historical_compositions.json'):
        if candidate.exists():
            archived = read(candidate)
            return archived['rows'], archived['sources'], candidate
    raise ValueError('Historical snapshot is not available in this checkout; it must not be rebuilt from local outputs')

def verify(samples, families, specs, history):
    errors=[]; ids=[r['id'] for r in samples]
    if len(samples)!=250 or len(set(ids))!=250: errors.append('250 distinct IDs required')
    if len({canonical(r['composition_percent']) for r in samples})!=len(samples): errors.append('Duplicate actual composition')
    if len(families)!=105: errors.append('105 design families required')
    expected={'ladder':90,'interference':50,'paired_negative_spike':60,'routine':50}
    if dict(collections.Counter(r['provenance']['scenario'] for r in samples))!=expected: errors.append('Category quota mismatch')
    if dict(collections.Counter(r['provenance']['matrix_type'] for r in samples))!={'silicate_oxide':150,'iron_oxide':100}: errors.append('Matrix quota mismatch')
    for category,sil,iron in [('ladder',54,36),('interference',30,20),('paired_negative_spike',36,24),('routine',30,20)]:
        actual_counts=collections.Counter(r['provenance']['matrix_type'] for r in samples if r['provenance']['scenario']==category)
        if actual_counts!={'silicate_oxide':sil,'iron_oxide':iron}: errors.append('Category/matrix quota mismatch')
    grouped=collections.defaultdict(list)
    for row in samples:
        comp=row['composition_percent']; p=row['provenance']; conv=p['conversion']; controls=conv['intervention']['controlled_element_ppm']
        if abs(sum(comp.values())-100)>1e-9 or comp.get('O',0)<=0: errors.append(row['id']+': closure/O')
        outside=sorted(set(comp)-set(TARGET_ELEMENTS)-{'O'})
        if outside: errors.append(row['id']+': untracked elements '+','.join(outside))
        rebuilt,_=components_to_elements(conv['compounds_percent'],conv['trace_ppm'],closure='strict')
        if canonical(rebuilt)!=canonical(comp): errors.append(row['id']+': conversion mismatch')
        if not in_bounds(conv,specs[p['matrix_type']]['routine'],controls): errors.append(row['id']+': range violation')
        if any(not np.isclose(comp.get(e,0)*10000,v,atol=1e-9,rtol=1e-10) for e,v in controls.items()): errors.append(row['id']+': actual ppm mismatch')
        original,_=components_to_elements(p['original_compounds_percent'],p['original_trace_ppm'],closure='strict')
        if canonical(original)!=canonical(p['original_composition_percent']): errors.append(row['id']+': original background mismatch')
        check_base={'provenance':{'compounds_percent':p['original_compounds_percent'],'trace_ppm':p['original_trace_ppm']},'composition_percent':original}
        independently_rebuilt,rebuilt_ledger=modify(check_base,controls)
        if canonical(independently_rebuilt)!=canonical(comp) or rebuilt_ledger!=conv: errors.append(row['id']+': compensation/provenance mismatch')
        grouped[p['parent_family']].append(row)
    for family in families:
        rows=grouped[family['design_family_id']]; e=family['target']; cat=family['category']
        if len(rows)!=family['variants']: errors.append('Incomplete family '+family['design_family_id']); continue
        if len({canonical(r['provenance']['original_composition_percent']) for r in rows})!=1: errors.append('Matched controls use different original backgrounds')
        actual=[r['composition_percent'].get(e,0)*10000 for r in rows] if e else []
        if cat=='ladder':
            if actual[0]!=0 or not all(a<b for a,b in zip(actual,actual[1:])): errors.append('Invalid ladder')
            for r,v in zip(rows[1:],actual[1:]):
                interval=r['provenance']['target_bin_ppm']
                if not isinstance(interval,list) or len(interval)!=2: errors.append('Invalid ladder bin metadata'); continue
                lo,hi=interval
                if not lo<=v<hi: errors.append('Wrong ladder bin')
        if cat=='paired_negative_spike' and not (actual[0]==0 and actual[1]>0): errors.append('Invalid negative/spike pair')
        if cat=='interference':
            b=family['interferent']; v=[r['composition_percent'].get(b,0)*10000 for r in rows]
            if not (actual[0]==actual[2]==0 and np.isclose(actual[1],actual[3]) and actual[4]>actual[3]>0 and np.isclose(v[0],v[1]) and np.isclose(v[2],v[3]) and np.isclose(v[3],v[4]) and v[2]>v[0]): errors.append('Invalid five-way interference controls')
    zero_conflicts, zero_verified=exact_zero_conflicts(samples)
    for row_id,symbol,sources in zero_conflicts[:20]: errors.append(f'{row_id}: exact-zero label {symbol} still carried by {",".join(sources)}')
    elements=sorted(set().union(*(r['composition_percent'] for r in samples+history)))
    a=np.array([[r['composition_percent'].get(e,0) for e in elements] for r in samples]); b=np.array([[r['composition_percent'].get(e,0) for e in elements] for r in history])
    distances=cdist(a,b,'cityblock'); nearest=distances.argmin(axis=1)
    matches=[{'sample_id':r['id'],'historical_id':history[int(j)]['id'],'minimum_L1_percentage_points':float(distances[i,j]),'requires_train_only':bool(distances[i,j]<=.5)} for i,(r,j) in enumerate(zip(samples,nearest))]
    within=cdist(a,a,'cityblock'); edges=[]
    for i,j in zip(*np.where(np.triu(within<=.5,1))):
        if samples[i]['provenance']['parent_family']!=samples[j]['provenance']['parent_family']: edges.append({'a':samples[i]['id'],'b':samples[j]['id'],'L1':float(within[i,j])})
    return {'status':'passed_member_candidate_checks' if not errors else 'failed','errors':errors,'candidate_count':len(samples),'design_family_count':len(families),'category_counts':dict(collections.Counter(r['provenance']['scenario'] for r in samples)),'matrix_counts':dict(collections.Counter(r['provenance']['matrix_type'] for r in samples)),'exact_zero_labels_verified':zero_verified,'exact_zero_label_conflicts':len(zero_conflicts),'historical_rows_compared':len(history),'historical_nearest':matches,'cross_design_family_near_edges':edges,'historical_coverage':'same published snapshot as member A: accepted round-2 recipes plus available round-1 candidate/pilot/research records; undocumented or missing historical ancestry not ruled out','cross_member_confirmation':'pending_A_B_D_global_closure','production_started':False,'eligible_for_training':False}

def cross_member(samples, other_path):
    """C recipes against A's published candidate recipes (pairwise only, not global closure)."""
    path=pathlib.Path(other_path)
    if not path.exists(): return {'status':'other_member_candidates_absent','path':path.relative_to(ROOT).as_posix()}
    other=read(path)['samples']
    elements=sorted(set().union(*(r['composition_percent'] for r in samples+other)))
    a=np.array([[r['composition_percent'].get(e,0) for e in elements] for r in samples])
    b=np.array([[r['composition_percent'].get(e,0) for e in elements] for r in other])
    distances=cdist(a,b,'cityblock'); nearest=distances.argmin(axis=1)
    edges=[{'c':samples[i]['id'],'a':other[int(j)]['id'],'L1':float(distances[i,j])}
           for i,j in zip(*np.where(distances<=.5))]
    exact=[edge for edge in edges if edge['L1']==0.]
    return {'status':'passed_pairwise_cross_member_screen' if not edges else 'near_duplicates_found','compared_owner':'A','other_candidate_count':len(other),'minimum_L1_percentage_points':float(distances.min()),'pairs_within_L1_0_5':len(edges),'near_duplicate_edges':edges,'exact_composition_matches':exact,'note':'pairwise C-vs-A screen only; global four-member closure and historical connected components remain pending in A\'s freeze step'}

def registry_rows(samples):
    rows=[]
    for r in samples:
        v=r['provenance']; conv=v['conversion']; controls=conv['intervention']['controlled_element_ppm']
        interval=v['target_bin_ppm']
        bin_label='zero' if controls.get(v['target'])==0 and v['target'] else (';'.join(f'{x:g}' for x in interval) if isinstance(interval,list) else ('routine_background' if v['scenario']=='routine' else 'matched_control_level'))
        rows.append({'round_id':'round3','member':'C','global_recipe_id':r['id'],'design_family_id':v['parent_family'],'historical_parent_id':'','lineage_evidence_path':v['lineage'],'category':v['scenario'],'matrix_class':v['matrix_type'],'target_element':v['target'] or '','interferent_element':v['interferent'] or '','control_role':v['control_role'],'actual_target_ppm':(r['composition_percent'].get(v['target'],0)*10000 if v['target'] else ''),'actual_interferent_ppm':(r['composition_percent'].get(v['interferent'],0)*10000 if v['interferent'] else ''),'concentration_bin':bin_label,'original_recipe_path':'candidates/original_backgrounds.json#'+v['parent_family'],'used_composition_path':'candidates/C_samples.json#'+r['id'],'conversion_and_compensation_path':'candidates/C_samples.json#'+r['id']+'.provenance.conversion','candidate_sha256':recipe_sha(r['composition_percent']),'assigned_usage':'pending_global_freeze','assigned_profiles':'pending_A_condition_assignment','status':'pending_global_freeze'})
    return rows

def main():
    p=argparse.ArgumentParser(); p.add_argument('--out',type=pathlib.Path,required=True); args=p.parse_args()
    if args.out.exists(): raise ValueError('Refusing to overwrite candidates')
    ranges=INPUTS/'design_ranges.json'; specs=read(ranges)
    families=assignment('C'); samples,built=construct(specs,families)
    history,sources,archive=historical(); report=verify(samples,built,specs,history)
    report['member_A_cross_check']=cross_member(samples,ROOT/'datasets/round3/member_A/candidates_v1/A_samples.json')
    if report['errors']: raise ValueError(report['errors'])
    args.out.mkdir(parents=True)
    write(args.out/'C_samples.json',{'round_id':'round3','owner':'C','status':'candidate_pending_global_freeze','production_started':False,'samples':samples})
    write(args.out/'family_registry.json',{'design_families':built,'status':'pending_global_connected_closure','source_allocation':{'path':ALLOCATION.relative_to(ROOT).as_posix(),'sha256':sha(ALLOCATION),'production_approved':False}})
    write(args.out/'original_backgrounds.json',{'status':'candidate_pending_global_freeze','note':'one fresh independent background board per design family; every variant of a family shares it','backgrounds':{f['design_family_id']:{'matrix_type':f['matrix'],'background_seed':f['background_seed'],'background_attempt':f['background_attempt'],'compounds_percent':next(r['provenance']['original_compounds_percent'] for r in samples if r['provenance']['parent_family']==f['design_family_id']),'trace_ppm':next(r['provenance']['original_trace_ppm'] for r in samples if r['provenance']['parent_family']==f['design_family_id']),'composition_percent':next(r['provenance']['original_composition_percent'] for r in samples if r['provenance']['parent_family']==f['design_family_id'])} for f in built}})
    write(args.out/'candidate_checks.json',report)
    archive_relative=archive.relative_to(ROOT).as_posix()
    write(args.out/'input_identity.json',{'builder_sha256':sha(__file__),'owner':'C','seed':SEED,
        'ranges':{'path':ranges.relative_to(ROOT).as_posix(),'sha256':sha(ranges)},
        'shared_allocation':{'path':ALLOCATION.relative_to(ROOT).as_posix(),'sha256':sha(ALLOCATION)},
        'historical_archive':{'path':archive_relative,'sha256':sha(archive),
            'location':'member_C inputs copy' if archive_relative.startswith('datasets/round3/member_C') else 'read from the repository copy already published under member_A/inputs; C does not re-upload identical bytes',
            'provenance':'the same historical snapshot member A screened against, so C and A are compared against one historical population','status':read(archive)['status'],'coverage_limit':read(archive)['coverage_limit']},
        'historical_sources':sources,
        'generator_source_sha256':{name:sha(INPUTS/'generator/fp_competition'/name) for name in ['core.py','minerals.py','dataset.py','app.py','version.py','requirements-lock.txt']},
        'source_manifest':{'path':(INPUTS/'source_manifest.json').relative_to(ROOT).as_posix(),'sha256':sha(INPUTS/'source_manifest.json')},
        'spectra_generated':0,'production_started':False})
    with (args.out/'formula_registry.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f); w.writerow(['global_recipe_id','design_family_id','matrix','category','target','interferent','control_role','actual_target_ppm','composition_sha256','status'])
        for r in samples:
            v=r['provenance']; w.writerow([r['id'],v['parent_family'],v['matrix_type'],v['scenario'],v['target'],v['interferent'],v['control_role'],r['composition_percent'].get(v['target'],0)*10000,recipe_sha(r['composition_percent']),'pending_global_freeze'])
    columns=list(registry_rows(samples)[0].keys())
    with (args.out/'candidate_registry.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns); w.writeheader()
        for row in registry_rows(samples): w.writerow(row)
    write(args.out/'coverage.json',{'targets':{e:{'zero':sum(r['composition_percent'].get(e,0)==0 for r in samples),'positive_below_10ppm':sum(0<r['composition_percent'].get(e,0)<.001 for r in samples),'positive_at_least_10ppm':sum(r['composition_percent'].get(e,0)>=.001 for r in samples)} for e in TARGET_ELEMENTS},'scope':'composition labels, not measured detection limits','target_elements_tracked':len(TARGET_ELEMENTS)})
    print(json.dumps({k:v for k,v in report.items() if k not in ['historical_nearest','member_A_cross_check']},ensure_ascii=False))
    print(json.dumps({k:report[k] for k in ['member_A_cross_check']},ensure_ascii=False)[:600])
if __name__=='__main__': main()
