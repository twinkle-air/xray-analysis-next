"""Decide whether one frozen batch is really finished, bound to its frozen identity.

A `sealed/<batch>` directory can exist after a crash, a failed generation, or a failed
replay. Treating "the directory exists" as "the batch is done" silently drops such a
batch from the pending set and can report a complete run that produced nothing. This
module is the single answer both drivers use before skipping a batch.

Completion is bound to the frozen plan, not just to a claimed status: the summary must
name this batch and this freeze, every external index row must repeat the frozen recipe,
profile, usage, repeat and noise seed, every window-budget row must pass under the frozen
cap for this profile's voltage, and the three required actions must be present, clean and
free of `--limit`.

States:
  complete   - all evidence present, consistent and bound to this frozen batch
  absent     - no sealed directory at all, so the batch still has to run
  incomplete - something exists but cannot be trusted; callers must stop non-zero
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import sys
import zipfile
from pathlib import Path

PASSED_STATUS = ('passed_batch_QC', 'passed_pilot_QC')
REQUIRED_ACTIONS = ('audit', 'replay', 'pack')
MAX_PROBLEMS = 50

_RECORD_CACHE: dict[tuple[str, str], list[dict]] = {}
_PROFILE_CACHE: dict[tuple[str, str], dict] = {}


def _read(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _record_plan_rows(freeze: Path, batch_id: str) -> list[dict]:
    key = (str(freeze), batch_id)
    if key not in _RECORD_CACHE:
        rows: list[dict] = []
        with (freeze / 'record_plan.csv').open(encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                if row['batch_id'] == batch_id:
                    rows.append(row)
        _RECORD_CACHE[key] = rows
    return _RECORD_CACHE[key]


def _profile(freeze: Path, profile_id: str) -> dict:
    key = (str(freeze), profile_id)
    if key not in _PROFILE_CACHE:
        registry = _read(freeze / 'profile_registry.json')
        relative = registry['files'][profile_id]['path']
        _PROFILE_CACHE[key] = _read(freeze / relative)
    return _PROFILE_CACHE[key]


def _frozen_cap(freeze: Path, profile_id: str) -> float:
    budget = _read(freeze / 'window_budget.json')
    voltage = float(_profile(freeze, profile_id).get('voltage_kV', 0))
    key = 'maximum_lost_fraction_20kV' if voltage == 20 else 'maximum_lost_fraction_49kV'
    return float(budget[key])


def inspect_batch(batch: dict, freeze: Path, sealed: Path, qc: Path) -> dict:
    batch_id = batch['batch_id']
    spectra = int(batch['spectra'])
    problems: list[str] = []

    if not sealed.is_dir():
        if qc.is_dir() and any(qc.iterdir()):
            return {'batch_id': batch_id, 'state': 'incomplete',
                    'problems': ['QC directory exists without a sealed batch directory']}
        return {'batch_id': batch_id, 'state': 'absent', 'problems': []}
    if not qc.is_dir():
        return {'batch_id': batch_id, 'state': 'incomplete',
                'problems': ['sealed batch directory exists without QC evidence']}

    summary_path = qc / 'summary.json'
    audit_path = qc / 'audit.json'
    replay_path = qc / 'replay.json'
    budget_path = qc / 'window_budget.json'
    commands_path = qc / 'commands.json'
    index_path = qc / 'external_record_index.csv'
    archive = qc / f'{batch_id}.zip'
    archive_sidecar = qc / f'{batch_id}.zip.sha256'
    sealed_manifest = sealed / 'manifest.json'
    sealed_integrity = sealed / 'integrity.json'

    required = (summary_path, audit_path, replay_path, budget_path, commands_path, index_path,
                archive, sealed_manifest, sealed_integrity)
    for path in required:
        if not path.is_file():
            problems.append(f'missing {path.name}')
    if problems:
        return {'batch_id': batch_id, 'state': 'incomplete', 'problems': problems}

    try:
        summary = _read(summary_path)
        audit = _read(audit_path)
        replay = _read(replay_path)
        budget = _read(budget_path)
        commands = _read(commands_path)
        manifest = _read(sealed_manifest)
    except Exception as error:  # noqa: BLE001 - any unreadable evidence is incomplete
        return {'batch_id': batch_id, 'state': 'incomplete',
                'problems': [f'unreadable QC evidence: {error}']}

    freeze_digest = _sha256(freeze / 'freeze_manifest.json')

    # --- identity: the evidence must name this batch and this freeze ---
    if summary.get('status') not in PASSED_STATUS:
        problems.append(f"summary status {summary.get('status')!r}")
    if summary.get('batch_id') != batch_id:
        problems.append(f"summary batch_id {summary.get('batch_id')!r} != {batch_id!r}")
    if summary.get('freeze_manifest_sha256') != freeze_digest:
        problems.append('summary freeze_manifest_sha256 differs from the frozen manifest')
    if int(summary.get('spectra', -1)) != spectra:
        problems.append(f"summary spectra {summary.get('spectra')} != {spectra}")
    if int(manifest.get('spectrum_count', -1)) != spectra:
        problems.append(f"sealed manifest spectrum_count {manifest.get('spectrum_count')} != {spectra}")

    # --- audit ---
    if audit.get('status') != 'passed':
        problems.append(f"audit status {audit.get('status')!r}")
    if int(audit.get('spectra_checked', -1)) != spectra:
        problems.append(f"audit spectra_checked {audit.get('spectra_checked')} != {spectra}")
    if audit.get('errors'):
        problems.append(f"audit reports {len(audit['errors'])} error(s)")

    # --- replay: complete, all records, no errors ---
    if replay.get('status') != 'passed':
        problems.append(f"replay status {replay.get('status')!r}")
    if not replay.get('complete_physics_recalculation'):
        problems.append('replay is not a complete physics recalculation')
    if int(replay.get('spectra_recalculated', -1)) != spectra:
        problems.append(f"replay spectra_recalculated {replay.get('spectra_recalculated')} != {spectra}")
    if replay.get('scope') != 'all_records':
        problems.append(f"replay scope {replay.get('scope')!r} is not all_records")
    if replay.get('errors'):
        problems.append(f"replay reports {len(replay['errors'])} error(s)")

    # --- frozen record expectations ---
    frozen_rows = _record_plan_rows(freeze, batch_id)
    expected = {row['native_id']: row for row in frozen_rows}
    if len(frozen_rows) != spectra:
        problems.append(f'record_plan rows {len(frozen_rows)} != {spectra}')

    # --- external record index: every row repeats the frozen record ---
    try:
        with index_path.open(encoding='utf-8-sig', newline='') as handle:
            index_rows = list(csv.DictReader(handle))
    except Exception as error:  # noqa: BLE001
        index_rows = []
        problems.append(f'unreadable external record index: {error}')
    if len(index_rows) != spectra:
        problems.append(f'external record index rows {len(index_rows)} != {spectra}')
    seen_ids = set()
    for row in index_rows:
        native = row.get('native_id', '')
        if native in seen_ids:
            problems.append(f'duplicate native id {native}')
        seen_ids.add(native)
        if row.get('batch_id') != batch_id:
            problems.append(f"index row {native} batch_id {row.get('batch_id')!r} != {batch_id!r}")
        frozen = expected.get(native)
        if frozen is None:
            problems.append(f'index row {native} is not in the frozen record plan')
            continue
        for field in ('recipe_id', 'profile_id', 'usage', 'repeat', 'noise_seed'):
            if str(row.get(field, '')) != str(frozen.get(field, '')):
                problems.append(f'index row {native} {field} {row.get(field)!r} != frozen {frozen.get(field)!r}')
    if seen_ids != set(expected):
        problems.append('external record index does not cover exactly the frozen native ids')

    # --- window budget: every row, under the frozen cap for this profile ---
    cap = _frozen_cap(freeze, batch['profile_id'])
    if not budget.get('passed'):
        problems.append('window budget top-level passed is not true')
    window_rows = budget.get('rows') or []
    if len(window_rows) != spectra:
        problems.append(f'window budget rows {len(window_rows)} != {spectra}')
    if {row.get('id') for row in window_rows} != set(expected):
        problems.append('window budget ids do not cover exactly the frozen native ids')
    for row in window_rows:
        row_id = row.get('id')
        if row.get('passed') is not True:
            problems.append(f'window budget row {row_id} is not passed')
        lost = row.get('lost_fraction')
        if not isinstance(lost, (int, float)) or not math.isfinite(float(lost)):
            problems.append(f'window budget row {row_id} lost_fraction is not a finite number')
            continue
        row_budget = row.get('budget')
        if not isinstance(row_budget, (int, float)) or not math.isfinite(float(row_budget)):
            problems.append(f'window budget row {row_id} budget is not a finite number')
            continue
        if abs(float(row_budget) - cap) > 1e-12:
            problems.append(f'window budget row {row_id} budget {row_budget} != frozen cap {cap}')
        if float(lost) < 0 or float(lost) > float(row_budget) + 1e-12:
            problems.append(f'window budget row {row_id} lost_fraction {lost} outside 0..{row_budget}')

    # --- required actions: audit, replay, pack; clean exits; no --limit ---
    if not isinstance(commands, list) or not commands:
        problems.append('commands.json is empty')
        commands = []
    grouped: dict[str, list[dict]] = {}
    for entry in commands:
        grouped.setdefault(str(entry.get('action')), []).append(entry)
    for action in REQUIRED_ACTIONS:
        entries = grouped.get(action, [])
        if not entries:
            problems.append(f'missing required {action} action')
            continue
        for entry in entries:
            if int(entry.get('exit_code', -1)) != 0:
                problems.append(f"{action} exited {entry.get('exit_code')}")
            argv = entry.get('command')
            joined = ' '.join(str(part) for part in argv) if isinstance(argv, list) else str(argv or '')
            if '--limit' in joined:
                problems.append(f'{action} command used --limit')

    # --- archive: digest, size, sidecar, CRC ---
    digest = _sha256(archive)
    if digest != summary.get('archive_sha256'):
        problems.append('archive sha256 differs from summary')
    if archive.stat().st_size != summary.get('archive_bytes'):
        problems.append('archive size differs from summary')
    if archive_sidecar.is_file():
        parts = archive_sidecar.read_text(encoding='utf-8').split()
        declared = parts[0] if parts else ''
        if declared != digest:
            problems.append('archive .sha256 sidecar is empty or differs from the file')
    else:
        problems.append('archive .sha256 sidecar missing')
    try:
        with zipfile.ZipFile(archive) as zf:
            if zf.testzip() is not None:
                problems.append('archive CRC failure')
    except Exception as error:  # noqa: BLE001
        problems.append(f'archive cannot be opened: {error}')

    if len(problems) > MAX_PROBLEMS:
        problems = problems[:MAX_PROBLEMS] + [f'... {len(problems) - MAX_PROBLEMS} more']
    return {'batch_id': batch_id, 'state': 'incomplete' if problems else 'complete',
            'problems': problems}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--sealed', type=Path, required=True)
    parser.add_argument('--qc', type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding='utf-8-sig'))
    batch = next((entry for entry in plan['batches'] if entry['batch_id'] == args.batch), None)
    if batch is None:
        print(json.dumps({'batch_id': args.batch, 'state': 'unknown', 'problems': ['batch not in plan']}))
        return 4
    result = inspect_batch(batch, args.freeze, args.sealed, args.qc)
    print(json.dumps(result, ensure_ascii=False))
    return {'complete': 0, 'absent': 2, 'incomplete': 3}[result['state']]


if __name__ == '__main__':
    sys.exit(main())
