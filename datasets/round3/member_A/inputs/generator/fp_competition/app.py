"""CLI and Chinese desktop interface for the independent FP generator."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import queue
import sys
import threading
import time
import uuid

import numpy as np

if __package__:
    from .core import Profile, composition, simulate as _simulate, element_support, TARGET_ELEMENTS, VERSION as PHYSICS_VERSION
    from .version import VERSION
    from . import dataset as dataset_tools
    from .minerals import components_to_elements, design_minerals
    from .robustness import read_channel_signal,write_views
else:
    from core import Profile, composition, simulate as _simulate, element_support, TARGET_ELEMENTS, VERSION as PHYSICS_VERSION
    from version import VERSION
    import dataset as dataset_tools
    from minerals import components_to_elements, design_minerals
    from robustness import read_channel_signal,write_views

HERE=Path(__file__).resolve().parent


def simulate(*args,**kwargs):
    result=_simulate(*args,**kwargs)
    result.update(software_version=VERSION,physical_model_version=PHYSICS_VERSION,
                  energy_window=dataset_tools.energy_window(result['profile']))
    return result


def read_json(path):
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:
                raise ValueError('Duplicate JSON key: '+k)
            result[k]=v
        return result
    def bad_constant(value):
        raise ValueError('Nonfinite JSON: '+value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=bad_constant)


def save_json(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def export_result(result,directory):
    """Only writes a newly created directory; existing data are never overwritten."""
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=False)
    save_json(directory/'result.json',result)
    with (directory/'spectrum.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f)
        keys=list(result['components_expected_counts'])
        writer.writerow(['channel','energy_keV','observed_counts','expected_counts']+keys)
        for i in range(len(result['channel'])):
            writer.writerow([result['channel'][i],result['energy_keV'][i],result['counts'][i],result['expected_counts'][i]]+[result['components_expected_counts'][k][i] for k in keys])
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig=Figure(figsize=(11,6));FigureCanvasAgg(fig)
    ax=fig.add_subplot(111)
    ax.plot(result['energy_keV'],result['counts'],lw=.6,label='Synthetic observed counts')
    ax.plot(result['energy_keV'],result['expected_counts'],lw=1,label='Model expectation')
    for key in ('primary','secondary','rayleigh','compton','escape'):
        ax.plot(result['energy_keV'],result['components_expected_counts'][key],lw=.5,label=key)
    ax.set_yscale('symlog',linthresh=1);ax.set_xlabel('Energy / keV');ax.set_ylabel('Synthetic counts')
    ax.set_title('FP method-validation simulation; hardware calibration unverified');ax.legend(fontsize=7)
    fig.tight_layout();fig.savefig(directory/'spectrum.png',dpi=160)
    try:
        import openpyxl
    except ImportError:
        # JSON/CSV retain all numbers; Excel is an optional format at runtime.
        (directory/'excel_unavailable.txt').write_text('安装 openpyxl 后可同时导出 Excel；JSON/CSV 已完整保存。',encoding='utf-8')
    else:
        book=openpyxl.Workbook(write_only=True)
        sheet=book.create_sheet('合成谱')
        sheet.append(['channel','energy_keV','observed_counts','expected_counts']+keys)
        for i in range(len(result['channel'])):
            sheet.append([result['channel'][i],result['energy_keV'][i],result['counts'][i],result['expected_counts'][i]]+[result['components_expected_counts'][k][i] for k in keys])
        config=book.create_sheet('参数与限制')
        config.append(['项目','数值或说明'])
        for key,value in result['profile'].items():
            config.append([key,value])
        for warning in result['warnings']:
            config.append(['限制',warning])
        if 'source_provenance' in result:
            config.append(['配方来源',json.dumps(result['source_provenance'],ensure_ascii=False)])
        for key in ('seed','synthetic','hardware_validated','poisson','xraylib_version'):
            config.append([key,result[key]])
        material=book.create_sheet('成分标签')
        material.append(['类别','元素','质量百分数'])
        for key in ('original_percent','used_percent'):
            for element,value in result['composition'][key].items():
                material.append([key,element,value])
        support=book.create_sheet('元素支持边界')
        support.append(['元素','结构支持状态','最大探测器与空气响应（非检出限）'])
        for symbol,row in result.get('element_support',{}).get('elements',{}).items():
            support.append([symbol,row['status'],row['maximum_window_detector_air_response']])
        book.save(directory/'spectrum.xlsx')
        book.close()
    return directory


def read_samples(path):
    path=Path(path)
    if path.suffix.lower()=='.json':
        data=read_json(path)
        samples=data.get('samples') if isinstance(data,dict) else data
        if isinstance(samples,dict):
            samples=[{'id':key,'composition_percent':value} for key,value in samples.items()]
    else:
        if path.suffix.lower()=='.csv':
            with path.open(encoding='utf-8-sig',newline='') as f:
                reader=csv.DictReader(f)
                if len(reader.fieldnames or [])!=len(set(reader.fieldnames or [])):
                    raise ValueError('Duplicate CSV column')
                rows=list(reader)
        elif path.suffix.lower()=='.xlsx':
            try:
                import openpyxl
            except ImportError as exc:
                raise ValueError('Excel support requires openpyxl; CSV/JSON work without it') from exc
            book=openpyxl.load_workbook(path,read_only=True,data_only=True)
            try:
                values=iter(book.active.values)
                header=list(next(values))
                if len(header)!=len(set(header)):
                    raise ValueError('Duplicate Excel column')
                rows=[dict(zip(header,row)) for row in values if any(v is not None for v in row)]
            finally:
                book.close()
        else:
            raise ValueError('Samples must be JSON, CSV or XLSX')
        samples=[]
        for row in rows:
            identity=row.pop('编号',None)
            if identity is None:
                identity=row.pop('id',None)
            if identity is None or str(identity).strip()=='':
                raise ValueError('Every row requires 编号 or id')
            values={k:float(v) for k,v in row.items() if v not in (None,'')}
            samples.append({'id':str(identity),'composition_percent':values})
    if not isinstance(samples,list) or not samples:
        raise ValueError('No samples found')
    ids=set()
    for sample in samples:
        if not isinstance(sample,dict) or set(sample)-{'id','composition_percent','provenance'} or not {'id','composition_percent'}<=set(sample):
            raise ValueError('Each sample needs id and composition_percent, and optional provenance')
        if 'provenance' in sample and not isinstance(sample['provenance'],dict):
            raise ValueError('Sample provenance must be an object')
        sample['id']=str(sample['id'])
        if sample['id'] in ids:
            raise ValueError('Duplicate sample ID '+sample['id'])
        ids.add(sample['id'])
    return samples


def load_profile(path):
    return Profile.from_dict(read_json(path)) if path else Profile()


def design_compositions(spec,count,seed):
    """Sample explicitly selected percentage ranges and assign a balance element."""
    if type(count) is not int or not 1<=count<=10000 or type(seed) is not int or seed<0:
        raise ValueError('design count 1..10000 and nonnegative integer seed required')
    if not isinstance(spec,dict) or set(spec)!={'ranges_percent','balance_element','balance_range_percent'}:
        raise ValueError('Design needs ranges_percent, balance_element, balance_range_percent')
    ranges=spec['ranges_percent'];balance=spec['balance_element'];brange=spec['balance_range_percent']
    if not isinstance(ranges,dict) or not ranges or balance in ranges:
        raise ValueError('Balance element must be separate from ranges')
    all_ranges=dict(ranges);all_ranges[balance]=brange
    for symbol,limits in all_ranges.items():
        if not isinstance(limits,list) or len(limits)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not np.isfinite(v) for v in limits) or not 0<=limits[0]<=limits[1]<=100:
            raise ValueError('Invalid percentage range for '+str(symbol))
        # Check element symbol without guessing or silently dropping any component.
        composition({symbol:100.})
    if sum(v[0] for v in ranges.values())+brange[0]>100 or sum(v[1] for v in ranges.values())+brange[1]<100:
        raise ValueError('No closed composition is possible within the specified ranges')
    rng=np.random.default_rng(seed);samples=[]
    for attempt in range(count*100+1000):
        row={s:float(rng.uniform(*v)) for s,v in ranges.items()}
        remainder=100-sum(row.values())
        if brange[0]<=remainder<=brange[1]:
            row[balance]=remainder
            samples.append({'id':f'DESIGN{len(samples)+1:05d}','composition_percent':row})
            if len(samples)==count:
                return {'synthetic_design':True,'design_spec':spec,'seed':seed,'samples':samples}
    raise ValueError('Ranges yield too few feasible mixtures; adjust design ranges')


def validate_jitter(jitter):
    return dataset_tools.validate_jitter(jitter)


def generate_batch(samples,profile,out,replicates=1,seed=0,jitter=None,closure='strict',legacy_al='reject',progress=None,targets=None,split_seed=None,source_files=None):
    return dataset_tools.generate_dataset(samples,profile,out,replicates,seed,jitter,closure,legacy_al,progress,targets,split_seed,source_files)


def start_gui():
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    root=tk.Tk();root.title('FP 能谱生成器 · 比赛研究版 '+VERSION);root.geometry('1220x830')
    root.minsize(950,650)
    main=ttk.Panedwindow(root,orient='horizontal');main.pack(fill='both',expand=True,padx=8,pady=8)
    left=ttk.Frame(main);right=ttk.Frame(main);main.add(left,weight=1);main.add(right,weight=2)
    ttk.Label(left,text='仪器响应配置（假设值，尚未实测校准）').pack(anchor='w')
    profile_text=tk.Text(left,height=21,width=48,wrap='none');profile_text.pack(fill='both',expand=True)
    profile_text.insert('1.0',json.dumps(asdict(Profile()),ensure_ascii=False,indent=2))
    def import_profile():
        path=filedialog.askopenfilename(filetypes=[('JSON','*.json')])
        if path:
            try:
                p=load_profile(path);profile_text.delete('1.0','end');profile_text.insert('1.0',json.dumps(asdict(p),ensure_ascii=False,indent=2))
            except Exception as exc:
                messagebox.showerror('配置错误',str(exc))
    ttk.Button(left,text='读取配置 JSON',command=import_profile).pack(anchor='w')
    presets=read_samples(HERE/'legacy_presets.json')
    if (HERE/'public_data'/'reference_samples.json').exists():
        presets+=read_samples(HERE/'public_data'/'reference_samples.json')
    selection=tk.StringVar(value='ZBG073a')
    box=ttk.Combobox(left,textvariable=selection,values=[s['id'] for s in presets],state='readonly');box.pack(fill='x',pady=(8,0))
    ttk.Label(left,text='样品质量百分数（钢材或公开资料合成重建）').pack(anchor='w')
    sample_text=tk.Text(left,height=8,width=48);sample_text.pack(fill='x')
    def set_sample(event=None):
        selected=next(s for s in presets if s['id']==selection.get())
        sample_text.delete('1.0','end');sample_text.insert('1.0',json.dumps(selected['composition_percent'],ensure_ascii=False))
    box.bind('<<ComboboxSelected>>',set_sample);set_sample()
    policies=ttk.Frame(left);policies.pack(fill='x',pady=5)
    closure=tk.StringVar(value='strict');legacy=tk.StringVar(value='reject')
    ttk.Label(policies,text='成分闭合').grid(row=0,column=0,sticky='w')
    ttk.Combobox(policies,textvariable=closure,values=['strict','normalize_explicit'],state='readonly',width=21).grid(row=0,column=1)
    ttk.Label(policies,text='Als/Alt 处理').grid(row=1,column=0,sticky='w')
    ttk.Combobox(policies,textvariable=legacy,values=['reject','sum_as_written','alt_is_total'],state='readonly',width=21).grid(row=1,column=1)
    ttk.Label(left,text='normalize_explicit：明确归一化并保留原值\nsum_as_written：按原值合并，含义未验证\nalt_is_total：假设 Alt 为总 Al，需自行核实',foreground='#805000').pack(anchor='w')
    seedvar=tk.StringVar(value='20261014');reps=tk.StringVar(value='3')
    seedrow=ttk.Frame(left);seedrow.pack(fill='x')
    ttk.Label(seedrow,text='随机种子').pack(side='left');ttk.Entry(seedrow,textvariable=seedvar,width=14).pack(side='left')
    ttk.Label(seedrow,text='每成分重复数').pack(side='left');ttk.Entry(seedrow,textvariable=reps,width=6).pack(side='left')
    jitter_enabled=tk.BooleanVar(value=False)
    ttk.Checkbutton(left,text='批量启用参数扰动（范围见 jitter_example.json）',variable=jitter_enabled).pack(anchor='w')
    status=tk.StringVar(value='就绪。输出为合成研究数据；ZBGS001 无成分预设。')
    ttk.Label(right,text='合成谱预览',font=('Microsoft YaHei UI',13,'bold')).pack(anchor='w')
    fig=Figure(figsize=(7,5));ax=fig.add_subplot(111);canvas=FigureCanvasTkAgg(fig,master=right);canvas.get_tk_widget().pack(fill='both',expand=True)
    notices=tk.Text(right,height=9,wrap='word');notices.pack(fill='x')
    ttk.Label(right,textvariable=status,wraplength=680).pack(fill='x',pady=5)
    current={'result':None,'busy':False};events=queue.Queue()
    def work(function):
        if current['busy']:
            return
        current['busy']=True;status.set('计算中……')
        def target():
            try:
                events.put(('done',function()))
            except Exception as exc:
                events.put(('error',str(exc)))
        threading.Thread(target=target,daemon=True).start()
    def settings():
        p=Profile.from_dict(json.loads(profile_text.get('1.0','end')))
        return p,int(seedvar.get()),closure.get(),legacy.get()
    def generate():
        try:
            p,seed,c,a=settings();percent=json.loads(sample_text.get('1.0','end'))
            preset=next(s for s in presets if s['id']==selection.get())
            provenance=(preset.get('provenance',{}) if percent==preset['composition_percent'] else
                        {'basis':'User-edited composition','preset_id':selection.get(),'edited':True})
            def run():
                result=simulate(percent,p,seed=seed,closure=c,legacy_al=a)
                result['source_provenance']=provenance
                return result
            work(run)
        except Exception as exc:
            messagebox.showerror('输入错误',str(exc))
    def export():
        if not current['result'] or current['busy']:
            return
        parent=filedialog.askdirectory(title='选择保存目录（自动建立独立子目录）')
        if parent:
            dest=Path(parent)/('fp-spectrum-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
            result=current['result']
            work(lambda:str(export_result(result,dest)))
    def batch():
        if current['busy']:
            return
        try:
            p,seed,c,a=settings();repeat=int(reps.get())
            path=filedialog.askopenfilename(title='质量百分数表：编号/id + 元素列',filetypes=[('样品表','*.json *.csv *.xlsx')])
            if not path:
                return
            samples=read_samples(path)
            parent=filedialog.askdirectory(title='选择谱库保存目录')
            if not parent:
                return
            dest=Path(parent)/('fp-dataset-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
            jitter=read_json(HERE/'jitter_example.json') if jitter_enabled.get() else {}
            work(lambda:str(generate_batch(samples,p,dest,repeat,seed,jitter,c,a,lambda i,n:events.put(('progress',f'{i}/{n}')))))
        except Exception as exc:
            messagebox.showerror('批量输入错误',str(exc))
    def import_measured():
        if not current['result'] or current['busy']:
            return
        path=filedialog.askopenfilename(filetypes=[('单列原始谱','*.pu *.txt')])
        if path:
            try:
                measured=np.array([float(v) for v in Path(path).read_text(encoding='utf-8-sig').splitlines()[:2048]])
                if len(measured)!=2048 or not np.isfinite(measured).all() or measured.max()<=0 or measured.min()<0:
                    raise ValueError('需要 2048 道有限、非负的单列数值')
                result=current['result'];ax.clear()
                model=np.asarray(result['expected_counts'])
                ax.plot(result['channel'],model/max(model),label='Simulation / own max')
                ax.plot(np.arange(len(measured)),measured/max(measured),lw=.7,label='Measured / own max')
                ax.set_xlabel('Channel');ax.set_ylabel('Normalized signal (shape only)');ax.legend();fig.tight_layout();canvas.draw()
                status.set('仅比较各自最大值归一化后的形状；不是含量或效率比。')
            except Exception as exc:
                messagebox.showerror('读取失败',str(exc))
    def robust_views():
        if not current['result'] or current['busy']:
            return
        parent=filedialog.askdirectory(title='保存附加展宽视图（不改变物理模拟和原谱）')
        if parent:
            result=current['result']
            dest=Path(parent)/('robust-views-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
            work(lambda:str(write_views(result['counts'],dest,source_info={'synthetic':True,'signal_unit':'counts','seed':result['seed']})))
    actions=ttk.Frame(left);actions.pack(fill='x',pady=8)
    for title,fn in [('生成单谱',generate),('保存结果',export),('批量谱库',batch),('叠加实测谱',import_measured)]:
        ttk.Button(actions,text=title,command=fn).pack(side='left',padx=2)
    ttk.Button(left,text='保存峰形稳健性视图（额外展宽 0 / 6 / 10 道）',command=robust_views).pack(fill='x')
    def poll():
        try:
            while True:
                kind,value=events.get_nowait()
                if kind=='progress':
                    status.set('批量生成 '+value);continue
                current['busy']=False
                if kind=='error':
                    status.set('失败：'+value);messagebox.showerror('执行失败',value)
                elif isinstance(value,dict):
                    current['result']=value;ax.clear()
                    ax.plot(value['channel'],value['counts'],lw=.6,label='Synthetic observed counts')
                    ax.plot(value['channel'],value['expected_counts'],lw=.9,label='Model expectation')
                    ax.set_yscale('symlog',linthresh=1);ax.set_xlabel('Channel');ax.set_ylabel('Synthetic counts');ax.legend();fig.tight_layout();canvas.draw()
                    notices.delete('1.0','end');notices.insert('1.0','\n'.join(value['warnings']))
                    status.set('生成完成。seed='+str(value['seed'])+'；尚未通过真实仪器精度验证。')
                else:
                    status.set('已保存：'+value)
        except queue.Empty:
            pass
        root.after(100,poll)
    root.after(100,poll)
    return root


def main(argv=None):
    parser=argparse.ArgumentParser(description='独立 FP 能谱生成器：物理模型合成数据，非实测真值')
    sub=parser.add_subparsers(dest='command')
    sub.add_parser('gui')
    p=sub.add_parser('generate');p.add_argument('--composition',required=True);p.add_argument('--profile');p.add_argument('--out',required=True);p.add_argument('--seed',type=int,default=0);p.add_argument('--no-poisson',action='store_true')
    b=sub.add_parser('batch');b.add_argument('--samples',required=True);b.add_argument('--profile');b.add_argument('--out',required=True);b.add_argument('--seed',type=int,default=0);b.add_argument('--replicates',type=int,default=1);b.add_argument('--jitter')
    d=sub.add_parser('design');d.add_argument('--ranges',required=True);d.add_argument('--count',type=int,required=True);d.add_argument('--out',required=True);d.add_argument('--seed',type=int,default=0)
    dm=sub.add_parser('design-mineral');dm.add_argument('--ranges',required=True);dm.add_argument('--count',type=int,required=True);dm.add_argument('--out',required=True);dm.add_argument('--seed',type=int,default=0)
    cm=sub.add_parser('convert-components');cm.add_argument('--input',required=True);cm.add_argument('--out',required=True);cm.add_argument('--closure',choices=['strict','normalize_explicit'],default='strict')
    support=sub.add_parser('support');support.add_argument('--profile');support.add_argument('--elements',nargs='+',default=list(TARGET_ELEMENTS));support.add_argument('--out',required=True)
    b.add_argument('--targets',nargs='+')
    b.add_argument('--split-seed',type=int)
    b.add_argument('--design-ranges',help='Archive the original composition-design configuration')
    for name in ('audit','replay','pack'):
        command=sub.add_parser(name);command.add_argument('--dataset',required=True);command.add_argument('--out',required=True)
        if name=='replay': command.add_argument('--limit',type=int)
    v=sub.add_parser('views');v.add_argument('--input',required=True);v.add_argument('--out',required=True);v.add_argument('--fwhm-channels',type=float,nargs='+',default=[0.,6.,10.])
    for item in (p,b):
        item.add_argument('--closure',choices=['strict','normalize_explicit'],default='strict')
        item.add_argument('--legacy-al',choices=['reject','sum_as_written','alt_is_total'],default='reject')
    args=parser.parse_args(argv)
    if args.command in (None,'gui'):
        start_gui().mainloop();return 0
    try:
        if Path(args.out).exists():
            raise ValueError('Output directory already exists; choose a fresh directory')
        if args.command in ('audit','replay','pack'):
            if args.command=='pack':
                report=dataset_tools.pack_dataset(args.dataset,args.out)
            else:
                target=dataset_tools.external_report_path(args.dataset,args.out)
                report=(dataset_tools.audit_dataset(args.dataset) if args.command=='audit' else
                        dataset_tools.replay_dataset(args.dataset,args.limit,lambda i,n:print(f'{i}/{n}',flush=True)))
                save_json(target,report)
            print(json.dumps(report,ensure_ascii=False))
            return 0 if report.get('status',report.get('qc')) in ('passed','passed_with_environment_differences') else 2
        if args.command=='views':
            y,info=read_channel_signal(args.input)
            print(write_views(y,args.out,args.fwhm_channels,info));return 0
        if args.command in ('design','design-mineral','convert-components','support'):
            if args.command=='support':
                result=element_support(load_profile(args.profile),args.elements)
            elif args.command=='convert-components':
                data=read_json(args.input)
                percent,provenance=components_to_elements(data['compounds_percent'],data.get('trace_ppm'),closure=args.closure)
                result={'samples':[{'id':data.get('id','CONVERTED'),'composition_percent':percent,'provenance':provenance}]}
            else:
                result=(design_minerals if args.command=='design-mineral' else design_compositions)(read_json(args.ranges),args.count,args.seed)
            target=Path(args.out)
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('x',encoding='utf-8') as stream:
                json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
            print(target);return 0
        profile=load_profile(args.profile)
        if args.command=='generate':
            value=read_json(args.composition)
            percent=value.get('composition_percent',value)
            result=simulate(percent,profile,seed=args.seed,poisson=not args.no_poisson,closure=args.closure,legacy_al=args.legacy_al)
            if 'provenance' in value:
                result['source_provenance']=value['provenance']
            dest=export_result(result,args.out)
        else:
            jitter=read_json(args.jitter) if args.jitter else {}
            dest=generate_batch(read_samples(args.samples),profile,args.out,args.replicates,args.seed,jitter,args.closure,args.legacy_al,lambda i,n:print(f'{i}/{n}',flush=True),targets=args.targets,split_seed=args.split_seed,source_files={k:v for k,v in {'samples':args.samples,'profile':args.profile,'jitter':args.jitter,'design_ranges':args.design_ranges}.items() if v})
        print(str(dest));return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print('错误：'+str(exc),file=sys.stderr);return 2


if __name__=='__main__':
    raise SystemExit(main())
