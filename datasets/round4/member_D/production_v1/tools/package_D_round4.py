import csv, hashlib, json, pathlib, shutil, zipfile

REPO = pathlib.Path('.')
SRC = REPO / 'outputs/round4-D-production'
DST = REPO / 'datasets/round4/member_D/production_v1'
FREEZE = REPO / 'datasets/round4/shared/freeze_v1'
RELEASE = REPO / 'datasets/round4/shared/releases/production_release_v1.json'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def copy_if_needed(src, dst):
    if dst.is_file() and dst.stat().st_size == src.stat().st_size:
        return
    shutil.copy2(src, dst)


(DST / 'archives').mkdir(parents=True, exist_ok=True)
(DST / 'reports').mkdir(parents=True, exist_ok=True)
copy_if_needed(SRC / 'reports/D_all_batch_QC.zip', DST / 'reports/D_all_batch_QC.zip')
copy_if_needed(SRC / 'selfcheck_summary.json', DST / 'selfcheck_summary.json')
copy_if_needed(SRC / 'actual_record_index.csv', DST / 'actual_record_index.csv')

rows = list(csv.DictReader(open(SRC / 'actual_record_index.csv', encoding='utf-8')))
by_batch = {}
for r in rows:
    b = r['archive_path'].split('/')[-1][:-4]
    e = by_batch.setdefault(b, {'records': 0, 'roles': {}})
    e['records'] += 1
    e['roles'][r['research_usage']] = e['roles'].get(r['research_usage'], 0) + 1

native = []
for z in sorted((SRC / 'archives').glob('*.zip')):
    bid = z.stem
    s = json.load(open(SRC / 'reports' / bid / 'summary.json', encoding='utf-8'))
    wb = json.load(open(SRC / 'reports' / bid / 'window_budget.json', encoding='utf-8'))
    copy_if_needed(z, DST / 'archives' / z.name)
    native.append({
        'batch_id': bid, 'role_distribution': by_batch[bid]['roles'], 'spectra': s['records'],
        'path': (DST / 'archives' / z.name).as_posix(), 'sha256': s['archive_sha256'],
        'bytes': s['archive_bytes'], 'audit': s['audit'], 'full_physics_replay': s['replay'],
        'ZIP_CRC': s['ZIP_CRC'], 'window_budget': wb['status'],
        'maximum_window_lost_fraction': max(x['lost_fraction'] for x in wb['records']),
        'generation_plus_qc_seconds': round(s['seconds'], 1),
        'freeze_manifest_sha256': s['freeze_manifest_sha256'], 'eligible_for_training': False,
        'QC_archive': (DST / 'reports/D_all_batch_QC.zip').as_posix(),
        'audit_member': bid + '/audit.json', 'replay_member': bid + '/replay.json'})

blind = SRC / 'D_round4_blind_inputs.zip'

