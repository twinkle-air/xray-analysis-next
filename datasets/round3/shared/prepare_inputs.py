"""Prepare inspectable profile/design inputs; never approve missing members or run production."""
from __future__ import annotations
import collections, hashlib, importlib.util, json, pathlib, shutil, sys, time
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
SOURCE_INPUTS=ROOT/'datasets/round3/member_A/inputs'
GENERATOR=SOURCE_INPUTS/'generator/fp_competition'
sys.path.insert(0,str(GENERATOR.parent))
from fp_competition.core import Profile, TARGET_ELEMENTS, element_support, simulate
from fp_competition.dataset import energy_window, environment

HERE=pathlib.Path(__file__).resolve().parent
DEST=HERE/'preparation_v1'

def read(path):return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))
def write(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def builder():
    spec=importlib.util.spec_from_file_location('round3_candidates',ROOT/'datasets/round3/member_A/build_candidates.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def main():
    if DEST.exists():raise ValueError('Refusing to overwrite existing preparation')
    remote=read(SOURCE_INPUTS/'repository_source.json')
    pinned={f['path']:f['sha256'] for f in remote['reference_profiles']}
    for rel,digest in read(SOURCE_INPUTS/'source_manifest.json')['files'].items():
        if sha(SOURCE_INPUTS/rel)!=digest:raise ValueError('Source input changed: '+rel)
    DEST.mkdir()
    identity={'repository_commit':remote['plan_ref'],'pr19_merged':remote['pr19']['merged'],'generator_source_sha256':{name:sha(GENERATOR/name) for name in ['core.py','minerals.py','dataset.py','app.py','version.py','requirements-lock.txt']},'environment':environment(),'physics_core_unchanged_from_round2':sha(GENERATOR/'core.py')=='e820ecdb5ed5fbceb870f382c8c7c411ba85c65673bc19258fb935f562ed83b0'}
    if not identity['physics_core_unchanged_from_round2']:raise ValueError('Physics core differs')
    write(DEST/'source_identity.json',identity)
    write(DEST/'design_allocation.json',{'status':'design_assigned_pending_actual_candidates','round_id':'round3','families':builder().allocation(),'production_approved':False})
    (DEST/'development_profiles').mkdir();(DEST/'heldout_profiles_qc_only').mkdir()
    profiles={};descriptions=[]
    for key in ['P1','P2','P3']:
        rel=f'datasets/round2/member_A/production_inputs_v2/profiles/{key}.json'
        data=(SOURCE_INPUTS/'reference_profiles'/f'{key}.json').read_bytes();assert hashlib.sha256(data).hexdigest()==pinned[rel]
        target=DEST/'development_profiles'/f'{key}.json';target.write_bytes(data)
        profiles[key]=read(target);Profile.from_dict(profiles[key])
        descriptions.append({'profile_id':key,'role':'development_anchor','path':target.relative_to(DEST).as_posix(),'sha256':sha(target),'source_path':rel,'source_sha256':pinned[rel],'exact_source_bytes_preserved':True})
    changes={
        'D1':('P1',{'gain_keV_channel':profiles['P1']['gain_keV_channel']*.995}),
        'D2':('P1',{'gain_keV_channel':profiles['P1']['gain_keV_channel']*1.005}),
        'D3':('P1',{'noise_fwhm_eV':profiles['P1']['noise_fwhm_eV']*1.15}),
        'D4':('P1',{'zero_keV':profiles['P1']['zero_keV']+.03}),
        'D5':('P1',{'live_time_s':profiles['P1']['live_time_s']*3}),
        'D6':('P2',{'exit_air_path_cm':profiles['P2']['exit_air_path_cm']+.5}),
        'T1':('P1',{'gain_keV_channel':profiles['P1']['gain_keV_channel']*1.0025,'zero_keV':profiles['P1']['zero_keV']+.015,'noise_fwhm_eV':profiles['P1']['noise_fwhm_eV']*1.075}),
        'T2':('P2',{'gain_keV_channel':profiles['P2']['gain_keV_channel']*.99,'zero_keV':profiles['P2']['zero_keV']+.04,'noise_fwhm_eV':profiles['P2']['noise_fwhm_eV']*1.25}),
        'T3':('P3',{'gain_keV_channel':profiles['P3']['gain_keV_channel']*1.003,'zero_keV':profiles['P3']['zero_keV']+.015,'noise_fwhm_eV':profiles['P3']['noise_fwhm_eV']*1.1,'live_time_s':profiles['P3']['live_time_s']*1.75})}
    for key,(parent,delta) in changes.items():
        full={**profiles[parent],**delta,'name':'round3_assumed_'+key};Profile.from_dict(full);profiles[key]=full
        role='heldout_qc_only_excluded_from_model' if key.startswith('T') else 'development'
        target=DEST/('heldout_profiles_qc_only' if key.startswith('T') else 'development_profiles')/(key+'.json');write(target,full)
        descriptions.append({'profile_id':key,'role':role,'path':target.relative_to(DEST).as_posix(),'sha256':sha(target),'parent':parent,'changes':delta,'status':'prepared_not_globally_frozen'})
    write(DEST/'profile_registry.json',{'status':'prepared_pending_global_freeze','profiles':descriptions,'development_allowlist':['P1','P2','P3','D1','D2','D3','D4','D5','D6'],'model_forbidden':['T1','T2','T3'],'T_choice':'fixed engineering stress combinations selected before new candidate spectra/model scores; not fitted real-device error distributions','production_approved':False,'all_profiles_still_assumed_unverified':True})
    # Written BEFORE any forward calculation. A failed budget is reported, not relaxed.
    budget={'status':'preregistered_engineering_guardrail_not_accuracy_limit','maximum_lost_fraction_49kV':.5,'maximum_lost_fraction_20kV':.1,'conservation_rtol':1e-9,'conservation_atol':1e-7,'nonnegative_tolerance':1e-12,'policy':'Retain known out-of-window lines and their mass accounting; Ba K exclusion does not exclude L/M. No post-hoc loosening or deletion of failed cases. Full candidate/pilot validation remains pending.'}
    write(DEST/'window_budget.json',budget)
    reference_materials={
        'silicate_numeric_probe':{'Si':28.,'O':45.,'Al':8.,'Fe':10.,'Ca':5.,'Na':2.,'Zn':1.,'Ba':1.},
        'iron_numeric_probe':{'Fe':45.,'O':35.,'Si':8.,'Al':5.,'Ca':4.,'Na':1.,'Zn':1.,'Ba':1.}}
    write(DEST/'numeric_probe_inputs.json',{'scope':'two fixed mathematical homogeneous mixtures for configuration QA, not CRM, third-round recipes or training spectra','materials':reference_materials,'poisson':False})
    rows=[];errors=[]
    for key,value in profiles.items():
        p=Profile.from_dict(value);support=element_support(p);write(DEST/'support'/f'{key}.json',{'profile_id':key,'scope':'structural support only; not LOD or measured accuracy','energy_window':energy_window(p),'support':support})
        for name,comp in reference_materials.items():
            started=time.perf_counter();result=simulate(comp,p,seed=0,poisson=False)
            expected=np.asarray(result['expected_counts']);components=np.array(list(result['components_expected_counts'].values()))
            total=result['detected_signal_before_window_counts'];lost=sum(result['outside_window_counts'].values());frac=lost/total if total else 0.
            cap=budget['maximum_lost_fraction_20kV' if p.voltage_kV==20 else 'maximum_lost_fraction_49kV']
            issues=[]
            if not np.isfinite(expected).all() or expected.min()<-1e-12:issues.append('Invalid expectation')
            if not np.allclose(components.sum(axis=0),expected,rtol=1e-9,atol=1e-7):issues.append('Component closure failed')
            if not np.isclose(total,float((expected-p.background_counts_channel).sum())+lost,rtol=1e-9,atol=1e-7):issues.append('Window accounting failed')
            if not 0<=frac<=cap:issues.append('Pre-registered window loss budget exceeded')
            errors.extend([f'{key}/{name}: '+s for s in issues])
            rows.append({'profile':key,'probe':name,'seconds':time.perf_counter()-started,'component_count':len(components),'window_lost_fraction':frac,'loss_budget':cap,'conservation_residual_counts':total-float((expected-p.background_counts_channel).sum())-lost,'expected_total_counts':float(expected.sum()),'errors':issues})
            print(key,name,'numeric_QA',not issues,flush=True)
    write(DEST/'profile_numeric_checks.json',{'status':'passed_numeric_configuration_checks' if not errors else 'failed','errors':errors,'checks':rows,'forward_calculations':len(rows),'training_spectra_generated':0,'scope':'engineering parameter and conservation QA on fixed probes, not full candidate window validation, production pilot, real calibration or scientific accuracy','budget_sha256':sha(DEST/'window_budget.json')})
    (DEST/'README.md').write_text('''# 第三轮公共输入准备 v1（未生产冻结）

已登记420个设计族的四人分配、9开发/3留出完整配置与哈希，并完成24次固定探针数值检查。P1/P2/P3逐字节继承第二轮A；D/T是工程压力假设，没有实测标定。未生成训练谱，未执行90谱试片。

- [设计分配](design_allocation.json) · [条件及角色](profile_registry.json)
- [源与环境](source_identity.json) · [窗口预算](window_budget.json)
- [固定探针输入](numeric_probe_inputs.json) · [24项数值结果](profile_numeric_checks.json)
- [文件哈希](preparation_manifest.json)

development_profiles只包含P1/P2/P3/D1～D6；heldout_profiles_qc_only中的T1/T2/T3禁止用于训练、校正、响应字典或选参。目录分离不是自动强制隔离；模型侧白名单/禁入适配尚未完成。420个design_seed是候选设计种子，不是已冻结的噪声子种子。

窗口预算在24次探针计算前写入；它是工程拦截阈值，不保证定量性能。完整候选的窗口复核、全局划分、每族条件匹配、长曝光覆盖、噪声种子、90谱试片及最终数量仍待完成。本目录的manifest不是生产批准书。
''',encoding='utf-8')
    write(DEST/'preparation_manifest.json',{'status':'prepared_pending_B_C_D_and_global_freeze','is_production_freeze':False,'production_approved':False,'files':{p.relative_to(DEST).as_posix():sha(p) for p in sorted(DEST.rglob('*')) if p.is_file() and p.name!='preparation_manifest.json'}})
    if errors:raise ValueError(errors)
if __name__=='__main__':main()
