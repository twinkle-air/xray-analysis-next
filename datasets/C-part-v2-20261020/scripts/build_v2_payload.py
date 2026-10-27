"""C 部分：把 v2 合格批次（P5_dataset_v2）整理成仓库交付载荷 datasets/C-part-v2-20261020/。

与 v1 布局同构（平铺 + 分卷 ZIP），但内容全部来自 v2：v2 主表、v2 索引与划分
（在 v2 数据上实测通过）、v2 QC 报告。只读源产物，不改动已密封的数据集。

用法：python -B scripts/build_v2_payload.py
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent                    # C_part
ROOT = HERE.parent                                               # 兴智杯AI
FP = ROOT / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition'
DATASET = FP / 'P5_dataset_v2'
BATCH = 'C-part-v2-20261020'
OUT = HERE / 'github_payload_v2' / 'datasets' / BATCH
CHECK = HERE / 'v2_datacheck'          # v2 索引策略在 v2 数据上的实测产物
QC = HERE / 'v2_qc'
MASTER = HERE / 'v2' / 'master_samples_v2.json'
SCRIPTS = ['design_c_alloy_formulas_v2.py', 'build_p5_index_v2.py', 'c_pilot_guard.py',
           'generate_v2_batch.py', 'loop_v2_chunks.py', 'pregenerate_dryrun_v2.py',
           'v2_generation_status.py', 'finalize_v2_reproducibility.py',
           'check_and_pack_p5_v2.py', 'build_v2_payload.py', 'run_v2_gate_examples.py']
MAX_PART = 43 * 2**20                 # 每卷 < 43 MiB，低于 GitHub 50 MiB 告警线


def sha256(path):
    d = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            d.update(block)
    return d.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                          encoding='utf-8')


def write_csv(path, rows):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / 'scripts').mkdir(parents=True)
    # 与 datasets/C-part-20261018 同规则：目录内文件原样入库，避免本机
    # core.autocrlf=true 把 CRLF 洗成 LF 导致字节与远端 blob 不一致。
    (OUT / '.gitattributes').write_text('* -text\n', encoding='ascii')

    zip_path = QC / 'P5_v2_dataset.zip'
    if not zip_path.exists():
        raise SystemExit('missing packed dataset: ' + str(zip_path))
    audit = read_json(QC / 'P5_v2_audit.json')
    policy = read_json(CHECK / 'index_policy_check_v2.json')
    manifest = read_json(DATASET / 'manifest.json')
    samples = read_json(MASTER)['samples']
    index_rows = list(csv.DictReader((CHECK / 'index_v2.csv').open(encoding='utf-8-sig')))

    # 逐配方登记表：谱号取自 v2 索引，情景/母族/闭合取自 v2 主表
    by_formula = {}
    for r in index_rows:
        by_formula.setdefault(r['formula_id'], []).append(r)
    registry = []
    for sample in samples:
        rows = by_formula[sample['id']]
        first = rows[0]
        registry.append({
            'formula_id': sample['id'],
            'scenario': sample['provenance'].get('design_scenario', ''),
            'matrix': sample['provenance'].get('matrix', ''),
            'parent_family': sample['provenance'].get('parent_family', ''),
            'composition_key': first['composition_key'],
            'leak_group': first['leak_group'],
            'generator_family': first['generator_family'],
            'benchmark_split': first['benchmark_split'],
            'usage_policy': first['usage_policy'],
            'recipe_family_split': first['recipe_family_split'],
            'spectra': ','.join(r['global_id'] for r in sorted(rows, key=lambda x: x['local_id'])),
            'n_spectra': len(rows),
            'n_elements_positive': sum(1 for v in sample['composition_percent'].values() if v > 0),
            'closure_sum_percent': round(sum(sample['composition_percent'].values()), 6),
            'blind_input_sha256': first['blind_input_sha256'],
        })

    copies = {
        'C_samples.json': MASTER,
        'C_authoritative_index.csv': CHECK / 'index_v2.csv',
        'C_global_split.csv': CHECK / 'global_split_v2.csv',
        'C_coverage.json': CHECK / 'coverage_v2.json',
        'C_index_policy_check_v2.json': CHECK / 'index_policy_check_v2.json',
        'C_index_policy_check_v2.md': CHECK / 'index_policy_check_v2.md',
        'P5.json': FP / 'profiles' / 'P5.json',
        'P5_audit.json': QC / 'P5_v2_audit.json',
        'P5_dataset.zip.sha256': Path(str(zip_path) + '.sha256'),
    }
    if (QC / 'P5_v2_replay.json').exists():
        copies['P5_replay.json'] = QC / 'P5_v2_replay.json'
    gates = read_json(QC / 'gate_examples.json') if (QC / 'gate_examples.json').exists() else None
    if gates:
        copies['C_qc_gate_report.json'] = QC / 'gate_examples.json'
    for name, src in copies.items():
        shutil.copy2(src, OUT / name)
    for script in SCRIPTS:
        shutil.copy2(HERE / 'scripts' / script, OUT / 'scripts' / script)

    write_csv(OUT / 'C_formula_registry.csv', registry)

    # 分卷
    total = zip_path.stat().st_size
    parts = []
    with zip_path.open('rb') as stream:
        for n in range(1, math.ceil(total / MAX_PART) + 1):
            data = stream.read(MAX_PART)
            if not data:
                break
            name = f'P5_pack.zip.part{n:02d}'
            (OUT / name).write_bytes(data)
            parts.append({'file': name, 'bytes': len(data), 'sha256': sha256(OUT / name)})
    join = '+'.join(p['file'] for p in parts)
    entries = sorted(zipfile.ZipFile(zip_path).namelist())

    qc_summary = read_json(QC / 'P5_v2_qc_summary.json') if (QC / 'P5_v2_qc_summary.json').exists() else {}
    replay = (read_json(QC / 'P5_v2_replay.json')
              if (QC / 'P5_v2_replay.json').exists() else {'status': qc_summary.get('replay', 'not_run')})
    zip_sha = Path(str(zip_path) + '.sha256').read_text(encoding='ascii').strip().split()[0]

    status = {
        'batch_id': BATCH,
        'batch_version': manifest.get('batch_version', 'C-recipes-v2'),
        'supersedes': manifest.get('supersedes', ''),
        'review_status': 'pending_independent_review',
        'role': 'C 部分：1000 条铁基合金主配方 + P5 留出条件 2000 谱（v2，修复 PR #2 首轮 5 条）',
        'identity': {
            'generator_version': manifest['software_version'],
            'physical_model_version': manifest['physical_model_version'],
            'physics_core_sha256': manifest['physics_core_sha256'],
            'profile_sha256': policy['coverage']['profile_sha256'],
            'master_samples_sha256': sha256(MASTER),
            'manifest_sha256': sha256(DATASET / 'manifest.json'),
            'zip_sha256': zip_sha,
            'seed_batch': manifest['seed'],
            'seed_split': manifest['split_seed'],
            'replicates': manifest['replicates'],
        },
        'scale': {'formulas': len(samples), 'spectra': len(index_rows),
                  'distinct_compositions': policy['checks']['distinct_formula_compositions'],
                  'duplicate_composition_groups': policy['checks']['duplicate_composition_groups'],
                  'leak_groups': policy['checks']['leak_groups'],
                  'group_size_histogram': policy['checks']['group_size_histogram'],
                  'scenario_counts': policy['coverage']['scenario_counts'],
                  'dataset_files_in_zip': len(entries), 'zip_bytes': total},
        'review_findings_addressed': {
            'P1-1_heldout_label': 'all rows benchmark_split=heldout, holdout_status=condition_heldout, '
                                  'usage_policy=pilot_only_isolated_from_training_and_tuning; '
                                  'recipe_family_split 仅描述配方来源',
            'P1-2_leakage': f"leak_group 粒度划分，跨集合组数 {len(policy['checks']['groups_crossing_recipe_split'])}，"
                            f"相同组成跨集合 {len(policy['checks']['identical_compositions_crossing_split'])}",
            'P2-1_distinct_compositions': f"{policy['checks']['distinct_formula_compositions']}/1000（v1 为 944）",
            'P2-2_interference_control': 'Ni/Cr/Mo/Cu 对照不再写死 8%，Fe 不作对照变量',
            'P2-3_declared_range': '逐情景区间校验，越界 0 项（v1 常规情景 548 行越界）',
        },
        'pr56_review_fixes': {
            'R3-1_guard_default_index': 'c_pilot_guard.py 的 INDEX_CANDIDATES 首位改为实际交付名 '
                                        'C_authoritative_index.csv（旧顺序只查 v2/index_v2.csv 等，'
                                        '从新 clone 默认入口会 FileNotFoundError）；'
                                        '新增 resolve_index()：候选全部缺失时报出候选名并以退出码 1 结束，'
                                        '自检未通过同样非零退出',
            'R3-2_replay_exit_code': 'check_and_pack_p5_v2.py 的 replay 分支改为"先落盘报告、再过门禁"：'
                                     'evaluate_replay() 校验 status/scope/spectra_recalculated==全量/'
                                     'complete_physics_recalculation/same_environment/errors/最大数组差为数值，'
                                     '任一项不符 raise SystemExit(1)；audit/pack 同样门禁，'
                                     '"报告写完"不再等于退出 0',
            'exit_code_examples': ({k: v.get('exit_code') for k, v in gates['cases'].items()
                                    if 'exit_code' in v} | {
                                    'E_delivered_replay_report': 'problems='
                                    + str(gates['cases']['E_delivered_replay_report']['problems'])}
                                   if gates else '未跑（重跑 scripts/run_v2_gate_examples.py）'),
            'expected_exit_codes': gates.get('expected_exit_codes') if gates else None,
            'examples_passed': gates.get('passed') if gates else None,
            'detail_file': 'C_qc_gate_report.json',
        },
        'qc': {
            'audit': {'status': audit.get('status'), 'spectra_checked': audit.get('spectra_checked'),
                      'errors': len(audit.get('errors', []))},
            'replay': {k: replay.get(k) for k in ('status', 'spectra_recalculated',
                                                  'complete_physics_recalculation',
                                                  'same_environment',
                                                  'maximum_absolute_array_difference')
                       if k in replay} or {'status': replay.get('status')},
            'replay_errors': len(replay.get('errors', [])),
            'pack': qc_summary.get('pack', {'zip_bytes': total, 'sha256': zip_sha}),
            'index_policy_check': {'passed': policy['checks']['passed']},
        },
        'usage': {
            'trainable': False,
            'note': 'P5 是留出条件批次：本批 2000 谱不得用于训练、调参或阈值挑选；'
                    '下游请经 scripts/c_pilot_guard.py::training_rows() 读取（会拒绝而非静默放行）。'
                    '本交付不为其他批次的可训练性作背书。',
        },
        'not_verified': [
            '全部为合成数据，无真实设备校准，不证明真实含量准确度或 95%/5% 目标',
            '模型未包含死时间、堆积、粒度、水分、多层、多次散射、粗糙度与长期漂移',
            'Ba K 线中心落在能窗外，保留 L/M 线记录',
            'acceptance_status = ' + manifest['acceptance_status'],
        ],
    }
    write_json(OUT / 'C_batch_status.json', status)

    gate_lines = ''
    if gates:
        for key, label in (('A_guard_default_entry', '从交付布局默认入口跑 c_pilot_guard 自检'),
                           ('B_guard_negative_index', '守卫负例：把全部行改成可训练语义（应显示 NOT BLOCKED 并非零退出）'),
                           ('C_qc_stub_pass', 'QC 门禁正例：合成通过报告走同一路径'),
                           ('D_qc_stub_fail', 'QC 门禁负例：故障注入（failed / 只重算 1 条 / complete=false / 1 条 error）')):
            case = gates['cases'][key]
            gate_lines += (f"\n  - {label}：实测退出码 **{case['exit_code']}**"
                           f"（期望 {gates['expected_exit_codes'][key]}）")
        e = gates['cases']['E_delivered_replay_report']
        gate_lines += (f"\n  - 随包真·全量 replay 报告 `P5_replay.json` 过同一门禁："
                       f"期望 {e['expected_spectra']} 条，不合格项 {len(e['problems'])} 项")
    else:
        gate_lines = '\n  - 未跑：重跑 `python -B scripts/run_v2_gate_examples.py` 生成 `C_qc_gate_report.json`'

    readme = f"""# C 部分 · {BATCH}（铁基合金 1000 配方 / P5 留出条件 / 2000 合成谱，v2）

