"""Drive member C's 48 frozen batches in parallel with the exact published commands."""
from __future__ import annotations
import concurrent.futures as cf, json, os, pathlib, subprocess, sys, time

REPO = pathlib.Path(__file__).resolve().parent.parent / 'repo_git'
CMDS = REPO / 'datasets/round3/shared/handoffs/20261024/member_C_full_commands.json'
OUTROOT = REPO / 'work/round3/member_C_production_v1_full'
LOGS = OUTROOT / 'logs'
WORKERS = int(os.environ.get('C_WORKERS', '10'))
PY = str(pathlib.Path(sys.executable))

def main():
    doc = json.loads(CMDS.read_text(encoding='utf-8-sig'))
    LOGS.mkdir(parents=True, exist_ok=True)
    batches = doc['commands']
    idx = {b['batch_id']: i for i, b in enumerate(batches)}
    # rewrite the documented out/qc paths to this run root, nothing else
    results = []
    def run(item):
        bid = item['batch_id']
        args = list(item['command'])
        assert args[0] == 'python'
        args[0] = PY
        args = [a.replace('work/round3/member_C_production_v1/', 'work/round3/member_C_production_v1_full/') for a in args]
        log = LOGS / (bid + '.log')
        started = time.time()
        with log.open('w', encoding='utf-8') as fh:
            p = subprocess.run(args, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT, text=True)
        rec = {'batch_id': bid, 'phase': item['phase'], 'spectra': item['spectra'], 'exit_code': p.returncode,
               'seconds': round(time.time() - started, 1), 'command': item['command'],
               'log': log.relative_to(REPO).as_posix()}
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        return rec
    stop = False
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {}
        queue = list(batches)
        while queue or futures:
            while queue and len(futures) < WORKERS and not stop:
                item = queue.pop(0)
                futures[ex.submit(run, item)] = item
            done, _ = cf.wait(list(futures), return_when=cf.FIRST_COMPLETED)
            for fut in done:
                item = futures.pop(fut)
                try:
                    rec = fut.result()
                except Exception as exc:  # pragma: no cover
                    rec = {'batch_id': item['batch_id'], 'exit_code': -1, 'error': repr(exc)}
                    print(json.dumps(rec, ensure_ascii=False), flush=True)
                results.append(rec)
                if rec.get('exit_code') != 0:
                    stop = True
    results.sort(key=lambda r: idx[r['batch_id']])
    summary = {'member': 'C', 'workers': WORKERS, 'batches_requested': len(batches),
               'batches_run': len(results), 'batches_passed': sum(r.get('exit_code') == 0 for r in results),
               'spectra': sum(r['spectra'] for r in results if r.get('exit_code') == 0),
               'seconds_sum': round(sum(r.get('seconds', 0) for r in results), 1),
               'results': results}
    (OUTROOT / 'parallel_run.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'results'}, ensure_ascii=False))
    return 0 if summary['batches_passed'] == len(batches) else 1

if __name__ == '__main__':
    raise SystemExit(main())