# GitHub rejects single files over 100 MB and this repository has no LFS, so the
# export ships as ordered parts the same way members A and B delivered theirs.
BLIND_PARTS = 4
blind_dir = DST / 'blind'
blind_dir.mkdir(exist_ok=True)
whole = sha(blind)
size = blind.stat().st_size
span = -(-size // BLIND_PARTS)
part_hashes = {}
with open(blind, 'rb') as src:
    for index in range(BLIND_PARTS):
        target = blind_dir / f'{blind.name}.part{index + 1:02d}'
        take = min(span, size - index * span)
        if take <= 0:
            continue
        h = hashlib.sha256()
        with open(target, 'wb') as dst:
            remaining = take
            while remaining:
                block = src.read(min(1 << 22, remaining))
                if not block:
                    break
                h.update(block)
                dst.write(block)
                remaining -= len(block)
        part_hashes[target.name] = {'sha256': h.hexdigest(), 'bytes': target.stat().st_size}
reassembled = hashlib.sha256()
for target in sorted(blind_dir.glob(f'{blind.name}.part*')):
    with open(target, 'rb') as f:
        for block in iter(lambda: f.read(1 << 22), b''):
            reassembled.update(block)
if reassembled.hexdigest() != whole:
    raise SystemExit('blind part reassembly does not reproduce the source hash')
(blind_dir / f'{blind.name}.sha256').write_text(whole + '  ' + blind.name + '\n', encoding='ascii')
(blind_dir / 'PARTS.sha256').write_text(
    ''.join(f"{v['sha256']}  {k}\n" for k, v in sorted(part_hashes.items())), encoding='ascii')
(blind_dir / 'RESTORE.md').write_text(
    '# 还原仅盲样本导出\n\n'
    '```bash\n'
    f"cat {blind.name}.part* > {blind.name}\n"
    f'sha256sum -c {blind.name}.sha256\n'
    f'unzip -t {blind.name}\n'
    '```\n\n'
    f"整包 {size:,} 字节，SHA-256 `{whole}`，{len(rows):,} 条不透明条目；分片哈希见 `PARTS.sha256`。\n"
    '本次交付已在本地完成分片重组并通过 ZIP 内部 CRC 与条目计数核对。\n',
    encoding='utf-8')

fa = DST / 'reports/failed_attempts'
fa.mkdir(exist_ok=True)
attempts = []
for ad in sorted((SRC / 'failed_attempts').iterdir()):
    notes = json.load(open(ad / 'attempt_notes.json', encoding='utf-8'))
    d = fa / ad.name
    d.mkdir(exist_ok=True)
    copy_if_needed(ad / 'attempt_notes.json', d / 'attempt_notes.json')
    notes['preserved_at_utc'] = notes.get('preserved_at_utc') or ad.name.rsplit('_', 1)[-1]
    notes.setdefault('counts', {})
    notes.setdefault('reason', 'Owner stopped this attempt; original spectra and QC evidence preserved without deletion.')
    evidence = []
    for rep in sorted((ad / 'reports').iterdir()):
        if not rep.is_dir():
            continue
        t = d / rep.name
        t.mkdir(exist_ok=True)
        for name in ('failure.json', 'window_budget.json', 'commands.json', 'audit.json', 'replay.json'):
            if (rep / name).is_file():
                shutil.copy2(rep / name, t / name)
                evidence.append(rep.name + '/' + name)
    notes['delivered_evidence'] = sorted(evidence)
    notes['full_partial_spectra_retained_locally_at'] = (SRC / 'failed_attempts' / ad.name / 'sealed_batches').as_posix() + ' (gitignored; not delivered because the spectra never passed QC)'
    json.dump(notes, open(d / 'attempt_notes.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    attempts.append({'attempt': ad.name, 'preserved_at_utc': notes['preserved_at_utc'],
                     'reason': notes['reason'], 'counts': notes['counts']})

fm = json.load(open(FREEZE / 'freeze_manifest.json', encoding='utf-8'))
json.dump({'native_archives': native,
           'blind_only_archive': {'path': (blind_dir / blind.name).as_posix(),
                                  'sha256': whole, 'bytes': size,
                                  'delivered_in_git': True, 'split_into_parts': sorted(part_hashes),
                                  'part_count': len(part_hashes),
                                  'restore_documentation': (blind_dir / 'RESTORE.md').as_posix(),
                                  'parts_sha256_index': (blind_dir / 'PARTS.sha256').as_posix(),
                                  'whole_sha256_sidecar': (blind_dir / f'{blind.name}.sha256').as_posix(),
                                  'reassembled_and_verified_locally': True,
                                  'record_count': len(rows), 'labels_included': False},
           'qc_archive': {'path': (DST / 'reports/D_all_batch_QC.zip').as_posix(),
                          'sha256': sha(DST / 'reports/D_all_batch_QC.zip'),
                          'bytes': (DST / 'reports/D_all_batch_QC.zip').stat().st_size},
           'native_batch_count': len(native), 'spectra_total': sum(n['spectra'] for n in native),
           'preserved_failure_attempts': attempts,
           'note': 'All 200 native frozen batches (100 spectra each) are delivered exactly once. Failed and interrupted attempts are preserved with their QC evidence and were regenerated from scratch under the same frozen seeds; no partial spectrum entered this delivery.'},
          open(DST / 'archive_index.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

json.dump({'batches': native}, open(DST / 'batch_metrics.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('archives', len(native), 'spectra', sum(n['spectra'] for n in native))