生成器 fp-spectrum-generator-competition-{manifest['software_version']}（物理模型 {manifest['physical_model_version']}）。
本批替代 `datasets/C-part-20261018`（PR #2 评审 requested changes 的归档批次，
`{manifest.get('supersedes', '')}`）；归档批次原样保留、未改动，其定位仍是失败批次。

## 这一批改了什么（对着首轮评审 5 条）

| 评审条 | v1 归档批次 | 本批实测 | 证据 |
| --- | --- | --- | --- |
| P1-1 留出批次被标成可训练划分 | benchmark_split = train/validation/test | 2000 行全部 `benchmark_split=heldout` + `holdout_status=condition_heldout` + `usage_policy=pilot_only_isolated_from_training_and_tuning`；训练语义降级为仅描述来源的 `recipe_family_split` | `C_index_policy_check_v2.json` |
| P1-2 相同组成跨集合 | 9 组 | 跨集合组数 0（划分粒度 = 并查集 `leak_group`） | 同上 |
| P2-1 1000 行仅 944 独立组成 | 944 | **{policy['checks']['distinct_formula_compositions']}/1000**，重复组成组 {policy['checks']['duplicate_composition_groups']}，leak_group {policy['checks']['leak_groups']} 组（ sizes {json.dumps(policy['checks']['group_size_histogram'])}） | 同上 |
| P2-2 干扰对照写死 Ni=8、Fe 参与对照 | 是 | Ni/Cr/Mo/Cu 按情景区间采样，Fe 只作基体 | `scripts/design_c_alloy_formulas_v2.py` |
| P2-3 548 行越出自身声明范围 | 常规 548 行/1334 项 | 逐情景区间校验，越界 0 | 同上 + `C_batch_status.json` |

