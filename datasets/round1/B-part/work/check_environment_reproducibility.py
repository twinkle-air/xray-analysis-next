"""Cross-environment reproducibility probe: rebuild part of A's sealed P1 pilot here.

Purpose: B's frozen interpreter is Python 3.13.14 while A generated on 3.12.14, so before
spending hours on 400 spectra B measures whether that interpreter delta changes any number.
The probe re-runs the shipped CLI over the first three formulas of A's own sealed pilot input
with A's own sealed profile, then compares the recomputed arrays with A's sealed arrays.

The produced directory is an environment measurement, not a training batch: it is labelled
``environment_reproducibility_check_only`` and must never enter any train/validation/test pool.
A's directory is only read.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # datasets/B-part/work
B_DIR = HERE.parent                                    # datasets/B-part
ROOT = B_DIR.parents[1]
GEN = ROOT / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition'
A_ZIP = ROOT / 'datasets' / 'A-part-20261018' / 'P1_pack.zip'
OUT = HERE / 'envcheck'
PROBE_FORMULAS = 3

sys.path.insert(0, str(GEN.parent))
from fp_competition.core import Profile                 # noqa: E402
import xraylib                                          # noqa: E402


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    started = time.time()
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / 'sealed').mkdir(parents=True)
    with zipfile.ZipFile(A_ZIP) as archive:
        recipe = json.loads(archive.read('reproducibility/recipe.json'))
        profile = json.loads(archive.read('configs/profile.json'))
        samples = json.loads(archive.read('inputs/samples.json'))
    if isinstance(samples, dict):
        samples = samples['samples']
    probe = samples[:PROBE_FORMULAS]
    samples_path = OUT / 'A_first_three_samples.json'
    samples_path.write_text(json.dumps({'samples': probe}, ensure_ascii=False), encoding='utf-8')
    profile_path = OUT / 'A_P1_profile.json'
    profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding='utf-8')

    dataset_dir = OUT / 'dataset_envcheck_v1'
    command = [sys.executable, '-B', 'app.py', 'batch', '--samples', str(samples_path),
               '--profile', str(profile_path), '--out', str(dataset_dir),
               '--seed', str(recipe['seed']), '--replicates', str(recipe['replicates']),
               '--closure', recipe['closure'], '--legacy-al', recipe['legacy_al'],
               '--targets'] + list(recipe['targets'])
    if recipe.get('split_seed') is not None:
        command += ['--split-seed', str(recipe['split_seed'])]
    done = subprocess.run(command, cwd=GEN, capture_output=True, text=True)
    (OUT / 'batch_command.log').write_text(
        'command: ' + ' '.join(command) + '\ncwd: ' + str(GEN) + '\nexit_code: %d\n'
        'thread_environment: %s\nstdout:\n%s\nstderr:\n%s\n'
        % (done.returncode, {k: v for k, v in os.environ.items() if 'THREAD' in k.upper()},
           done.stdout, done.stderr), encoding='utf-8')
    if done.returncode != 0:
        raise RuntimeError('batch failed, see work/envcheck/batch_command.log')

    mine = sorted((dataset_dir / 'full_results').glob('*.json'))
    comparisons, worst_expected, counts_exact, blind_exact = [], 0.0, True, True
    with zipfile.ZipFile(A_ZIP) as archive:
        for path in mine:
            sealed = json.loads(archive.read('full_results/' + path.name))
            local = json.loads(path.read_text(encoding='utf-8'))
            row = {'record': path.name}
            for key in ('expected_counts', 'energy_keV'):
                a = [float(v) for v in sealed[key]]
                b = [float(v) for v in local[key]]
                row[key + '_max_abs_diff'] = max(abs(x - y) for x, y in zip(a, b))
                row[key + '_max_rel_diff'] = max(abs(x - y) / max(abs(x), 1e-30)
                                                 for x, y in zip(a, b))
                if key == 'expected_counts':
                    worst_expected = max(worst_expected, row[key + '_max_abs_diff'])
            row['components_expected_counts_bit_identical'] = all(
                max(abs(x - y) for x, y in zip(sealed['components_expected_counts'][name],
                                               local['components_expected_counts'][name])) == 0.0
                for name in sealed['components_expected_counts'])
            row['counts_identical'] = sealed['counts'] == local['counts']
            row['total_expected_counts'] = float(sum(local['expected_counts']))
            row['total_observed_counts'] = int(sum(local['counts']))
            counts_exact = counts_exact and row['counts_identical']
            sealed_blind = hashlib.sha256(archive.read('blind_inputs/' + path.name)).hexdigest()
            row['blind_input_sha256_matches_a'] = sealed_blind == sha256(
                dataset_dir / 'blind_inputs' / path.name)
            blind_exact = blind_exact and row['blind_input_sha256_matches_a']
            comparisons.append(row)
    manifest = json.loads((dataset_dir / 'manifest.json').read_text(encoding='utf-8'))
    result = {
        'status': 'passed' if counts_exact and blind_exact and worst_expected == 0.0 else
                  'measured_differences',
        'purpose': 'environment_reproducibility_check_only; never a training, validation, tuning '
                   'or test batch and never counted in the 50,000 formal budget',
        'a_sealed_source': {'zip': str(A_ZIP), 'sha256': sha256(A_ZIP),
                            'recipe': recipe, 'profile_name': profile['name']},
        'probe': {'formulas': PROBE_FORMULAS, 'records': len(mine),
                  'sample_ids': [s['id'] for s in probe],
                  'formula_order': 'the first formulas of A\'s own sealed inputs/samples.json, so '
                                   'record numbering and child seeds align with A\'s pack'},
        'b_environment': {
            'python': sys.version,
            'executable': sys.executable,
            'platform': platform.platform(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'cpu_count': os.cpu_count(),
            'thread_environment': {k: v for k, v in os.environ.items() if 'THREAD' in k.upper()},
            'xraylib_version': xraylib.__version__ if hasattr(xraylib, '__version__')
            else xraylib.XraylibVersionString() if hasattr(xraylib, 'XraylibVersionString')
            else 'unknown',
            'numpy_version': __import__('numpy').__version__,
            'profile_validation': asdict_profile()},
        'comparison_rule': 'recomputed with the shipped CLI (app.py batch) using A\'s sealed '
                           'profile, A\'s sealed first formulas, A\'s batch seed, replicate count, '
                           'split seed, closure and legacy-al policy; compared against A\'s sealed '
                           'full_results and blind_inputs byte/array values',
        'records': comparisons,
        'maximum_absolute_expected_counts_difference': worst_expected,
        'observed_counts_bit_identical_to_a': counts_exact,
        'blind_input_files_byte_identical_to_a': blind_exact,
        'local_manifest_software_version': manifest['software_version'],
        'local_manifest_physical_model_version': manifest['physical_model_version'],
        'elapsed_seconds': round(time.time() - started, 3),
        'seconds_per_spectrum': round((time.time() - started) / max(len(mine), 1), 3),
        'interpretation': 'a non-zero maximum_absolute_expected_counts_difference or '
                          'observed_counts_bit_identical_to_a=false means B\'s interpreter cannot '
                          'reproduce A\'s numbers, so A\'s cross-replay of B would not be '
                          'comparable to A\'s own 0.0 baseline and the interpreter choice must be '
                          'revisited before formal production'}
    (B_DIR / 'B_environment_crosscheck.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': result['status'],
                      'records': len(comparisons),
                      'max_expected_diff': worst_expected,
                      'counts_bit_identical': counts_exact,
                      'blind_bytes_identical': blind_exact,
                      'seconds_per_spectrum': result['seconds_per_spectrum']}, indent=2))
    return 0


def asdict_profile():
    import dataclasses
    return {field.name: getattr(Profile.from_dict(json.loads(
        (OUT / 'A_P1_profile.json').read_text(encoding='utf-8'))), field.name)
        for field in dataclasses.fields(Profile)}


if __name__ == '__main__':
    raise SystemExit(main())
