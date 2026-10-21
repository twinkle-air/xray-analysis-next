"""Run whole-family shards under three fixed A profiles, full sealed-source checks and packages.

This standalone data runner does not change the FP generator or create global
cross-member approval. Run --preflight first, then --run for actual production.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FROZEN=HERE/'production_inputs_v2'
OUTPUT=HERE/'production_v2'
THREAD_KEYS=('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,
                                   allow_nan=False),encoding='utf-8')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def preflight():
    manifest=read(FROZEN/'freeze_manifest.json')
    for relative,digest in manifest['files'].items():
        if sha(FROZEN/relative)!=digest:
            raise ValueError('Frozen input changed: '+relative)
    samples=read(FROZEN/'A_samples.json')['samples']
    if len(samples)!=250 or len({s['id'] for s in samples})!=250:
        raise ValueError('Expected 250 unique formula IDs')
    checks=read(HERE/'candidates_v1/candidate_checks.json')
    if checks['status']!='passed' or checks['errors']:
        raise ValueError('Candidate checks failed')
    source=FROZEN/'generator/fp_competition'
    for name,digest in read(source/'physics_baseline.json')['files'].items():
        if sha(source/name)!=digest:raise ValueError('Protected physics source changed')
    compiled=[]
    for p in [Path(__file__)]+list(source.rglob('*.py')):
        compile(p.read_text(encoding='utf-8-sig'),str(p),'exec')
        compiled.append(str(p.relative_to(ROOT)))
    if shutil.disk_usage(HERE).free<4*1024**3:
        raise ValueError('Less than 4 GiB free; measure capacity before production')
    return {'status':'passed','checked_at':now(),'compiled_sources':compiled,
            'frozen_files_checked':len(manifest['files']),
            'cross_member_confirmation':'pending; no global training approval',
            'spectra_planned':1500,'conditions':['P1','P2','P3'],
            'free_bytes':shutil.disk_usage(HERE).free}


def command(profile,stage,args):
    log=OUTPUT/f'{profile}_{stage}.log'
    record={'profile':profile,'stage':stage,'argv':args,'started_at':now(),
            'cwd':str(ROOT),'thread_environment':{k:'1' for k in THREAD_KEYS}}
    env=os.environ.copy()
    env.update({k:'1' for k in THREAD_KEYS})
    env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    started=time.perf_counter()
    with log.open('x',encoding='utf-8') as stream:
        proc=subprocess.run(args,cwd=ROOT,env=env,stdout=stream,
                            stderr=subprocess.STDOUT,check=False)
    record.update(exit_code=proc.returncode,seconds=time.perf_counter()-started,
                  finished_at=now(),log=log.name)
    write(OUTPUT/f'{profile}_{stage}_command.json',record)
    if proc.returncode!=0:
        raise RuntimeError(profile+' '+stage+' failed; see '+str(log))
    return record


def one_profile(identity):
    batch=OUTPUT/(identity+'_dataset')
    state={'profile':identity,'status':'running','stage':'generation',
           'started_at':now(),'expected_spectra':50,'completed_commands':[]}
    def update():write(OUTPUT/(identity+'_state.json'),state)
    update()
    try:
        m=read(FROZEN/'A_run_config.json')
        app=FROZEN/'generator/fp_competition/app.py'
        argv=[sys.executable,'-B',str(app),'batch','--samples',str(FROZEN/m['batches'][identity]['samples']),
              '--profile',str(FROZEN/'profiles'/(m['batches'][identity]['profile_id']+'.json')),
              '--design-ranges',str(FROZEN/'design_ranges.json'),
              '--replicates','2','--seed',str(m['batches'][identity]['seed']),
              '--split-seed',str(m['split_seed']),'--closure','strict',
              '--legacy-al','reject','--targets',*m['target_elements'],'--out',str(batch)]
        state['completed_commands'].append(command(identity,'generation',argv));update()
        manifest=read(batch/'manifest.json')
        if manifest['status']!='complete' or manifest['spectrum_count']!=50:
            raise ValueError('Generation incomplete or wrong spectrum count')
        sealed=batch/'reproducibility/generator/fp_competition/app.py'
        for stage in ('audit','replay'):
            state['stage']=stage;update()
            reportpath=OUTPUT/f'{identity}_{stage}.json'
            record=command(identity,stage,[sys.executable,'-B',str(sealed),stage,
                           '--dataset',str(batch),'--out',str(reportpath)])
            report=read(reportpath)
            if report.get('errors') or report['status'] not in ('passed','passed_with_environment_differences'):
                raise ValueError(identity+' '+stage+' did not pass')
            if stage=='replay' and (not report.get('complete_physics_recalculation') or
                   report.get('scope')!='all_records' or report.get('spectra_recalculated')!=50):
                raise ValueError('Replay did not cover every record')
            state['completed_commands'].append(record);state[stage]=report;update()
        state['stage']='pack';update()
        archive=OUTPUT/(identity+'_dataset.zip')
        state['completed_commands'].append(command(identity,'pack',
             [sys.executable,'-B',str(sealed),'pack','--dataset',str(batch),'--out',str(archive)]))
        if not archive.with_suffix('.zip.sha256').read_text(encoding='utf-8').startswith(sha(archive)):
            raise ValueError('Archive external hash mismatch')
        state.update(status='selfcheck_passed',stage='complete',finished_at=now(),
                     spectra=50,archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,
                     dataset_bytes=sum(p.stat().st_size for p in batch.rglob('*') if p.is_file()),
                     independent_person_review=False,global_inclusion='pending_cross_member_checks')
        update()
        return state
    except BaseException as exc:
        state.update(status='failed_preserved',error=str(exc),finished_at=now());update()
        raise


def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--preflight',action='store_true')
    group.add_argument('--run',action='store_true')
    args=parser.parse_args()
    report=preflight()
    if args.preflight:
        write(HERE/'production_preflight.json',report)
        print(json.dumps(report,ensure_ascii=False));return 0
    if OUTPUT.exists():raise ValueError('Refusing to reuse production output directory')
    OUTPUT.mkdir()
    write(OUTPUT/'preflight.json',report)
    write(OUTPUT/'run_status.json',{'status':'running','started_at':now(),
          'workers':15,'expected_spectra':1500,'cross_member_confirmation':'pending'})
    failures=[];states=[]
    with ThreadPoolExecutor(max_workers=15) as pool:
        pending={pool.submit(one_profile,p):p for p in read(FROZEN/'A_run_config.json')['batches']}
        for future in as_completed(pending):
            identity=pending[future]
            try:
                state=future.result();states.append(state)
                print(identity+' completed: 50 spectra, full selfcheck and archive',flush=True)
            except BaseException as exc:
                failures.append({'profile':identity,'error':str(exc)})
                print(identity+' failed; preserved: '+str(exc),flush=True)
    summary={'status':'selfcheck_passed' if not failures else 'failed_preserved',
             'finished_at':now(),'profiles':[s['profile'] for s in states],
             'spectra_selfchecked':sum(s['spectra'] for s in states),'failures':failures,
             'global_inclusion':'pending_cross_member_checks','independent_person_review':False}
    write(OUTPUT/'run_status.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    return 0 if not failures else 2


if __name__=='__main__':raise SystemExit(main())
