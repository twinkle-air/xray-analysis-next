"""Decide whether one frozen batch is really finished.

A `sealed/<batch>` directory can exist after a crash, a failed generation, or a failed
replay. Treating "the directory exists" as "the batch is done" silently drops such a
batch from the pending set and can report a complete run that produced nothing. This
module is the single answer both drivers use before skipping a batch.

States:
  complete   - passed QC evidence, matching spectra count, archive SHA/CRC and record index
  absent     - no sealed directory at all, so the batch still has to run
  incomplete - something exists but cannot be trusted; callers must stop non-zero
"""
from __future__ import annotations
import csv
import hashlib
import json
import sys
import zipfile
from pathlib import Path


def _read(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_batch(batch_id: str, expected_spectra: int, sealed: Path, qc: Path) -> dict:
    problems: list[str] = []
    if not sealed.is_dir():
        if qc.is_dir() and any(qc.iterdir()):
            problems.append('QC directory exists without a sealed batch directory')
            return {'batch_id': batch_id, 'state': 'incomplete', 'problems': problems}
        return {'batch_id': batch_id, 'state': 'absent', 'problems': problems}
    if not qc.is_dir():
        problems.append('sealed batch directory exists without QC evidence')
        return {'batch_id': batch_id, 'state': 'incomplete', 'problems': problems}

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

    for path in (summary_path, audit_path, replay_path, budget_path, commands_path, index_path,
                 archive, sealed_manifest, sealed_integrity):
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
        problems.append(f'unreadable QC evidence: {error}')
        return {'batch_id': batch_id, 'state': 'incomplete', 'problems': problems}

    if summary.get('status') not in ('passed_batch_QC', 'passed_pilot_QC'):
        problems.append(f'summary status {summary.get("status")!r}')
    if int(summary.get('spectra', -1)) != expected_spectra:
        problems.append(f'summary spectra {summary.get("spectra")} != {expected_spectra}')
    if int(manifest.get('spectrum_count', -1)) != expected_spectra:
        problems.append(f'sealed manifest spectrum_count {manifest.get("spectrum_count")} != {expected_spectra}')

    if audit.get('status') != 'passed':
        problems.append(f'audit status {audit.get("status")!r}')
    if int(audit.get('spectra_checked', -1)) != expected_spectra:
        problems.append(f'audit spectra_checked {audit.get("spectra_checked")} != {expected_spectra}')

    if replay.get('status') != 'passed':
        problems.append(f'replay status {replay.get("status")!r}')
    if not replay.get('complete_physics_recalculation'):
        problems.append('replay is not a complete physics recalculation')
    if int(replay.get('spectra_recalculated', -1)) != expected_spectra:
        problems.append(f'replay spectra_recalculated {replay.get("spectra_recalculated")} != {expected_spectra}')

    if not budget.get('passed'):
        problems.append('window budget not passed')
    if len(budget.get('rows') or []) != expected_spectra:
        problems.append(f'window budget rows {len(budget.get("rows") or [])} != {expected_spectra}')

    if not isinstance(commands, list) or not commands:
        problems.append('commands.json is empty')
    else:
        for entry in commands:
            if int(entry.get('exit_code', -1)) != 0:
                problems.append(f'{entry.get("action")} exited {entry.get("exit_code")}')

    try:
        with index_path.open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != expected_spectra:
            problems.append(f'external record index rows {len(rows)} != {expected_spectra}')
        if len({(row.get('batch_id'), row.get('native_id')) for row in rows}) != len(rows):
            problems.append('external record index has duplicate batch-qualified ids')
    except Exception as error:  # noqa: BLE001
        problems.append(f'unreadable external record index: {error}')

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

    return {'batch_id': batch_id, 'state': 'incomplete' if problems else 'complete',
            'problems': problems}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--sealed', type=Path, required=True)
    parser.add_argument('--qc', type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding='utf-8-sig'))
    batch = next((entry for entry in plan['batches'] if entry['batch_id'] == args.batch), None)
    if batch is None:
        print(json.dumps({'batch_id': args.batch, 'state': 'unknown', 'problems': ['batch not in plan']}))
        return 4
    result = inspect_batch(args.batch, int(batch['spectra']), args.sealed, args.qc)
    print(json.dumps(result, ensure_ascii=False))
    return {'complete': 0, 'absent': 2, 'incomplete': 3}[result['state']]


if __name__ == '__main__':
    sys.exit(main())
