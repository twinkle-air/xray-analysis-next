"""C 部分：铁基合金主配方表设计。

按《三人训练集产生方案 v1.0》第 2 节，C 负责 1,000 条铁基合金配方：
  - 常规变化 600
  - 稀疏/边界 200
  - 干扰对照 200（50 组 × 5 变体 × 2 档浓度）
同一母配方的对照变体共享 parent_family。
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
MAIN_ELEMENTS = ('Cr', 'Ni', 'Mn', 'Mo', 'Cu', 'Co', 'Si', 'C', 'Al', 'Ti', 'V', 'Nb', 'W')
TRAMP_ELEMENTS = ('Zn', 'Pb', 'As', 'Sb', 'Sn', 'Cd', 'Ba', 'Zr', 'Sr', 'Y', 'Rb', 'Se')
MAIN_RANGES = {'Cr': (0.0, 28.0), 'Ni': (0.0, 25.0), 'Mn': (0.0, 12.0), 'Mo': (0.0, 6.0),
               'Cu': (0.0, 5.0), 'Co': (0.0, 5.0), 'Si': (0.0, 3.0), 'C': (0.0, 0.8),
               'Al': (0.0, 2.0), 'Ti': (0.0, 2.0), 'V': (0.0, 2.0), 'Nb': (0.0, 1.0),
               'W': (0.0, 2.0)}
LOW_TRAMP_MAX = {s: 0.02 for s in TRAMP_ELEMENTS}

PROVENANCE_BASIS = ('C 铁基合金合成设计范围；人为实验设计，不代表实际牌号分布或认证值')


def close_percent(percent):
    """保留 1e-8 个百分点并让 Fe 承担闭合误差；返回总和恰为 100 的 dict。"""
    out = {s: round(float(v), 8) for s, v in percent.items() if abs(float(v)) > 1e-12}
    total = round(sum(out.values()), 8)
    if abs(total - 100.0) > 1e-6:
        out['Fe'] = round(out.get('Fe', 0.0) + 100.0 - total, 8)
    return {s: out.get(s, 0.0) for s in sorted(out) if abs(out.get(s, 0.0)) > 1e-12}


def family_key(percent):
    return hashlib.sha256(
        json.dumps({s: v for s, v in percent.items() if v > 0.0},
                   sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()[:16]


def regular_alloys(count, seed):
    rng = np.random.default_rng(seed)
    samples = []
    attempts = 0
    while len(samples) < count:
        attempts += 1
        if attempts > count * 100 + 5000:
            raise ValueError('Regular ranges yield too few feasible mixtures')
        fe = float(rng.uniform(55.0, 90.0))
        remaining = 100.0 - fe
        ratios = rng.dirichlet(np.ones(len(MAIN_ELEMENTS)))
        main_total = float(rng.uniform(min(5.0, remaining * 0.3),
                                       min(remaining - 1e-9, remaining * 0.85)))
        main = {e: main_total * ratios[i] for i, e in enumerate(MAIN_ELEMENTS)}
        tramp = {e: float(rng.uniform(0.0, LOW_TRAMP_MAX[e])) for e in TRAMP_ELEMENTS}
        if sum(tramp.values()) > remaining * 0.1:
            continue
        percent = close_percent({**main, **tramp, 'Fe': fe})
        if percent['Fe'] < 55.0 or percent['Fe'] > 90.0:
            continue
        samples.append(percent)
    return samples


def sparse_alloys(count, seed):
    """每个适用元素至少 5 个独立零配方和 5 个独立低含量配方。"""
    rng = np.random.default_rng(seed)
    targets = list(MAIN_ELEMENTS) + list(TRAMP_ELEMENTS)[:7]
    targets = [s for s in targets if s != 'Fe']
    samples = []
    for e in targets:
        for k in range(5):
            level = 0.002 if e == 'C' else (0.005 if e == 'Si' else float(rng.uniform(0.001, 0.05)))
            fe = 95.0 - 0.1 * k
            samples.append(close_percent({e: level, 'Fe': fe}))
    for i, e in enumerate(targets):
        for k in range(5):
            filler = TRAMP_ELEMENTS[(i + k) % len(TRAMP_ELEMENTS)]
            fe = 99.9 - 0.001 * (i * 5 + k)
            samples.append(close_percent({'Fe': fe, filler: 0.001 * (i % 7 + 1)}))
    return samples


def interference_groups(seed):
    pairs = [('Cr', 'Mn'), ('Co', 'Ni'), ('Mn', 'Fe'), ('Cr', 'Ni'), ('Fe', 'Co'),
             ('Cu', 'Ni'), ('Mo', 'W'), ('V', 'Nb'), ('Ti', 'Al'), ('As', 'Pb'),
             ('Sb', 'Sn'), ('Zn', 'Cd'), ('Se', 'Ba'), ('Y', 'Zr'), ('Sr', 'Rb'),
             ('Cr', 'Mo'), ('Ni', 'Mn'), ('Co', 'Cu'), ('W', 'Fe'), ('Pb', 'Sb')]
    rng = np.random.default_rng(seed)
    groups = []
    for idx, (a, b) in enumerate(pairs):
        for level, base in ((1, 2.0), (2, 10.0)):
            variants = {
                'only_' + a: {a: base * (1.0 + 0.2 * rng.random())},
                'only_' + b: {b: base * (1.0 + 0.2 * rng.random())},
                'equal': {a: base, b: base},
                'ratio_1_5': {a: base * 0.5, b: base * 2.5},
                'ratio_5_1': {a: base * 2.5, b: base * 0.5},
            }
            family = f'INTERF{idx + 1:03d}_L{level}'
            for name, vals in variants.items():
                fe = max(55.0, 100.0 - sum(vals.values()) - 8.0)
                percent = close_percent({**vals, 'Ni': 8.0, 'Fe': fe})
                groups.append({'family': family, 'pair': f'{a}/{b}',
                               'variant': name, 'percent': percent})
    return groups


def main():
    regular = regular_alloys(600, 2026101801)
    sparse = sparse_alloys(200, 2026101802)
    inter = interference_groups(2026101803)

    samples = []
    for i, percent in enumerate(regular, start=1):
        samples.append({
            'id': f'C{i:04d}',
            'composition_percent': percent,
            'provenance': {
                'basis': PROVENANCE_BASIS,
                'matrix': 'iron-based-alloy',
                'design_scenario': 'regular_variation',
                'design_seed': 2026101801,
                'ranges_percent': {**MAIN_RANGES, 'Fe': (55.0, 90.0),
                                   **{e: (0.0, v) for e, v in LOW_TRAMP_MAX.items()}},
                'parent_family': family_key(percent),
                'notes': ['Fe 为平衡元素，按严格闭合补足至 100%；微量元素为模型假设的夹杂/残余元素。']
            }
        })
    offset = len(regular)
    for i, percent in enumerate(sparse, start=1):
        samples.append({
            'id': f'C{offset + i:04d}',
            'composition_percent': percent,
            'provenance': {
                'basis': PROVENANCE_BASIS,
                'matrix': 'iron-based-alloy',
                'design_scenario': 'sparse_boundary',
                'design_seed': 2026101802,
                'parent_family': family_key(percent),
                'notes': ['精确零与低含量边界配方；Fe 为平衡元素。']
            }
        })
    offset += len(sparse)
    for i, g in enumerate(inter, start=1):
        samples.append({
            'id': f'C{offset + i:04d}',
            'composition_percent': g['percent'],
            'provenance': {
                'basis': PROVENANCE_BASIS,
                'matrix': 'iron-based-alloy',
                'design_scenario': 'interference_control',
                'design_seed': 2026101803,
                'parent_family': g['family'],
                'interference_pair': g['pair'],
                'variant': g['variant'],
                'notes': ['同一母配方的对照变体共享 parent_family，划分时保持同组。']
            }
        })

    out = HERE / 'master_samples.json'
    out.write_text(json.dumps({
        'synthetic_design': True, 'matrix': 'iron-based-alloy', 'designer': 'C',
        'seed': 20261018,
        'scenario_counts': {'regular': len(regular), 'sparse_boundary': len(sparse),
                            'interference_control': len(inter)},
        'samples': samples
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{out}: {len(samples)} samples')


if __name__ == '__main__':
    main()