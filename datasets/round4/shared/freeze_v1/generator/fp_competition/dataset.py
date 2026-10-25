"""Self-contained, sealed synthetic datasets and read-only independent checks.

No physical equations are implemented here. core.py remains the FP solver.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sys
import zipfile
import numpy as np

if __package__:
    from .core import Profile,composition,simulate,element_support,VERSION as PHYSICS_VERSION
    from .version import VERSION
else:
    from core import Profile,composition,simulate,element_support,VERSION as PHYSICS_VERSION
    from version import VERSION

HERE=Path(__file__).resolve().parent
RTOL=1e-12
ATOL=1e-8


def read_json(path):
    def pairs(items):
        row={}
        for key,value in items:
            if key in row: raise ValueError('Duplicate JSON key: '+key)
            row[key]=value
        return row
    def invalid(value): raise ValueError('Nonfinite JSON: '+value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=invalid,parse_float=finite_float)


def finite_float(value):
    number=float(value)
    if not np.isfinite(number): raise ValueError('Nonfinite JSON float')
    return number


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def semantic_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
    return digest.hexdigest()


def safe_path(root,relative):
    if not isinstance(relative,str) or '\\' in relative:
        raise ValueError('Expected a relative POSIX bundle path')
    value=PurePosixPath(relative)
    if value.is_absolute() or '..' in value.parts or not value.parts or ':' in relative:
        raise ValueError('Unsafe bundle path: '+relative)
    target=(Path(root)/relative).resolve()
    if not target.is_relative_to(Path(root).resolve()): raise ValueError('Bundle path escapes root')
    return target


def environment():
    versions={name:metadata.version(name) for name in ('numpy','scipy','xraylib','matplotlib','openpyxl')}
    return {'python':platform.python_version(),'implementation':platform.python_implementation(),
            'system':platform.system(),'machine':platform.machine(),'packages':versions,
            'bit_generator':type(np.random.default_rng(0).bit_generator).__name__,
            'thread_environment':{key:os.environ.get(key) for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')}}


def energy_window(profile):
    p=profile if isinstance(profile,Profile) else Profile.from_dict(profile)
    first=p.zero_keV; last=first+(p.channels-1)*p.gain_keV_channel
    return {'unit':'keV','first_center':first,'last_center':last,
            'lower_edge':first-.5*p.gain_keV_channel,'upper_edge':last+.5*p.gain_keV_channel}


def target_support(result,profile,targets):
    """Reuse the solver's already-computed support; evaluate absent targets only."""
    existing=result['element_support'];rows=dict(existing['elements'])
    missing=set(targets)-set(rows)
    if missing: rows.update(element_support(profile,missing)['elements'])
    return {**existing,'elements':{s:rows[s] for s in sorted(targets)}}


def validate_jitter(jitter):
    allowed={'voltage_kV','current_uA','live_time_s','incident_photons_s','gain_keV_channel','zero_keV',
             'noise_fwhm_eV','detector_distance_cm','filter_Al_um','mass_thickness_g_cm2',
             'tube_line_fraction','escape_fraction','incident_air_path_cm','exit_air_path_cm','detector_be_um'}
    if not isinstance(jitter,dict) or set(jitter)-allowed: raise ValueError('Unsupported jitter fields')
    for key,bounds in jitter.items():
        if not isinstance(bounds,list) or len(bounds)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not np.isfinite(v) for v in bounds) or bounds[0]>bounds[1]:
            raise ValueError('Jitter requires finite [minimum,maximum]: '+key)