## 内容

| 文件 | 说明 |
| --- | --- |
| `C_samples.json` | 1000 条铁基合金主配方（常规 600 / 稀疏边界 200 / 干扰对照 200），SHA-256 `{sha256(MASTER)[:12]}…` |
| `C_formula_registry.csv` | 逐配方登记：情景、母族、实际采用组成键、leak_group、双划分、谱号、正元素数、闭合和 |
| `C_authoritative_index.csv` | 2000 条谱的权威索引（留出字段 + 盲/满双 SHA-256） |
| `C_global_split.csv` | leak_group 粒度的划分表 |
| `C_coverage.json` | 元素覆盖、能窗、窗外损失、身份哈希 |
| `C_index_policy_check_v2.json/.md` | 划分与泄漏策略的机器自检（`passed: true`） |
| `C_batch_status.json` | 批次身份、规模、评审条目对照、QC 结果、用法限制、未验证事项 |
| `P5.json` | 条件配置 candidate_holdout_P45_Al50_air1 |
| `P5_audit.json` | 全量 audit 报告（{audit.get('spectra_checked')} 条、错误 {len(audit.get('errors', []))}） |
| `P5_dataset.zip.sha256` | 整包外部校验值：`{zip_sha}` |
| `P5_pack.zip.part01`…`part{len(parts):02d}` | 密封数据集目录的 ZIP 分卷（每卷 < 43 MiB，合计 {total:,} B） |
| `scripts/` | v2 设计、生成、索引/划分、守卫、密封补齐、QC 与本布局生成脚本；`run_v2_gate_examples.py` 复现退出码正/负例 |
| `C_qc_gate_report.json` | PR #56 复核两条阻断项的正/负例实跑记录（真实退出码、命令、输出尾部、随包真报告的判定结果） |

