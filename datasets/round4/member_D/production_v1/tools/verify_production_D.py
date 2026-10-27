#!/usr/bin/env python
"""Independent full-corpus verification of the round-4 member-D production run.

Exit code is part of the contract: 0 only when every check passes against the
frozen batch plan and record plan; any missing batch, failed QC, or set/row
mismatch exits non-zero and is listed in the machine-readable report.
"""
import argparse
import csv
import hashlib
import json
import pathlib
import re
import sys
import tempfile
import time
import zipfile

MEMBER = 'D'
PLAN_COLUMNS = (
    'global_record_id', 'batch_id', 'native_id', 'opaque_blind_id', 'candidate_id',
    'unified_family_id', 'member', 'research_usage', 'training_stage',
    'condition_instance_id', 'condition_group', 'repeat', 'noise_seed',
    'profile_physical_sha256', 'native_split_not_authoritative',
    'eligible_for_training', 'exposure_status',
)
BLIND_ALLOWED_KEYS = {'axis', 'counts', 'signal_unit', 'synthetic', 'x'}
BLIND_NAME_RE = re.compile(r'[A-Za-z0-9_-]{8,64}\.json\Z')


def sha256_file(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


_archive_digests = {}


def sha256_file_cached(path):
    """Archives are hashed by both the batch and the record-link pass."""
    key = str(path)
    if key not in _archive_digests:
        _archive_digests[key] = sha256_file(path)
    return _archive_digests[key]


class Checks:
    def __init__(self):
        self.failures = []
        self.totals = {}

    def fail(self, check, detail, batch=None, record=None):
        self.failures.append({'check': check, 'detail': detail,
                              'batch': batch, 'record': record})

    def ok(self, check, passed, detail, **ids):
        if not passed:
            self.fail(check, detail, **ids)
        return passed

    def count(self, name, value):
        self.totals[name] = value


def load_expectations(args, checks):
    """Frozen batch plan + record plan, or an explicit expectations file (self-tests)."""
    if args.expectations:
        data = json.loads(pathlib.Path(args.expectations).read_text(encoding='utf-8'))
        return data, data['freeze_manifest_sha256']
    freeze = pathlib.Path(args.freeze)
    manifest = freeze / 'freeze_manifest.json'
    if not manifest.is_file():
        checks.fail('freeze_missing', f'no freeze_manifest.json under {freeze}')
        raise SystemExit(2)
    freeze_sha = sha256_file(manifest)
    plan = json.loads((freeze / 'batch_plan.json').read_text(encoding='utf-8'))
    batches = {b['batch_id']: {'spectra': b['spectra'], 'usage': b['usage'],
                               'training_stage': b['training_stage'],
                               'condition_group': b['condition_group']}
               for b in plan['batches'] if b['member'] == MEMBER}
    with open(freeze / f'record_plan_{MEMBER}.csv', newline='', encoding='utf-8') as f:
        records = [{k: r[k] for k in PLAN_COLUMNS} for r in csv.DictReader(f)]
    budget = json.loads((freeze / 'window_budget.json').read_text(encoding='utf-8'))
    return ({'batches': batches, 'records': records,
             'maximum_lost_fraction_49kV': budget['maximum_lost_fraction_49kV'],
             'maximum_lost_fraction_20kV': budget['maximum_lost_fraction_20kV']},
            freeze_sha)


def check_batches(out, expect, freeze_sha, checks):
    reports = out / 'reports'
    present = sorted(p.name for p in reports.glob('*') if (p / 'summary.json').is_file())
    expected = sorted(expect['batches'])
    missing = sorted(set(expected) - set(present))
    extra = sorted(set(present) - set(expected))
    checks.ok('batch_set_complete', not missing, f'{len(missing)} frozen batches without evidence: {missing[:5]}')
    checks.ok('batch_set_exact', not extra, f'{len(extra)} unexpected batch evidence dirs: {extra[:5]}')
    if missing or extra:
        checks.count('batches_with_evidence', len(present))
        return

    max_49 = expect['maximum_lost_fraction_49kV']
    max_20 = expect['maximum_lost_fraction_20kV']
    native_ids = {}
    for r in expect['records']:
        native_ids.setdefault(r['batch_id'], set()).add(r['native_id'])
    for bid in expected:
        d = reports / bid
        spec = expect['batches'][bid]
        n = spec['spectra']
        s = json.loads((d / 'summary.json').read_text(encoding='utf-8'))
        checks.ok('summary_status', s.get('status') == 'passed_all_records', str(s.get('status')), batch=bid)
        checks.ok('summary_batch_id', s.get('batch_id') == bid, str(s.get('batch_id')), batch=bid)
        checks.ok('summary_records', s.get('records') == n, f'records={s.get("records")} expected={n}', batch=bid)
        checks.ok('summary_audit', s.get('audit') == 'all_records_passed', str(s.get('audit')), batch=bid)
        checks.ok('summary_replay', s.get('replay') == 'all_records_passed', str(s.get('replay')), batch=bid)
        checks.ok('summary_window_budget', s.get('window_budget') == 'all_records_passed',
                  str(s.get('window_budget')), batch=bid)
        checks.ok('summary_zip_crc', s.get('ZIP_CRC') == 'passed', str(s.get('ZIP_CRC')), batch=bid)
        checks.ok('summary_not_eligible', s.get('eligible_for_training') is False,
                  f'eligible_for_training={s.get("eligible_for_training")!r}', batch=bid)
        checks.ok('summary_freeze_sha', s.get('freeze_manifest_sha256') == freeze_sha,
                  str(s.get('freeze_manifest_sha256')), batch=bid)

        audit = json.loads((d / 'audit.json').read_text(encoding='utf-8'))
        checks.ok('audit_full', audit.get('status') == 'passed' and audit.get('spectra_checked') == n
                  and not audit.get('errors'),
                  f"status={audit.get('status')} checked={audit.get('spectra_checked')} errors={len(audit.get('errors') or [])}", batch=bid)
        replay = json.loads((d / 'replay.json').read_text(encoding='utf-8'))
        checks.ok('replay_full', replay.get('status') == 'passed' and replay.get('scope') == 'all_records'
                  and replay.get('spectra_recalculated') == n and not replay.get('errors'),
                  f"status={replay.get('status')} scope={replay.get('scope')} recalculated={replay.get('spectra_recalculated')} errors={len(replay.get('errors') or [])}", batch=bid)

        wb = json.loads((d / 'window_budget.json').read_text(encoding='utf-8'))
        recs = wb.get('records') or []
        caps = {max_20, max_49}
        bad_budget = [r for r in recs if not r.get('passed') or float(r['lost_fraction']) > float(r['budget'])]
        over_frozen = [r for r in recs
                       if float(r['budget']) not in caps or float(r['lost_fraction']) > max_49]
        checks.ok('window_budget_rows', len(recs) == n, f'{len(recs)} window records expected {n}', batch=bid)
        checks.ok('window_budget_passed', not bad_budget, f'{len(bad_budget)} records over their own budget', batch=bid)
        checks.ok('window_budget_within_frozen_caps', not over_frozen,
                  f'{len(over_frozen)} records outside frozen caps {sorted(caps)}', batch=bid)
        checks.ok('qc_files_hashed', all(sha256_file(d / name) == digest
                                         for name, digest in (s.get('qc_files_sha256') or {}).items()),
                  'a QC evidence file no longer matches the recorded summary hash', batch=bid)

        ap = out / 'archives' / (bid + '.zip')
        if not checks.ok('archive_present', ap.is_file(), f'missing {ap}', batch=bid):
            continue
        digest = sha256_file_cached(ap)
        checks.ok('archive_sha256', digest == s.get('archive_sha256'),
                  f'digest {digest[:12]} != summary {str(s.get("archive_sha256"))[:12]}', batch=bid)
        checks.ok('archive_bytes', ap.stat().st_size == s.get('archive_bytes'),
                  f'{ap.stat().st_size} != {s.get("archive_bytes")}', batch=bid)
        with zipfile.ZipFile(ap) as z:
            checks.ok('archive_crc', z.testzip() is None, 'internal CRC failure', batch=bid)
            names = set(z.namelist())
            for native_id in sorted(native_ids.get(bid, ())):
                checks.ok('archive_has_blind_entry', f'blind_inputs/{native_id}.json' in names,
                          'blind entry absent from native archive', batch=bid, record=native_id)
                checks.ok('archive_has_full_entry', f'full_results/{native_id}.json' in names,
                          'full result entry absent from native archive', batch=bid, record=native_id)
    checks.count('batches_with_evidence', len(present))


def check_index(out, expect, checks):
    path = out / 'actual_record_index.csv'
    if not path.is_file():
        checks.fail('index_present', f'missing {path}')
        return {}
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    by_id = {r['global_record_id']: r for r in rows}
    expected = {r['global_record_id']: r for r in expect['records']}
    checks.ok('index_present', True, str(path))
    checks.ok('index_row_count', len(rows) == len(expected),
              f'{len(rows)} rows, frozen plan requires {len(expected)}')
    checks.ok('index_ids_exact', set(by_id) == set(expected),
              f"missing={sorted(set(expected) - set(by_id))[:3]} extra={sorted(set(by_id) - set(expected))[:3]}")
    checks.ok('index_ids_unique', len(by_id) == len(rows), f'{len(rows)} rows, {len(by_id)} unique ids')
    for gid, want in expected.items():
        got = by_id.get(gid)
        if got is None:
            continue
        drift = [c for c in PLAN_COLUMNS if str(got.get(c)) != str(want[c])]
        checks.ok('index_matches_frozen_plan', not drift, f'fields differ from frozen plan: {drift}', record=gid)
        checks.ok('index_not_eligible', got.get('eligible_for_training') == 'False',
                  f'eligible_for_training={got.get("eligible_for_training")!r}', record=gid)
        checks.ok('index_qc_passed', got.get('qc_status') == 'passed', str(got.get('qc_status')), record=gid)
    ids = {r['opaque_blind_id'] for r in rows}
    checks.ok('blind_ids_unique', len(ids) == len(rows), f'{len(rows)} rows, {len(ids)} unique blind ids')
    seeds = {r['noise_seed'] for r in rows}
    checks.ok('noise_seeds_unique', len(seeds) == len(rows), f'{len(rows)} rows, {len(seeds)} unique seeds')
    usage_by_family = {}
    for r in rows:
        usage_by_family.setdefault(r['unified_family_id'], set()).add(r['research_usage'])
    crossed = sorted(f for f, u in usage_by_family.items() if len(u) > 1)
    checks.ok('families_do_not_cross_usage', not crossed, f'{len(crossed)} families split across usages: {crossed[:3]}')
    roles = {}
    for r in rows:
        roles[r['research_usage']] = roles.get(r['research_usage'], 0) + 1
    want_roles = {}
    for r in expect['records']:
        want_roles[r['research_usage']] = want_roles.get(r['research_usage'], 0) + 1
    checks.ok('index_role_distribution', roles == want_roles, f'{roles} != frozen {want_roles}')
    checks.count('index_rows', len(rows))
    checks.count('roles', roles)
    return by_id


def check_archive_links(by_id, out, checks):
    per_batch = {}
    for r in by_id.values():
        per_batch.setdefault(r['batch_id'], []).append(r)
    for bid, recs in sorted(per_batch.items()):
        ap = out / recs[0]['archive_path']
        if not checks.ok('archive_link_present', ap.is_file(), f'missing {ap}', batch=bid):
            continue
        digest = sha256_file_cached(ap)
        for r in recs:
            checks.ok('index_archive_sha256', r['archive_sha256'] == digest,
                      f"index records {r['archive_sha256'][:12]} but the archive hashes {digest[:12]}",
                      batch=bid, record=r['native_id'])
        with zipfile.ZipFile(ap) as z:
            for r in recs:
                checks.ok('full_result_sha256',
                          hashlib.sha256(z.read(r['full_path'])).hexdigest() == r['full_sha256'],
                          'full result bytes no longer hash to the recorded digest', batch=bid, record=r['native_id'])
                checks.ok('archive_blind_sha256',
                          hashlib.sha256(z.read(r['blind_path'])).hexdigest() == r['blind_sha256'],
                          'native blind entry no longer hashes to the recorded digest', batch=bid, record=r['native_id'])
    checks.count('records_full_hash_checked', sum(len(v) for v in per_batch.values()))


def assemble_blind(out, args, checks):
    """Return the path of a single-file blind export, reassembling delivered parts when needed."""
    single = pathlib.Path(args.blind_zip) if args.blind_zip else out / 'D_round4_blind_inputs.zip'
    if single.is_file():
        return single
    parts_dir = pathlib.Path(args.blind_parts) if args.blind_parts else None
    if parts_dir is None:
        checks.fail('blind_source', f'{single} not found and no --blind-parts given')
        return None
    parts = sorted(p for p in parts_dir.glob('*.part[0-9][0-9]'))
    if not parts:
        checks.fail('blind_source', f'no parts under {parts_dir}')
        return None
    tmp = pathlib.Path(tempfile.mkstemp(prefix='D_blind_reassembled_', suffix='.zip')[1])
    h = hashlib.sha256()
    with open(tmp, 'wb') as dst:
        for p in parts:
            with open(p, 'rb') as src:
                for block in iter(lambda: src.read(1 << 22), b''):
                    dst.write(block)
                    h.update(block)
    sidecar = parts_dir / (parts[0].name.split('.part')[0] + '.sha256')
    if sidecar.is_file():
        checks.ok('blind_parts_whole_sha256', h.hexdigest() == sidecar.read_text(encoding='utf-8').split()[0],
                  f'reassembled {h.hexdigest()} != sidecar')
    else:
        checks.fail('blind_parts_sidecar', f'missing {sidecar}')
    return tmp


def check_blind(out, by_id, checks, args, temps):
    path = assemble_blind(out, args, checks)
    if path is None:
        return
    if path != out / 'D_round4_blind_inputs.zip':
        temps.append(path)
    by_opaque = {r['opaque_blind_id']: r for r in by_id.values()}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        checks.ok('blind_entry_count', len(names) == len(by_id),
                  f'{len(names)} blind entries vs {len(by_id)} index rows')
        checks.ok('blind_crc', z.testzip() is None, 'internal CRC failure in blind export')
        leaky = [n for n in names if not BLIND_NAME_RE.match(n)]
        checks.ok('blind_name_shape', not leaky, f'{len(leaky)} entries not opaque-named: {leaky[:3]}')
        keys = set()
        stem_mismatch = 0
        hash_mismatch = 0
        for name in names:
            raw = z.read(name)
            stem = name[:-5]
            row = by_opaque.get(stem)
            if row is None:
                stem_mismatch += 1
                continue
            if hashlib.sha256(raw).hexdigest() != row['blind_sha256']:
                hash_mismatch += 1
            try:
                keys |= set(json.loads(raw).keys())
            except json.JSONDecodeError:
                checks.fail('blind_json_valid', f'{name} is not valid JSON')
        checks.ok('blind_ids_resolve', stem_mismatch == 0, f'{stem_mismatch} entries have no index row for their opaque id')
        checks.ok('blind_entry_sha256', hash_mismatch == 0, f'{hash_mismatch} blind entries no longer hash to the recorded digest')
        forbidden = sorted(k for k in keys if any(t in k.lower() for t in
                      ('member', 'element', 'concentration', 'family', 'seed', 'condition', 'truth', 'role', 'sealed', 'usage')))
        checks.ok('blind_keys_allowed', set(keys) <= BLIND_ALLOWED_KEYS,
                  f'unexpected top-level keys {sorted(set(keys) - BLIND_ALLOWED_KEYS)}')
        checks.ok('blind_no_label_leakage', not forbidden, f'label-bearing keys {forbidden}')
        checks.count('blind_entries', len(names))
        checks.count('blind_top_level_keys', sorted(keys))


def main(argv=None):
    here = pathlib.Path(__file__).resolve()
    root = here
    while root != root.parent and not (root / 'datasets' / 'round4' / 'shared' / 'production_tools').is_dir():
        root = root.parent
    ap = argparse.ArgumentParser(description='independent verification of the round-4 member-D production corpus')
    ap.add_argument('--out', default=str(root / 'outputs' / 'round4-D-production'),
                    help='production output directory (archives/, reports/, actual_record_index.csv)')
    ap.add_argument('--freeze', default=str(root / 'datasets' / 'round4' / 'shared' / 'freeze_v1'))
    ap.add_argument('--expectations', help='precomputed expectations JSON (used by the negative self-tests)')
    ap.add_argument('--blind-zip', help='single-file blind export; defaults to <out>/D_round4_blind_inputs.zip')
    ap.add_argument('--blind-parts', help='directory holding the delivered .partNN shards to reassemble')
    ap.add_argument('--report', help='report path; defaults to <out>.independent_verification.json')
    args = ap.parse_args(argv)

    out = pathlib.Path(args.out)
    checks = Checks()
    temps = []
    started = time.time()
    expect = {'batches': {}, 'records': []}
    freeze_sha = None
    by_id = {}
    try:
        expect, freeze_sha = load_expectations(args, checks)
        checks.ok('expectations_loaded', bool(expect['batches']) and bool(expect['records']),
                  f"{len(expect['batches'])} batches / {len(expect['records'])} records")
        check_batches(out, expect, freeze_sha, checks)
        by_id = check_index(out, expect, checks)
        if by_id:
            check_archive_links(by_id, out, checks)
            check_blind(out, by_id, checks, args, temps)
    except (OSError, KeyError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        checks.fail('verifier_crashed', f'{type(exc).__name__}: {exc}')
    finally:
        for t in temps:
            t.unlink(missing_ok=True)

    status = 'pass' if not checks.failures else 'fail'
    report = {
        'schema': 'round4-member-D-independent-verification/v2',
        'status': status,
        'exit_code': 0 if status == 'pass' else 1,
        'generated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'elapsed_seconds': round(time.time() - started, 3),
        'out': str(out),
        'freeze': str(args.freeze),
        'freeze_manifest_sha256': freeze_sha,
        'expected_batches': len(expect['batches']),
        'expected_records': len(expect['records']),
        'totals': checks.totals,
        'failure_count': len(checks.failures),
        'failed_check_names': sorted({f['check'] for f in checks.failures}),
        'failed_checks': checks.failures[:200],
        'truncation': 'failed_checks truncated at 200 entries' if len(checks.failures) > 200 else None,
    }
    report_path = pathlib.Path(args.report) if args.report else out.parent / (out.name + '.independent_verification.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')

    print(f'status={status} failures={len(checks.failures)} batches={checks.totals.get("batches_with_evidence")} '
          f'index_rows={checks.totals.get("index_rows")} blind_entries={checks.totals.get("blind_entries")} '
          f'elapsed={report["elapsed_seconds"]}s report={report_path}')
    for f in checks.failures[:20]:
        print('FAIL', f['check'], f.get('batch') or '', f.get('record') or '', f['detail'], file=sys.stderr)
    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
