"""启动生成前的可行性预检（不写任何数据，只跑 make_plan 与配方校验）。

目的：确认 v2 主配方表能被 0.2.1 生成器接受（closure=strict、legacy_al=reject），
并给出"精确采用组成族数"这一关键指标——v1 的 1000 行只塌成 944 族（P2-1 的直接证据），
v2 必须是 1000 族；同时记录将要使用的批次种子与谱数预算。
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

FP = Path(os.environ.get('FP_COMPETITION',
                         'C:/Users/TianT/Desktop/兴智杯AI/'
                         'fp-spectrum-generator-competition-v0.2.1/fp_competition'))
sys.path.insert(0, str(FP))
from dataset import make_plan, semantic_hash          # noqa: E402
from core import Profile                              # noqa: E402

C = Path(os.environ.get('C_PART_DIR', str(Path(__file__).resolve().parent.parent)))
BATCH_SEED = 2026110205
SPLIT_SEED = 20261102
REPLICATES = 2


def run(path, label):
    samples = json.loads(Path(path).read_text(encoding='utf-8'))['samples']
    profile = Profile.from_dict(json.loads((FP / 'profiles' / 'P5.json').read_text(encoding='utf-8')))
    jobs, targets, eff = make_plan(samples, profile, REPLICATES, BATCH_SEED, {},
                                   'strict', 'reject', None, SPLIT_SEED)
    fams = {j[4] for j in jobs}
    return {
        'master': Path(path).name,
        'master_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        'label': label, 'formulas': len(samples),
        'spectra': len(jobs), 'exact_composition_families': len(fams),
        'families_equal_formulas': len(fams) == len(samples),
        'target_elements': len(targets), 'targets': sorted(targets),
        'generator_split': dict(Counter(j[5] for j in jobs)),
        'split_seed': eff, 'batch_seed': BATCH_SEED, 'replicates': REPLICATES,
        'closure': 'strict', 'legacy_al': 'reject',
        'samples_semantic_sha256': semantic_hash(samples),
        'profile_name': getattr(profile, 'name', 'P5'), 'profile_sha256_note': 'profiles/P5.json 未改动',
        'accepted': True,
    }


def main():
    out = {}
    v1_master = next(p for p in (C / 'master_samples.json', C / 'C_samples.json') if p.is_file())
    for path, label in [(C / 'v2' / 'master_samples_v2.json', 'C-recipes-v2'),
                        (v1_master, 'C-recipes-v1(review_failed)')]:
        try:
            out[label] = run(path, label)
        except Exception as exc:                        # noqa: BLE001
            out[label] = {'master': Path(path).name, 'accepted': False,
                          'error': f'{type(exc).__name__}: {exc}'}
    out['verdict'] = {
        'v2_accepted': out.get('C-recipes-v2', {}).get('accepted', False),
        'v2_families_equal_formulas': out.get('C-recipes-v2', {}).get('families_equal_formulas'),
        'v1_families': out.get('C-recipes-v1(review_failed)', {}).get('exact_composition_families'),
        'spectra_to_generate': out.get('C-recipes-v2', {}).get('spectra'),
        'generation_status_file': 'v2/generation_status_v2.json',
        'note': '预检只调用 make_plan（纯计划计算），本文件不声明生成进度；'
                '实际进度只读地写在 generation_status_v2.json 里。'}
    (C / 'v2' / 'pregenerate_dryrun.json').write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                                      encoding='utf-8')
    print(json.dumps(out['verdict'], ensure_ascii=False))


if __name__ == '__main__':
    main()