def make_plan(samples,profile,replicates,seed,jitter,closure,legacy_al,targets=None,split_seed=None):
    if not isinstance(samples,list) or not samples or type(replicates) is not int or replicates<1 or len(samples)*replicates>10000:
        raise ValueError('Batch size must be 1..10000')
    if type(seed) is not int or seed<0 or (split_seed is not None and (type(split_seed) is not int or split_seed<0)):
        raise ValueError('Seeds must be nonnegative integers')
    profile.validate();validate_jitter(jitter)
    family_by_id={};known=set()
    for sample in samples:
        identity=sample['id']
        if not isinstance(identity,str) or not identity or identity in family_by_id: raise ValueError('Distinct nonempty sample IDs required')
        _,material=composition(sample['composition_percent'],closure,legacy_al)
        family_by_id[identity]=hashlib.sha256(json.dumps(material['used_percent'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        known.update(material['used_percent']);known.update(s for s in material['original_percent'] if s not in ('Als','Alt'))
    targets=sorted(known) if targets is None else list(targets)
    if not targets or len(set(targets))!=len(targets): raise ValueError('Distinct target elements required')
    for symbol in targets: composition({symbol:100.})
    effective_split_seed=seed if split_seed is None else split_seed
    families=sorted(set(family_by_id.values()),key=lambda family:hashlib.sha256((str(effective_split_seed)+':'+family).encode()).hexdigest())
    n=len(families);train=min(n-2,max(1,round(n*.7))) if n>=3 else 1
    val=min(max(1,round(n*.15)),n-train-1) if n>=3 else 0
    splits={family:('train' if i<train else 'validation' if i<train+val else 'test') for i,family in enumerate(families)}
    # Preserve the 0.2.0 batch RNG sequence; JSON order of jitter is intentional.
    rng=np.random.default_rng(seed);jobs=[]
    for sample in samples:
        for repeat in range(replicates):
            if 'profile_override' in sample:
                if jitter: raise ValueError('Explicit condition profiles cannot be combined with jitter')
                override=sample['profile_override']
                if not isinstance(override,dict) or set(override)!=set(asdict(profile)):
                    raise ValueError('profile_override must contain the complete Profile schema')
                values=asdict(Profile.from_dict(override))
            else:
                values=asdict(profile)
            values.update({k:float(rng.uniform(*v)) for k,v in jitter.items()})
            variant=Profile.from_dict(values);child=int(rng.integers(0,2**63-1))
            jobs.append((sample,repeat,variant,child,family_by_id[sample['id']],splits[family_by_id[sample['id']]]))
    return jobs,targets,effective_split_seed


def _snapshot(out,samples,profile,jitter,source_files):
    for directory in ('inputs','configs','reproducibility/generator/fp_competition'):
        (out/directory).mkdir(parents=True,exist_ok=True)
    write_json(out/'inputs/samples.json',{'samples':samples})
    write_json(out/'configs/profile.json',asdict(profile));write_json(out/'configs/jitter.json',jitter)
    env=environment();write_json(out/'reproducibility/environment.json',env)
    installed=sorted(f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions())
    (out/'reproducibility/requirements-lock.txt').write_text('\n'.join(installed)+'\n',encoding='utf-8')
    destination=out/'reproducibility/generator/fp_competition'
    for path in sorted(HERE.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix.lower() in ('.py','.json','.md','.txt','.cmd','.pdf') and path.name not in ('validation_record.json','generator-tests.log'):
            relative=path.relative_to(HERE);target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target)
    original={}
    for key,path in (source_files or {}).items():
        if key not in ('samples','profile','jitter','design_ranges'): raise ValueError('Unsupported source file role')
        path=Path(path);target=out/'inputs'/('original_'+key+path.suffix.lower());shutil.copyfile(path,target)
        original[key]={'file':target.relative_to(out).as_posix(),'sha256':sha256(target)}
    return env,original


def seal(out):
    files={p.relative_to(out).as_posix():sha256(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='integrity.json'}
    write_json(out/'integrity.json',{'algorithm':'SHA-256','self_excluded':True,'files':files,
                                   'note':'Snapshot integrity, not authenticity or scientific accuracy certification'})


def generate_dataset(samples,profile,out,replicates=1,seed=0,jitter=None,closure='strict',legacy_al='reject',progress=None,targets=None,split_seed=None,source_files=None):
    jitter={} if jitter is None else jitter
    jobs,targets,effective_split_seed=make_plan(samples,profile,replicates,seed,jitter,closure,legacy_al,targets,split_seed)
    # All supplied source files are checked before any output creation.
    for role,path in (source_files or {}).items():
        if role not in ('samples','profile','jitter','design_ranges') or not Path(path).is_file(): raise ValueError('Invalid original source file')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    for directory in ('blind_inputs','full_results'): (out/directory).mkdir()
    manifest={'schema':'competition-fp-dataset/0.2','software_version':VERSION,'physical_model_version':PHYSICS_VERSION,
              'synthetic':True,'hardware_validated':False,'status':'running','acceptance_status':'pending_independent_validation',
              'source_samples_semantic_sha256':semantic_hash(samples),'seed':seed,'split_seed':effective_split_seed,
              'split_seed_defaulted_to_batch':split_seed is None,'replicates':replicates,'target_elements':targets,
              'closure':closure,'legacy_al':legacy_al,'jitter_ranges':jitter,'records':[],
              'split_rule':'Exact used-composition families, seeded ordering, approximately 70/15/15; not a device/matrix holdout',
              'target_label_basis':'Modeled elemental mass percent; zero is not real-world non-detection',
              'warnings':['Synthetic only; no real-device calibration or 95%/5% blind accuracy proof',
                          'Jitter and synthetic composition ranges are assumptions, not fitted real-world distributions']}
    write_json(out/'manifest.json',manifest)
    try:
        env,original=_snapshot(out,samples,profile,jitter,source_files)
        manifest.update(environment=env,original_inputs=original,physics_core_sha256=sha256(HERE/'core.py'),
                        inputs={'samples':'inputs/samples.json','profile':'configs/profile.json','jitter':'configs/jitter.json'})
        first=[];last=[];lower=[];upper=[];loss_fractions=[];ba=Counter()
        with (out/'truth.jsonl').open('w',encoding='utf-8') as truth:
            for index,(sample,repeat,variant,child,family,split) in enumerate(jobs):
                result=simulate(sample['composition_percent'],variant,seed=child,closure=closure,legacy_al=legacy_al)
                identity=f'S{index+1:06d}';window=energy_window(variant)
                result.update(software_version=VERSION,physical_model_version=PHYSICS_VERSION,record_id=identity,
                              energy_window=window,source_provenance=sample.get('provenance',{}))
                blind={'axis':'channel','signal_unit':'counts','synthetic':True,'x':result['channel'],'counts':result['counts']}
                blind_path='blind_inputs/'+identity+'.json';full_path='full_results/'+identity+'.json'
                write_json(out/blind_path,blind);write_json(out/full_path,result)
                label={'id':identity,'original_sample_id':sample['id'],'family':family,'split':split,'repeat':repeat,
                       'seed':child,'profile':result['profile'],'composition':result['composition'],'warnings':result['warnings'],
                       'targets_percent':{s:result['composition']['used_percent'].get(s,0.) for s in targets},
                       'element_support':target_support(result,variant,targets),'source_provenance':result['source_provenance'],'energy_window':window}
                truth.write(json.dumps(label,ensure_ascii=False,allow_nan=False)+'\n');truth.flush()
                blind_hash=sha256(out/blind_path)
                manifest['records'].append({'id':identity,'file':blind_path,'blind_input_sha256':blind_hash,'sha256':blind_hash,
                                            'full_results':full_path,'full_results_sha256':sha256(out/full_path),'family':family,'split':split})
                first.append(window['first_center']);last.append(window['last_center']);lower.append(window['lower_edge']);upper.append(window['upper_edge'])
                total=result['detected_signal_before_window_counts'];lost=sum(result['outside_window_counts'].values())
                if total>0: loss_fractions.append(lost/total)
                if result['composition']['used_percent'].get('Ba',0)>0:
                    ba['present']+=1
                    for shell in ('K','L','M'):
                        if any(line['element']=='Ba' and line['line'].startswith(shell) and window['lower_edge']<=line['energy_keV']<=window['upper_edge'] for line in result['lines']): ba[shell+'_center_in_window']+=1
                if (index+1)%25==0: write_json(out/'manifest.json',manifest)
                if progress: progress(index+1,len(jobs))
        manifest.update(status='complete',spectrum_count=len(jobs),family_count=len({j[4] for j in jobs}),
                        window_summary={'unit':'keV','first_center_range':[min(first),max(first)],'last_center_range':[min(last),max(last)],
                                        'lower_edge_range':[min(lower),max(lower)],'upper_edge_range':[min(upper),max(upper)]},
                        ba_window_summary=dict(ba),
                        window_loss_fraction={'definition':'sum(outside_window_counts) / detected_signal_before_window_counts, excludes artificial background',
                                              'range':[min(loss_fractions),max(loss_fractions)] if loss_fractions else None})
        write_json(out/'reproducibility/recipe.json',{'software_version':VERSION,'seed':seed,'split_seed':split_seed,
                   'replicates':replicates,'closure':closure,'legacy_al':legacy_al,'targets':targets,'inputs':manifest['inputs']})
        (out/'README_dataset.md').write_text(dataset_readme(manifest),encoding='utf-8')
    except BaseException as exc:
        manifest.update(status='failed_partial',error=str(exc));raise
    finally:
        write_json(out/'manifest.json',manifest);seal(out)
    return out


def dataset_readme(m):
    return f'''# FP 合成数据集交付说明

生成器 {VERSION}；物理模型 {PHYSICS_VERSION}。谱数 {m['spectrum_count']}，成分族 {m['family_count']}。
生成完成不等于独立验收通过；本包状态为 pending_independent_validation。
全部为合成数据，未验证真实设备校准、检出限或真实盲测95%/5%准确度。

## 来源与复现
Each input row may carry a complete profile_override for one frozen condition. Two replicates of that row share the identical response and use different child seeds. configs/profile.json is only the fallback for rows without profile_override. Authoritative family/usage/stage assignments are external to the native batch split.\ninputs/samples.json 是本批采用的完整输入；original_* 为CLI提供的原文件副本（如有）。
configs/profile.json、configs/jitter.json 是实际配置；reproducibility/recipe.json 是重建配方。
reproducibility/generator/fp_competition/ 是本批源码快照，含QC和重算工具。
reproducibility/requirements-lock.txt 是实际安装依赖；environment.json 记录Python和平台。
源码快照的core.py哈希记录在manifest。physics_baseline.json用于核实工作区基线的物理模块未变；
它不是此前缺源码的队友交付包的来源认证。

## 随机种子
批次seed={m['seed']}：影响响应扰动与不同子种子的派生；每条谱使用自己记录的子种子抽计数。
有效split_seed={m['split_seed']}；未单独指定时沿用批次seed，因此改变批次seed也会影响划分。
配方设计种子在原始design文件中记录，独立于批次命令。仅在配方和响应固定时，改变单谱seed才只改变Poisson抽样。
同成分的重复谱不会跨集合；这不隔离未见设备、基体、近邻配方或不同批次合并后的泄漏。

## 能窗与损失
每条full和truth记录energy_window：通道中心 E_i=zero+gain*i；窗口边界为首中心-gain/2和末中心+gain/2。
整批窗口统计（keV）：{json.dumps(m['window_summary'],ensure_ascii=False)}。
源网格延伸到管压；荧光和散射均通过响应deposit；outside_window_counts记录响应卷积后窗外份额，
包括整条中心位于窗外的线或散射能量点及高斯尾部，不只记录峰尾。校验式：
detected_signal_before_window_counts ≈ sum(expected_counts-background) + sum(outside_window_counts)。
这里是效率/出射空气衰减后、截窗前的信号账目，不是源端光子守恒或仪器准确度证明。
损失比例仅按manifest中的明确定义统计：{json.dumps(m['window_loss_fraction'],ensure_ascii=False)}。
Ba统计：{json.dumps(m['ba_window_summary'],ensure_ascii=False)}。K线中心在窗外不意味着不能利用L/M线；
窗内线是否可定量还需单独评价响应、重叠、信噪与独立验证。

## 哈希与检查
每条record的blind_input_sha256（兼容别名sha256）对应盲输入，full_results_sha256对应完整结果。
integrity.json覆盖所有封存文件，包括truth、输入、配置、源码及manifest；自身排除以避免循环。
生成后不要向封存目录添加或改写文件；QC和重算报告写到包外。修改后须新建修订版、重建校验清单。
包内源码安装依赖后，从任意位置以其app.py运行：
python <包内app.py> audit --dataset <数据集目录> --out <包外qc.json>
python <包内app.py> replay --dataset <数据集目录> --out <包外replay.json>
replay默认重算全部；--limit仅抽查，不能写成全部完整重生成。对浮点使用rtol={RTOL}、atol={ATOL} counts；
同环境计数要求逐道一致。环境差异和文件字节差异单独报告，不替代数值比较。
'''


def verify_integrity(root):
    root=Path(root);errors=[]
    index=read_json(root/'integrity.json');files=index.get('files',{})
    if not files or index.get('algorithm')!='SHA-256': raise ValueError('Missing complete integrity index')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='integrity.json' and '__pycache__' not in p.parts}
    if actual!=set(files): errors.append('Integrity inventory differs from bundle files')
    for name,digest in files.items():
        path=safe_path(root,name)
        if not path.is_file() or sha256(path)!=digest: errors.append('Hash mismatch: '+name)
    return errors


def audit_dataset(root):
    root=Path(root);errors=[];checked=0;targets={};windows=[];families={};seen=set()
    try:
        errors.extend(verify_integrity(root));m=read_json(root/'manifest.json')
        if m['status']!='complete': errors.append('Generation is not complete')
        truth=[read_json_line(line) for line in (root/'truth.jsonl').read_text(encoding='utf-8').splitlines()]
        if len(truth)!=len(m['records']) or len({r['id'] for r in truth})!=len(truth): raise ValueError('Record/truth cardinality or IDs mismatch')
        labels={r['id']:r for r in truth};samples=read_json(root/'inputs/samples.json')['samples']
        if semantic_hash(samples)!=m['source_samples_semantic_sha256']: errors.append('Input sample semantic hash mismatch')
        profile=Profile.from_dict(read_json(root/'configs/profile.json'));jitter=read_json(root/'configs/jitter.json')
        recipe=read_json(root/'reproducibility/recipe.json')
        jobs,planned_targets,_=make_plan(samples,profile,recipe['replicates'],recipe['seed'],jitter,recipe['closure'],recipe['legacy_al'],recipe['targets'],recipe['split_seed'])
        if len(jobs)!=len(m['records']) or planned_targets!=m['target_elements']: errors.append('Recipe plan differs from manifest')
        snapshot=root/'reproducibility/generator/fp_competition'
        if sha256(snapshot/'core.py')!=m['physics_core_sha256']: errors.append('Physics core snapshot hash mismatch')
        baseline=read_json(snapshot/'physics_baseline.json')
        for name,digest in baseline['files'].items():
            if sha256(safe_path(snapshot,name))!=digest: errors.append('Protected physics module changed: '+name)
        for i,record in enumerate(m['records']):
            try:
                identity=record['id']
                if identity in seen: raise ValueError('Duplicate manifest ID')
                seen.add(identity);label=labels[identity]
                blind_path=safe_path(root,record['file']);full_path=safe_path(root,record['full_results'])
                if sha256(blind_path)!=record['blind_input_sha256'] or record.get('sha256')!=record['blind_input_sha256']: raise ValueError('Blind hash mismatch')
                if sha256(full_path)!=record['full_results_sha256']: raise ValueError('Full result hash mismatch')
                blind=read_json(blind_path);full=read_json(full_path)
                if set(blind)!={'axis','signal_unit','synthetic','x','counts'} or blind['axis']!='channel' or blind['signal_unit']!='counts' or blind['synthetic'] is not True: raise ValueError('Blind input schema or isolation violation')
                p=Profile.from_dict(label['profile']);n=p.channels
                if blind['x']!=list(range(n)) or full['channel']!=blind['x']: raise ValueError('Channel axis mismatch')
                counts=np.asarray(blind['counts']);expected=np.asarray(full['expected_counts'],dtype=float)
                if counts.shape!=(n,) or counts.dtype.kind not in 'iu' or np.any(counts<0): raise ValueError('Invalid count array')
                if expected.shape!=(n,) or not np.isfinite(expected).all() or np.any(expected<0): raise ValueError('Invalid expected array')
                if full['counts']!=blind['counts'] or full['seed']!=label['seed'] or full['profile']!=label['profile']: raise ValueError('Cross-file signal/seed/profile mismatch')
                for name in ('composition','warnings','source_provenance'):
                    if full[name]!=label[name]: raise ValueError('Cross-file '+name+' mismatch')
                if full['synthetic'] is not True or full['hardware_validated'] is not False: raise ValueError('Unsupported scientific identity')
                components=full['components_expected_counts']
                if set(components)!={'primary','secondary','rayleigh','compton','escape','background'}: raise ValueError('Physical components missing')
                arrays=[np.asarray(v,dtype=float) for v in components.values()]
                if any(a.shape!=(n,) or not np.isfinite(a).all() or np.any(a<0) for a in arrays): raise ValueError('Invalid component')
                if not np.allclose(sum(arrays),expected,rtol=RTOL,atol=ATOL): raise ValueError('Component sum mismatch')
                loss=np.asarray(list(full['outside_window_counts'].values()),dtype=float)
                total=full['detected_signal_before_window_counts']
                accounted=float(expected.sum()-sum(components['background'])+loss.sum())
                if not np.isfinite(loss).all() or np.any(loss<0) or not np.isfinite(total) or total<0 or not np.isclose(total,accounted,rtol=RTOL,atol=ATOL): raise ValueError('Window signal accounting mismatch')
                if not np.array_equal(np.random.default_rng(label['seed']).poisson(expected),counts): raise ValueError('Poisson replay mismatch')
                used=label['composition']['used_percent']
                if not np.isclose(sum(used.values()),100,atol=1e-6,rtol=0) or any(not np.isfinite(v) or v<0 for v in used.values()): raise ValueError('Composition closure mismatch')
                _,recomputed=composition(label['composition']['original_percent'],label['composition']['closure_policy'],label['composition']['legacy_al_policy'])
                if recomputed!=label['composition']: raise ValueError('Composition provenance mismatch')
                if label['targets_percent']!={s:used.get(s,0.) for s in m['target_elements']}: raise ValueError('Target label mismatch')
                for s,v in label['targets_percent'].items():
                    c=targets.setdefault(s,{'positive':0,'zero':0,'min_percent':v,'max_percent':v})
                    c['positive' if v>0 else 'zero']+=1;c['min_percent']=min(c['min_percent'],v);c['max_percent']=max(c['max_percent'],v)
                window=energy_window(p);windows.append(window)
                if full['energy_window']!=window or label['energy_window']!=window: raise ValueError('Energy window metadata mismatch')
                if not np.allclose(full['energy_keV'],p.zero_keV+p.gain_keV_channel*np.arange(n),rtol=RTOL,atol=1e-12): raise ValueError('Energy axis mismatch')
                sample,repeat,variant,child,family,split=jobs[i]
                if (label['original_sample_id'],label['repeat'],label['profile'],label['seed'],label['family'],label['split'])!=(sample['id'],repeat,asdict(variant),child,family,split): raise ValueError('Batch sampling/seed/split replay mismatch')
                if record['family']!=family or record['split']!=split: raise ValueError('Manifest grouping mismatch')
                families.setdefault(family,set()).add(split)
                checked+=1
            except (ValueError,KeyError,TypeError,OverflowError,IndexError,OSError) as exc:
                errors.append(record.get('id','?')+': '+str(exc))
        if any(len(s)>1 for s in families.values()): errors.append('Composition family crossed splits')
        if m.get('spectrum_count')!=len(m['records']) or m.get('family_count')!=len(families): errors.append('Manifest size summary mismatch')
        if windows:
            summary={'unit':'keV',**{key+'_range':[min(w[key] for w in windows),max(w[key] for w in windows)]
                                     for key in ('first_center','last_center','lower_edge','upper_edge')}}
            if summary!=m.get('window_summary'): errors.append('Batch energy-window summary mismatch')
    except (ValueError,KeyError,TypeError,OverflowError,IndexError,OSError) as exc:
        errors.append(str(exc))
    return {'status':'passed' if not errors else 'failed','check_type':'bundle_integrity_and_synthetic_flow',
            'spectra_checked':checked,'family_count':len(families),'target_coverage':targets,'errors':errors,
            'tolerances':{'rtol':RTOL,'atol_counts':ATOL},'complete_physics_recalculation':False,
            'physical_calibration_verified':False,'concentration_accuracy_verified':False}


def read_json_line(line):
    # Apply the same duplicate/nonfinite guard without a temporary file.
    def pairs(items):
        result={}
        for k,v in items:
            if k in result: raise ValueError('Duplicate truth JSON key')
            result[k]=v
        return result
    def bad(value): raise ValueError('Nonfinite truth JSON')
    return json.loads(line,object_pairs_hook=pairs,parse_constant=bad,parse_float=finite_float)


def numerically_equal(a,b):
    if isinstance(a,dict) and isinstance(b,dict):
        return set(a)==set(b) and all(numerically_equal(a[k],b[k]) for k in a)
    if isinstance(a,(tuple,list)) and isinstance(b,(tuple,list)):
        return len(a)==len(b) and all(numerically_equal(x,y) for x,y in zip(a,b))
    if isinstance(a,(int,float)) and not isinstance(a,bool) and isinstance(b,(int,float)) and not isinstance(b,bool):
        return bool(np.isclose(a,b,rtol=RTOL,atol=ATOL))
    return type(a)==type(b) and a==b


def replay_dataset(root,limit=None,progress=None):
    root=Path(root);qc=audit_dataset(root)
    if qc['status']!='passed': return {'status':'blocked_failed_qc','qc':qc,'complete_physics_recalculation':False}
    m=read_json(root/'manifest.json');current=environment()
    if sha256(HERE/'core.py')!=m['physics_core_sha256']:
        return {'status':'blocked_source_mismatch','message':'Run the bundle snapshot app.py, not a different physics core','complete_physics_recalculation':False}
    if limit is not None and (type(limit) is not int or limit<1): raise ValueError('Replay limit must be positive')
    truth=[read_json_line(line) for line in (root/'truth.jsonl').read_text(encoding='utf-8').splitlines()]
    selected=m['records'] if limit is None else m['records'][:limit];labels={r['id']:r for r in truth}
    errors=[];maximum=0.
    for i,record in enumerate(selected):
        label=labels[record['id']];saved=read_json(safe_path(root,record['full_results']))
        result=simulate(label['composition']['original_percent'],Profile.from_dict(label['profile']),seed=label['seed'],
                        closure=label['composition']['closure_policy'],legacy_al=label['composition']['legacy_al_policy'])
        if result['counts']!=saved['counts']: errors.append(record['id']+': counts differ')
        for name in ('profile','composition','lines','outside_window_counts','warnings','element_support','secondary_model'):
            if not numerically_equal(result[name],saved[name]): errors.append(record['id']+': '+name+' differs')
        for name in ('expected_counts','energy_keV'):
            a=np.asarray(result[name]);b=np.asarray(saved[name]);maximum=max(maximum,float(np.max(np.abs(a-b))))
            if not np.allclose(a,b,rtol=RTOL,atol=ATOL): errors.append(record['id']+': '+name+' differs')
        for name in saved['components_expected_counts']:
            if not np.allclose(result['components_expected_counts'][name],saved['components_expected_counts'][name],rtol=RTOL,atol=ATOL): errors.append(record['id']+': '+name+' component differs')
        if not np.isclose(result['detected_signal_before_window_counts'],saved['detected_signal_before_window_counts'],rtol=RTOL,atol=ATOL): errors.append(record['id']+': prewindow differs')
        if progress: progress(i+1,len(selected))
    same_environment=current==m['environment'];all_records=len(selected)==len(m['records'])
    return {'status':'failed' if errors else ('passed' if same_environment else 'passed_with_environment_differences'),
            'scope':'all_records' if all_records else 'subset','spectra_recalculated':len(selected),
            'complete_physics_recalculation':all_records,'same_environment':same_environment,
            'maximum_absolute_array_difference':maximum,'errors':errors,'rtol':RTOL,'atol_counts':ATOL,
            'file_byte_identity_tested':False,'physical_calibration_verified':False,'concentration_accuracy_verified':False}


def external_report_path(root,out):
    root=Path(root).resolve();out=Path(out).resolve()
    if out.is_relative_to(root): raise ValueError('Write reports outside the sealed dataset')
    if out.exists(): raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    return out


def pack_dataset(root,out):
    root=Path(root).resolve();out=external_report_path(root,out)
    if out.suffix.lower()!='.zip': raise ValueError('Package output must end in .zip')
    sidecar=out.with_suffix(out.suffix+'.sha256')
    if sidecar.exists(): raise FileExistsError(sidecar)
    qc=audit_dataset(root)
    if qc['status']!='passed': raise ValueError('Package refused: independent QC failed')
    with zipfile.ZipFile(out,'x',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(root.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts: z.write(path,path.relative_to(root).as_posix())
    with zipfile.ZipFile(out) as z:
        if z.testzip() is not None: raise ValueError('ZIP CRC check failed')
    digest=sha256(out);sidecar.write_text(digest+'  '+out.name+'\n',encoding='ascii')
    return {'archive':str(out),'sha256':digest,'qc':qc['status'],'physics_replay_required_separately':True}
