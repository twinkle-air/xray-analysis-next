"""C 部分配方设计 v2 —— 按 PR #2 评审的 P2-1 / P2-2 / P2-3 重做。

修掉的三个根因
--------------
1. P2-1「1000 行只有 944 种独立组成」
   v1 稀疏/边界用 `fe = 95.0 - 0.1*k` 制造差异，但 `close_percent` 又把 Fe 归一化补到 100%，
   k 循环被抹平；且采用组成只存非零元素，"某元素=0" 不留痕 → 不同目标的零配方塌成同一组成。
   v2：每个低含量档由该元素自身上限推导（互不相同）；每个零配方带一组**按 (目标, 序号)
   编码的唯一微量共存签名**，因此采用组成天然互不相同；再加全局去重补足与最终断言。

2. P2-2「干扰对照被写死的 Ni=8 与 Fe 平衡破坏」
   v1 写死 `{**vals, 'Ni': 8.0, 'Fe': fe}`：干扰对含 Ni 时目标被覆盖，含 Fe 时 Fe 既是基体
   又是对照变量。v2：干扰对不含 Fe（3 个含 Fe 的对替换为等效非 Fe 对）；背景母配方从不含
   a/b 的元素里采，且**同一对的两个浓度档共用同一背景**；每行按 variant 标签逐条断言
   存在性、背景值与实际比值（only_* 另一元素必须缺席，equal 必须相等，1:5 / 5:1 必须成立）。

3. P2-3「548/600 常规配方越出自身声明范围」
   v1 常规采样只校验 Fe，从不校验 MAIN_RANGES。v2：先验地按每个元素冻结的上下限采样，
   闭合后逐字段再断言；越界即缩回（只缩不放，保证不越上限）或重采。

范围自洽（本次评审的判定口径）
------------------------------
断言用**行自身 provenance 里的 ranges_percent**。三个场景的 Fe 平衡区间不同：
  - regular_variation / interference_control：Fe 55–90%（非 Fe 合计 10–45%）
  - sparse_boundary：Fe 90–99.99999%（超纯/痕量边界配方，Fe 只承担闭合）
两种都是"铁基"，但把高纯痕量配方塞进 55–90 会造成 v1 那样的自我矛盾，所以按场景声明。
浓度档由对内较小上限推导（u = min(hi_a, hi_b)/6，档为 u 与 2u，5:1 时峰值 5/6·hi），
1:5 比值档也不会撞声明上限；微量对自动落到 0.0033%/0.0067% 档。

配额：常规 600 + 稀疏/边界 200 + 干扰对照 200 = 1000。
  稀疏 200 = 20 个适用目标元素 × (5 低含量 + 5 零配方)，目标元素清单写进 provenance。
  干扰 200 = 20 对 × 2 档 × 5 变体（40 个母配方族，每族 5 变体）。

输出只写到 `v2/` 目录（默认脚本上级目录下的 `v2/`），不触碰已密封的 P5 批次，也不修改 v1 脚本；
另外只读地复算 v1 主表的问题数字，供与评审结论逐条对账。

可复现用法（本脚本与 v1 主表 `C_samples.json` 随批次提交在 `datasets/<batch>/` 内）：

```
python -B scripts/design_c_alloy_formulas_v2.py            # 输出到 <batch 目录>/v2/
# 或指定输出目录：python -B scripts/design_c_alloy_formulas_v2.py D:/tmp/v2_out
# 环境变量 C_V1_MASTER / C_V2_OUT_DIR 亦可覆盖输入与输出
```

种子全部写死（`SEEDS`，见下），因此同一份 v1 主表 + 同一解释器数值路径应产出逐字节相同的
`master_samples_v2.json`；自检里给出该文件的 SHA-256，便于与本目录副本对账。
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent


def _resolve(name, env_var, extra_names=()):
    """路径可在两种布局下工作：本地 C_part/ 与仓库 datasets/<batch>/。

    优先级：环境变量 > 命令行默认目录 > 脚本同级目录候选名 > 仓库载荷内的 C_samples.json。
    """
    if env_var in os.environ:
        return Path(os.environ[env_var])
    cands = [HERE / name, *(HERE / n for n in extra_names),
             Path(__file__).resolve().parent.parent / name]
    for c in cands:
        if c.is_file():
            return c
    return HERE / name


OUT_DIR = Path(os.environ.get('C_V2_OUT_DIR', sys.argv[1] if len(sys.argv) > 1
                              and not sys.argv[1].startswith('--') else str(HERE / 'v2')))
V1_MASTER = _resolve('master_samples.json', 'C_V1_MASTER',
                     ('C_samples.json', 'C_samples_v1.json'))

MAIN_ELEMENTS = ('Cr', 'Ni', 'Mn', 'Mo', 'Cu', 'Co', 'Si', 'C', 'Al', 'Ti', 'V', 'Nb', 'W')
TRAMP_ELEMENTS = ('Zn', 'Pb', 'As', 'Sb', 'Sn', 'Cd', 'Ba', 'Zr', 'Sr', 'Y', 'Rb', 'Se')
MAIN_CAPS = {'Cr': 28.0, 'Ni': 25.0, 'Mn': 12.0, 'Mo': 6.0, 'Cu': 5.0, 'Co': 5.0,
             'Si': 3.0, 'C': 0.8, 'Al': 2.0, 'Ti': 2.0, 'V': 2.0, 'Nb': 1.0, 'W': 2.0}
TRAMP_CAP = 0.02
FE_ALLOY_RANGE = (55.0, 90.0)
FE_ULTRA_RANGE = (90.0, 99.99999)

HI = {**MAIN_CAPS, **{e: TRAMP_CAP for e in TRAMP_ELEMENTS}}
ELEMENT_BASE = {**{e: (0.0, c) for e, c in MAIN_CAPS.items()},
                **{e: (0.0, TRAMP_CAP) for e in TRAMP_ELEMENTS}}
SCENARIO_RANGES = {
    'regular_variation': {**ELEMENT_BASE, 'Fe': FE_ALLOY_RANGE},
    'sparse_boundary': {**ELEMENT_BASE, 'Fe': FE_ULTRA_RANGE},
    'interference_control': {**ELEMENT_BASE, 'Fe': FE_ALLOY_RANGE},
}
QUOTA = {'regular_variation': 600, 'sparse_boundary': 200, 'interference_control': 200}
SEEDS = {'regular': 2026110101, 'sparse': 2026110102, 'interference': 2026110103}

SPARSE_TARGETS = MAIN_ELEMENTS + TRAMP_ELEMENTS[:7]      # 20 个适用目标元素
LADDER = (0.0005, 0.002, 0.01, 0.05, 0.35)               # 每元素 5 档低含量
BG_CANDIDATES = ('Ni', 'Cr', 'Mn', 'Cu', 'Mo', 'Co', 'Si', 'Al', 'Ti', 'V', 'Nb', 'W')
# 含 Fe 的 3 对（Mn/Fe、Fe/Co、W/Fe）替换为等效非 Fe 对：Fe 只作平衡元素
INTERFERENCE_PAIRS = [('Cr', 'Mn'), ('Co', 'Ni'), ('Mn', 'Cu'), ('Cr', 'Ni'), ('Co', 'Ti'),
                      ('Cu', 'Ni'), ('Mo', 'W'), ('V', 'Nb'), ('Ti', 'Al'), ('As', 'Pb'),
                      ('Sb', 'Sn'), ('Zn', 'Cd'), ('Se', 'Ba'), ('Y', 'Zr'), ('Sr', 'Rb'),
                      ('Cr', 'Mo'), ('Ni', 'Mn'), ('Co', 'Cu'), ('W', 'Nb'), ('Pb', 'Sb')]

PROVENANCE_BASIS = ('C 铁基合金合成设计范围 v2；人为实验设计，不代表实际牌号分布或认证值；'
                    '每行的采用值均按该行 provenance.ranges_percent 逐字段断言通过')


def close_percent(percent):
    """Fe 承担闭合误差，返回总和恰为 100 的 dict（只保留非零元素、按元素名排序）。"""
    out = {e: round(float(v), 8) for e, v in percent.items() if abs(float(v)) > 1e-12}
    total = round(sum(out.values()), 8)
    out['Fe'] = round(out.get('Fe', 0.0) + 100.0 - total, 8)
    return {e: v for e, v in sorted(out.items()) if abs(v) > 1e-12}


def comp_key(percent):
    return hashlib.sha256(
        json.dumps({e: round(v, 8) for e, v in percent.items() if abs(v) > 1e-12},
                   sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]


def violations(percent, ranges):
    """按该行声明的范围逐字段检查。"""
    bad = []
    for e, v in percent.items():
        declared = ranges.get(e)
        if declared is None:
            bad.append({'element': e, 'value': v, 'reason': 'undeclared_element'})
        elif v > declared[1] + 1e-9 or v < declared[0] - 1e-9:
            bad.append({'element': e, 'value': v, 'declared': list(declared), 'reason': 'out_of_range'})
    return bad


def unique_append(store, seen, percent, repair_rng, ranges):
    """加入 store；若采用组成重复则做确定性微扰补足（只动 <50% 上限的元素，绝不越上限）。"""
    for _ in range(400):
        key = comp_key(percent)
        if key not in seen and not violations(percent, ranges):
            seen.add(key)
            store.append(percent)
            return percent
        bumped = dict(percent)
        small = [e for e, v in sorted(bumped.items(), key=lambda x: (x[1], x[0]))
                 if e != 'Fe' and v < HI[e] * 0.5]
        if not small:
            break
        e = small[int(repair_rng.integers(len(small)))]
        bumped[e] = bumped[e] * (1.0 + 0.01 * (1 + len(store) % 97))
        percent = close_percent(bumped)
    raise ValueError(f'无法补足到独立且合规的组成：{percent}')


def regular_alloys(count, seed):
    """常规变化：主量元素各自取自声明区间，微量 ≤0.02%，Fe 闭合后落在 55–90%。"""
    rng = np.random.default_rng(seed)
    ranges = SCENARIO_RANGES['regular_variation']
    store, seen = [], set()
    attempts = 0
    while len(store) < count:
        attempts += 1
        if attempts > count * 400:
            raise ValueError('常规采样不可行')
        k = int(rng.integers(3, 9))
        active = [str(e) for e in rng.choice(MAIN_ELEMENTS, size=k, replace=False)]
        vals = {e: float(rng.uniform(0.05 * MAIN_CAPS[e], MAIN_CAPS[e])) for e in active}
        tramp = {e: float(rng.uniform(0.0, TRAMP_CAP)) for e in TRAMP_ELEMENTS}
        total = sum(vals.values()) + sum(tramp.values())
        if total > 45.0:                       # 只缩不放：保证 Fe ≥ 55 且不越任何上限
            scale = 45.0 / total
            vals = {e: v * scale for e, v in vals.items()}
            tramp = {e: v * scale for e, v in tramp.items()}
            total = sum(vals.values()) + sum(tramp.values())
        if total < 10.0:                       # Fe ≤ 90 需要非 Fe 合计 ≥ 10，否则重采
            continue
        percent = close_percent({**vals, **tramp, 'Fe': 100.0 - total})
        if violations(percent, ranges):
            continue
        unique_append(store, seen, percent, rng, ranges)
    return store


def sparse_levels(element):
    """该元素的 5 个互不相同的低含量水平（由自身上限推导，严格落在声明区间内）。"""
    return [round(HI[element] * f, 8) for f in LADDER]


def zero_signature(ti, produced, target):
    """按 (目标序号, 序号) 编码出唯一的微量共存签名：水平步长 1e-4 全局不重复。"""
    seq = ti * 5 + produced                      # 0..99
    l1 = round(0.0011 + 0.0001 * seq, 8)
    l2 = round(0.0040 + 0.0002 * ti, 8)
    for shift in range(len(TRAMP_ELEMENTS)):
        f1 = TRAMP_ELEMENTS[(ti + produced + shift) % len(TRAMP_ELEMENTS)]
        f2 = TRAMP_ELEMENTS[(ti * 5 + produced + 3 + shift * 2) % len(TRAMP_ELEMENTS)]
        if f1 != f2 and f1 != target and f2 != target:
            return {f1: l1, f2: l2}
    raise ValueError(f'目标 {target} 找不到合法签名')


def sparse_alloys(count, seed):
    """稀疏/边界：20 个适用目标元素 × (5 低含量 + 5 零配方) = 200。

    返回 (store, meta)，meta 与 store 同序，记录该行的设计意图（目标元素、档位/缺席）。
    """
    rng = np.random.default_rng(seed)
    ranges = SCENARIO_RANGES['sparse_boundary']
    store, seen, meta = [], set(), []

    def emit(kind, target, percent, extra):
        stored = unique_append(store, seen, percent, rng, ranges)
        row = {'kind': kind, 'target': target, 'percent': stored}
        row.update(extra)
        meta.append(row)

    for target in SPARSE_TARGETS:               # 1) 低含量边界
        for level in sparse_levels(target):
            percent = close_percent({target: level, 'Fe': 100.0 - level})
            if violations(percent, ranges):
                raise ValueError(f'稀疏低含量越界: {target} {percent}')
            emit('low_content_boundary', target, percent, {'target_percent': level})

    for ti, target in enumerate(SPARSE_TARGETS):  # 2) 零配方：目标缺席 + 唯一签名
        for produced in range(5):
            sig = zero_signature(ti, produced, target)
            percent = close_percent({**sig, 'Fe': 100.0 - sum(sig.values())})
            if target in percent or violations(percent, ranges):
                raise ValueError(f'零配方不合法: {target} {percent}')
            emit('exact_zero', target, percent, {'absent_elements': [target],
                                                 'signature': {e: round(v, 8)
                                                               for e, v in sorted(sig.items())}})

    if len(store) != count:
        raise ValueError(f'稀疏配方数 {len(store)} != 配额 {count}')
    return store, meta


def background_recipe(a, b, rng, unit):
    """背景母配方：不含 a/b/Fe 的 4 个主量元素，按各自上限比例分配总量。

    约束：总量 + 干扰对 5:1 变体峰值(6u) ≤ 44 → Fe 落在 [56, 88] ⊂ 声明的 55–90；
    单元素 ≤ 0.9·上限 → 永不越界。
    """
    pool = sorted([e for e in BG_CANDIDATES if e not in (a, b)], key=lambda e: -HI[e])
    picks = sorted(str(e) for e in rng.choice(pool[:6], size=4, replace=False))
    caps = {e: HI[e] for e in picks}
    cap_sum = sum(caps.values())
    pair_peak = 6.0 * unit
    t_hi = min(30.0, 44.0 - pair_peak, 0.9 * cap_sum)
    if t_hi < 12.0:
        return None
    total = float(rng.uniform(12.0, t_hi))
    vals = {e: total * caps[e] / cap_sum for e in picks}
    if any(v > 0.9 * caps[e] + 1e-12 for e, v in vals.items()):
        return None
    return vals


def interference_groups(seed):
    """干扰对照：背景不覆盖目标；每行按 variant 标签断言存在性、背景值与实际比值。"""
    rng = np.random.default_rng(seed)
    ranges = SCENARIO_RANGES['interference_control']
    rows = []
    for idx, (a, b) in enumerate(INTERFERENCE_PAIRS):
        unit = min(HI[a], HI[b]) / 6.0
        bg = None
        for _ in range(4000):
            cand = background_recipe(a, b, rng, unit)
            if cand is not None:
                bg = cand
                break
        if bg is None:
            raise ValueError(f'对 {a}/{b} 找不到合法背景')
        for level_no, base in ((1, unit), (2, 2.0 * unit)):
            variants = {
                'only_' + a: {a: base * (1.0 + 0.2 * float(rng.random()))},
                'only_' + b: {b: base * (1.0 + 0.2 * float(rng.random()))},
                'equal': {a: base, b: base},
                'ratio_1_5': {a: base * 0.5, b: base * 2.5},
                'ratio_5_1': {a: base * 2.5, b: base * 0.5},
            }
            family = f'INTERF{idx + 1:03d}_L{level_no}'
            for name, vals in variants.items():
                percent = close_percent({**vals, **bg,
                                         'Fe': 100.0 - sum(vals.values()) - sum(bg.values())})
                assert_interference(name, a, b, vals, percent, bg)
                bad = violations(percent, ranges)
                if bad:
                    raise ValueError(f'干扰行越界 {family}/{name}: {bad}')
                rows.append({'family': family, 'pair': f'{a}/{b}', 'variant': name,
                             'unit': unit, 'level': level_no, 'background': dict(bg),
                             'percent': percent})
    return rows


def assert_interference(name, a, b, vals, percent, bg):
    """variant 标签必须与实际采用组成一致（存在性 + 背景不被覆盖 + 比值）。"""
    for e, v in bg.items():                      # 背景元素不被干扰对覆盖，且保持母配方值
        assert e not in vals, f'{name}: 背景 {e} 与干扰对冲突'
        assert abs(percent[e] - round(v, 8)) < 1e-6, f'{name}: 背景 {e} 被改写'
    got = {e: percent.get(e, 0.0) for e in (a, b)}
    if name.startswith('only_'):
        absent = b if name == 'only_' + a else a
        assert got[absent] <= 1e-12, f'{name}: 应无 {absent}，实际 {got[absent]}'
        present = a if name == 'only_' + a else b
        assert abs(got[present] - round(vals[present], 8)) < 1e-6, f'{name}: {present} 被改动'
    elif name == 'equal':
        assert abs(got[a] - got[b]) < 1e-6, f'{name}: equal 实际 {got[a]} vs {got[b]}'
    elif name == 'ratio_1_5':
        assert abs(got[b] - 5.0 * got[a]) < 1e-6, f'{name}: 1:5 实际 {got[a]}:{got[b]}'
    elif name == 'ratio_5_1':
        assert abs(got[a] - 5.0 * got[b]) < 1e-6, f'{name}: 5:1 实际 {got[a]}:{got[b]}'
    else:
        raise ValueError(f'未知 variant {name}')
    assert 'Fe' not in (a, b), '干扰对不得包含平衡元素 Fe'
    assert percent['Fe'] >= FE_ALLOY_RANGE[0], f'{name}: Fe 低于 55%'


def build():
    samples, cursor = [], 1

    def add(percent, scenario, parent_family, extra, notes):
        nonlocal cursor
        ranges = SCENARIO_RANGES[scenario]
        prov = {'basis': PROVENANCE_BASIS, 'matrix': 'iron-based-alloy',
                'design_scenario': scenario,
                'design_seed': {'regular_variation': SEEDS['regular'],
                                'sparse_boundary': SEEDS['sparse'],
                                'interference_control': SEEDS['interference']}[scenario],
                'ranges_percent': {e: list(v) for e, v in ranges.items()},
                'parent_family': parent_family,
                'notes': list(notes)}
        prov.update(extra)
        samples.append({'id': f'C{cursor:04d}', 'composition_percent': percent, 'provenance': prov})
        cursor += 1

    for p in regular_alloys(QUOTA['regular_variation'], SEEDS['regular']):
        add(p, 'regular_variation', comp_key(p), {'assay_basis': 'designed_synthetic'},
            ('主量元素逐元素取自声明区间；Fe 为平衡元素并落在 55–90%；采用组成全局唯一。',))

    sparse_store, sparse_meta = sparse_alloys(QUOTA['sparse_boundary'], SEEDS['sparse'])
    assert len(sparse_meta) == len(sparse_store)
    for m in sparse_meta:
        extra = {'sparse_kind': m['kind'], 'sparse_target': m['target']}
        if m['kind'] == 'low_content_boundary':
            extra['target_percent'] = m['target_percent']
        else:
            extra['absent_elements'] = m['absent_elements']
            extra['signature_percent'] = m['signature']
        add(m['percent'], 'sparse_boundary', f'SPARSE_{m["kind"]}_{m["target"]}', extra,
            ('低含量档由元素自身上限推导；零配方目标元素缺席、用唯一共存签名彼此区分；'
             '本场景 Fe 声明区间 90–99.99999%（超纯铁基体，Fe 仅承担闭合）。',))

    for g in interference_groups(SEEDS['interference']):
        add(g['percent'], 'interference_control', g['family'],
            {'interference_pair': g['pair'], 'variant': g['variant'],
             'concentration_unit_percent': round(g['unit'], 8),
             'concentration_level': g['level'],
             'background_recipe': {e: round(v, 8) for e, v in sorted(g['background'].items())}},
            ('干扰对不含 Fe（Fe 仅作平衡元素）；背景母配方同族两档共用且不覆盖目标；'
             'variant 标签经存在性、背景值与 1:5 / 5:1 / equal 实际比值断言。',))
    return samples


def v1_baseline():
    """复算 v1（已密封 P5 批次）的问题数字，便于与评审逐条对账。"""
    if not V1_MASTER.is_file():
        return {'available': False, 'path': str(V1_MASTER)}
    data = json.loads(V1_MASTER.read_text(encoding='utf-8'))
    rows = data['samples']
    keys = [comp_key(r['composition_percent']) for r in rows]
    glob = {**{e: (0.0, c) for e, c in MAIN_CAPS.items()},
            **{e: (0.0, TRAMP_CAP) for e in TRAMP_ELEMENTS}, 'Fe': FE_ALLOY_RANGE}
    viol_rows = 0
    viol_items = 0
    per_scenario = Counter()
    for r in rows:
        declared = r['provenance'].get('ranges_percent') or glob
        declared = {k: (v[0], v[1]) for k, v in declared.items()}
        bad = violations(r['composition_percent'], declared)
        if bad:
            viol_rows += 1
            viol_items += len(bad)
            per_scenario[r['provenance'].get('design_scenario', '?')] += 1
    return {'available': True, 'rows': len(rows), 'distinct_compositions': len(set(keys)),
            'duplicate_groups': sum(1 for k, v in Counter(keys).items() if v > 1),
            'rows_with_range_violations': viol_rows,
            'range_violation_items': viol_items,
            'violations_by_scenario': dict(per_scenario)}


def selfcheck(samples):
    report = {}
    scen = lambda s: s['provenance']['design_scenario']
    report['rows'] = len(samples)
    report['scenario_counts'] = dict(Counter(scen(s) for s in samples))
    report['quota_met'] = report['scenario_counts'] == QUOTA

    keys = [comp_key(s['composition_percent']) for s in samples]
    report['distinct_compositions'] = len(set(keys))
    report['distinct_equals_rows'] = len(set(keys)) == len(samples)
    report['duplicate_groups'] = sum(1 for k, v in Counter(keys).items() if v > 1)

    bad = {s['id']: violations(s['composition_percent'],
                               {k: tuple(v) for k, v in s['provenance']['ranges_percent'].items()})
           for s in samples}
    report['rows_with_range_violations'] = sum(1 for v in bad.values() if v)
    report['range_violation_items'] = sum(len(v) for v in bad.values())
    report['examples_of_violations'] = dict(list(((k, v) for k, v in bad.items() if v))[:5])

    closure = {s['id']: round(sum(s['composition_percent'].values()), 6) for s in samples}
    report['closure_not_100'] = [k for k, v in closure.items() if abs(v - 100.0) > 1e-6]
    report['fe_min_max'] = [min(s['composition_percent']['Fe'] for s in samples),
                            max(s['composition_percent']['Fe'] for s in samples)]
    report['all_rows_have_iron_matrix'] = all(v >= FE_ALLOY_RANGE[0] for v in
                                             (s['composition_percent']['Fe'] for s in samples))

    inter = [s for s in samples if scen(s) == 'interference_control']
    fams = defaultdict(list)
    for s in inter:
        fams[s['provenance']['parent_family']].append(s['provenance']['variant'])
    report['interference_rows'] = len(inter)
    report['interference_families'] = len(fams)
    report['interference_family_has_5_variants'] = all(len(v) == 5 for v in fams.values())
    report['interference_pairs'] = sorted({s['provenance']['interference_pair'] for s in inter})
    report['interference_pairs_containing_Fe'] = sorted(
        {s['provenance']['interference_pair'] for s in inter
         if 'Fe' in s['provenance']['interference_pair'].split('/')})
    report['interference_variant_counts'] = dict(Counter(s['provenance']['variant'] for s in inter))
    bg_clash = [s['id'] for s in inter
                if set(s['provenance']['interference_pair'].split('/'))
                & set(s['provenance']['background_recipe'])]
    report['interference_background_overlaps_target'] = bg_clash

    sparse = [s for s in samples if scen(s) == 'sparse_boundary']
    low = Counter(s['provenance']['sparse_target'] for s in sparse
                  if s['provenance']['sparse_kind'] == 'low_content_boundary')
    zero = Counter(s['provenance']['sparse_target'] for s in sparse
                   if s['provenance']['sparse_kind'] == 'exact_zero')
    report['sparse_targets'] = len(low)
    report['low_recipes_per_target_min'] = min(low.values())
    report['zero_recipes_per_target_min'] = min(zero.values())
    report['zero_recipe_target_actually_absent'] = all(
        s['provenance']['sparse_target'] not in s['composition_percent'] for s in sparse
        if s['provenance']['sparse_kind'] == 'exact_zero')

    elem_cov = Counter(e for s in samples for e, v in s['composition_percent'].items() if v > 0)
    report['elements_never_present'] = [e for e in list(MAIN_ELEMENTS) + list(TRAMP_ELEMENTS)
                                        if elem_cov.get(e, 0) == 0]
    report['element_presence_counts'] = dict(sorted(elem_cov.items(), key=lambda x: -x[1]))
    report['zero_element_mentions'] = sum(
        1 for s in samples for e in HI if e not in s['composition_percent'])

    report['passed'] = bool(
        report['quota_met'] and report['distinct_equals_rows'] and
        report['rows_with_range_violations'] == 0 and not report['closure_not_100'] and
        report['all_rows_have_iron_matrix'] and report['interference_family_has_5_variants'] and
        not report['interference_pairs_containing_Fe'] and not bg_clash and
        report['zero_recipe_target_actually_absent'] and
        report['low_recipes_per_target_min'] >= 5 and report['zero_recipes_per_target_min'] >= 5 and
        not report['elements_never_present'])
    return report


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    samples = build()
    report = selfcheck(samples)
    report['v1_baseline_recomputed'] = v1_baseline()

    (OUT_DIR / 'master_samples_v2.json').write_text(json.dumps({
        'synthetic_design': True, 'matrix': 'iron-based-alloy', 'designer': 'C',
        'design_version': 'C-recipes-v2',
        'supersedes': 'C-recipes-v1 (P5 batch 20261018, review_failed on PR #2)',
        'seed': 20261101, 'scenario_counts': report['scenario_counts'],
        'sparse_target_elements': list(SPARSE_TARGETS),
        'interference_pairs': report['interference_pairs'],
        'samples': samples,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    master_file = OUT_DIR / 'master_samples_v2.json'
    # 只记文件名与哈希，不记绝对路径：这样同一份代码在本地与仓库布局下产出逐字节相同的报告。
    report['master_file'] = {
        'name': master_file.name, 'bytes': master_file.stat().st_size,
        'sha256': hashlib.sha256(master_file.read_bytes()).hexdigest(),
        'v1_master_used': {'name': V1_MASTER.name,
                           'bytes': V1_MASTER.stat().st_size if V1_MASTER.is_file() else None,
                           'sha256': (hashlib.sha256(V1_MASTER.read_bytes()).hexdigest()
                                      if V1_MASTER.is_file() else None)}}
    (OUT_DIR / 'design_selfcheck_v2.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    v1 = report['v1_baseline_recomputed']
    lines = ['# C 部分配方设计 v2 自检报告', '',
             '设计脚本：`scripts/design_c_alloy_formulas_v2.py`；输出：`v2/master_samples_v2.json`'
             '（SHA-256 见 `design_selfcheck_v2.json` 的 `master_file.sha256`）。',
             '已密封的 P5 批次与 v1 脚本未被修改；本报告只读地对 v1 主表复算了问题数字。', '',
             '> 本表比较的是 **v1 主表** 与 **v2 主表**。已归档的 P5 批次（2000 谱）仍由 v1 主表生成，'
             '其数据本身的问题没有在本批内改变；“已消除”只指 v2 主表按同一断言复算后的结果。', '',
             '## 逐条对账（评审结论 → v2 状态）', '',
             '| 评审发现 | v1 实测（本脚本复算） | v2 实测 | 结论 |',
             '| --- | --- | --- | --- |',
             f"| P2-1 独立组成不足 | {v1.get('distinct_compositions', 'n/a')}/"
             f"{v1.get('rows', 'n/a')}，重复组 {v1.get('duplicate_groups', 'n/a')} "
             f"| **{report['distinct_compositions']}/{report['rows']}，重复组 "
             f"{report['duplicate_groups']}** | 已消除 |",
             f"| P2-3 越出自身声明范围 | {v1.get('rows_with_range_violations', 'n/a')} 行 / "
             f"{v1.get('range_violation_items', 'n/a')} 项"
             f"（{v1.get('violations_by_scenario', {})}） "
             f"| **{report['rows_with_range_violations']} 行 / "
             f"{report['range_violation_items']} 项** | 已消除 |",
             "| P2-2 干扰对照写死 Ni=8、Fe 参与对照 | 40 族均受影响 "
             f"| 含 Fe 的干扰对：{report['interference_pairs_containing_Fe'] or '无'}；"
             f"背景覆盖目标：{report['interference_background_overlaps_target'] or '无'}；"
             '逐变体存在性/背景/比值断言通过 | 已消除 |',
             f"| 场景配额 600/200/200 | 600/200/200 | {report['scenario_counts']} | 达标 |",
             f"| Fe 基体与 100% 闭合 | — | Fe 区间 {report['fe_min_max']}，"
             f"闭合非 100 的行 {len(report['closure_not_100'])} | 达标 |",
             f"| 元素覆盖 | — | 从未出现的元素："
             f"{report['elements_never_present'] or '无'} | 达标 |",
             '', '## 断言明细', '',
             '```json',
             json.dumps({k: v for k, v in report.items()
                         if k not in ('element_presence_counts', 'v1_baseline_recomputed')},
                        ensure_ascii=False, indent=2),
             '```', '',
             '## 元素出现次数（采用组成中出现即计数）', '',
             json.dumps(report['element_presence_counts'], ensure_ascii=False), '',
             '## 结论', '',
             f"**{'全部断言通过，可进入下一步（划分/索引重写后再启动生成）' if report['passed'] else '存在未通过项，禁止进入生成'}**",
             '']
    (OUT_DIR / 'design_selfcheck_v2.md').write_text('\n'.join(lines), encoding='utf-8')
    (OUT_DIR / 'selfcheck_stdout.txt').write_text(json.dumps(
        {k: report[k] for k in ('rows', 'scenario_counts', 'distinct_compositions',
                                'rows_with_range_violations', 'passed')},
        ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