## 重建与校验

```
copy /b {join} P5_dataset.zip
certutil -hashfile P5_dataset.zip SHA256     # 应等于 P5_dataset.zip.sha256
tar -xf P5_dataset.zip -C P5_dataset_v2
python -B P5_dataset_v2/reproducibility/generator/fp_competition/app.py audit --dataset P5_dataset_v2 --out P5_qc_after_clone.json
```

## 划分与用法

- 每一行 `benchmark_split=heldout`、`holdout_status=condition_heldout`、
  `usage_policy=pilot_only_isolated_from_training_and_tuning`。本批 2000 谱禁止训练、调参与阈值挑选。
- `recipe_family_split`（train/validation/test）只描述配方来源，不得作为基准划分。
- 划分粒度为并查集 `leak_group`（实际采用组成 ∪ parent_family ∪ 生成器族 ∪ 噪声重复），同组不跨集合。
- 下游入口请用 `scripts/c_pilot_guard.py::training_rows()`，它会抛 `PilotIsolationError` 而非静默放行。
- 不使用其他批次替代本批做基准：任何批次（含 A/B 试产数据）都要各自核对其 `usage_policy` 与评审状态。

## QC 结果

- audit：`{audit.get('status')}`，检查 {audit.get('spectra_checked')} 条谱，错误 {len(audit.get('errors', []))} 条
  （逐谱校验盲/满双哈希、通道轴、分量求和、窗口账目、泊松重放、闭合与来源一致性）。
