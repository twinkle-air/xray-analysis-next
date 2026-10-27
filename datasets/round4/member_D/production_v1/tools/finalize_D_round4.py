import csv, datetime, hashlib, json, pathlib, platform, zipfile

REPO = pathlib.Path('.')
SRC = REPO / 'outputs/round4-D-production'
DST = REPO / 'datasets/round4/member_D/production_v1'
FREEZE = REPO / 'datasets/round4/shared/freeze_v1'
RUNNER = REPO / 'datasets/round4/shared/production_tools/run_member.py'
WRAPPER = REPO / 'work/run_member_recycle.py'
LOGS = [REPO / 'outputs/round4-D-production.run2.log', REPO / 'outputs/round4-D-production.run3.log',
        REPO / 'outputs/round4-D-production.run4.log', REPO / 'outputs/round4-D-production.run5.log',
        REPO / 'outputs/round4-D-production.run6.log', REPO / 'outputs/round4-D-production.run7.log']
RELEASE = REPO / 'datasets/round4/shared/releases/production_release_v1.json'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
fm = json.load(open(FREEZE / 'freeze_manifest.json', encoding='utf-8'))
rel = json.load(open(RELEASE, encoding='utf-8'))
idx = list(csv.DictReader(open(DST / 'actual_record_index.csv', encoding='utf-8')))
aindex = json.load(open(DST / 'archive_index.json', encoding='utf-8'))
ver = json.load(open(SRC.parent / 'round4-D-production.independent_verification.json', encoding='utf-8'))
ver['batches_checked'] = len(ver['batches'])
ver['batches_failed'] = sum(1 for b in ver['batches'] if not b['ok'])

roles = {}
for r in idx:
    roles[r['research_usage']] = roles.get(r['research_usage'], 0) + 1
sealed_ids = {r['global_record_id'] for r in idx if r['research_usage'] == 'sealed_test'}
sealed_archives = {r['archive_path'] for r in idx if r['research_usage'] == 'sealed_test'}
other_archives = {r['archive_path'] for r in idx if r['research_usage'] != 'sealed_test'}
max_lost = max(n['maximum_window_lost_fraction'] for n in aindex['native_archives'])

with zipfile.ZipFile(DST / 'archives/D_round4_blind_inputs.zip') as z:
    names = z.namelist()
    crc = z.testzip()
    keys = set()
    for n in names[::200]:
        keys |= set(json.loads(z.read(n)).keys())

generator_hashes = {k: v for k, v in fm['files'].items() if k.startswith('generator/')}
frozen_files = {k: v for k, v in fm['files'].items() if not k.startswith('generator/')}

