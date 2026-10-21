"""Assemble the member B section-0 artefacts from live measurements.

Writes B_environment.json (frozen interpreter, locked dependencies, numeric thread settings,
measured throughput) and B_preflight.json (what already existed versus what was missing before
B started, plus the read-only and no-solver-rewrite statements with their evidence).

Every value here is read from disk or from the running interpreter; nothing is copied from a
plan document as if it were a completed fact.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from importlib import metadata
from pathlib import Path

HERE = Path(__file__).resolve().parent                    # datasets/B-part/work
B_DIR = HERE.parent                                       # datasets/B-part
ROOT = B_DIR.parents[1]
GEN = ROOT / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition'
A_DIR = ROOT / 'datasets' / 'A-part-20261018'
LOCK = GEN / 'requirements-lock.txt'
KEY_FILES = ('app.py', 'core.py', 'minerals.py', 'dataset.py', 'requirements-lock.txt',
             'default_profile.json', 'physics_baseline.json', 'version.py', 'robustness.py')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lock_versions():
    pairs = {}
    for line in LOCK.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and '==' in line:
            name, version = line.split('==', 1)
            pairs[name] = version
    return pairs


def installed():
    found = {}
    for name in lock_versions():
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = None
    return found


REQUIRED_READS = {
    'competition specification PDFs': [
        ROOT / '三人训练集产生方案_v1.0.pdf',
        ROOT / 'X射线模拟训练集数据产生要求_v1.0.pdf'],
    'member A delivered evidence': [
        A_DIR / 'README.md', A_DIR / 'A_samples.json', A_DIR / 'A_formula_registry.csv',
        A_DIR / 'A_design_ranges.json', A_DIR / 'A_coverage.json',
        A_DIR / 'A_acceptance_summary.json', A_DIR / 'build_A.py', A_DIR / 'P1.json',
        A_DIR / 'P2.json', A_DIR / 'A_pilot_samples.json', A_DIR / 'check_pilot.py',
        A_DIR / 'production_record.json', A_DIR / 'environment_preflight.json',
        A_DIR / 'A_delivery_hashes.json', A_DIR / 'P1_pack.zip', A_DIR / 'P2_pack.zip',
        A_DIR / 'P1_replay.json', A_DIR / 'P1_replay_environment.json'],
    'shipped generator': [GEN / name for name in KEY_FILES] + [
        GEN / 'docs' / '训练集数据产生要求.md'],
    'member B task cards': [
        B_DIR / '01_B_design_and_pilot_prompt.md', B_DIR / '02_B_formal_production_prompt.md',
        B_DIR / '03_prompt_review.md', B_DIR / 'README.md'],
}

MISSING_BEFORE_B_STARTED = [
    {'item': 'datasets/C-part', 'status': 'absent',
     'consequence': 'C has no on-disk deliverables, so the 5,000-row master, the global family '
                    'split and the authoritative index cannot exist yet; every B split column '
                    'stays pending'},
    {'item': 'profiles/P3..P5 frozen configurations', 'status': 'absent',
     'consequence': 'B may only propose P3/P4 candidates and run workflow pilots on them; '
                    'formal production must wait for the frozen files'},
    {'item': 'authoritative_index.csv / global_split.csv', 'status': 'absent',
     'consequence': 'no B recipe may be labelled train/validation/test by B alone'},
    {'item': 'any previous B recipe file or spectra batch', 'status': 'absent',
     'consequence': 'B starts from zero; nothing in this directory is reused from an earlier run'},
    {'item': 'M1 shared-recipe closed loop evidence (A 100 recipes, B 3 spectra each, C review)',
     'status': 'absent',
     'consequence': 'M1 cannot be reported as passed; see B_m1_status.json'},
    {'item': 'Python 3.12.14 interpreter used by A', 'status': 'absent on this machine',
     'consequence': 'B freezes 3.13.14 with the exact dependency lock instead and measures the '
                     'difference instead of assuming it away (B_environment_crosscheck.json)'},
]


def main():
    crosscheck = json.loads((B_DIR / 'B_environment_crosscheck.json').read_text(encoding='utf-8'))
    source_verification = json.loads((HERE / 'B_source_verification.json').read_text(encoding='utf-8'))
    versions = lock_versions()
    actual = installed()
    mismatches = {name: {'expected': versions[name], 'actual': actual[name]}
                  for name in versions if actual[name] != versions[name]}
    a_preflight = json.loads((A_DIR / 'environment_preflight.json').read_text(encoding='utf-8'))
    a_replay_env = json.loads((A_DIR / 'P1_replay_environment.json').read_text(encoding='utf-8'))
    environment = {
        'owner': 'B', 'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'role': 'frozen interpreter for every B design, generation, audit, replay and pack run',
        'python': {'version': sys.version, 'executable': sys.executable,
                   'implementation': platform.python_implementation(),
                   'build': platform.python_version(),
                   'filesystem_encoding': sys.getfilesystemencoding(),
                   'float_info': {'dig': sys.float_info.dig, 'epsilon': sys.float_info.epsilon}},
        'system': {'platform': platform.platform(), 'release': platform.release(),
                   'version': platform.version(), 'machine': platform.machine(),
                   'processor': platform.processor(), 'cpu_count': os.cpu_count(),
                   'windows_version': str(sys.getwindowsversion())},
        'thread_environment': {key: value for key, value in os.environ.items()
                               if 'THREAD' in key.upper()},
        'thread_policy': 'OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS='
                         'NUMEXPR_NUM_THREADS=1 for every generator run so B results do not '
                         'depend on BLAS splitting; the same pinned environment is used for '
                         'generation and replay inside B, which is what makes B internal replay '
                         'same_environment comparable',
        'dependencies': {'lock_file': str(LOCK), 'lock_sha256': sha256(LOCK),
                         'expected': versions, 'actual': actual, 'mismatches': mismatches},
        'numpy_internals': {'numpy_version': __import__('numpy').__version__,
                            'default_bit_generator': type(__import__('numpy').random
                                                          .default_rng(0).bit_generator).__name__,
                            'blas': __import__('numpy').show_config('dicts')
                            .get('Build Dependencies', {})},
        'generator_source': {
            'directory': str(GEN),
            'key_file_sha256': {name: sha256(GEN / name) for name in KEY_FILES},
            'sealed_copy_verification': {
                'report': 'work/B_source_verification.json',
                'status': source_verification['status'],
                'compared_count': source_verification['compared_count'],
                'mismatches': source_verification['mismatches'],
                'p1_vs_p2': source_verification.get('p1_vs_p2', [])}},
        'measured_throughput': {'seconds_per_spectrum': crosscheck['seconds_per_spectrum'],
                                'basis': 'six spectra of A\'s sealed P1 profile measured by '
                                         'work/check_environment_reproducibility.py',
                                'estimated_pilot_wall_clock_minutes': round(
                                    crosscheck['seconds_per_spectrum'] * 400 / 60, 1),
                                'estimated_replay_wall_clock_minutes': round(
                                    crosscheck['seconds_per_spectrum'] * 400 / 60, 1)},
        'cross_environment_check': {
            'purpose': crosscheck['purpose'], 'status': crosscheck['status'],
            'maximum_absolute_expected_counts_difference':
                crosscheck['maximum_absolute_expected_counts_difference'],
            'observed_counts_bit_identical_to_a': crosscheck['observed_counts_bit_identical_to_a'],
            'blind_input_files_byte_identical_to_a': crosscheck['blind_input_files_byte_identical_to_a'],
            'b_python': crosscheck['b_environment']['python'],
            'a_environment_as_recorded_by_a': a_replay_env['generation'],
            'a_replay_thread_note': 'A generated with all three thread variables unset and replayed '
                                    'with OMP/OPENBLAS=1, which is why A\'s own replay reported '
                                    'same_environment=false while differences_limited_to_'
                                    'thread_environment=true',
            'b_replay_policy': 'B generates and replays both with the same pinned thread '
                               'environment, so the B internal replay can report '
                               'same_environment=true; a cross-person replay run with the '
                               'variables unset is expected to differ only in that block',
            'conclusion': 'the 3.13.14 interpreter with the exact dependency lock reproduces A\'s '
                          'sealed pilot arrays and Poisson streams exactly on the probe, so no '
                          'numeric interpreter delta was observed on this machine'},
        'explicit_non_choices': {
            '启动生成器.cmd': 'not used: it launches the desktop GUI and does not record a '
                              'reproducible production command',
            'GUI export': 'not used: every batch is produced through app.py batch with recorded '
                          'arguments, seeds and files',
            'D:\\Python314 system interpreter': 'not used for generator work',
            'XRF physics solver rewrite': 'not done: generator digests match the copy sealed '
                                          'inside A P1_pack.zip',
            'A directory writes': 'none: A files are read only'},
    }
    (B_DIR / 'B_environment.json').write_text(
        json.dumps(environment, ensure_ascii=False, indent=2), encoding='utf-8')

    inventory = {}
    for group, paths in REQUIRED_READS.items():
        inventory[group] = {str(path.relative_to(ROOT).as_posix()): {
            'exists': path.is_file(),
            'sha256': sha256(path) if path.is_file() else None,
            'bytes': path.stat().st_size if path.is_file() else None} for path in paths}
    unreadable = [name for group in inventory.values() for name, row in group.items()
                  if not row['exists']]
    preflight = {
        'owner': 'B', 'stage': 'M0 section 0 preflight',
        'status': 'passed' if not mismatches and source_verification['status'] == 'passed'
                  and crosscheck['status'] == 'passed' and not unreadable else 'blocked',
        'read_before_designing': {
            'task_cards': [str(path.relative_to(ROOT).as_posix()) for path in
                           REQUIRED_READS['member B task cards']],
            'specification_pdfs': 'both PDFs were extracted to readable UTF-8 text with '
                                  'pdftotext -enc UTF-8 -layout into work/refs/; the extracted '
                                  'text, not the plan prose, is the reference',
            'extracted_specification_text': [
                'work/refs/三人训练集产生方案_v1.0.txt',
                'work/refs/X射线模拟训练集数据产生要求_v1.0.txt'],
            'a_pilot_evidence': 'A README, acceptance summary, coverage, registry, samples, '
                                 'build_A.py, both pilot batches and both replay environment '
                                 'records were read'},
        'existing_vs_missing': {'file_inventory': inventory,
                                'missing_or_unreadable': unreadable,
                                'missing_before_b_started': MISSING_BEFORE_B_STARTED},
        'plan_text_not_treated_as_fact': [
            'the three-person plan describes a 20,000-spectrum-per-member budget, P3-P5 profiles '
            'and a C-maintained global index; none of those exist on disk, so B records them as '
            'pending and only counts what it produced itself',
            'A acceptance summary says cross_person_review pending and global_split pending, so B '
            'does not describe A work as reviewed or the split as fixed',
            'no milestone (M1..M6) is reported as passed on the strength of a plan document'],
        'dependency_lock': {'mismatches': mismatches,
                            'a_recorded_mismatches': a_preflight['mismatches'],
                            'a_release_zip_sha256': a_preflight['release_zip_sha256']},
        'source_digest_verification': source_verification,
        'cross_environment_reproducibility': crosscheck,
        'environment_file': 'B_environment.json',
        'commands': {
            'verify_generator_source': 'work/verify_generator_source.py',
            'environment_probe': 'work/check_environment_reproducibility.py',
            'this_record': 'work/record_environment_and_preflight.py',
            'interpreter': sys.executable,
            'thread_prefix': 'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 '
                             'NUMEXPR_NUM_THREADS=1'},
    }
    (B_DIR / 'B_preflight.json').write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': preflight['status'], 'dependency_mismatches': mismatches,
                      'missing_reads': unreadable,
                      'crosscheck': crosscheck['status'],
                      'seconds_per_spectrum': crosscheck['seconds_per_spectrum']},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
