"""Run, verify and seal the member B workflow pilots (200 spectra per candidate condition).

Task card section 3, executed exactly as written:

* the same 100-recipe sample file feeds both batches, so any difference between the two pilots is a
  condition effect and not a composition effect;
* ``--replicates 2`` gives 200 spectra per batch, ``--closure strict``, ``--legacy-al reject``,
  all 32 target elements, ``--design-ranges B_design_ranges.json``, **no ``--jitter``**,
  ``--split-seed 20261018`` (allowed) and generation seeds that are NOT A's 2026101803/2026101804;
* ``audit`` / ``replay`` / ``pack`` reports are written outside the sealed dataset directory, and the
  full replay is executed with the ``reproducibility/generator/fp_competition/app.py`` copy that was
  sealed inside the batch itself, which is the only copy the batch can honestly be replayed with;
* the batch directories are versioned (``_v1``, ``_v2`` ...) and never deleted, because a partial or
  failed batch has to stay on disk with its original report.

Phases (``--phase``): generate | verify | audit | replay_pack | all. Each phase appends to
``work/pilot_ledger.json`` and writes its evidence under ``work/pilot_reports/<batch_id>/``.

The verification phase checks the things the delivered CLI does not: that two replicates of one
recipe share composition, profile and the whole expected spectrum while differing only in counting
noise; that the six physics components add up to the in-window expectation; and that no spectrum
loses more than the declared window-loss budget.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent                    # datasets/B-part/work
B_DIR = HERE.parent
ROOT = B_DIR.parents[1]
GEN = ROOT / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition'
sys.path.insert(0, str(GEN.parent))
from fp_competition.core import (TARGET_ELEMENTS, Profile, air_transmission,  # noqa: E402
                                 detector_efficiency)
from fp_competition.dataset import energy_window as delivered_energy_window  # noqa: E402

SAMPLES = B_DIR / 'B_pilot_samples.json'
DESIGN_RANGES = B_DIR / 'B_design_ranges.json'
SPLIT_SEED = 20261018
BATCHES = (('P3', B_DIR / 'P3_candidate.json', 2026101825),
           ('P4', B_DIR / 'P4_candidate.json', 2026101826))
REPLICATES = 2
SIX_COMPONENTS = ('primary', 'secondary', 'rayleigh', 'compton', 'escape', 'background')
WINDOW_LOSS_BUDGET = 0.01
FORBIDDEN_SEEDS = (2026101803, 2026101804)
LEDGER = HERE / 'pilot_ledger.json'
LEDGER_DIR = HERE / 'ledger'
REPORTS = HERE / 'pilot_reports'
THREAD_ENV = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')


def sha256_bytes(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fresh_dataset_dir(stem):
    """Never overwrite or delete a batch: pick pilot_<stem>_vN with the lowest free N."""
    used = []
    for path in B_DIR.glob('pilot_%s_v*' % stem):
        suffix = path.name.rsplit('_v', 1)[-1]
        if suffix.isdigit():
            used.append(int(suffix))
    return B_DIR / ('pilot_%s_v%d' % (stem, max(used, default=0) + 1))


def fresh_file(path):
    """Same rule for report files: a rerun must keep the previous evidence on disk."""
    path = Path(path)
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    index = 2
    while (path.parent / ('%s_v%d%s' % (stem, index, suffix))).exists():
        index += 1
    return path.parent / ('%s_v%d%s' % (stem, index, suffix))


def cli(python, args, cwd, log_path, env=None):
    merged = dict(os.environ)
    for name in THREAD_ENV:
        merged[name] = '1'
    merged.update(env or {})
    started = time.time()
    done = subprocess.run([str(python), '-B', 'app.py'] + [str(a) for a in args],
                          cwd=str(cwd), capture_output=True, text=True, env=merged)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text('command: %s -B app.py %s\ncwd: %s\nexit_code: %d\nwall_seconds: %.1f\n'
                        'thread_env: %s\nstdout:\n%s\nstderr:\n%s\n'
                        % (python, ' '.join(str(a) for a in args), cwd, done.returncode,
                           time.time() - started, {k: merged[k] for k in THREAD_ENV},
                           done.stdout, done.stderr), encoding='utf-8')
    return done


def load_ledger():
    """Merge the per-batch ledger files (and the older single file) into one view.

    One file per batch is what makes it safe to run two batches side by side: a process only ever
    writes the file of the batch it is working on, so the heavy full replays of P3 and P4 can be
    executed in parallel without either run clobbering the other record.
    """
    merged = {'stage': 'member B section 3 workflow pilots', 'purpose': 'workflow_pilot_only',
              'purpose_note': 'these batches validate the pipeline and the candidate conditions. They '
                              'are not training, validation or final-test data, they are not counted '
                              'in the formal 20,000 (or the 50,000 total budget), and if the team '
                              'freezes P3/P4 with values different from these candidates the pilot '
                              'acceptance must be repeated against the frozen files',
              'excluded_from_budget': True,
              'forbidden_generation_seeds_documented': list(FORBIDDEN_SEEDS),
              'layout': 'work/ledger/<batch id>.json holds one batch entry each; '
                        'work/pilot_ledger.json is the pre-parallel merged view and is only read',
              'batches': []}
    batches = {}
    for path in ([LEDGER] if LEDGER.exists() else []) + sorted(LEDGER_DIR.glob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        for entry in data.get('batches', []):
            batches[entry['id']] = entry
    merged['batches'] = [batches[key] for key in sorted(batches)]
    return merged


def save_ledger(ledger, ids=None):
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    wanted = set(ids) if ids is not None else {entry['id'] for entry in ledger['batches']}
    for entry in ledger['batches']:
        if entry['id'] in wanted:
            (LEDGER_DIR / ('%s.json' % entry['id'])).write_text(
                json.dumps({'stage': 'member B section 3 workflow pilots',
                            'batch_id': entry['id'], 'batches': [entry]},
                           ensure_ascii=False, indent=2), encoding='utf-8')


def find_batch(ledger, batch_id=None):
    entries = [b for b in ledger['batches'] if batch_id is None or b['id'] == batch_id]
    if not entries:
        raise SystemExit('no pilot batch recorded in the ledger yet; run --phase generate first')
    return entries


# ------------------------------------------------------------------ generate
def phase_generate(ledger):
    for tag, profile_path, seed in BATCHES:
        if seed in FORBIDDEN_SEEDS:
            raise SystemExit('seed %d belongs to A, the B pilot must not reuse it' % seed)
        out = fresh_dataset_dir(tag)
        report_dir = REPORTS / out.name
        args = ['batch', '--samples', SAMPLES, '--profile', profile_path, '--out', out,
                '--seed', seed, '--replicates', REPLICATES, '--split-seed', SPLIT_SEED,
                '--closure', 'strict', '--legacy-al', 'reject', '--targets',
                *list(TARGET_ELEMENTS), '--design-ranges', DESIGN_RANGES]
        done = cli(sys.executable, args, GEN, report_dir / ('generate_%s.log' % tag))
        entry = {'id': out.name, 'condition': tag,
                 'dataset': str(out.relative_to(ROOT).as_posix()),
                 'profile_file': str(profile_path.relative_to(ROOT).as_posix()),
                 'profile_sha256': sha256_bytes(profile_path),
                 'samples_file': str(SAMPLES.relative_to(ROOT).as_posix()),
                 'samples_sha256': sha256_bytes(SAMPLES),
                 'design_ranges_sha256': sha256_bytes(DESIGN_RANGES),
                 'seed': seed, 'replicates': REPLICATES, 'split_seed': SPLIT_SEED,
                 'closure': 'strict', 'legacy_al': 'reject', 'jitter': None,
                 'targets_count': len(TARGET_ELEMENTS),
                 'command': 'python -B app.py ' + ' '.join(str(a) for a in args),
                 'working_directory': str(GEN),
                 'thread_env_pinned': {name: '1' for name in THREAD_ENV},
                 'generation_exit_code': done.returncode,
                 'generation_log': str((report_dir / ('generate_%s.log' % tag))
                                       .relative_to(ROOT).as_posix()),
                 'status': 'generated' if done.returncode == 0 else 'failed_partial'}
        if done.returncode != 0:
            entry['failure_stderr_tail'] = done.stderr[-1500:]
            print(json.dumps(entry, ensure_ascii=False))
            ledger['batches'].append(entry)
            save_ledger(ledger, [entry['id']])
            raise SystemExit('generation failed for %s, see %s' % (out.name, entry['generation_log']))
        manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
        entry.update({
            'spectrum_count': manifest['spectrum_count'],
            'family_count': manifest['family_count'],
            'manifest_status': manifest['status'],
            'manifest_acceptance_status': manifest['acceptance_status'],
            'manifest_jitter_ranges': manifest['jitter_ranges'],
            'manifest_closure': manifest['closure'],
            'manifest_legacy_al': manifest['legacy_al'],
            'manifest_split_rule': manifest['split_rule'],
            'manifest_split_counts': {},
            'source_samples_semantic_sha256': manifest['source_samples_semantic_sha256'],
            'physics_core_sha256': manifest['physics_core_sha256'],
            'software_version': manifest['software_version'],
            'physical_model_version': manifest['physical_model_version'],
            'window_loss_fraction_manifest': manifest['window_loss_fraction'],
            'ba_window_summary': manifest['ba_window_summary'],
            'manifest_warnings_count': len(manifest['warnings']),
            'environment': str((out / 'reproducibility' / 'environment.json')
                               .relative_to(ROOT).as_posix()),
            'sealed_generator_app_sha256': sha256_bytes(
                out / 'reproducibility' / 'generator' / 'fp_competition' / 'app.py'),
            'external_core_sha256': sha256_bytes(GEN / 'core.py')})
        for record in manifest['records']:
            entry['manifest_split_counts'][record['split']] = \
                entry['manifest_split_counts'].get(record['split'], 0) + 1
        print(json.dumps({'batch': entry['id'], 'spectra': entry['spectrum_count'],
                          'families': entry['family_count'],
                          'splits': entry['manifest_split_counts']}, ensure_ascii=False))
        ledger['batches'].append(entry)
        save_ledger(ledger, [entry['id']])


# ------------------------------------------------------------------ verify
# The lines member B designs an experiment around. Fe KL3 is the matrix anchor that must be modeled
# in every spectrum, the other four are the designed overlap partners of the interference families.
# xraylib line labels are used verbatim in full_results ('KL3_LINE', 'L3M5_LINE', 'M5N6_LINE').
KEY_LINES = frozenset({('Fe', 'KL3_LINE'), ('As', 'KL3_LINE'), ('S', 'KL3_LINE'),
                       ('Pb', 'L3M5_LINE'), ('Pb', 'M5N6_LINE')})


def phase_verify(ledger, batch_id=None):
    for entry in find_batch(ledger, batch_id):
        dataset = ROOT / entry['dataset']
        condition_file = B_DIR / ('%s_candidate.json' % entry['condition'])
        candidate = json.loads(condition_file.read_text(encoding='utf-8'))
        candidate_window = delivered_energy_window(candidate)
        # The same delivered factors core.simulate() uses (core.py:379 then core.py:365), so the line
        # strengths below are expected net counts, not the solver's pre-scaling intermediates.
        profile_obj = Profile.from_dict(candidate)
        profile_obj.validate()
        geometric_scale = (profile_obj.incident_photons_s * profile_obj.live_time_s
                           * profile_obj.current_uA / profile_obj.reference_current_uA
                           * profile_obj.solid_angle / (4.0 * math.pi))
        response_cache = {}

        def expected_detected_counts(emitted, energy):
            if energy not in response_cache:
                response_cache[energy] = float(
                    detector_efficiency(profile_obj, [energy])[0]
                    * air_transmission(profile_obj, [energy], profile_obj.exit_air_path_cm)[0])
            return emitted * geometric_scale * response_cache[energy]
        truth = {}
        for line in (dataset / 'truth.jsonl').read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            truth[row['id']] = row
        problems = []
        per_recipe = {}
        component_check = []
        losses = []
        coverage = {}
        statuses = {}
        support_extras = {}
        support_target_histogram = {}
        line_groups = {}
        sample_warnings = None
        for record_id, row in sorted(truth.items()):
            full = json.loads((dataset / 'full_results' / ('%s.json' % record_id))
                              .read_text(encoding='utf-8'))
            if sample_warnings is None:
                sample_warnings = list(full['warnings'])
            key = row['original_sample_id']
            per_recipe.setdefault(key, []).append(record_id)
            if full['profile'] != candidate:
                problems.append('%s profile differs from %s' % (record_id, condition_file.name))
            if full['energy_window'] != candidate_window:
                problems.append('%s energy window %s != %s delivered from the candidate'
                                % (record_id, full['energy_window'], candidate_window))
            comps = full['components_expected_counts']
            if sorted(comps) != sorted(SIX_COMPONENTS):
                problems.append('%s components are %s' % (record_id, sorted(comps)))
            in_window = sum(sum(v) for v in comps.values())
            outside = sum(full['outside_window_counts'].values())
            detected = float(full['detected_signal_before_window_counts'])
            expected = sum(full['expected_counts'])
            if detected <= 0:
                problems.append('%s detected signal before the window is %.6f' % (record_id, detected))
            elif abs(in_window + outside - detected) > 1e-6 * detected:
                problems.append('%s six-component identity broken: %.6f + %.6f != %.6f'
                                % (record_id, in_window, outside, detected))
            if abs(in_window - expected) > 1e-6 * max(expected, 1):
                problems.append('%s component sum != expected_counts sum (%.6f vs %.6f)'
                                % (record_id, in_window, expected))
            if expected > 0:
                row_loss = outside / detected
                component_check.append({'id': record_id, 'in_window_component_counts': in_window,
                                       'outside_window_counts': outside,
                                       'outside_by_component': dict(full['outside_window_counts']),
                                       'detected_before_window': detected,
                                       'window_loss_fraction': row_loss})
                losses.append(row_loss)
            used = full['composition']['used_percent']
            total_percent = sum(used.values())
            if abs(total_percent - 100.0) > 1e-6:
                problems.append('%s used percent sums to %.8f' % (record_id, total_percent))
            # the sealed truth row lists all 32 targets explicitly, zeros included
            for symbol, percent in row['targets_percent'].items():
                value = float(percent)
                cell = coverage.setdefault(symbol, {'spectra': 0, 'positive': 0,
                                                    'exact_zero': 0, 'low_le_0p1': 0,
                                                    'min_positive_percent': None,
                                                    'max_positive_percent': None})
                cell['spectra'] += 1
                if value > 0:
                    cell['positive'] += 1
                    if value <= 0.1:
                        cell['low_le_0p1'] += 1
                    cell['min_positive_percent'] = (value if cell['min_positive_percent'] is None
                                                    else min(cell['min_positive_percent'], value))
                    cell['max_positive_percent'] = (value if cell['max_positive_percent'] is None
                                                    else max(cell['max_positive_percent'], value))
                else:
                    cell['exact_zero'] += 1
            # line systems actually modeled in this spectrum, grouped by interference pair
            detail = full['source_provenance'].get('design_detail') or {}
            pair = '/'.join(detail.get('candidate_pair', [])) or 'not-an-interference-family'
            scenario = full['source_provenance'].get('scenario', 'unknown')
            group = line_groups.setdefault('%s | %s' % (scenario, pair),
                                           {'scenario': scenario, 'candidate_pair': pair,
                                            'spectra': 0, 'elements_present': {}, 'lines': {}})
            group['spectra'] += 1
            for symbol in ('Fe', 'As', 'S', 'Pb'):
                if float(used.get(symbol, 0.0)) > 0:
                    group['elements_present'][symbol] = \
                        group['elements_present'].get(symbol, 0) + 1
            modeled = {}
            for line_entry in full['lines']:
                ident = (line_entry['element'], line_entry['line'])
                if ident not in KEY_LINES:
                    continue
                emitted = float(line_entry['primary_emitted']) + float(
                    line_entry['secondary_emitted'])
                modeled[ident] = {
                    'energy_keV': line_entry['energy_keV'],
                    'channel': round((line_entry['energy_keV'] - candidate['zero_keV'])
                                     / candidate['gain_keV_channel'], 2),
                    'in_window': bool(candidate_window['lower_edge'] <= line_entry['energy_keV']
                                      <= candidate_window['upper_edge']),
                    'expected_detected_counts': expected_detected_counts(
                        emitted, line_entry['energy_keV'])}
            for ident in sorted(KEY_LINES):
                name = '%s %s' % ident
                cell = group['lines'].setdefault(name, {'modeled_in_spectra': 0,
                                                        'in_window_in_spectra': 0,
                                                        'energy_keV': None,
                                                        'channel': None,
                                                        'max_expected_detected_counts': 0.0})
                found = modeled.get(ident)
                if found is not None:
                    cell['modeled_in_spectra'] += 1
                    cell['in_window_in_spectra'] += int(found['in_window'])
                    cell['energy_keV'] = found['energy_keV']
                    cell['channel'] = found['channel']
                    cell['max_expected_detected_counts'] = max(
                        cell['max_expected_detected_counts'], found['expected_detected_counts'])
            if float(used.get('Fe', 0.0)) > 0 and ('Fe', 'KL3_LINE') not in modeled:
                problems.append('%s has Fe in the matrix but no modeled Fe KL3_LINE' % record_id)
            support = full['element_support']['elements']
            # core.py:406 builds the table as original_percent keys minus {Als, Alt} union the
            # modelled weights, so it documents this recipe's elements, not all 32 targets.
            delivered_support_rule = (set(full['composition']['original_percent']) - {'Als', 'Alt'}
                                      | {symbol for symbol, value in used.items() if value > 0.0})
            if set(support) != delivered_support_rule:
                problems.append('%s support key set does not reproduce the delivered rule, '
                                'symmetric difference %s'
                                % (record_id, sorted(set(support) ^ delivered_support_rule)))
            uncovered = sorted(symbol for symbol in TARGET_ELEMENTS
                               if float(used.get(symbol, 0.0)) > 0.0 and symbol not in support)
            if uncovered:
                problems.append('%s support is missing target(s) carrying positive mass %s'
                                % (record_id, uncovered))
            covered = sum(1 for symbol in TARGET_ELEMENTS if symbol in support)
            support_target_histogram[covered] = support_target_histogram.get(covered, 0) + 1
            for symbol in sorted(set(support) - set(TARGET_ELEMENTS)):
                support_extras[symbol] = support_extras.get(symbol, 0) + 1
            for symbol, row2 in support.items():
                statuses.setdefault(symbol, {}).setdefault(row2['status'], 0)
                statuses[symbol][row2['status']] += 1
        replicate_rows = []
        for key, ids in sorted(per_recipe.items()):
            if len(ids) != REPLICATES:
                problems.append('recipe %s has %d spectra, expected %d' % (key, len(ids), REPLICATES))
                continue
            arrays = [json.loads((dataset / 'full_results' / ('%s.json' % i)).read_text(
                encoding='utf-8')) for i in ids]
            same_composition = all(a['composition'] == arrays[0]['composition'] for a in arrays)
            same_profile = all(a['profile'] == arrays[0]['profile'] for a in arrays)
            same_axis = all(a['energy_keV'] == arrays[0]['energy_keV'] for a in arrays)
            same_expected = all(a['expected_counts'] == arrays[0]['expected_counts'] for a in arrays)
            same_components = all(a['components_expected_counts'] == arrays[0]['components_expected_counts']
                                  for a in arrays)
            counts_differ = any(a['counts'] != arrays[0]['counts'] for a in arrays)
            seeds_distinct = len({a['seed'] for a in arrays}) == len(arrays)
            total_counts = [sum(a['counts']) for a in arrays]
            row = {'original_sample_id': key, 'record_ids': ids,
                   'composition_identical': same_composition,
                   'profile_identical': same_profile,
                   'energy_axis_identical': same_axis,
                   'expected_spectrum_identical': same_expected,
                   'component_spectra_identical': same_components,
                   'observed_counts_differ': counts_differ,
                   'seeds_distinct': seeds_distinct,
                   'observed_totals': total_counts,
                   'max_abs_expected_difference': max(
                       (abs(x - y) for a in arrays[1:]
                        for x, y in zip(a['expected_counts'], arrays[0]['expected_counts'])),
                       default=0.0),
                   'max_abs_counts_difference': max(
                       (abs(x - y) for a in arrays[1:]
                        for x, y in zip(a['counts'], arrays[0]['counts'])), default=0)}
            replicate_rows.append(row)
            for flag in ('composition_identical', 'profile_identical', 'energy_axis_identical',
                         'expected_spectrum_identical', 'component_spectra_identical',
                         'observed_counts_differ', 'seeds_distinct'):
                if not row[flag]:
                    problems.append('%s: replicate check %s failed for recipe %s'
                                    % (entry['id'], flag, key))
        over_budget = [r['id'] for r in component_check
                       if r['window_loss_fraction'] > WINDOW_LOSS_BUDGET]
        outside_share = {}
        for row_item in component_check:
            if row_item['window_loss_fraction'] > WINDOW_LOSS_BUDGET:
                for name, value in row_item['outside_by_component'].items():
                    outside_share[name] = outside_share.get(name, 0.0) + float(value)
        outside_total = sum(outside_share.values())
        budget_finding = None
        if over_budget:
            budget_finding = (
                '%d of %d spectra are above the pre-declared out-of-window budget of %.2f '
                '(measured max %.6f, mean %.6f). Discarded counts on those records by component: %s. '
                'The window is the one the delivered tool derives from the candidate profile, so this '
                'is a property of the condition, not of the recipes or of the solver; the threshold was '
                'declared before the run, so B reports the miss instead of re-drawing it'
                % (len(over_budget), len(truth), WINDOW_LOSS_BUDGET, max(losses),
                   sum(losses) / len(losses),
                   {name: round(100.0 * value / outside_total, 2)
                    for name, value in sorted(outside_share.items(),
                                              key=lambda kv: -float(kv[1]))}
                   if outside_total else {}))
            problems.append(budget_finding)
        # Where the discarded counts can physically sit. The sealed records state that the delivered
        # source grid starts at 1 keV and sub-keV fluorescence is omitted, so a window whose lower edge
        # is below 1 keV cannot lose anything at the low end: the whole loss is above the upper edge.
        upper_edge = float(candidate_window['upper_edge'])
        grid_from_1_keV = any('source grid starts at 1 keV' in w for w in (sample_warnings or []))
        loss_side = {
            'lower_edge_keV': float(candidate_window['lower_edge']),
            'upper_edge_keV': upper_edge,
            'tube_voltage_keV': float(candidate['voltage_kV']),
            'delivered_source_grid_starts_at_1_keV': grid_from_1_keV,
            'compton_90deg_threshold_keV': (round(upper_edge / (1.0 - upper_edge / 511.0), 3)
                                            if upper_edge < 511.0 else None),
            'conclusion': (
                'the discarded band is the high-energy side, from %.3f keV to the %.0f keV tube voltage '
                '(unscattered continuum plus its Rayleigh and Compton tail; a photon above %.1f keV '
                'Compton-scattered at 90 degrees still lands above the window). Nothing can sit below '
                'the %.3f keV lower edge because the delivered source grid starts at 1 keV'
                % (upper_edge, float(candidate['voltage_kV']),
                   upper_edge / (1.0 - upper_edge / 511.0), float(candidate_window['lower_edge'])))
            if (grid_from_1_keV and float(candidate_window['lower_edge']) < 1.0
                and upper_edge < float(candidate['voltage_kV']))
            else 'the window spans the whole modeled source range, so the loss needs another origin'}
        report = {
            'batch': entry['id'], 'condition': entry['condition'],
            'purpose': 'workflow pilot verification only, not an accuracy or detection-limit claim',
            'declared_checks': {
                'replicate_identity': 'two spectra of one recipe must share composition, profile, '
                                      'energy axis, the full expected spectrum and the six component '
                                      'spectra, and differ only in Poisson counting noise',
                'six_component_identity': 'sum(components) = sum(expected_counts) and '
                                          'sum(components) + sum(outside_window) = '
                                          'detected_signal_before_window_counts, tolerance 1e-6 '
                                          'relative',
                'window_loss_budget': 'declared before the run: outside/detected <= %.2f per '
                                      'spectrum' % WINDOW_LOSS_BUDGET,
                'profile_matches_candidate_file': 'every sealed profile must equal '
                                                  '%s field for field' % condition_file.name,
                'energy_window_matches_candidate': 'every sealed energy_window must equal the window '
                                                   'the delivered dataset.energy_window() derives '
                                                   'from %s' % condition_file.name,
                'composition_sums_to_100': 'used_percent must sum to 100 within the documented '
                                           'strict tolerance of 1e-6 percentage points',
                'support_table': 'the delivered core.element_support() is called with '
                                'original_percent keys minus {Als, Alt} union the modelled weights '
                                '(core.py:406), so the table documents the elements of this recipe, '
                                'not a fixed 32-target panel. Accepted rule, checked per spectrum: '
                                'the key set must reproduce that call exactly, every target with '
                                'positive used mass must have an entry, and O is counted separately '
                                'as a non-target key.',
                'matrix_line': 'every spectrum with Fe mass must model Fe KL3_LINE'},
            'spectra_checked': len(truth),
            'recipes_checked': len(per_recipe),
            'candidate_energy_window': candidate_window,
            'sealed_windows_all_identical': not any(
                p.endswith('!= delivered from the candidate') for p in problems),
            'replicate_pairs_all_passed': all(r['composition_identical']
                                              and r['expected_spectrum_identical']
                                              and r['observed_counts_differ']
                                              and r['seeds_distinct'] for r in replicate_rows),
            'replicate_rows': replicate_rows,
            'window_loss': {'min': min(losses), 'max': max(losses),
                            'mean': sum(losses) / len(losses),
                            'budget': WINDOW_LOSS_BUDGET,
                            'over_budget_count': len(over_budget),
                            'over_budget_component_share_percent': (
                                {name: round(100.0 * value / outside_total, 3)
                                 for name, value in sorted(outside_share.items(),
                                                           key=lambda kv: -float(kv[1]))}
                                if outside_total else {}),
                            'over_budget_record_ids': over_budget,
                            'loss_side_attribution': loss_side},
            'element_status_counts_per_spectrum': statuses,
            'support_non_target_keys': support_extras,
            'support_target_count_histogram': support_target_histogram,
            'target_coverage': coverage,
            'line_system_check': {
                'meaning': 'per scenario/interference-pair group: how many of the 200 spectra model '
                           'each watched line, how many of those place it inside the recorded '
                           'window, and the largest expected net detected counts that line reaches in '
                           'that group. Modeled counts are bounded by how many spectra actually '
                           'contain the element, listed in elements_present. Line existence is not '
                           'resolvability, and a modeled line with a small net count is not '
                           'detectability either.',
                'expected_detected_counts': 'primary_emitted + secondary_emitted, multiplied by the '
                                            'same factors core.simulate() applies '
                                            '(incident_photons_s * live_time_s * current_uA / '
                                            'reference_current_uA * solid_angle / 4pi, then '
                                            'detector_efficiency * exit-air transmission), so the '
                                            'number is an expected net count over the whole live time',
                'geometry_multiplier': geometric_scale,
                'watched_lines': ['%s %s' % ident for ident in sorted(KEY_LINES)],
                'groups': line_groups},
            'problems': problems,
            'integrity_problems': [p for p in problems if p != budget_finding],
            'declared_budget_finding': budget_finding,
            'status': 'passed' if not problems and len(truth) == 200 else 'failed'}
        out_path = fresh_file(REPORTS / entry['id'] / 'verification.json')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        entry['verification'] = {'report': str(out_path.relative_to(ROOT).as_posix()),
                                 'status': report['status'], 'problems': problems,
                                 'spectra_checked': report['spectra_checked'],
                                 'window_loss_max': report['window_loss']['max'],
                                 'replicate_pairs_all_passed':
                                     report['replicate_pairs_all_passed'],
                                 'pairs': {group: {line_name: cell['modeled_in_spectra']
                                                   for line_name, cell in
                                                   data['lines'].items()}
                                           for group, data in line_groups.items()
                                           if data['scenario'] == 'interference'}}
        save_ledger(ledger, [entry['id']])
        print(json.dumps({'batch': entry['id'], 'status': report['status'],
                          'problems': len(problems), 'window_loss_max':
                          round(report['window_loss']['max'], 6),
                          'replicate_pairs_all_passed':
                              report['replicate_pairs_all_passed'],
                          'problem_sample': problems[:5]}, ensure_ascii=False))


# ------------------------------------------------------------------ audit
def phase_audit(ledger, batch_id=None):
    for entry in find_batch(ledger, batch_id):
        dataset = ROOT / entry['dataset']
        report_dir = REPORTS / entry['id']
        out_path = fresh_file(report_dir / 'audit.json')
        done = cli(sys.executable, ['audit', '--dataset', dataset, '--out', out_path], GEN,
                   out_path.with_suffix('.log'))
        entry['audit'] = {'exit_code': done.returncode,
                          'report': str(out_path.relative_to(ROOT).as_posix()),
                          'report_outside_sealed_dataset': not out_path.is_relative_to(dataset),
                          'log': str(out_path.with_suffix('.log').relative_to(ROOT).as_posix())}
        if done.returncode in (0, 2) and out_path.exists():
            report = json.loads(out_path.read_text(encoding='utf-8'))
            entry['audit'].update(report)
        save_ledger(ledger, [entry['id']])
        print(json.dumps({'batch': entry['id'], 'audit_exit': done.returncode,
                          'audit': entry['audit'].get('status'),
                          'audit_errors': entry['audit'].get('errors')}, ensure_ascii=False))


# ------------------------------------------------------------------ replay + pack
def phase_replay_pack(ledger, batch_id=None):
    for entry in find_batch(ledger, batch_id):
        dataset = ROOT / entry['dataset']
        sealed_app = dataset / 'reproducibility' / 'generator' / 'fp_competition' / 'app.py'
        if not sealed_app.exists():
            raise SystemExit('sealed generator copy missing for %s' % entry['id'])
        report_dir = REPORTS / entry['id']
        replay_path = fresh_file(report_dir / 'replay.json')
        done = cli(sys.executable, ['replay', '--dataset', dataset, '--out', replay_path],
                   sealed_app.parent, replay_path.with_suffix('.log'))
        entry['replay'] = {'exit_code': done.returncode,
                           'executed_with': str(sealed_app.relative_to(ROOT).as_posix()),
                           'executed_with_sha256': sha256_bytes(sealed_app),
                           'working_directory': str(sealed_app.parent),
                           'limit': None,
                           'report': str(replay_path.relative_to(ROOT).as_posix()),
                           'log': str(replay_path.with_suffix('.log').relative_to(ROOT).as_posix())}
        if done.returncode in (0, 2) and replay_path.exists():
            entry['replay'].update(json.loads(replay_path.read_text(encoding='utf-8')))
        pack_path = fresh_file(dataset.parent / (entry['id'] + '_pack.zip'))
        done = cli(sys.executable, ['pack', '--dataset', dataset, '--out', pack_path], GEN,
                   report_dir / (pack_path.stem + '.log'))
        zip_sha = sha256_bytes(pack_path)
        (pack_path.parent / (pack_path.name + '.sha256')).write_text(
            '%s  %s\n' % (zip_sha, pack_path.name), encoding='utf-8')
        with zipfile.ZipFile(pack_path) as archive:
            bad = archive.testzip()
            members = len(archive.namelist())
        entry['pack'] = {'exit_code': done.returncode,
                         'zip': str(pack_path.relative_to(ROOT).as_posix()),
                         'zip_sha256': zip_sha,
                         'zip_sha256_sidecar': str((pack_path.parent / (pack_path.name + '.sha256'))
                                                   .relative_to(ROOT).as_posix()),
                         'zip_member_count': members,
                         'zip_crc_test': 'passed' if bad is None else 'failed:%s' % bad,
                         'log': str((report_dir / (pack_path.stem + '.log'))
                                    .relative_to(ROOT).as_posix()),
                         'meaning': 'pack is a QC/archiving step, not a physics replay'}
        save_ledger(ledger, [entry['id']])
        print(json.dumps({'batch': entry['id'], 'replay_status': entry['replay'].get('status'),
                          'same_environment': entry['replay'].get('same_environment'),
                          'max_abs_diff': entry['replay'].get('maximum_absolute_array_difference'),
                          'pack_crc': entry['pack']['zip_crc_test'],
                          'zip_sha256': zip_sha[:16]}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', default='all',
                        choices=['generate', 'verify', 'audit', 'replay_pack', 'all'])
    parser.add_argument('--batch')
    args = parser.parse_args()
    ledger = load_ledger()
    if args.phase in ('generate', 'all'):
        phase_generate(ledger)
    if args.phase in ('verify', 'all'):
        phase_verify(ledger, args.batch)
    if args.phase in ('audit', 'all'):
        phase_audit(ledger, args.batch)
    if args.phase in ('replay_pack', 'all'):
        phase_replay_pack(ledger, args.batch)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