- 全量物理重算：`{replay.get('status', 'not_run')}`，重算 {replay.get('spectra_recalculated', '—')} 条，
  最大数组绝对差 {replay.get('maximum_absolute_array_difference', '—')}，环境一致 {replay.get('same_environment', '—')}。
- 打包：确定性 ZIP {total:,} B，SHA-256 `{zip_sha}`。

## 退出码约定与正/负例（PR #56 复核两条阻断项）

- `scripts/c_pilot_guard.py` 的默认索引入口即本目录的 `C_authoritative_index.csv`
  （候选名首位；从新 clone 直接 `python -B scripts/c_pilot_guard.py` 即可，无需 `--index`）。
  自检未通过、或候选名全部找不到 → **退出码 1** 并打印原因。
- `scripts/check_and_pack_p5_v2.py`：全量物理重算只有同时满足
  `status=passed`、`scope=all_records`、`spectra_recalculated=` 密封 manifest 的全量条数、
  `complete_physics_recalculation=true`、`same_environment=true`、`errors=[]` 才退出 0；
  不合格时**报告仍然先落盘**（证据不丢），随后以退出码 1 结束。audit 与 pack 同样有门禁。
- 实测退出码（`python -B scripts/run_v2_gate_examples.py`，逐条命令与输出见 `C_qc_gate_report.json`）：
{gate_lines}

## 未验证事项

合成数据、未做真实设备校准；模型不含死时间、堆积、粒度、水分、多层、多次散射与粗糙度；
含量相对误差 ≤5% 的结论不能由本批数据得出；`acceptance_status = {manifest['acceptance_status']}`。
"""
    (OUT / 'README.md').write_text(readme, encoding='utf-8')

    files = sorted(p for p in OUT.rglob('*') if p.is_file())
    write_json(OUT / 'C_delivery_hashes.json', {
        'batch_id': BATCH, 'zip_sha256': zip_sha, 'zip_parts': parts,
        'files': {f.relative_to(OUT).as_posix(): {'bytes': f.stat().st_size, 'sha256': sha256(f)}
                  for f in files},
    })
    files = sorted(p for p in OUT.rglob('*') if p.is_file())
    print('payload files', len(files), 'bytes', sum(f.stat().st_size for f in files))
    print('parts', len(parts), 'over 50 MiB:', [f.name for f in files if f.stat().st_size > 50 * 2**20])
    print('registry rows', len(registry), 'index rows', len(index_rows))


if __name__ == '__main__':
    main()
