"""C 部分：v2 批次（C-recipes-v2）续跑生成。

与 v1 的 resume_p5_batch.py 同构，只有四处不同：
  - 主配方表：`C_part/v2/master_samples_v2.json`（1000 条已过设计自检与 make_plan 预检）
  - 输出目录：`fp_competition/P5_dataset_v2`（**不触碰 v1 的 P5_dataset**）
  - 批次种子 2026110205、划分种子 20261102
  - manifest 多记 batch_version / supersedes，便于追溯它替代哪个失败批次

断点由已写入的 blind_inputs 文件数确定；结束时按磁盘实际文件重建清单，
保证 manifest.records、truth.jsonl 与盲/满结果文件三者一致。
"""
from __future__ import annotations
import json
import os
import sys
from collections import Counter
from pathlib import Path

FP = Path(os.environ.get('FP_COMPETITION',
                         'C:/Users/TianT/Desktop/兴智杯AI/'
                         'fp-spectrum-generator-competition-v0.2.1/fp_competition'))
CHUNK = int(sys.argv[1]) if len(sys.argv) > 1 else 0
SAMPLES = Path(os.environ.get('C_V2_MASTER',
                              'C:/Users/TianT/Desktop/兴智杯AI/C_part/v2/master_samples_v2.json'))
PROFILE = FP / 'profiles/P5.json'
OUT = Path(os.environ.get('C_V2_OUT', str(FP / 'P5_dataset_v2')))
REPLICATES = 2
BATCH_SEED = 2026110205
SPLIT_SEED = 20261102
BATCH_VERSION = 'C-recipes-v2'
SUPERSEDES = 'C-part-20261018 (C-recipes-v1, PR #2 review_failed)'
TARGETS = 'Na Mg Al Si P S Cl K Ca Ti V Cr Mn Fe Co Ni Cu Zn As Se Rb Sr Y Zr Nb Mo Cd Sn Sb Ba W Pb'.split()

sys.path.insert(0, str(FP))
from core import Profile
from app import read_json, read_samples, simulate as _simulate
from dataset import (dataset_readme, energy_window, environment, make_plan, seal,
                     semantic_hash, sha256, write_json)


def simulate(*args, **kwargs):
    result = _simulate(*args, **kwargs)
    result.update(software_version='0.2.1', physical_model_version='0.2.0',
                  energy_window=energy_window(result['profile']))
    return result


def existing_ids():
    blind = OUT / 'blind_inputs'
    if not blind.exists():
        return []
    ids = sorted(p.stem for p in blind.glob('*.json'))
    return [i for i in (int(p[1:]) if p.startswith('S') and p[1:].isdigit() else None for p in ids) if i]


def record_from(identity):
    blind = OUT / ('blind_inputs/' + identity + '.json')
    full = OUT / ('full_results/' + identity + '.json')
    return {'id': identity, 'file': 'blind_inputs/' + identity + '.json',
            'blind_input_sha256': sha256(blind), 'sha256': sha256(blind),
            'full_results': 'full_results/' + identity + '.json',
            'full_results_sha256': sha256(full),
            'family': None, 'split': None}


