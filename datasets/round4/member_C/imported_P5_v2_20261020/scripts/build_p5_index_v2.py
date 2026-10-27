"""C 部分：P5 索引与全局划分的 v2 构建器（修 PR #2 的 P1-1 / P1-2）。

评审的两条 P1
--------------
P1-1 留出语义被划分字段污染：v1 索引把本批 2000 条 P5 谱又标成
     benchmark_split = train 1402 / validation 302 / test 296，交付 README 还写
     "下游只按 benchmark_split 读取训练数据"。P5 是**留出条件**批次，任何"可训练"
     标签都是入口泄漏。
     v2：每一行 `holdout_status='condition_heldout'`、`benchmark_split='heldout'`、
     `usage_policy='pilot_only_isolated_from_training_and_tuning'`；
     原先的训练语义标签降级为**仅描述配方来源**的 `recipe_family_split`，
     并明确"不得作为基准划分使用"。

P1-2 相同组成跨集合：v1 的 parent_family 是设计族哈希，而生成器的 family 是
     **实际采用组成**哈希；两者不等价，于是 9 组完全相同的组成落进了不同集合。
     v2：用并查集把「实际采用组成」∪「parent_family」连同「同一配方的噪声重复」
     合成一个 `leak_group`，所有划分只在 leak_group 粒度上进行，
     因此同组不可能跨集合（脚本会断言这一点）。

只读已密封数据集（manifest/truth/inputs），不写回、不改名、不改哈希；
全部输出写到 `C_part/v2/`。可对任意 (主配方表, 数据集) 组合运行：
先用现有 v1 批次验证新策略，重生成后再对 v2 批次运行。

在仓库布局下的用法（本脚本与主表随批次一起提交在 `datasets/<batch>/` 内）：

```
python -B scripts/build_p5_index_v2.py <解包后的数据集目录> [主表] [批次标签] [版本] [输出目录]
# 例：python -B scripts/build_p5_index_v2.py ../P5_dataset_dir
# 省略主表时自动取本目录的 C_samples.json（v1 主表，与本地 master_samples.json 逐字节相同）
# 输出默认写到 <batch 目录>/v2/，可用第 5 个参数或环境变量 C_V2_OUT_DIR 改写
```
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get('C_V2_OUT_DIR', sys.argv[5] if len(sys.argv) > 5 else str(HERE / 'v2')))
DEFAULT_DATASET = HERE.parent / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition' / 'P5_dataset'


def _default_master():
    """本地跑用 master_samples.json，仓库布局（datasets/<batch>/scripts/）用同目录 C_samples.json。"""
    for name in ('master_samples.json', 'C_samples.json', 'C_samples_v1.json'):
        p = HERE / name
        if p.is_file():
            return p
    return HERE / 'master_samples.json'


DEFAULT_MASTER = _default_master()

RECIPE_SPLIT_FRAC = (0.70, 0.15, 0.15)
HOLDOUT = {'holdout_status': 'condition_heldout',
           'benchmark_split': 'heldout',
           'usage_policy': 'pilot_only_isolated_from_training_and_tuning'}
LOW_THRESHOLD_DEFAULT = 0.1


def sha256(path):
    d = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            d.update(block)
    return d.hexdigest()


def comp_key(percent):
    return hashlib.sha256(
        json.dumps({e: round(float(v), 8) for e, v in percent.items() if abs(float(v)) > 1e-12},
                   sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def recipe_split_for_groups(groups, split_seed):
    """按 leak_group 粒度做 70/15/15，仅用于描述配方来源，不是基准划分。"""
    ordered = sorted(groups, key=lambda g: hashlib.sha256(
        (str(split_seed) + ':' + g).encode()).hexdigest())
    n = len(ordered)
    train = min(n - 2, max(1, round(n * RECIPE_SPLIT_FRAC[0]))) if n >= 3 else 1
    val = min(max(1, round(n * RECIPE_SPLIT_FRAC[1])), n - train - 1) if n >= 3 else 0
    return {g: ('train' if i < train else 'validation' if i < train + val else 'test')
            for i, g in enumerate(ordered)}


def load_dataset(dataset):
    dataset = Path(dataset)
    manifest = json.loads((dataset / 'manifest.json').read_text(encoding='utf-8'))
    truth = [json.loads(l) for l in (dataset / 'truth.jsonl').read_text(encoding='utf-8').splitlines()]
    samples = json.loads((dataset / 'inputs' / 'samples.json').read_text(encoding='utf-8'))['samples']
    profile = json.loads((dataset / 'configs' / 'profile.json').read_text(encoding='utf-8'))
    return manifest, truth, samples, profile


def build(dataset, master_path, batch_label, batch_version):
    manifest, truth, samples, profile = load_dataset(dataset)
    master = json.loads(Path(master_path).read_text(encoding='utf-8'))
    master_by_id = {s['id']: s for s in master['samples']}

    record_map = {r['id']: r for r in manifest['records']}
    label_map = {t['id']: t for t in truth}
    sample_index = {s['id']: i for i, s in enumerate(samples)}

    dsu = DSU()
    fam_of, comp_of, parent_of = {}, {}, {}
    for s in samples:
        sid = s['id']
        parent = s['provenance']['parent_family']
        comp = comp_key(s['composition_percent'])
        fam_of[sid] = comp
        comp_of[comp] = s['composition_percent']
        parent_of.setdefault(parent, set()).add(sid)
        dsu.union('C:' + comp, 'S:' + sid)          # 同一配方与其精确组成
        dsu.union('P:' + parent, 'S:' + sid)        # 同一设计族（母配方变体）
    # 生成器精确组成族（manifest 里的 family）并入，确保与密封数据一致
    gen_family_by_sample = defaultdict(set)
    for r in manifest['records']:
        sid = label_map[r['id']]['original_sample_id']
        gen_family_by_sample[sid].add('G:' + r['family'])
        dsu.union('S:' + sid, 'G:' + r['family'])

    group_of = {sid: dsu.find('S:' + sid) for sid in fam_of}
    groups = sorted(set(group_of.values()))
    recipe_split = recipe_split_for_groups(groups, manifest['split_seed'])

    rows = []
    for sample in samples:
        sid = sample['id']
        prov = sample['provenance']
        idx = sample_index[sid]
        group = group_of[sid]
        for repeat in range(manifest['replicates']):
            identity = f'S{idx * manifest["replicates"] + repeat + 1:06d}'
            record, label = record_map[identity], label_map[identity]
            rows.append({
                'batch_id': batch_label, 'batch_version': batch_version,
                'local_id': identity, 'global_id': f'{batch_label}-{sid}-{repeat + 1}',
                'formula_id': sid, 'design_scenario': prov.get('design_scenario', ''),
                'parent_family': prov['parent_family'],
                'composition_key': fam_of[sid],
                'generator_family': label['family'],
                'leak_group': group,
                'matrix': prov['matrix'],
                'profile_id': profile['name'],
                **HOLDOUT,
                'recipe_family_split': recipe_split[group],
                'generator_split': record['split'],
                'blind_input_sha256': record['blind_input_sha256'],
                'full_results_sha256': record['full_results_sha256'],
            })
    rows.sort(key=lambda r: r['local_id'])
    return rows, samples, manifest, profile, dict(group_of), recipe_split, master_by_id


def check(rows, samples, group_of, recipe_split, manifest):
    """断言：留出语义统一、划分不跨 leak_group、组成去重与族完整性。"""
    out = {}
    out['rows'] = len(rows)
    out['uniform_holdout'] = all(r['benchmark_split'] == 'heldout' and
                                 r['holdout_status'] == 'condition_heldout' for r in rows)
    out['benchmark_split_values'] = dict(Counter(r['benchmark_split'] for r in rows))
    out['recipe_family_split_by_spectra'] = dict(Counter(r['recipe_family_split'] for r in rows))

    # 同一 leak_group 必须只有一个 recipe_family_split（构造保证，再验一次）
    crossing = defaultdict(set)
    for r in rows:
        crossing[r['leak_group']].add(r['recipe_family_split'])
    out['groups_crossing_recipe_split'] = [g for g, v in crossing.items() if len(v) > 1]

    # 相同精确组成不得跨 recipe_family_split
    comp_split = defaultdict(set)
    for r in rows:
        comp_split[r['composition_key']].add(r['recipe_family_split'])
    out['identical_compositions_crossing_split'] = sorted(
        k for k, v in comp_split.items() if len(v) > 1)

    # parent_family 不得跨 recipe_family_split
    pf_split = defaultdict(set)
    for r in rows:
        pf_split[r['parent_family']].add(r['recipe_family_split'])
    out['parent_families_crossing_split'] = sorted(k for k, v in pf_split.items() if len(v) > 1)

    # 同一配方的噪声重复必须在同一组
    rep = defaultdict(set)
    for r in rows:
        rep[r['formula_id']].add(r['leak_group'])
    out['formula_replicates_split'] = [k for k, v in rep.items() if len(v) > 1]

    keys = [r['composition_key'] for r in rows]
    per_formula = {r['formula_id']: r['composition_key'] for r in rows}
    out['distinct_formula_compositions'] = len(set(per_formula.values()))
    out['formulas'] = len(per_formula)
    dup = {k: v for k, v in Counter(per_formula.values()).items() if v > 1}
    out['duplicate_composition_groups'] = len(dup)
    # 每个重复组里的配方是否被并查集收进同一个 leak_group（即隔离是否有效）
    out['duplicate_groups_all_single_leak_group'] = all(
        len({group_of[sid] for sid, ck in per_formula.items() if ck == k}) == 1 for k, v in dup.items())
    out['leak_groups'] = len(set(group_of.values()))
    out['group_size_histogram'] = dict(sorted(Counter(
        Counter(group_of.values()).values()).items()))
    out['generator_split_untouched'] = dict(Counter(r['generator_split'] for r in rows))
    out['sealed_manifest_split_seed'] = manifest['split_seed']
    out['passed'] = bool(out['uniform_holdout'] and not out['groups_crossing_recipe_split']
                         and not out['identical_compositions_crossing_split']
                         and not out['parent_families_crossing_split']
                         and not out['formula_replicates_split']
                         and out['duplicate_groups_all_single_leak_group'])
    return out


def coverage(rows, samples, manifest, profile, dataset):
    dataset = Path(dataset)
    targets = manifest['target_elements']
    stats = {s: {'zero': 0, 'low': 0, 'mid': 0, 'high': 0,
                 'min_percent': None, 'max_percent': None} for s in targets}
    for sm in samples:
        used = sm['composition_percent']
        for s in targets:
            v = float(used.get(s, 0.0))
            st = stats.setdefault(s, {'zero': 0, 'low': 0, 'mid': 0, 'high': 0,
                                      'min_percent': None, 'max_percent': None})
            lo = LOW_THRESHOLD_DEFAULT
            if v <= 0:
                st['zero'] += 1
            elif v < lo:
                st['low'] += 1
            elif v < 1.0:
                st['mid'] += 1
            else:
                st['high'] += 1
            st['min_percent'] = v if st['min_percent'] is None else min(st['min_percent'], v)
            st['max_percent'] = v if st['max_percent'] is None else max(st['max_percent'], v)
    return {
        'dataset_dir': dataset.name,
        'profile_id': profile['name'],
        'profile_sha256': sha256(dataset / 'configs' / 'profile.json'),
        'spectra': manifest['spectrum_count'],
        'formulas': len(samples),
        'replicates': manifest['replicates'],
        'scenario_counts': dict(Counter(sm['provenance'].get('design_scenario', '?')
                                        for sm in samples)),
        'holdout_status': HOLDOUT,
        'element_coverage': stats,
        'window_keV': manifest['window_summary'],
        'window_loss_fraction': manifest['window_loss_fraction'],
        'target_elements': targets,
        'input_semantic_sha256': manifest['source_samples_semantic_sha256'],
        'physics_core_sha256': manifest['physics_core_sha256'],
        'index_rows': len(rows),
    }


def main():
    dataset = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASET
    master = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_MASTER
    label = sys.argv[3] if len(sys.argv) > 3 else 'P5-v1'
    version = sys.argv[4] if len(sys.argv) > 4 else 'C-recipes-v1(review_failed,pilot_only)'
    OUT.mkdir(parents=True, exist_ok=True)

    rows, samples, manifest, profile, group_of, recipe_split, _ = build(dataset, master, label, version)
    checks = check(rows, samples, group_of, recipe_split, manifest)
    cov = coverage(rows, samples, manifest, profile, dataset)

    fields = list(rows[0])
    with (OUT / 'index_v2.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    group_rows = []
    parent_by_id = {s['id']: s['provenance']['parent_family'] for s in samples}
    for g in sorted(set(group_of.values())):
        mem = sorted(sid for sid, x in group_of.items() if x == g)
        group_rows.append({'leak_group': g, 'recipe_family_split': recipe_split[g],
                           'benchmark_split': 'heldout', 'formulas': len(mem),
                           'spectra': len(mem) * manifest['replicates'],
                           'parent_families': len({parent_by_id[sid] for sid in mem}),
                           'formula_ids': ' '.join(mem[:12]) + (' …' if len(mem) > 12 else '')})
    with (OUT / 'global_split_v2.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(group_rows[0]))
        w.writeheader()
        w.writerows(group_rows)

    # 报告里只记文件名与 SHA-256，不记绝对路径：换机器/换布局也能逐字节复现同一份报告。
    (OUT / 'index_policy_check_v2.json').write_text(json.dumps(
        {'batch_label': label, 'batch_version': version,
         'dataset_dir': dataset.name,
         'dataset_manifest_sha256': sha256(dataset / 'manifest.json'),
         'master_file': master.name, 'master_sha256': sha256(master),
         'checks': checks, 'coverage': {
            k: v for k, v in cov.items() if k != 'element_coverage'}},
        ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'coverage_v2.json').write_text(json.dumps(cov, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = ['# P5 索引与划分策略 v2 自检', '',
             f'- 批次：{label} / {version}',
             f'- 数据集目录名：{dataset.name}（manifest.json SHA-256 `{sha256(dataset / "manifest.json")}`）',
             f'- 主配方表：{master.name}（SHA-256 `{sha256(master)}`）', '',
             '## 断言', '', '```json', json.dumps(checks, ensure_ascii=False, indent=2), '```', '',
             '## 字段语义', '',
             '| 字段 | v1 | v2 |',
             '| --- | --- | --- |',
             '| benchmark_split | train/validation/test（可被当训练集读） | **全部 heldout** |',
             '| holdout_status | 无 | condition_heldout |',
             '| usage_policy | 无 | pilot_only_isolated_from_training_and_tuning |',
             '| recipe_family_split | —（原语义降级到此描述性字段） | 仅描述配方来源，禁止作基准划分 |',
             '| leak_group | —（仅按 parent_family 划分） | 精确组成 ∪ parent_family ∪ 生成器族 的并查集分量 |',
             '', f'结论：**{"全部断言通过" if checks["passed"] else "存在未通过项"}**', '']
    (OUT / 'index_policy_check_v2.md').write_text('\n'.join(lines), encoding='utf-8')
    print(label, checks['passed'], checks['leak_groups'], checks['duplicate_composition_groups'])


if __name__ == '__main__':
    main()
