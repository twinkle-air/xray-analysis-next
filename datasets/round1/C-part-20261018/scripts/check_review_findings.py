"""逐条复核 PR #2 评审提出的 5 个问题（只读，不改动任何已密封产物）。

输出 UTF-8 报告：P5_review_findings_check.json
"""
from __future__ import annotations
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
# 本地布局：C_part/scripts/…，载荷在 C_part/github_payload/datasets/<batch>/
# 仓库布局：datasets/<batch>/scripts/…，批次目录就是 HERE
_BATCH = HERE / 'github_payload' / 'datasets' / 'C-part-20261018'
BATCH_DIR = _BATCH if (_BATCH / 'C_formula_registry.csv').is_file() else HERE


def _master():
    for cand in (HERE / 'master_samples.json', BATCH_DIR / 'C_samples.json',
                 BATCH_DIR / 'C_samples_v1.json'):
        if cand.is_file():
            return cand
    raise SystemExit('找不到 v1 主表（master_samples.json 或 C_samples.json）')


def comp_key(comp):
    return tuple(sorted((e, round(float(v), 6)) for e, v in comp.items()))


def main():
    samples = json.loads(_master().read_text(encoding='utf-8'))['samples']
    by_id = {s['id']: s for s in samples}
    registry = list(csv.DictReader(open(BATCH_DIR / 'C_formula_registry.csv', encoding='utf-8-sig')))
    index = list(csv.DictReader(open(BATCH_DIR / 'C_authoritative_index.csv', encoding='utf-8-sig')))
    first_col = list(registry[0])[0]
    split_of = {r[first_col]: r['benchmark_split'] for r in registry}

    out = {'master_rows': len(samples), 'registry_rows': len(registry), 'index_rows': len(index),
           'scenario_counts_in_master': dict(Counter(s['provenance']['design_scenario'] for s in samples)),
           'scenario_counts_in_registry': dict(Counter(r['scenario'] for r in registry))}

    # P1-1：P5 谱在权威索引里被标成 train/validation/test
    out['P1_1_index_benchmark_split'] = dict(Counter(r['benchmark_split'] for r in index))
    out['P1_1_index_generator_split'] = dict(Counter(r['generator_split'] for r in index))
    out['P1_1_formula_benchmark_split'] = dict(Counter(split_of.values()))

    # P2-1：1000 行里实际有多少种"采用组成"
    groups = defaultdict(list)
    for s in samples:
        groups[comp_key(s['composition_percent'])].append(s['id'])
    dup = {k: sorted(v) for k, v in groups.items() if len(v) > 1}
    out['P2_1_distinct_compositions'] = len(groups)
    out['P2_1_duplicate_groups'] = len(dup)
    out['P2_1_redundant_rows'] = sum(len(v) - 1 for v in dup.values())
    out['P2_1_examples'] = [{'composition': dict(k), 'ids': v} for k, v in list(dup.items())[:6]]
    out['P2_1_C0631_C0640'] = {i: by_id[i]['composition_percent'] for i in
                               (f'C{n:04d}' for n in range(631, 641)) if i in by_id}

    # P1-2：同一采用组成跨 benchmark_split（泄漏）
    cross = [(dict(k), v, sorted({split_of[i] for i in v if split_of.get(i)}))
             for k, v in dup.items() if len({split_of.get(i) for i in v}) > 1]
    out['P1_2_cross_split_groups'] = len(cross)
    out['P1_2_examples'] = [{'composition': c, 'ids': i, 'splits': s} for c, i, s in cross[:12]]
    out['P1_2_Fe92_Ni8'] = [{'ids': i, 'splits': s} for c, i, s in cross
                            if c.get('Fe') == 92.0 and c.get('Ni') == 8.0]

    # P2-2：干扰对照族，固定 Ni=8 / Fe 平衡是否覆盖目标元素
    inter = [s for s in samples if 'INTERF' in s['provenance'].get('parent_family', '')]
    fam = defaultdict(list)
    for s in inter:
        fam[s['provenance']['parent_family']].append(s)
    out['P2_2_interference_rows'] = len(inter)
    out['P2_2_interference_families'] = len(fam)
    out['P2_2_C0812_C0821'] = {i: {k: v for k, v in by_id[i]['composition_percent'].items() if v >= 0.5}
                               for i in (f'C{n:04d}' for n in range(812, 822)) if i in by_id}
    # 同一族内 equal 变体应满足 a==b；用实际成分反推被覆盖的族
    broken = []
    for f, items in fam.items():
        for s in items:
            comp = s['composition_percent']
            if abs(comp.get('Ni', 0) - 8.0) < 1e-9:
                broken.append({'family': f, 'id': s['id'], 'Ni': comp.get('Ni'),
                               'others': {k: v for k, v in comp.items() if v >= 0.5 and k != 'Fe'}})
    out['P2_2_rows_with_pinned_Ni_8'] = len(broken)
    out['P2_2_examples'] = broken[:8]

    # P2-3：常规配方是否超出自身 provenance 声明的范围
    def violations(s):
        ranges = s['provenance'].get('ranges_percent') or {}
        return [{'element': e, 'value': v, 'declared': ranges[e]} for e, v in s['composition_percent'].items()
                if ranges.get(e) and (v > ranges[e][1] + 1e-9 or v < ranges[e][0] - 1e-9)]

    reg = [s for s in samples if s['provenance']['design_scenario'] == 'regular_variation']
    reg_bad = [(s, violations(s)) for s in reg]
    out['P2_3_regular_rows'] = len(reg)
    out['P2_3_regular_rows_violating'] = sum(1 for _, v in reg_bad if v)
    out['P2_3_regular_items_violating'] = sum(len(v) for _, v in reg_bad)
    out['P2_3_examples'] = [{'id': s['id'], 'bad': v[:6]} for s, v in reg_bad if v][:6]
    out['P2_3_all_1000_rows_violating'] = sum(1 for s in samples if violations(s))

    out['master_file'] = _master().name
    out['batch_dir'] = BATCH_DIR.name
    (HERE / 'v2').mkdir(exist_ok=True)
    (HERE / 'v2' / 'review_findings_check.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print('written v2/review_findings_check.json')


if __name__ == '__main__':
    main()
