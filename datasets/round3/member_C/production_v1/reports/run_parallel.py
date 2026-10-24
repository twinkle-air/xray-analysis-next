"""Drive member C's 48 frozen batches in parallel with the exact published commands."""
from __future__ import annotations
import concurrent.futures as cf, json, os, pathlib, subprocess, sys, time

REPO = pathlib.Path(__file__).resolve().parent.parent / 'repo_git'
CMDS = REPO / 'datasets/round3/shared/handoffs/20261024/member_C_full_commands.json'
OUTROOT = REPO / 'work/round3/member_C_production_v1_full'
LOGS = OUTROOT / 'logs'
WORKERS = int(os.environ.get('C_WORKERS', '10'))
PY = str(sys.executable)


def schedule(items, worker, workers, on_stop=None):
    """Run items with a bounded pool; stop scheduling after the first failure.

    Always drains running futures and appends ``not_started`` records for the
    remainder, so the caller can persist a final summary even on failure.
    """
    results, queue, stop = [], list(items), False

    def finish(rec):
        nonlocal stop
        results.append(rec)
        if rec.get('exit_code') != 0:
            stop = True

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {}
        while queue or futures:
            while queue and len(futures) < workers and not stop:
                item = queue.pop(0)
                futures[ex.submit(worker, item)] = item
            if not futures:
                break
            done, _ = cf.wait(list(futures), return_when=cf.FIRST_COMPLETED)
            for fut in done:
                item = futures.pop(fut)
                try:
                    rec = fut.result()
                except Exception as exc:  # preserve a record instead of aborting the pool
                    rec = {'batch_id': item.get('batch_id'), 'exit_code': -1, 'error': repr(exc)}
                finish(rec)
                if on_stop and stop:
                    on_stop()
    for item in queue:
        results.append({'batch_id': item.get('batch_id'), 'phase': item.get('phase'),
                        'spectra': item.get('spectra'), 'exit_code': None, 'status': 'not_started'})
    return results


def main():
    doc = json.loads(CMDS.read_text(encoding='utf-8-sig'))
    LOGS.mkdir(parents=True, exist_ok=True)
    batches = doc['commands']
    idx = {b['batch_id']: i for i, b in enumerate(batches)}

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
               'status': 'passed' if p.returncode == 0 else 'failed',
               'seconds': round(time.time() - started, 1), 'command': item['command'],
               'log': log.relative_to(REPO).as_posix()}
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        return rec

    results = schedule(batches, run, WORKERS)
    results.sort(key=lambda r: idx[r['batch_id']])
    summary = {'member': 'C', 'workers': WORKERS, 'batches_requested': len(batches),
               'batches_run': sum(r.get('exit_code') is not None for r in results),
               'batches_passed': sum(r.get('exit_code') == 0 for r in results),
               'batches_failed': sum(r.get('exit_code') not in (0, None) for r in results),
               'batches_not_started': sum(r.get('exit_code') is None for r in results),
               'spectra': sum(r['spectra'] for r in results if r.get('exit_code') == 0),
               'seconds_sum': round(sum(r.get('seconds', 0) or 0 for r in results), 1),
               'results': results}
    (OUTROOT / 'parallel_run.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'results'}, ensure_ascii=False))
    return 0 if summary['batches_passed'] == len(batches) else 1


def self_test():
    """Fault injection: a failing batch must stop scheduling and still yield a summary."""
    items = [{'batch_id': f'fake_{i:02d}', 'phase': 'base', 'spectra': 1} for i in range(6)]

    def worker(item):
        if item['batch_id'] == 'fake_01':
            return {'batch_id': item['batch_id'], 'exit_code': 9, 'status': 'failed', 'seconds': 0.01}
        time.sleep(0.02)
        return {'batch_id': item['batch_id'], 'exit_code': 0, 'status': 'passed', 'seconds': 0.02}

    started = time.time()
    results = schedule(items, worker, 2)
    elapsed = time.time() - started
    assert elapsed < 5, elapsed
    assert len(results) == len(items)
    assert sum(r.get('exit_code') == 0 for r in results) >= 1
    assert any(r.get('exit_code') == 9 for r in results)
    assert all('exit_code' in r for r in results)
    summary = {'fault_injection': 'passed', 'items': len(items), 'elapsed_seconds': round(elapsed, 3),
               'passed': sum(r.get('exit_code') == 0 for r in results),
               'failed': sum(r.get('exit_code') not in (0, None) for r in results),
               'not_started': sum(r.get('exit_code') is None for r in results),
               'all_items_accounted_for': True}
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(self_test() if '--self-test' in sys.argv else main())