def main():
    samples = read_json(SAMPLES)['samples']
    profile = Profile.from_dict(read_json(PROFILE))
    jobs, targets, effective_split_seed = make_plan(
        samples, profile, REPLICATES, BATCH_SEED, {}, 'strict', 'reject', TARGETS, SPLIT_SEED)

    done = existing_ids()
    start = done[-1] if done else 0
    todo = jobs[start:]
    if CHUNK:
        todo = todo[:CHUNK]
    print('existing', start, '| generating', len(todo), 'of', len(jobs), flush=True)
    if not todo:
        print('nothing to do')
        return

    if start == 0:
        OUT.mkdir(parents=True, exist_ok=False)
        (OUT / 'blind_inputs').mkdir()
        (OUT / 'full_results').mkdir()
        (OUT / 'inputs').mkdir()
        (OUT / 'configs').mkdir()
        (OUT / 'reproducibility/generator/fp_competition').mkdir(parents=True, exist_ok=True)
        write_json(OUT / 'inputs/samples.json', {'samples': samples})
        write_json(OUT / 'configs/profile.json', json.loads(PROFILE.read_text(encoding='utf-8')))
        write_json(OUT / 'configs/jitter.json', {})
        env = environment()
        write_json(OUT / 'reproducibility/environment.json', env)
    else:
        env = read_json(OUT / 'reproducibility/environment.json')

    truth = (OUT / 'truth.jsonl').open('a' if start else 'w', encoding='utf-8')
    manifest = {
        'schema': 'competition-fp-dataset/0.2', 'software_version': '0.2.1',
        'physical_model_version': '0.2.0', 'synthetic': True, 'hardware_validated': False,
        'status': 'running', 'acceptance_status': 'pending_independent_validation',
        'batch_version': BATCH_VERSION, 'supersedes': SUPERSEDES,
        'source_samples_semantic_sha256': semantic_hash(samples), 'seed': BATCH_SEED,
        'split_seed': effective_split_seed, 'split_seed_defaulted_to_batch': SPLIT_SEED is None,
        'replicates': REPLICATES, 'target_elements': targets,
        'closure': 'strict', 'legacy_al': 'reject', 'jitter_ranges': {},
        'records': [],
        'split_rule': 'Exact used-composition families, seeded ordering, approximately 70/15/15; not a device/matrix holdout',
        'target_label_basis': 'Modeled elemental mass percent; zero is not real-world non-detection',
        'warnings': ['Synthetic only; no real-device calibration or 95%/5% blind accuracy proof',
                     'Jitter and synthetic composition ranges are assumptions, not fitted real-world distributions'],
        'environment': env,
        'physics_core_sha256': sha256(FP / 'core.py'),
        'original_inputs': {'samples': 'inputs/samples.json', 'profile': 'configs/profile.json',
                            'jitter': 'configs/jitter.json'},
        'inputs': {'samples': 'inputs/samples.json', 'profile': 'configs/profile.json',
                   'jitter': 'configs/jitter.json'},
    }
    write_json(OUT / 'manifest.json', manifest)

    total = start + len(todo)
    try:
        for index, (sample, repeat, variant, child, family, split) in enumerate(todo):
            idx = start + index + 1
            result = simulate(sample['composition_percent'], variant, seed=child,
                              closure='strict', legacy_al='reject')
            identity = f'S{idx:06d}'
            result.update(record_id=identity, source_provenance=sample.get('provenance', {}))
            blind = {'axis': 'channel', 'signal_unit': 'counts', 'synthetic': True,
                     'x': result['channel'], 'counts': result['counts']}
            blind_path = OUT / 'blind_inputs' / (identity + '.json')
            full_path = OUT / 'full_results' / (identity + '.json')
            write_json(blind_path, blind)
            write_json(full_path, result)
            truth.write(json.dumps({
                'id': identity, 'original_sample_id': sample['id'], 'family': family,
                'split': split, 'repeat': repeat, 'seed': child, 'profile': result['profile'],
                'composition': result['composition'], 'warnings': result['warnings'],
                'targets_percent': {s: result['composition']['used_percent'].get(s, 0.) for s in targets},
                'source_provenance': result['source_provenance'], 'energy_window': energy_window(variant),
            }, ensure_ascii=False, allow_nan=False) + '\n')
            truth.flush()
            if idx % 25 == 0:
                write_json(OUT / 'manifest.json', manifest)
                print(f'{idx}/{total} total', flush=True)
    except BaseException as exc:
        manifest.update(status='failed_partial', error=str(exc))
        raise
    finally:
        truth.close()
        ids = existing_ids()
        labels = {}
        for line in (OUT / 'truth.jsonl').read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            lab = json.loads(line)
            labels[lab['id']] = lab
        records = []
        for i in ids:
            identity = f'S{i:06d}'
            rec = record_from(identity)
            lab = labels.get(identity, {})
            rec['family'] = lab.get('family')
            rec['split'] = lab.get('split')
            records.append(rec)
        first, last, lower, upper = [], [], [], []
        loss_fractions = []
        ba = Counter()
        for rec in records:
            full = read_json(OUT / rec['full_results'])
            w = full['energy_window']
            first.append(w['first_center']); last.append(w['last_center'])
            lower.append(w['lower_edge']); upper.append(w['upper_edge'])
            total = full['detected_signal_before_window_counts']
            lost = sum(full['outside_window_counts'].values())
            if total > 0:
                loss_fractions.append(lost / total)
            if full['composition']['used_percent'].get('Ba', 0) > 0:
                ba['present'] += 1
                for shell in ('K', 'L', 'M'):
                    if any(line['element'] == 'Ba' and line['line'].startswith(shell)
                           and w['lower_edge'] <= line['energy_keV'] <= w['upper_edge']
                           for line in full['lines']):
                        ba[shell + '_center_in_window'] += 1
        manifest.update(status='complete', spectrum_count=len(records),
                        family_count=len({r['family'] for r in records if r['family']}),
                        records=records,
                        window_summary={
                            'unit': 'keV', 'first_center_range': [min(first), max(first)],
                            'last_center_range': [min(last), max(last)],
                            'lower_edge_range': [min(lower), max(lower)],
                            'upper_edge_range': [min(upper), max(upper)],
                        },
                        ba_window_summary=dict(ba),
                        window_loss_fraction={
                            'definition': 'sum(outside_window_counts) / detected_signal_before_window_counts, excludes artificial background',
                            'range': [min(loss_fractions), max(loss_fractions)] if loss_fractions else None,
                        })
        write_json(OUT / 'manifest.json', manifest)
        seal(OUT)
    print('complete:', manifest['spectrum_count'], 'records', 'families:',
          manifest['family_count'], flush=True)


if __name__ == '__main__':
    main()
