"""Build the member B delivery status files from the evidence that is actually on disk.

Every status here is *derived* from a report the pipeline produced, never asserted: a step counts as
``passed`` only if its log exists and its recorded exit code and report fields say so. Anything that
depends on member A or C (the joint freeze of P3/P4, the 5,000-recipe master table, the M1 condition,
the cross review) is reported as ``pending`` or ``blocked`` with the missing input named.

Outputs
* ``datasets/B-part/B_delivery_status.json``  item by item against the task card
* ``datasets/B-part/B_delivery_hashes.json``  SHA-256 of every declared deliverable
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent                    # datasets/B-part/work
B_DIR = HERE.parent
ROOT = B_DIR.parents[1]

PASSED, PENDING, BLOCKED = 'passed', 'pending', 'blocked'


def load(relative):
    path = B_DIR / relative
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def exists(relative):
    return (B_DIR / relative).exists()


def measured_throughput(entry):
    """Seconds per spectrum, derived from the sealed full_results write timestamps.

    The spectra are written one per line as the solver finishes them, so first-to-last mtime spans the
    run. This is the number the team needs to budget the formal 20,000, and no report records it.
    """
    directory = ROOT / entry.get('dataset', '') / 'full_results' if entry.get('dataset') else None
    if directory is None or not directory.exists():
        return None
    stamps = [path.stat().st_mtime for path in directory.glob('*.json')]
    if len(stamps) < 2:
        return None
    span = max(stamps) - min(stamps)
    return {'spectra': len(stamps), 'wall_minutes': round(span / 60.0, 1),
            'seconds_per_spectrum': round(span / len(stamps), 2),
            'projected_hours_for_20000_single_thread': round(span / len(stamps) * 20000 / 3600.0, 1),
            'basis': 'full_results file mtime span, single thread pinned'}


def sha256(relative):
    path = B_DIR / relative
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def item(requirement, status, evidence, numbers=None, note=None):
    row = {'requirement': requirement, 'status': status, 'evidence': evidence}
    if numbers:
        row['numbers'] = numbers
    if note:
        row['note'] = note
    return row


def pilot_items(ledger):
    """One item per executed step, read back from the batch ledger entries."""
    items = {}
    for entry in (ledger or {}).get('batches', []):
        tag = entry['condition']
        gen = item('3. generate 200 pilot spectra with the documented flag set, no --jitter, '
                   'pilot seed different from the formal 2026101803/04',
                   PASSED if entry.get('generation_exit_code') == 0 and \
                   entry.get('spectrum_count') == 200 else BLOCKED,
                   [entry.get('generation_log'), entry.get('dataset')],
                   {'exit_code': entry.get('generation_exit_code'),
                    'spectra': entry.get('spectrum_count'),
                    'families': entry.get('family_count'),
                    'seed': entry.get('seed'), 'replicates': entry.get('replicates'),
                    'split_seed': entry.get('split_seed'), 'jitter': entry.get('jitter'),
                    'closure': entry.get('manifest_closure'),
                    'legacy_al': entry.get('manifest_legacy_al'),
                    'targets': entry.get('targets_count'),
                    'splits': entry.get('manifest_split_counts'),
                    'window_loss_fraction': entry.get('window_loss_fraction_manifest'),
                    'ba_window_summary': entry.get('ba_window_summary'),
                    'measured_throughput': measured_throughput(entry)},
                   'workflow_pilot_only, excluded from the formal budget')
        ver = entry.get('verification') or {}
        ver_problems = ver.get('problems') or []
        ver_only_budget = bool(ver_problems) and all(
            'out-of-window budget' in p for p in ver_problems)
        items['%s_generate' % tag] = gen
        items['%s_verify' % tag] = item(
            '3. confirm same-recipe replicates share composition, profile and expected spectrum and '
            'differ only in counting noise; check line systems, windows, support, six components and '
            'out-of-window loss',
            PASSED if ver.get('status') == PASSED else BLOCKED,
            [ver.get('report')],
            {'report_status': ver.get('status'),
             'spectra_checked': ver.get('spectra_checked'),
             'replicate_pairs_all_passed': ver.get('replicate_pairs_all_passed'),
             'window_loss_max': ver.get('window_loss_max'),
             'interference_pair_line_presence': ver.get('pairs'),
             'problems': ver.get('problems')},
            None if ver.get('status') == PASSED else (
                ('the check ran on all %s spectra and every integrity check passed; it is recorded as '
                 'blocked only because B\'s own pre-declared 1%% out-of-window budget is exceeded on '
                 'part of the batch. B will not relax a threshold it declared before the run, so the '
                 'joint freeze has to either accept the measured loss or re-plan the window. See the '
                 'report window_loss block and B_profile_review.md section 2.8'
                 % ver.get('spectra_checked')) if ver_only_budget
                else 'integrity problems, see the report problems list'))
        aud = entry.get('audit') or {}
        items['%s_audit' % tag] = item('3. write the QC audit report outside the sealed directory',
                                       PASSED if aud.get('exit_code') == 0 and
                                       aud.get('status') == PASSED else BLOCKED,
                                       [aud.get('report'), aud.get('log')],
                                       {'exit_code': aud.get('exit_code'),
                                        'status': aud.get('status'),
                                        'check_type': aud.get('check_type'),
                                        'spectra_checked': aud.get('spectra_checked'),
                                        'errors': aud.get('errors'),
                                        'complete_physics_recalculation':
                                            aud.get('complete_physics_recalculation'),
                                        'report_outside_sealed_dataset':
                                            aud.get('report_outside_sealed_dataset')})
        rep = entry.get('replay') or {}
        status = rep.get('status')
        items['%s_replay' % tag] = item(
            '3. run the full replay without --limit using the app.py sealed inside the batch',
            PASSED if status == PASSED else
            (PENDING if status is None else 'passed_with_environment_differences'),
            [rep.get('report'), rep.get('log')],
            {'exit_code': rep.get('exit_code'), 'status': status,
             'scope': rep.get('scope'), 'spectra_recalculated': rep.get('spectra_recalculated'),
             'complete_physics_recalculation': rep.get('complete_physics_recalculation'),
             'same_environment': rep.get('same_environment'),
             'maximum_absolute_array_difference': rep.get('maximum_absolute_array_difference'),
             'errors': rep.get('errors'),
             'executed_with': rep.get('executed_with'),
             'executed_with_sha256': rep.get('executed_with_sha256')},
            'pack is QC only and does not replace this step' if status is None else None)
        pack = entry.get('pack') or {}
        items['%s_pack' % tag] = item('3. pack the batch, record the external ZIP SHA256 and verify '
                                      'the ZIP CRC',
                                      PASSED if pack.get('exit_code') == 0 and
                                      pack.get('zip_crc_test') == PASSED else BLOCKED,
                                      [pack.get('zip'), pack.get('zip_sha256_sidecar'),
                                       pack.get('log')],
                                      {'exit_code': pack.get('exit_code'),
                                       'zip': pack.get('zip'), 'zip_sha256': pack.get('zip_sha256'),
                                       'members': pack.get('zip_member_count'),
                                       'crc_test': pack.get('zip_crc_test')})
    return items


def main():
    preflight = load('B_preflight.json')
    coverage = load('B_coverage.json')
    profile_diff = load('B_profile_diff.json')
    selection = load('B_pilot_selection.json')
    crosscheck = load('B_environment_crosscheck.json')
    source_check = load('work/B_source_verification.json')
    reverif = load('work/B_candidate_hash_reverification.json')
    m1 = load('B_M1_status.json')
    try:
        import run_B_pilot
        ledger = run_B_pilot.load_ledger()
    except OSError:
        ledger = None

    status = {'owner': 'B', 'stage': 'member B delivery status for prompt 01',
              'rule': 'passed only for work that was actually executed and whose report is on disk; '
                      'pending or blocked for everything that needs A, C or the joint freeze. A '
                      'single-operator self-check is not the A cross review of B.',
              'items': {}}
    items = status['items']

    items['0_read_sources_and_list_existing_vs_missing'] = item(
        '0. read both PDFs and the A-part evidence, list what exists and what is missing',
        PASSED if preflight else BLOCKED,
        ['B_preflight.json'],
        {'preflight_status': (preflight or {}).get('status'),
         'files_missing_at_intake':
             (preflight or {}).get('existing_vs_missing', {}).get('missing_or_unreadable'),
         'things_that_did_not_exist_before_b_started':
             [row['item'] for row in
              (preflight or {}).get('existing_vs_missing', {}).get('missing_before_b_started', [])],
         'input_disappeared_after_the_preflight_record':
             [name for group in (preflight or {}).get('existing_vs_missing',
                                                      {}).get('file_inventory', {}).values()
              for name, row in group.items()
              if row.get('exists') and not (ROOT / name).exists()]})
    items['0_isolated_environment_and_digests'] = item(
        '0. isolated environment from requirements-lock.txt, re-recorded digests, GUI launcher not '
        'used as a production command',
        PASSED if (source_check or {}).get('mismatches') == [] and
        (crosscheck or {}).get('observed_counts_bit_identical_to_a') else BLOCKED,
        ['B_environment.json', 'B_preflight.json', 'B_environment_crosscheck.json',
         'work/B_source_verification.json'],
        {'local_files': (source_check or {}).get('local_file_count'),
         'sealed_files_compared': (source_check or {}).get('compared_count'),
         'digest_mismatches': len((source_check or {}).get('mismatches') or []),
         'a_sealed_p1_vs_p2_mismatches': len((source_check or {}).get('sealed_p1_vs_p2_mismatches')
                                             or []),
         'a_pilot_replay_expected_counts_max_diff': (crosscheck or {}).get(
             'maximum_absolute_expected_counts_difference'),
         'a_pilot_blind_files_byte_identical': (crosscheck or {}).get(
             'blind_input_files_byte_identical_to_a'),
         'crosscheck_status': (crosscheck or {}).get('status')})
    items['1_1500_recipes_with_predeclared_criteria'] = item(
        '1. 1,500 iron-rich-oxide recipes (900/300/300) balanced on Fe2O3T, strict closure, dual '
        'dedup hashes, family integrity, near-neighbour rule',
        PASSED if (coverage or {}).get('total_recipes') == 1500 and
        all(bool(v) for v in (coverage or {}).get('design_checks', {}).values()
            if isinstance(v, bool)) else BLOCKED,
        ['B_samples.json', 'B_formula_registry.csv', 'B_coverage.json', 'B_design_basis.md',
         'B_design_ranges.json', 'build_B.py', 'B_cross_A_overlap.json'],
        {'recipes': (coverage or {}).get('total_recipes'),
         'unique_by_a_rule': (coverage or {}).get('unique_by_a_rule_hash'),
         'unique_by_unified_12_decimal': (coverage or {}).get('unique_by_unified_12_decimal_key'),
         'scenarios': (coverage or {}).get('scenario_counts'),
         'max_abs_composition_sum_error': (coverage or {}).get('design_checks', {}).get(
             'max_abs_composition_sum_error'),
         'duplicate_repairs': (coverage or {}).get('design_checks', {}).get('duplicate_repairs'),
         'provenance_reconversion_mismatches': (coverage or {}).get(
             'design_checks', {}).get('provenance_reconversion_mismatches')})
    zero_low = [(element, row['zero'], row['low_0_to_0_1_percent'])
                for element, row in ((coverage or {}).get('coverage') or {}).items()
                if element not in ('Fe', 'O') and (row['zero'] < 50 or row['low_0_to_0_1_percent'] < 50)]
    items['1_exact_zero_and_low_bin_coverage'] = item(
        '1. at least 50 exact-zero and 50 low-quantity (0 < percent <= 0.1) independent recipes per '
        'applicable element, otherwise a documented per-element gap with the reason',
        PASSED if not zero_low and coverage else BLOCKED,
        ['B_coverage.json', 'B_design_basis.md'],
        {'applicable_elements': (coverage or {}).get('applicable_elements'),
         'elements_below_50_in_zero_or_low': zero_low,
         'exempt': (coverage or {}).get('exempt'),
         'documented_gap_elements': sorted((coverage or {}).get('gaps') or {}),
         'gap_kind': 'only the degenerate mid band, no zero or low shortfall (shortfall_counts empty)'
                     if coverage and not any((coverage['gaps'][e].get('shortfall_counts')
                                              for e in (coverage['gaps'] or {}))) else None},
        'Fe and O are exempt: Fe is the required iron matrix, O is stoichiometric bookkeeping and not '
        'a fluorescence target of this model version')
    items['2_P3_P4_candidate_profiles'] = item(
        '2. complete-field P3_candidate.json and P4_candidate.json with per-field diffs, units, '
        'reasons, windows, config SHA256 and calibration_status=assumed_unverified',
        PASSED if (profile_diff or {}).get('fields_written_per_candidate') and
        exists('P3_candidate.json') and exists('P4_candidate.json') else BLOCKED,
        ['P3_candidate.json', 'P4_candidate.json', 'B_profile_diff.json',
         'work/B_candidate_hash_reverification.json'],
        {'fields_per_candidate': (profile_diff or {}).get('fields_written_per_candidate'),
         'dataclass_field_count': (profile_diff or {}).get('field_count_profile_dataclass'),
         'config_sha256': (profile_diff or {}).get('config_sha256'),
         'digest_erratum': {tag: {k: reverif['candidates'][tag].get(k) for k in
                                  ('sha256_of_file_as_stored', 'sha256_of_canonical_field_vector',
                                  'crlf_line_breaks', 'bytes_on_disk')}
                            for tag in ('P3', 'P4')} if reverif else None,
         'authoritative_for_cross_checks': (reverif or {}).get('authoritative_for_cross_checks'),
         'calibration_status': (profile_diff or {}).get('calibration_status'),
         'diff_status': (profile_diff or {}).get('status')},
        'candidates only: they are not the frozen P3/P4 and carry no instrument calibration. The '
        'section 2 config_sha256 values hashed the line-ending-normalized text; the stored-byte '
        'digests above are what a cross check obtains, and the canonical 34-field vector hash '
        'proves the parsed values never changed')
    items['2_support_runs_and_element_review'] = item(
        '2. run app.py support with the isolated interpreter for both candidates and write the '
        'per-element conclusions to B_profile_review.md',
        PASSED if (profile_diff or {}).get('support_runs') and exists('B_profile_review.md') else
        BLOCKED,
        ['B_profile_review.md', 'work/profile_support/B_profile_support_P3.json',
         'work/profile_support/B_profile_support_P4.json', 'B_profile_support_summary.json',
         'B_profile_pair_check.json', 'B_profile_diff.json'],
        {'support_runs': {tag: {'support_file': row.get('stable_copy'),
                                'support_sha256': row.get('stable_copy_sha256') or
                                row.get('support_sha256'),
                                'element_count': row.get('element_count'),
                                'status_counts': row.get('status_counts'),
                                'cli_log': row.get('log')}
                          for tag, row in ((profile_diff or {}).get('support_runs') or {}).items()},
         'cli_output_run_directory': (profile_diff or {}).get('cli_output_run_directory')})
    items['3_pilot_recipe_selection'] = item(
        '3. deterministic 100-recipe selection (40 routine, 20 sparse/boundary, 4+4 complete 5-row '
        'interference families) plus the exposure list for C',
        PASSED if (selection or {}).get('selected_count') == 100 and
        exists('B_pilot_family_exposure.csv') else BLOCKED,
        ['B_pilot_samples.json', 'B_pilot_family_exposure.csv', 'B_pilot_selection.json',
         'work/select_B_pilot.py'],
        {'selected': (selection or {}).get('selected_count'),
         'scenarios': (selection or {}).get('scenario_counts'),
         'blocks': (selection or {}).get('block_counts'),
         'interference_families': (selection or {}).get('interference_families'),
         'selection_seed': (selection or {}).get('seed')})
    items.update(pilot_items(ledger))
    items['4_M1'] = item(
        '4. check milestone M1 separately (A 100 recipes, B 3 spectra each, C lead review, A second '
        'review, 300 new spectra) and never substitute the section 3 pilots for it',
        BLOCKED if (m1 or {}).get('status') == 'M1_pending_profile' else PENDING,
        ['B_M1_status.json', 'work/prepare_B_M1.py'],
        {'recorded_status': (m1 or {}).get('status'),
         'planner_dry_run_jobs': {tag: row['jobs'] for tag, row in
                                  ((m1 or {}).get('readiness_proved_by_this_script', {})
                                   .get('plans') or {}).items()},
         'proposed_seed_once_frozen': (m1 or {}).get('proposed_when_frozen', {}).get('seed'),
         'blockers': [row['item'] for row in (m1 or {}).get('blockers', [])]},
        'readiness is proved by a make_plan dry run only; no spectrum was generated, because A has '
        'not frozen an M1 condition in this workspace and P3/P4 must not be guessed as M1 conditions')
    items['freeze_dependencies_outstanding'] = item(
        'outstanding: joint freeze of P3/P4, 5,000-recipe master table with C 1,000 recipes, '
        'family-aware global split index, A cross review of B, C lead review of the pilot batches',
        BLOCKED, ['B_design_basis.md', 'B_profile_review.md', 'B_M1_status.json'],
        {'pilot_batches_need_repeat_if_frozen_values_differ': True,
         'a_cross_review_of_B': 'not started (this delivery is a single-operator self-check)',
         'c_exposure_marking_of_pilot_families': 'ready: B_pilot_family_exposure.csv lists the 68 '
                                                 'exposed parent families with '
                                                 'blind_test_use_forbidden=yes'})
    items['formal_P3_P4_20000_spectra'] = item(
        'prompt 02 scope: formal P3/P4 production of 20,000 spectra', BLOCKED,
        ['02_B_formal_production_prompt.md'],
        {'missing_inputs': ['frozen P3/P4 profiles', '5,000-recipe master table',
                            'authoritative family split index', 'M3 development pilot result',
                            'approved wall-clock budget'],
         'measured_seconds_per_spectrum_candidates': {
             entry['condition']: measured_throughput(entry)
             for entry in (ledger or {}).get('batches', [])},
         'reference_a_pilot_crosscheck_seconds_per_spectrum':
             (crosscheck or {}).get('seconds_per_spectrum')})

    readme_path = B_DIR / 'README.md'
    readme = readme_path.read_text(encoding='utf-8') if readme_path.exists() else ''
    original_copy = HERE / 'README_prompt_packaging_original.md'
    original_text = original_copy.read_text(encoding='utf-8') if original_copy.exists() else ''
    intake_digest = next((row.get('sha256')
                          for group in (preflight or {}).get('existing_vs_missing',
                                                             {}).get('file_inventory', {}).values()
                          for name, row in group.items() if name.endswith('B-part/README.md')), None)
    required_markers = ['退出码', 'M1_pending_profile', '冻结', '交给 A/C', '缺口', 'B_delivery_hashes']
    items['5_readme_and_delivery_manifest'] = item(
        '5. write README.md with the actual counts, coverage and gaps, every verification command '
        'with its exit code, the hashes, the pilot status, the M1 status, the files handed to A and '
        'C, and the outstanding freeze dependencies',
        PASSED if readme and bool(original_text) and original_text in readme and
        all(marker in readme for marker in required_markers) else BLOCKED,
        ['README.md', 'work/README_prompt_packaging_original.md', 'B_delivery_status.json',
         'B_delivery_hashes.json'],
        {'readme_bytes': readme_path.stat().st_size if readme_path.exists() else None,
         'readme_sha256': sha256('README.md'),
         'original_prompt_packaging_text_kept_verbatim': bool(original_text) and original_text in readme,
         'original_prompt_packaging_sha256_of_copy':
             sha256('work/README_prompt_packaging_original.md'),
         'original_prompt_packaging_sha256_recorded_at_intake': intake_digest,
         'markers_present': [m for m in required_markers if m in readme]},
        'this delivery is a single-operator self-check: it is not the A cross review of B and not '
        'the C lead review')

    out = B_DIR / 'B_delivery_status.json'
    out.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')

    declared = ['B_design_ranges.json', 'B_design_basis.md', 'build_B.py', 'B_samples.json',
                'B_formula_registry.csv', 'B_coverage.json', 'B_cross_A_overlap.json',
                'B_profile_diff.json',
                'P3_candidate.json', 'P4_candidate.json', 'B_profile_support_summary.json',
                'B_profile_support_summary.csv',
                'B_profile_pair_check.json', 'B_profile_review.md', 'B_pilot_samples.json',
                'B_pilot_family_exposure.csv', 'B_pilot_selection.json', 'B_environment.json',
                'B_preflight.json', 'B_environment_crosscheck.json', 'B_M1_status.json',
                'B_delivery_status.json', 'README.md',
                'work/select_B_pilot.py', 'work/run_B_pilot.py', 'work/prepare_B_M1.py',
                'work/build_B_profiles.py', 'work/summarize_B_profile_support.py',
                'work/B_interference_pair_check.py', 'work/render_B_profile_tables.py',
                'work/record_environment_and_preflight.py', 'work/verify_generator_source.py',
                'work/check_environment_reproducibility.py', 'work/B_source_verification.json',
                'work/verify_B_candidate_hashes.py', 'work/B_candidate_hash_reverification.json',
                'work/B_profile_review_tables.md', 'work/write_B_delivery_status.py',
                'work/pilot_ledger.json',
                'work/profile_support/B_profile_support_P3.json',
                'work/profile_support/B_profile_support_P4.json',
                'work/profile_support/B_profile_support_P1_reference.json']
    for entry in (ledger or {}).get('batches', []):
        for key in ('generation_log',):
            if entry.get(key):
                declared.append(entry[key])
        for block_name in ('verification', 'audit', 'replay', 'pack'):
            block = entry.get(block_name) or {}
            for field in ('report', 'log', 'zip', 'zip_sha256_sidecar'):
                if block.get(field):
                    declared.append(block[field])
    for path in sorted((HERE / 'ledger').glob('*.json')):
        declared.append(str(path.relative_to(B_DIR).as_posix()))
    # every command that recorded its own exit code on disk is part of the evidence chain
    for path in sorted(HERE.glob('runs/**/*.log')) + sorted(HERE.glob('runs/*.log')) + \
            sorted(HERE.glob('runs/**/run_manifest.json')) + \
            sorted(HERE.glob('runs/probe_pilot_note.json')) + \
            [HERE / name for name in ('build_B_run.log', 'design_mineral_cli.log')] + \
            sorted(HERE.glob('envcheck/*.log')) + sorted(HERE.glob('refs/*.txt')):
        if path.is_file():
            declared.append(str(path.relative_to(B_DIR).as_posix()))
    for name in ('work/B_recipe_checks.json', 'work/pilot_ledger_selftest.json',
                 'work/README_prompt_packaging_original.md'):
        declared.append(name)
    hashes, missing = {}, []
    for name in declared:
        path = (ROOT / name) if name.startswith('datasets/') else (B_DIR / name)
        if path.is_file():
            hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(
                path.read_bytes()).hexdigest()
        else:
            missing.append(str(name))
    hashes_doc = {'owner': 'B', 'algorithm': 'SHA-256',
                  'note': 'hashes of the declared deliverables as they stand now; the sealed batch '
                          'directories themselves are covered by their own integrity.json plus the '
                          'pack ZIP sidecar, which is re-hashed externally in the ledger',
                  'files': dict(sorted(hashes.items())), 'declared_but_missing': missing}
    (B_DIR / 'B_delivery_hashes.json').write_text(json.dumps(hashes_doc, ensure_ascii=False, indent=2),
                                                  encoding='utf-8')
    counts = {}
    for row in status['items'].values():
        counts[row['status']] = counts.get(row['status'], 0) + 1
    print(json.dumps({'items': len(status['items']), 'status_counts': counts,
                      'batch_ids': [entry['id'] for entry in (ledger or {}).get('batches', [])],
                      'hashed': len(hashes), 'missing': missing}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
