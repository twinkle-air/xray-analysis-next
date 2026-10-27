import csv, hashlib, json, pathlib, sys, zipfile

OUT = pathlib.Path('outputs/round4-D-production')


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


summaries = sorted((OUT / 'reports').glob('*/summary.json'))
rows = []
for sp in summaries:
    bid = sp.parent.name
    s = json.load(open(sp, encoding='utf-8'))
    ap = OUT / 'archives' / (bid + '.zip')
    checks = {'archive_exists': ap.is_file(), 'status': s.get('status') == 'passed_all_records',
              'records_100': s.get('records') == 100,
              'audit': s.get('audit') == 'all_records_passed', 'replay': s.get('replay') == 'all_records_passed',
              'zip_crc': s.get('ZIP_CRC') == 'passed', 'not_eligible': s.get('eligible_for_training') is False}
    digest = sha(ap) if ap.is_file() else None
    checks['archive_sha'] = digest == s.get('archive_sha256')
    qc_ok = True
    for name, d in (s.get('qc_files_sha256') or {}).items():
        fp = sp.parent / name
        qc_ok = qc_ok and fp.is_file() and sha(fp) == d
    checks['qc_hashes'] = qc_ok
    a = json.load(open(sp.parent / 'audit.json', encoding='utf-8'))
    r = json.load(open(sp.parent / 'replay.json', encoding='utf-8'))
    checks['audit_all'] = a.get('status') == 'passed' and a.get('spectra_checked') == 100
    checks['replay_all'] = r.get('status') == 'passed' and r.get('scope') == 'all_records' and r.get('spectra_recalculated') == 100 and not r.get('errors')
    with zipfile.ZipFile(ap) as z:
        checks['crc_recheck'] = z.testzip() is None
    rows.append({'batch': bid, 'ok': all(checks.values()), 'failed_checks': [k for k, v in checks.items() if not v]})

bad = [r for r in rows if not r['ok']]
print('batches_checked', len(rows), 'batches_failed', len(bad))
for b in bad[:10]:
    print('FAIL', b)

idx = list(csv.DictReader(open(OUT / 'actual_record_index.csv', encoding='utf-8')))
roles = {}
elig = set()
for r in idx:
    roles[r['research_usage']] = roles.get(r['research_usage'], 0) + 1
    elig.add(r['eligible_for_training'])
print('index_rows', len(idx), 'unique_ids', len({r['global_record_id'] for r in idx}), 'roles', roles, 'eligible_values', elig)

blind = OUT / 'D_round4_blind_inputs.zip'
with zipfile.ZipFile(blind) as z:
    names = z.namelist()
    print('blind_entries', len(names), 'crc', z.testzip() is None)
    import re
    leak = [n for n in names if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}\.json', n)]
    print('blind_name_shape_bad', len(leak))
    sample = [names[i] for i in range(0, len(names), max(1, len(names) // 40))][:40]
    keys = set()
    for n in sample:
        keys |= set(json.loads(z.read(n)).keys())
    forbidden = [k for k in keys if any(t in k.lower() for t in ('member', 'element', 'concentration', 'family', 'seed', 'condition', 'truth', 'role', 'sealed'))]
    print('blind_top_keys', sorted(keys)[:12])
    print('blind_leak_keys', forbidden)
print('blind_sha256', sha(blind))
print('qc_sha256', sha(OUT / 'reports' / 'D_all_batch_QC.zip'))
json.dump({'batches': rows, 'index': {'rows': len(idx), 'unique': len({r['global_record_id'] for r in idx}), 'roles': roles}},
          open('outputs/round4-D-production.independent_verification.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
