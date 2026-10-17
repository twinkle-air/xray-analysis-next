"""Read-only full checks for one completed pilot; reports outside sealed data."""
import sys,time,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from fp_competition.dataset import environment
OUT=Path(__file__).resolve().parent
name=sys.argv[1]
dataset=OUT/('pilot_'+name)
while True:
    m=json.loads((dataset/'manifest.json').read_text(encoding='utf-8'))
    if m['status']=='complete' and (dataset/'integrity.json').exists():break
    if m['status']=='failed_partial':raise RuntimeError('Generation failed')
    time.sleep(2)
app=dataset/'reproducibility/generator/fp_competition/app.py'
current=environment()
original=m['environment']
assert {k:v for k,v in current.items() if k!='thread_environment'}=={k:v for k,v in original.items() if k!='thread_environment'}
(OUT/f'{name}_replay_environment.json').write_text(json.dumps({'generation':original,'replay':current,'differences_limited_to_thread_environment':True},indent=2),encoding='utf-8')
timings={}
for command in ('audit','replay','pack'):
    target=OUT/(f'{name}_'+command+('.zip' if command=='pack' else '.json'))
    args=[sys.executable,'-B',str(app),command,'--dataset',str(dataset),'--out',str(target)]
    start=time.perf_counter()
    reused=target.exists()
    if not reused:
        with (OUT/f'{name}_{command}.log').open('w',encoding='utf-8') as stream:
            subprocess.run(args,check=True,stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT)
    timings[command+'_seconds']=None if reused else time.perf_counter()-start
    timings[command+'_reused_existing_report']=reused
    if command!='pack':
        report=json.loads(target.read_text(encoding='utf-8'))
        assert report['status'] in ('passed','passed_with_environment_differences'),report
        assert not report['errors']
        if command=='replay':assert report['complete_physics_recalculation'] and report['spectra_recalculated']==200
    print(name,command,report['status'] if command!='pack' else 'archive_created',flush=True)
(OUT/f'{name}_check_timings.json').write_text(json.dumps(timings,indent=2),encoding='utf-8')
