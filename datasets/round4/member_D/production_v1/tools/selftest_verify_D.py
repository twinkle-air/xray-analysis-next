#!/usr/bin/env python
"""Negative self-tests for verify_production_D.py.

Each case mutates a synthetic corpus, runs the verifier as a subprocess and
asserts it exits non-zero while naming the expected failed check. A case that
reports success on broken data is itself a failure of this suite.
"""
import csv
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

VERIFY = pathlib.Path(__file__).resolve().parent / 'verify_production_D.py'
BATCHES = {
    'R4_D_train_stage1_0001': {'usage': 'train', 'condition_group': 'gradient', 'training_stage': 'stage1'},
    'R4_D_validation_stage1_0001': {'usage': 'validation', 'condition_group': 'gradient', 'training_stage': 'stage1'},
}
RECORDS_PER_BATCH = 100
CAPS = {'maximum_lost_fraction_49kV': 0.5, 'maximum_lost_fraction_20kV': 0.1}
PLAN_COLUMNS = ('global_record_id', 'batch_id', 'native_id', 'opaque_blind_id', 'candidate_id',
                'unified_family_id', 'member', 'research_usage', 'training_stage',
                'condition_instance_id', 'condition_group', 'repeat', 'noise_seed',
                'profile_physical_sha256', 'native_split_not_authoritative',
                'eligible_for_training', 'exposure_status')
INDEX_COLUMNS = PLAN_COLUMNS + ('blind_path', 'blind_sha256', 'full_path', 'full_sha256',
                                'archive_path', 'archive_sha256', 'qc_status')


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha_file(path):
    return sha_bytes(path.read_bytes())


def blind_payload(batch_index, record_index):
    return json.dumps({'axis': [str(i) for i in range(8)], 'counts': [record_index] * 8,
                       'signal_unit': 'counts', 'synthetic': True,
                       'x': [0.1 * i for i in range(8)]}, sort_keys=True).encode()