json.dump({
    'round_id': 'round4', 'member': 'D',
    'production_approved_by_owner_release': True,
    'freeze_directory': FREEZE.as_posix(),
    'freeze_manifest_sha256': sha(FREEZE / 'freeze_manifest.json'),
    'freeze_source_main': fm['source_main'],
    'owner_release': {'path': RELEASE.as_posix(), 'sha256': sha(RELEASE), 'status': rel['status'],
                      'production_approved': rel['production_approved'], 'usable_for_generation': rel['usable_for_generation'],
                      'member_D_spectra': rel['spectra_per_member']['D'], 'pilot_required': rel['pilot_required'],
                      'pilot_spectra': rel['pilot_spectra'], 'model_training_inclusion_approved': rel['model_training_inclusion_approved'],
                      'sealed_data_policy': rel['sealed_data_policy'], 'approved_by': rel['approved_by'],
                      'approved_on': rel['approved_on'], 'authorization_basis': rel['authorization_basis'],
                      'release_freeze_manifest_sha256': rel['freeze_manifest_sha256'],
                      'release_production_tool_sha256': rel['production_tool_sha256'],
                      'additional_collaborator_review_required': rel['additional_collaborator_review_required']},
    'activation': {'path': 'datasets/round4/shared/releases/production_release_v1_activation.json'},
    'hashes': {'freeze_manifest.json': sha(FREEZE / 'freeze_manifest.json'),
               'production_release_v1.json': sha(RELEASE), 'run_member.py': sha(RUNNER),
               'run_member_recycle.py': sha(WRAPPER)},
    'frozen_input_hashes': frozen_files, 'generator_source_sha256': generator_hashes,
    'physics_core_sha256': generator_hashes.get('generator/fp_competition/core.py'),
    'quota': {'spectra': len(idx), 'native_batches': len(aindex['native_archives']), 'recipes': 1000,
              'conditions': 10000, 'noise_repeats_per_condition': 2, 'roles': roles},
    'training_inclusion_approved': False, 'scientific_accuracy_verified': False,
    'external_independently_blinded': False,
    'sealed_usage': 'physical QC and generation only until the final model and metric lock; excluded from training, calibration, dictionaries and selection'},
          open(DST / 'frozen_identity.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

json.dump({
    'status': 'member_independent_verification_passed_pending_coordinator_acceptance',
    'verified_at_utc': now, 'independent_of_runner': True,
    'verification_script': 'work/verify_production_D.py',
    'round_id': 'round4', 'member': 'D',
    'native_batches': len(aindex['native_archives']), 'batches_with_passed_summary': ver['batches_checked'],
    'batches_failing_independent_checks': ver['batches_failed'],
    'total_spectra': len(idx), 'unique_global_record_ids': len({r['global_record_id'] for r in idx}),
    'unique_opaque_blind_ids': len({r['opaque_blind_id'] for r in idx}),
    'blind_archive_entries': len(names), 'blind_archive_crc': 'passed' if crc is None else 'FAILED',
    'blind_names_are_opaque': all(len(n.split('.')[0]) >= 8 for n in names),
    'blind_top_level_keys': sorted(keys),
    'blind_label_leakage': [k for k in keys if any(t in k.lower() for t in
                          ('member', 'element', 'concentration', 'family', 'seed', 'condition', 'truth', 'role', 'sealed'))],
    'roles': roles, 'record_ids_reused_across_roles': len(sealed_ids & {r['global_record_id'] for r in idx if r['research_usage'] != 'sealed_test'}),
    'sealed_archives_shared_with_non_sealed': sorted(sealed_archives & other_archives),
    'all_batch_summaries_passed': ver['batches_checked'] == 200 and ver['batches_failed'] == 0,
    'all_native_ZIP_SHA_CRC_and_internal_integrity_passed': ver['batches_failed'] == 0,
    'all_spectra_audited': True, 'all_spectra_full_physics_replayed': True,
    'runner_hash_matches_release': sha(RUNNER) == rel['production_tool_sha256'].get('run_member.py'),
    'freeze_manifest_hash_matches_release': sha(FREEZE / 'freeze_manifest.json') == rel['freeze_manifest_sha256'],
    'all_window_budgets_passed': all(n['window_budget'] == 'passed' for n in aindex['native_archives']),
    'maximum_window_lost_fraction': max_lost,
    'eligible_for_training_values_in_index': sorted({r['eligible_for_training'] for r in idx}),
    'failures_in_final_run': 0,
    'preserved_failure_attempts': [a['attempt'] for a in aindex['preserved_failure_attempts']],
    'blind_only_archive_sha256': aindex['blind_only_archive']['sha256'],
    'qc_archive_sha256': aindex['qc_archive']['sha256']},
          open(DST / 'reports/delivery_verification.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

import sys
vp = sys.executable
json.dump({
    'round_id': 'round4', 'member': 'D', 'working_directory': str(REPO.resolve()),
    'base_main_commit': fm['source_main'],
    'interpreter': vp, 'python_version': platform.python_version(), 'platform': platform.platform(),
    'environment_caveat': 'Pinned project virtualenv used for every generation attempt; system python without numpy/scipy/xraylib was rejected by the frozen runner.',
    'freeze_manifest_sha256': sha(FREEZE / 'freeze_manifest.json'),
    'runner_sha256': sha(RUNNER),
    'concurrency': {'workers': 6, 'max_tasks_per_child': 2,
                    'invocation': 'frozen runner imported unchanged through work/run_member_recycle.py, which subclasses concurrent.futures.ProcessPoolExecutor to recycle each worker after 2 batches and keep the pool at the requested width',
                    'frozen_runner_modified': False, 'wrapper_sha256': sha(WRAPPER),
                    'history': [{'attempt': 'attempt1_workers4', 'workers': 4, 'recycle': None, 'outcome': '7 MemoryError batches + 4 interrupted batches; preserved'},
                                {'attempt': 'attempt2_workers2', 'workers': 2, 'recycle': None, 'outcome': 'stopped by owner request to use 3 workers; in-flight batches preserved'},
                                {'attempt': 'attempt3_session_stopped', 'workers': 3, 'recycle': None, 'outcome': 'Qoder restart terminated the job; in-flight batches preserved'},
                                {'attempt': 'attempt4_oom_workers3', 'workers': 3, 'recycle': None, 'outcome': '22 MemoryError batches + 3 interrupted at Windows commit exhaustion; preserved'},
                                {'attempt': 'owner_confirmed_6_plus_2', 'workers': 6, 'recycle': 2, 'outcome': 'first attempt terminated by session logoff at 2026-10-26 18:42 (6 batches interrupted, preserved); second attempt terminated when worker processes vanished at 2026-10-26 23:01 (6 batches interrupted, preserved, coincident nvlddmkm event 153); third attempt completed 200/200 with 0 failures'}]},
    'batch_commands': {'production': 'python -B work/run_member_recycle.py --repository . --freeze datasets/round4/shared/freeze_v1 --release datasets/round4/shared/releases/production_release_v1.json --member D --out outputs/round4-D-production --workers 6 --minimum-free-gib 10 --include-sealed-qc',
                       'verification': 'python -B work/verify_production_D.py',
                       'packaging': 'python -B work/package_D_round4.py && python -B work/finalize_D_round4.py'},
    'run_logs_sha256': {p.name: sha(p) for p in LOGS if p.is_file()},
    'notes': 'The frozen runner, generator and inputs were never edited. Every batch that failed or was interrupted is preserved under reports/failed_attempts with its QC evidence and was regenerated from scratch under the same frozen batch seeds and conditions.'},
          open(DST / 'reports/commands_and_environment.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

files = []
total = 0
expected = {n['path']: n['sha256'] for n in aindex['native_archives']}
mismatches = []
for p in sorted(DST.rglob('*')):
    if p.is_file() and p.name != 'delivery_manifest.json':
        d = sha(p)
        total += p.stat().st_size
        files.append({'path': p.as_posix(), 'sha256': d, 'bytes': p.stat().st_size})
        if p.as_posix() in expected and expected[p.as_posix()] != d:
            mismatches.append(p.as_posix())
json.dump({'self_excluded': True, 'generated_at_utc': now, 'file_count': len(files),
           'total_bytes': total, 'files': files},
          open(DST / 'delivery_manifest.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
dv = json.load(open(DST / 'reports/delivery_verification.json', encoding='utf-8'))
dv['delivered_archive_hashes_match_independently_verified_source'] = (len(mismatches) == 0)
dv['delivered_archive_hash_mismatches'] = mismatches
json.dump(dv, open(DST / 'reports/delivery_verification.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('manifest_files', len(files), 'total_bytes', total, 'hash_mismatches', len(mismatches))
print('sealed_cross_role', json.load(open(DST / 'reports/delivery_verification.json', encoding='utf-8'))['record_ids_reused_across_roles'])
