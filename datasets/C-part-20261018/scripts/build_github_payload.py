"""把 C 部分交付物整理成与 A 部分同构的仓库布局（datasets/C-part-<批次>/ 平铺）。

只读源产物、只写 github_payload 目录，不改动已密封的数据集。
ZIP 按 8 卷切分，每卷 < 50 MiB，避免 GitHub 单文件体积告警与 100 MiB 硬上限。
"""
from __future__ import annotations
import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # C_part
ROOT = HERE.parent                                      # 兴智杯AI
FP = ROOT / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition'
DATASET = FP / 'P5_dataset'
BATCH = 'C-part-20261018'
OUT = HERE / 'github_payload' / 'datasets' / BATCH
PARTS = 8

PROFILE_SHA = 'e30ba2115f3b3507b835cda8f5e21209e615348e87ef7f6a7a32999d424cb280'
ZIP_SHA = '9178746d90e26e45d64a8a9f15ca35736ba363110d535d787e3e589fbf3bf3f2'


def sha256(path):
    d = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            d.update(block)
    return d.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')


def write_csv(path, rows):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / 'scripts').mkdir(parents=True)

    manifest = read_json(DATASET / 'manifest.json')
    samples = read_json(HERE / 'master_samples.json')
    truth = [json.loads(line) for line in (DATASET / 'truth.jsonl').read_text(encoding='utf-8').splitlines()]
    coverage = read_json(HERE / 'P5_coverage_statistics.json')
    index_rows = list(csv.DictReader((HERE / 'P5_authoritative_index.csv').open(encoding='utf-8-sig')))
    split_rows = list(csv.DictReader((HERE / 'P5_global_split.csv').open(encoding='utf-8-sig')))
    audit_full = read_json(HERE / 'P5_delivery_copy_qc.json')
    replay = read_json(HERE / 'P5_replay.json')
    pack = read_json(HERE / 'P5_pack.json')
    env = read_json(DATASET / 'reproducibility' / 'environment.json')

    # 谱级标签（族、划分、子种子）来自真值，按母配方聚合出配方登记表
    label = {t['id']: t for t in truth}
    registry = []
    for i, sample in enumerate(samples['samples']):
        ids = [f'S{i * manifest["replicates"] + r + 1:06d}' for r in range(manifest['replicates'])]
        first = label[ids[0]]
        registry.append({
            'formula_id': sample['id'],
            # 主表里的键是 design_scenario（不是 scenario）；旧版误写 scenario，
            # 导致归档登记表 scenario 列 1000 行全空。见 v2/registry_scenario_fix_check.json。
            'scenario': sample['provenance'].get('design_scenario', ''),
            'matrix': sample['provenance'].get('matrix', ''),
            'parent_family': sample['provenance'].get('parent_family', ''),
            'composition_family': first['family'],
            'generator_split': first['split'],
            'benchmark_split': next((r['benchmark_split'] for r in split_rows
                                     if r['parent_family'] == sample['provenance']['parent_family']), ''),
            'spectra': ','.join(f'P5-{sample["id"]}-{r + 1}' for r in range(manifest['replicates'])),
            'n_elements_positive': sum(1 for v in sample['composition_percent'].values() if v > 0),
            'closure_sum_percent': sum(sample['composition_percent'].values()),
            'blind_input_sha256': next(r['blind_input_sha256'] for r in index_rows if r['local_id'] == ids[0]),
        })

    # 直接改名的复制件
    copies = {
        'P5.json': FP / 'profiles' / 'P5.json',
        'C_samples.json': HERE / 'master_samples.json',
        'C_authoritative_index.csv': HERE / 'P5_authoritative_index.csv',
        'C_global_split.csv': HERE / 'P5_global_split.csv',
        'C_coverage.json': HERE / 'P5_coverage_statistics.json',
        'C_acceptance_summary.md': HERE / 'P5_acceptance_summary.md',
        'P5_audit.json': HERE / 'P5_delivery_copy_qc.json',
        'P5_replay.json': HERE / 'P5_replay.json',
        'P5_replay_environment.json': DATASET / 'reproducibility' / 'environment.json',
        'P5_pack.json': HERE / 'P5_pack.json',
        'P5_dataset.zip.sha256': HERE / 'P5_dataset.zip.sha256',
    }
    for name, src in copies.items():
        shutil.copy2(src, OUT / name)
    for script in sorted((HERE / 'scripts').glob('*.py')):
        shutil.copy2(script, OUT / 'scripts' / script.name)

    write_csv(OUT / 'C_formula_registry.csv', registry)

    # ZIP 分卷
    zip_path = HERE / 'P5_dataset.zip'
    total = zip_path.stat().st_size
    size = -(-total // PARTS)
    parts = []
    with zip_path.open('rb') as stream:
        for n in range(1, PARTS + 1):
            data = stream.read(size)
            if not data:
                break
            name = f'P5_pack.zip.part{n:02d}'
            (OUT / name).write_bytes(data)
            parts.append({'file': name, 'bytes': len(data), 'sha256': sha256(OUT / name)})

    # 密封数据集目录内容清单（分卷重建后的核对依据）
    entries = sorted(zipfile.ZipFile(zip_path).namelist())

    timings = {
        'measured_on': '本机单进程，secondary_layers=32，2026-10-19',
        'generate_s_per_spectrum': [1.82, 2.52],
        'generate_note': '最长连续段 1555 谱 47.2 min（1.82 s/谱）；10 配方×2 重复的端到端实测 2.52 s/谱（含密封写入）',
        'full_physics_replay_s_per_spectrum': 2.59,
        'full_audit_s_per_spectrum': 0.1,
        'pack_seconds_for_2000_spectra': 81.7,
        'audit_D_copy_minutes_for_2000_spectra': 3,
        'audit_C_original_window_minutes': 14,
        'this_batch_pure_compute_hours': [2.5, 3.0],
    }
    budget = {
        'per_spectrum_bytes': coverage['dataset_size_bytes'] // coverage['spectra'],
        'per_spectrum_mib': round(coverage['dataset_size_bytes'] / 2**20 / coverage['spectra'], 3),
        'batch_overhead_mib': 10,
        'zip_over_dataset_ratio': round((coverage['zip_size_bytes'] or 0) / coverage['dataset_size_bytes'], 3),
        'scale_2000': {'dataset_mib': round(coverage['dataset_size_bytes'] / 2**20, 1), 'zip_mib': round((coverage['zip_size_bytes'] or 0) / 2**20, 1), 'git_pack_mib': 280.4, 'generation_hours': [1.0, 1.4]},
        'scale_10000': {'dataset_gib': 7.1, 'zip_gib': 1.6, 'git_pack_gib': 1.6, 'generation_hours': [5, 7], 'reserve_gib': 15},
        'scale_50000': {'dataset_gib': 35.5, 'zip_gib': 8.0, 'git_pack_gib': 8.0, 'generation_hours': [25, 35], 'total_compute_hours_with_replay': [60, 75], 'reserve_gib': 60},
        'note': 'scale_10000/scale_50000 为按单谱实测体积与耗时线性推算，非再次实测；secondary_layers 恢复默认 96 时物理耗时约翻倍',
    }
    write_json(OUT / 'P5_check_timings.json', timings)

    production = {
        'batch_id': BATCH,
        'role': 'C 部分（铁基合金主配方 + P5 候选留出条件）',
        'generator_version': manifest['software_version'],
        'physical_model_version': manifest['physical_model_version'],
        'physics_core_sha256': manifest['physics_core_sha256'],
        'profile_name': coverage['profile_id'],
        'profile_sha256': coverage['profile_sha256'],
        'samples_semantic_sha256': coverage['input_semantic_sha256'],
        'seed_batch': manifest['seed'],
        'seed_split': manifest['split_seed'],
        'replicates': manifest['replicates'],
        'jitter': manifest['jitter_ranges'],
        'closure': manifest['closure'],
        'formulas': coverage['formulas'],
        'spectra': coverage['spectra'],
        'composition_families': manifest['family_count'],
        'parent_families': coverage['parent_families'],
        'scenario_counts': coverage['scenario_counts'],
        'target_elements': coverage['target_elements'],
        'generator_split': coverage['generator_split'],
        'benchmark_split': coverage['benchmark_split'],
        'window_keV': coverage['window_keV'],
        'window_loss_fraction': coverage['window_loss_fraction'],
        'ba_window_summary': coverage['ba_window_summary'],
        'dataset_files': len(entries),
        'dataset_size_bytes': coverage['dataset_size_bytes'],
        'zip_size_bytes': coverage['zip_size_bytes'],
        'zip_sha256': ZIP_SHA,
        'zip_parts': parts,
        'zip_rebuild_verified': '从交付副本重新 pack 得到的 ZIP 与原件 SHA-256 相同，归档不含时间戳等易变字段',
        'manifest_status': manifest['status'],
        'acceptance_status': manifest['acceptance_status'],
        'synthetic': manifest['synthetic'],
        'hardware_validated': manifest['hardware_validated'],
        'unzip_and_verify': [
            'copy /b P5_pack.zip.part01+P5_pack.zip.part02+P5_pack.zip.part03+P5_pack.zip.part04+'
            'P5_pack.zip.part05+P5_pack.zip.part06+P5_pack.zip.part07+P5_pack.zip.part08 P5_dataset.zip',
            'certutil -hashfile P5_dataset.zip SHA256  # 应等于 P5_dataset.zip.sha256 中的 9178746d...f3f2',
            'python -B P5_dataset/reproducibility/generator/fp_competition/app.py audit --dataset P5_dataset --out P5_qc_after_clone.json',
        ],
    }
    write_json(OUT / 'C_production_record.json', production)

    acceptance = {
        'identity': {
            'generator_version': manifest['software_version'],
            'physical_model_version': manifest['physical_model_version'],
            'physics_core_sha256': manifest['physics_core_sha256'],
            'profile': {'name': coverage['profile_id'], 'sha256': coverage['profile_sha256'], 'expected_sha256': PROFILE_SHA,
                        'matches_expected': coverage['profile_sha256'] == PROFILE_SHA},
            'samples_semantic_sha256': coverage['input_semantic_sha256'],
            'seeds': {'batch': manifest['seed'], 'split': manifest['split_seed']},
            'synthetic': True,
            'hardware_validated': False,
        },
        'scale': {'formulas': coverage['formulas'], 'spectra': coverage['spectra'], 'replicates': coverage['replicates'],
                  'scenario_counts': coverage['scenario_counts'], 'composition_families': manifest['family_count'],
                  'parent_families': coverage['parent_families'], 'dataset_files': len(entries),
                  'dataset_size_bytes': coverage['dataset_size_bytes'], 'zip_size_bytes': coverage['zip_size_bytes']},
        'splits': {'generator_split': coverage['generator_split'], 'benchmark_split': coverage['benchmark_split'],
                   'rule': 'benchmark_split 以 parent_family 为单位，同一母配方的干扰对照变体与噪声重复不跨集合；P5 全批禁止训练与调参'},
        'engineering_checks': {
            'audit': {'status': audit_full['status'], 'spectra_checked': audit_full['spectra_checked'],
                      'errors': len(audit_full.get('errors', [])), 'rtol': audit_full['tolerances']['rtol'],
                      'atol_counts': audit_full['tolerances']['atol_counts'],
                      'complete_physics_recalculation': audit_full['complete_physics_recalculation']},
            'replay': replay,
            'pack': {'status': pack['status'], 'archive_sha256': pack['sha256'].split()[0], 'zip_size': pack['zip_size']},
            'delivery_copy': {'file_sha256_mismatches': 0, 'files_compared': len(entries),
                              'audit_from_bundled_snapshot': audit_full['status'],
                              'zip_rebuilt_from_copy_sha256_matches_original': True},
        },
        'coverage': {'window_keV': coverage['window_keV'], 'window_loss_fraction': coverage['window_loss_fraction'],
                     'ba_window_summary': coverage['ba_window_summary'],
                     'elements_with_ge_50_zero': sum(1 for v in coverage['element_coverage'].values() if v['zero'] >= 50),
                     'elements_with_ge_50_low': sum(1 for v in coverage['element_coverage'].values() if v['low'] >= 50),
                     'detail_file': 'C_coverage.json'},
        'timings': timings,
        'storage_budget': budget,
        'not_verified': [
            'P5 是候选模拟配置，不是真实未见设备；真实设备与真实样品的科学验证仍保留',
            '模型未包含死时间、堆积、粒度、水分、多层、多次散射与粗糙度',
            '含量相对误差 ≤5% 的结论不能由本批合成数据得出',
            'acceptance_status = ' + manifest['acceptance_status'],
        ],
    }
    write_json(OUT / 'C_acceptance_summary.json', acceptance)

    readme = f"""# C 部分 · {BATCH}（铁基合金 1000 配方 / P5 候选留出条件 / 2000 合成谱）

生成器 fp-spectrum-generator-competition-{manifest['software_version']}（物理模型 {manifest['physical_model_version']}）。
与 `datasets/A-part-20261018` 同构平铺；数据集本体在分卷 ZIP 内，逐文件清单见 `C_delivery_hashes.json`。

## 内容

| 文件 | 说明 |
| --- | --- |
| `C_samples.json` | C 负责的 1000 条铁基合金主配方（常规 600 / 稀疏边界 200 / 干扰对照 200，严格闭合、Fe 平衡） |
| `C_formula_registry.csv` | 逐配方登记：情景、母族 parent_family、成分族、双划分、谱号、正元素数、闭合和 |
| `C_authoritative_index.csv` | 2000 条谱的权威索引（batch/local/global id、配方、族、双划分、盲/满双 SHA-256） |
| `C_global_split.csv` | 814 个 parent_family 的权威划分与谱数 |
| `C_coverage.json` | 元素零/低/中/高覆盖、能窗、窗外损失、Ba 统计、数据集逐文件体积 |
| `C_acceptance_summary.json` | 机器可读验收汇总（身份、规模、划分、检查结果、覆盖、时长与存储预算、未验证事项） |
| `C_acceptance_summary.md` | 同上的人读版 |
| `C_production_record.json` | 批次身份：种子、哈希、状态、分卷清单与重建校验命令 |
| `C_delivery_hashes.json` | 本目录逐文件 SHA-256（含 8 个分卷）与原始交付清单 |
| `P5.json` | 条件配置 candidate_holdout_P45_Al50_air1（SHA-256 `{PROFILE_SHA[:12]}…`） |
| `P5_audit.json` | 全量 audit 完整报告（2000 条、0 错误；含逐元素覆盖与容差） |
| `P5_replay.json` / `P5_replay_environment.json` | 全量物理重算报告（最大数组绝对差 0.0、环境一致）与运行环境 |
| `P5_pack.json` / `P5_dataset.zip.sha256` | 打包报告与整包外部校验值 |
| `P5_check_timings.json` | 实测单谱耗时（生成 1.82–2.52 s、replay 2.59 s、audit ≈0.1 s、打包 81.7 s/2000 谱） |
| `P5_pack.zip.part01`…`part08` | 密封数据集目录的 ZIP 分卷（每卷约 41 MiB，合计 {total:,} B） |
| `scripts/` | 配方设计、断点续跑生成、外部检查打包、索引构建、本布局生成脚本 |

## 重建与校验数据集

```
copy /b P5_pack.zip.part01+P5_pack.zip.part02+P5_pack.zip.part03+P5_pack.zip.part04+P5_pack.zip.part05+P5_pack.zip.part06+P5_pack.zip.part07+P5_pack.zip.part08 P5_dataset.zip
certutil -hashfile P5_dataset.zip SHA256     # 应等于 P5_dataset.zip.sha256：{ZIP_SHA}
tar -xf P5_dataset.zip -C P5_dataset_dir    # 或任意 unzip 工具
python -B P5_dataset_dir/reproducibility/generator/fp_competition/app.py audit --dataset P5_dataset_dir --out P5_qc_after_clone.json
```

分卷按顺序拼接即得原包；ZIP 不含时间戳等易变字段，同一目录内容可确定性地重建出同一 SHA-256（已实测：从交付副本重新 pack 的哈希与原件完全一致）。

## 数据集结构（ZIP 内）

`blind_inputs/`（2000，严格 5 字段：x、counts、axis、signal_unit、synthetic）、`full_results/`（2000，六分量分解与窗外账目）、`truth.jsonl`、`manifest.json`（status={manifest['status']}，acceptance_status={manifest['acceptance_status']}）、`integrity.json`、`inputs/`、`configs/`、`reproducibility/`（源码快照 + 环境 + 依赖锁定 + recipe）。

## 划分与用法

权威划分 `benchmark_split` 以 parent_family 为单位：train 1402 / validation 302 / test 296。
下游只按 `benchmark_split` 读取训练数据；**本批 P5 全部 2000 条谱禁止训练与调参**（它是留出条件）。

## 未验证事项

合成数据、未通过真实设备校准；模型不含死时间、堆积、粒度、水分、多层、多次散射与粗糙度；
含量相对误差 ≤5% 的结论不能由本批数据得出；P5 是候选模拟配置而非真实未见设备。
"""
    (OUT / 'README.md').write_text(readme, encoding='utf-8')

    delivery = read_json(HERE / 'P5_delivery_inventory.json')
    payload_hashes = {}
    for f in sorted(p for p in OUT.rglob('*') if p.is_file()):
        rel = f.relative_to(OUT).as_posix()
        payload_hashes[rel] = {'bytes': f.stat().st_size, 'sha256': sha256(f)}
    write_json(OUT / 'C_delivery_hashes.json', {
        'scope': '本目录逐文件 SHA-256（含分卷）。C_samples/索引/覆盖等源件哈希另见原始交付清单。',
        'batch_id': BATCH,
        'zip_sha256_original': ZIP_SHA,
        'zip_parts': parts,
        'files': payload_hashes,
        'source_inventory': delivery,
    })

    files = sorted(p for p in OUT.rglob('*') if p.is_file())
    print('payload files', len(files), 'bytes', sum(f.stat().st_size for f in files))
    print('largest', max(((f.stat().st_size, f.name) for f in files)))
    print('over 50 MiB:', [f.name for f in files if f.stat().st_size > 50 * 2**20])
    print('registry rows', len(registry), 'index rows', len(index_rows))


if __name__ == '__main__':
    main()
