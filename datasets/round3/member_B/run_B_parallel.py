"""Run every remaining frozen round-3 member-B batch, a few at a time.

A batch is skipped only when its QC evidence proves it finished: passed summary,
complete audit and physics replay, window budget, matching spectra count, archive
SHA-256 and CRC, and a complete external record index. A sealed directory without
that evidence is a failed attempt, not a finished batch, so this driver stops
non-zero instead of pretending the member is complete.
"""
from __future__ import annotations
import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import subprocess
import sys
import time

DELIVERY = pathlib.Path(__file__).resolve().parent


def _default_root(start: pathlib.Path) -> pathlib.Path:
    """Walk up to the repository root, so the driver works from datasets/round3/member_B."""
    for candidate in (start, *start.parents):
        if (candidate / 'datasets/round3/shared/freeze_v1/batch_plan.json').is_file():
            return candidate
    return start / 'repo'


ROOT = pathlib.Path(os.environ.get('B_REPO_ROOT', str(_default_root(DELIVERY))))
FREEZE = ROOT / 'datasets/round3/shared/freeze_v1'
RELEASE = ROOT / 'datasets/round3/shared/releases/owner_release_v3.json'
RUNNER = ROOT / 'datasets/round3/shared/production_tools/run_batch.py'
OUT = pathlib.Path(os.environ.get('B_OUTPUT_ROOT', str(ROOT / 'work/round3/member_B_production_v1')))
LOG = DELIVERY / 'production_parallel.log'

sys.path.insert(0, str(DELIVERY))
from verify_batch_qc import inspect_batch  # noqa: E402


def log(msg: str) -> None:
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    with LOG.open('a', encoding='utf-8') as handle:
        handle.write(line + '\n')
    print(line, flush=True)


def state_of(batch: dict) -> dict:
    batch_id = batch['batch_id']
    return inspect_batch(batch_id, int(batch['spectra']),
                         OUT / 'sealed' / batch_id, OUT / 'qc' / batch_id)


def run_batch(batch: dict, runner: pathlib.Path) -> dict:
    batch_id = batch['batch_id']
    out_dir = OUT / 'sealed' / batch_id
    qc_dir = OUT / 'qc' / batch_id
    started = time.monotonic()
    cmd = [sys.executable, '-X', 'utf8', '-B', str(runner),
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

    verified = state_of(batch)
    record['qc_state'] = verified['state']
    if verified['state'] != 'complete':
        record['exit_code'] = 4
        record['error'] = ('; '.join(verified['problems'])
                           or f"post-run QC state {verified['state']}")[:400]
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--limit', type=int, default=0, help='run at most N pending batches')
    parser.add_argument('--runner', type=pathlib.Path, default=RUNNER)
    parser.add_argument('--verify-only', action='store_true',
                        help='only classify existing batches; never generate')
    args = parser.parse_args()

    plan = json.loads((FREEZE / 'batch_plan.json').read_text(encoding='utf-8-sig'))
    batches = [b for b in plan['batches'] if b['member'] == 'B']

    pending = []
    finished = 0
    broken = []
    for batch in batches:
        state = state_of(batch)
        if state['state'] == 'absent':
            pending.append(batch)
        elif state['state'] == 'complete':
            finished += 1
        else:
            broken.append(state)

    log(f'plan: total={len(batches)} complete={finished} pending={len(pending)} '
        f'incomplete={len(broken)} workers={args.workers}')

    if broken:
        for state in broken:
            log(f"INCOMPLETE {state['batch_id']}: {'; '.join(state['problems'])[:300]}")
        log('stop: a sealed batch directory exists without complete QC evidence')
        sys.exit(3)

    if args.verify_only:
        log(f'verify-only: complete={finished} pending={len(pending)}')
        sys.exit(0 if len(pending) == 0 else 5)

    if args.limit > 0:
        pending = pending[:args.limit]

    start = time.monotonic()
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_batch, batch, args.runner): batch for batch in pending}
        for future in cf.as_completed(futures):
            record = future.result()
            results.append(record)
            log(f"{'ok' if record['exit_code'] == 0 else 'FAIL'} {record['batch_id']} "
                f"spectra={record['spectra']} {record['seconds']}s"
                + ('' if record['exit_code'] == 0 else f" :: {record.get('error', '')}"))
    elapsed = time.monotonic() - start
    failed = [record for record in results if record['exit_code'] != 0]
    summary = {
        'batches_run': len(results),
        'batches_failed': len(failed),
        'batches_already_complete': finished,
        'wall_seconds': round(elapsed, 1),
        'workers': args.workers,
        'results': sorted(results, key=lambda record: record['batch_id']),
    }
    stamp = time.strftime('%H%M%S')
    (DELIVERY / f'production_chunk_{stamp}.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    log(f'end: run={len(results)} failed={len(failed)} wall_min={elapsed/60:.1f}')
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