def build_fixture(root):
    root = pathlib.Path(root)
    (root / 'reports').mkdir(parents=True, exist_ok=True)
    (root / 'archives').mkdir(parents=True, exist_ok=True)

    expectations_batches = {}
    records = []
    blind_entries = {}
    for batch_position, (bid, meta) in enumerate(BATCHES.items()):
        d = root / 'reports' / bid
        d.mkdir(parents=True, exist_ok=True)
        archive = root / 'archives' / f'{bid}.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for i in range(RECORDS_PER_BATCH):
                native_id = f'S{i:06d}'
                raw = blind_payload(batch_position, i)
                blind_path = f'blind_inputs/{native_id}.json'
                full_path = f'full_results/{native_id}.json'
                z.writestr(blind_path, raw)
                z.writestr(full_path, json.dumps({'native_id': native_id, 'counts': list(raw)[:8]}).encode())
                opaque = sha_bytes(f'{bid}/{native_id}'.encode())[:24]
                blind_entries[f'{opaque}.json'] = raw
                records.append({
                    'global_record_id': f'{bid}/{native_id}', 'batch_id': bid, 'native_id': native_id,
                    'opaque_blind_id': opaque, 'candidate_id': f'R4_D_CANDIDATE_{batch_position:02d}_REPEAT_{i % 10 + 1:02d}',
                    'unified_family_id': f'R4_D_FAMILY_{batch_position:02d}', 'member': 'D',
                    'research_usage': meta['usage'], 'training_stage': meta['training_stage'],
                    'condition_instance_id': f'q{sha_bytes(f"cond-{bid}-{i}".encode())[:25]}',
                    'condition_group': meta['condition_group'], 'repeat': str(i % 2),
                    'noise_seed': str(1000000 + batch_position * 1000 + i),
                    'profile_physical_sha256': sha_bytes(f'profile-{batch_position}'.encode()),
                    'native_split_not_authoritative': 'train', 'eligible_for_training': 'False',
                    'exposure_status': 'synthetic_production_generated',
                    'blind_path': blind_path, 'blind_sha256': sha_bytes(raw),
                    'full_path': full_path,
                    'full_sha256': sha_bytes(z.read(full_path)),
                    'archive_path': f'archives/{bid}.zip', 'archive_sha256': sha_file(archive),
                    'qc_status': 'passed',
                })
        expectations_batches[bid] = {'spectra': RECORDS_PER_BATCH, 'usage': meta['usage'],
                                     'training_stage': meta['training_stage'],
                                     'condition_group': meta['condition_group']}
        archive_digest = sha_file(archive)
        for r in records:
            if r['batch_id'] == bid:
                r['archive_sha256'] = archive_digest

        index_rows = [r for r in records if r['batch_id'] == bid]
        evidence = {
            'audit.json': {'status': 'passed', 'check_type': 'registered_targets', 'spectra_checked': RECORDS_PER_BATCH,
                           'family_count': 1, 'target_coverage': 'complete', 'errors': [],
                           'tolerances': {}, 'complete_physics_recalculation': True,
                           'physical_calibration_verified': False, 'concentration_accuracy_verified': False},
            'replay.json': {'status': 'passed', 'scope': 'all_records', 'spectra_recalculated': RECORDS_PER_BATCH,
                            'complete_physics_recalculation': True, 'same_environment': True,
                            'maximum_absolute_array_difference': 0.0, 'errors': [], 'rtol': 1e-9,
                            'atol_counts': 1e-7, 'file_byte_identity_tested': False,
                            'physical_calibration_verified': False, 'concentration_accuracy_verified': False},
            'window_budget.json': {'records': [{'native_id': r['native_id'], 'lost_fraction': 0.02,
                                                'budget': CAPS['maximum_lost_fraction_49kV'], 'passed': True}
                                               for r in index_rows]},
            'commands.json': {'actions': ['generate', 'audit', 'replay']},
            'actual_record_index.csv': None,
        }
        with open(d / 'actual_record_index.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=INDEX_COLUMNS)
            writer.writeheader()
            writer.writerows(index_rows)
        for name in evidence:
            if name == 'actual_record_index.csv':
                continue
            (d / name).write_text(json.dumps(evidence[name], ensure_ascii=False), encoding='utf-8')
        summary = {
            'status': 'passed_all_records', 'batch_id': bid, 'records': RECORDS_PER_BATCH,
            'freeze_manifest_sha256': sha_bytes(b'fixture-freeze'), 'archive_sha256': sha_file(archive),
            'archive_bytes': archive.stat().st_size, 'audit': 'all_records_passed',
            'replay': 'all_records_passed', 'window_budget': 'all_records_passed', 'ZIP_CRC': 'passed',
            'eligible_for_training': False,
            'qc_files_sha256': {name: sha_file(d / name) for name in evidence if name != 'summary.json'},
        }
        (d / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')

    with open(root / 'actual_record_index.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    with zipfile.ZipFile(root / 'D_round4_blind_inputs.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in blind_entries.items():
            z.writestr(name, raw)

    expectations = {'freeze_manifest_sha256': sha_bytes(b'fixture-freeze'),
                    'batches': expectations_batches, 'records': [{k: r[k] for k in PLAN_COLUMNS} for r in records],
                    **CAPS}
    (root / 'expectations.json').write_text(json.dumps(expectations, ensure_ascii=False), encoding='utf-8')
    return root


def write_index(root, rows):
    with open(root / 'actual_record_index.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def read_index(root):
    with open(root / 'actual_record_index.csv', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def patch_summary(root, bid, **changes):
    path = root / 'reports' / bid / 'summary.json'
    summary = json.loads(path.read_text(encoding='utf-8'))
    summary.update(changes)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')


def rehash_qc(root, bid, name):
    """Keep the summary QC hash valid so only the intended check fails."""
    d = root / 'reports' / bid
    patch_summary(root, bid, qc_files_sha256={
        k: (sha_file(d / k) if k == name else v)
        for k, v in json.loads((d / 'summary.json').read_text(encoding='utf-8'))['qc_files_sha256'].items()})


def cases():
    def missing_batch(root):
        shutil.rmtree(root / 'reports' / 'R4_D_validation_stage1_0001')
        return ['batch_set_complete']

    def extra_batch(root):
        shutil.copytree(root / 'reports' / 'R4_D_train_stage1_0001', root / 'reports' / 'R4_D_train_stage1_9999')
        patch_summary(root, 'R4_D_train_stage1_9999', batch_id='R4_D_train_stage1_9999')
        return ['batch_set_exact']

    def archive_tampered(root):
        path = root / 'archives' / 'R4_D_train_stage1_0001.zip'
        path.write_bytes(path.read_bytes() + b'x')
        return ['archive_sha256']

    def qc_hash_broken(root):
        (root / 'reports' / 'R4_D_train_stage1_0001' / 'audit.json').write_text('{"status": "passed"}', encoding='utf-8')
        return ['qc_files_hashed']

    def audit_incomplete(root):
        bid = 'R4_D_train_stage1_0001'
        path = root / 'reports' / bid / 'audit.json'
        audit = json.loads(path.read_text(encoding='utf-8'))
        audit['spectra_checked'] = RECORDS_PER_BATCH - 1
        path.write_text(json.dumps(audit), encoding='utf-8')
        rehash_qc(root, bid, 'audit.json')
        return ['audit_full']

    def summary_not_passed(root):
        patch_summary(root, 'R4_D_train_stage1_0001', status='failed_records_retained')
        return ['summary_status']

    def index_row_dropped(root):
        rows = read_index(root)
        write_index(root, rows[:-1])
        return ['index_row_count', 'index_ids_exact']

    def index_role_flipped(root):
        rows = read_index(root)
        rows[0]['research_usage'] = 'sealed_test'
        write_index(root, rows)
        return ['index_matches_frozen_plan', 'index_role_distribution', 'families_do_not_cross_usage']

    def index_eligibility_flipped(root):
        rows = read_index(root)
        rows[3]['eligible_for_training'] = 'True'
        write_index(root, rows)
        exp = json.loads((root / 'expectations.json').read_text(encoding='utf-8'))
        exp['records'][3]['eligible_for_training'] = 'True'
        (root / 'expectations.json').write_text(json.dumps(exp, ensure_ascii=False), encoding='utf-8')
        return ['index_not_eligible']

    def window_budget_breached(root):
        bid = 'R4_D_train_stage1_0001'
        path = root / 'reports' / bid / 'window_budget.json'
        budget = json.loads(path.read_text(encoding='utf-8'))
        budget['records'][0]['lost_fraction'] = 0.9
        path.write_text(json.dumps(budget), encoding='utf-8')
        rehash_qc(root, bid, 'window_budget.json')
        return ['window_budget_passed', 'window_budget_within_frozen_caps']

    def blind_entry_dropped(root):
        src = root / 'D_round4_blind_inputs.zip'
        with zipfile.ZipFile(src) as zin:
            kept = [(n, zin.read(n)) for n in zin.namelist()][1:]
        with zipfile.ZipFile(src, 'w', zipfile.ZIP_DEFLATED) as zout:
            for name, raw in kept:
                zout.writestr(name, raw)
        return ['blind_entry_count']

    def blind_payload_relabelled(root):
        src = root / 'D_round4_blind_inputs.zip'
        with zipfile.ZipFile(src) as zin:
            entries = [(n, zin.read(n)) for n in zin.namelist()]
        name, raw = entries[0]
        leaked = json.loads(raw)
        leaked['element'] = 'Fe'
        entries[0] = (name, json.dumps(leaked).encode())
        with zipfile.ZipFile(src, 'w', zipfile.ZIP_DEFLATED) as zout:
            for n, b in entries:
                zout.writestr(n, b)
        return ['blind_keys_allowed', 'blind_no_label_leakage', 'blind_entry_sha256']

    def full_result_tampered(root):
        archive = root / 'archives' / 'R4_D_train_stage1_0001.zip'
        with zipfile.ZipFile(archive) as zin:
            entries = [(n, zin.read(n)) for n in zin.namelist()]
        entries = [(n, (b'{"counts": [9,9,9,9,9,9,9,9]}' if n == 'full_results/S000001.json' else b))
                   for n, b in entries]
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zout:
            for n, b in entries:
                zout.writestr(n, b)
        patch_summary(root, 'R4_D_train_stage1_0001', archive_sha256=sha_file(archive),
                      archive_bytes=archive.stat().st_size)
        return ['full_result_sha256']

    return [('missing_batch', missing_batch), ('extra_batch', extra_batch),
            ('archive_tampered', archive_tampered), ('qc_hash_broken', qc_hash_broken),
            ('audit_incomplete', audit_incomplete), ('summary_not_passed', summary_not_passed),
            ('index_row_dropped', index_row_dropped), ('index_role_flipped', index_role_flipped),
            ('index_eligibility_flipped', index_eligibility_flipped),
            ('window_budget_breached', window_budget_breached), ('blind_entry_dropped', blind_entry_dropped),
            ('blind_payload_relabelled', blind_payload_relabelled), ('full_result_tampered', full_result_tampered)]


def run_verifier(fixture, report):
    proc = subprocess.run([sys.executable, '-B', str(VERIFY), '--out', str(fixture),
                           '--expectations', str(fixture / 'expectations.json'), '--report', str(report)],
                          capture_output=True, text=True)
    data = json.loads(pathlib.Path(report).read_text(encoding='utf-8')) if pathlib.Path(report).is_file() else None
    return proc, data


def main(argv=None):
    ap_args = argv if argv is not None else sys.argv[1:]
    report_path = None
    if '--report' in ap_args:
        report_path = pathlib.Path(ap_args[ap_args.index('--report') + 1])

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        workspace = pathlib.Path(tmp)
        pristine = build_fixture(workspace / 'pristine')
        baseline_dir = workspace / 'baseline'
        shutil.copytree(pristine, baseline_dir)
        proc, data = run_verifier(baseline_dir, workspace / 'baseline.json')
        checks = (data or {}).get('failed_check_names', [])
        baseline_ok = proc.returncode == 0 and data and data['status'] == 'pass' and not data['failure_count']
        results.append({'case': 'baseline_passes', 'expected_exit': 0, 'exit': proc.returncode,
                        'status': (data or {}).get('status'), 'failed_checks': checks,
                        'passed': baseline_ok})

        for name, mutate in cases():
            case_dir = workspace / name
            shutil.copytree(pristine, case_dir)
            expected = mutate(case_dir)
            proc, data = run_verifier(case_dir, workspace / f'{name}.json')
            got = (data or {}).get('failed_check_names', [])
            missing = [c for c in expected if c not in got]
            ok = (proc.returncode != 0 and data is not None and data['status'] == 'fail'
                  and data['exit_code'] == 1 and not missing)
            results.append({'case': name, 'expected_checks': expected, 'expected_exit': 'non-zero',
                            'exit': proc.returncode, 'status': (data or {}).get('status'),
                            'failed_checks': got[:12], 'undetected': missing, 'passed': ok})

    failures = [r for r in results if not r['passed']]
    payload = {
        'schema': 'round4-member-D-verifier-selftest/v1',
        'status': 'pass' if not failures else 'fail',
        'exit_code': 0 if not failures else 1,
        'generated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'verifier': str(VERIFY),
        'cases': results,
        'case_count': len(results),
        'failed_case_count': len(failures),
    }
    for r in results:
        print(f"{r['case']:<28} exit={r['exit']} status={r['status']} "
              f"undetected={r.get('undetected', [])} passed={r['passed']}")
    print('selftest', payload['status'], f'{len(failures)} of {len(results)} cases misbehaved')
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    return payload['exit_code']


if __name__ == '__main__':
    sys.exit(main())
