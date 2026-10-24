"""Run every remaining frozen round-3 member-B batch, eight at a time.

Each batch is an independent run_batch.py invocation with its own sealed/qc
directory, so concurrency cannot mix records. Batches already sealed are
skipped (identity/QC are checked by the later aggregation step).
"""
from __future__ import annotations
import argparse
import concurrent.futures as cf
import json
import pathlib
import subprocess
import sys
import time

DELIVERY = pathlib.Path(__file__).resolve().parent
ROOT = DELIVERY / 'repo'
FREEZE = ROOT / 'datasets/round3/shared/freeze_v1'
RELEASE = ROOT / 'datasets/round3/shared/releases/owner_release_v3.json'
RUNNER = ROOT / 'datasets/round3/shared/production_tools/run_batch.py'
OUT = ROOT / 'work/round3/member_B_production_v1'
LOG = DELIVERY / 'production_parallel.log'
WORKERS = 8

def log(msg: str) -> None:
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    with LOG.open('a', encoding='utf-8') as fh:
        fh.write(line + '\n')
    print(line, flush=True)

def run_batch(batch: dict) -> dict:
    batch_id = batch['batch_id']
    out_dir = OUT / 'sealed' / batch_id
    qc_dir = OUT / 'qc' / batch_id
    started = time.monotonic()
    cmd = [sys.executable, '-X', 'utf8', '-B', str(RUNNER),
           '--repository', str(ROOT), '--freeze', str(FREEZE), '--release', str(RELEASE),
           '--batch', batch_id, '--out', str(out_dir), '--qc-out', str(qc_dir)]
    if batch['phase'] == 'challenge':
        cmd.append('--heldout-qc')
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    seconds = time.monotonic() - started
    record = {
        'batch_id': batch_id,
        'spectra': batch['spectra'],
        'phase': batch['phase'],
        'exit_code': proc.returncode,
        'seconds': round(seconds, 1),
    }
    tail = (proc.stdout or '') + (proc.stderr or '')
    (DELIVERY / 'logs').mkdir(exist_ok=True)
    (DELIVERY / 'logs' / f'{batch_id}.terminal.log').write_text(tail, encoding='utf-8')
    if proc.returncode != 0:
        record['error'] = tail.strip().splitlines()[-1][:400] if tail.strip() else 'unknown'
    return record

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=WORKERS)
    parser.add_argument('--limit', type=int, default=0, help='run at most N pending batches')
    args = parser.parse_args()
    plan = json.loads((FREEZE / 'batch_plan.json').read_text(encoding='utf-8-sig'))
    batches = [b for b in plan['batches'] if b['member'] == 'B']
    pending = [b for b in batches if not (OUT / 'sealed' / b['batch_id']).exists()]
    if args.limit > 0:
        pending = pending[:args.limit]
    log(f'plan: total={len(batches)} pending={len(pending)} workers={args.workers}')
    start = time.monotonic()
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_batch, b): b for b in pending}
        for fut in cf.as_completed(futures):
            rec = fut.result()
            results.append(rec)
            log(f"{'ok' if rec['exit_code'] == 0 else 'FAIL'} {rec['batch_id']} "
                f"spectra={rec['spectra']} {rec['seconds']}s")
    elapsed = time.monotonic() - start
    failed = [r for r in results if r['exit_code'] != 0]
    summary = {
        'batches_run': len(results),
        'batches_failed': len(failed),
        'wall_seconds': round(elapsed, 1),
        'workers': args.workers,
        'results': sorted(results, key=lambda r: r['batch_id']),
    }
    stamp = time.strftime('%H%M%S')
    (DELIVERY / f'production_chunk_{stamp}.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    log(f'end: run={len(results)} failed={len(failed)} wall_min={elapsed/60:.1f}')
    if failed:
        sys.exit(1)

if __name__ == '__main__':
    main()
