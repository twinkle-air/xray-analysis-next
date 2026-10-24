"""Assemble the member-B round-3 delivery from sealed batches and their QC evidence.

Produces (inside this delivery directory):
  production_v1/<batch>.zip + .zip.sha256
  reports/<batch>/{audit,replay,window_budget,commands,summary}.json
  reports/external_record_index.csv          one row per spectrum (1746)
  environment.json                          interpreter, packages, frozen identities
  delivery_manifest.json                    every delivered file with size + sha256
  selfcheck_summary.json                    aggregated check scope and results
  README.md                                 counts, commands, environment, timing, size
"""
from __future__ import annotations
import csv
import hashlib
import json
import platform
import shutil
import sys
import time
import zipfile
from pathlib import Path

DELIVERY = Path(__file__).resolve().parent
ROOT = Path(__import__('os').environ.get('B_REPO_ROOT', str(DELIVERY / 'repo')))
FREEZE = ROOT / 'datasets/round3/shared/freeze_v1'
RELEASE = ROOT / 'datasets/round3/shared/releases/owner_release_v3.json'
RUNNER = ROOT / 'datasets/round3/shared/production_tools/run_batch.py'
OUT = ROOT / 'work/round3/member_B_production_v1'
PROD = DELIVERY / 'production_v1'
REPORTS = DELIVERY / 'reports'


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def fail(message: str) -> None:
    print('ERROR: ' + message)
    sys.exit(1)


def main() -> None:
    plan = read_json(FREEZE / 'batch_plan.json')
    batches = [b for b in plan['batches'] if b['member'] == 'B']
    expected = sum(b['spectra'] for b in batches)

    PROD.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)

    rows: list[dict] = []
    audited = replayed = 0
    max_diff = 0.0
    budgets_ok = True
    archives = 0
    archive_bytes = 0
    missing = []
    record_rows: list[dict] = []

    for batch in batches:
        bid = batch['batch_id']
        sealed = OUT / 'sealed' / bid
        qc = OUT / 'qc' / bid
        if not sealed.is_dir() or not qc.is_dir():
            missing.append(bid)
            continue
        summary = read_json(qc / 'summary.json')
        audit = read_json(qc / 'audit.json')
        replay = read_json(qc / 'replay.json')
        budget = read_json(qc / 'window_budget.json')

        if summary.get('status') not in ('passed_batch_QC', 'passed_pilot_QC'):
            fail(f'{bid}: unexpected QC status {summary.get("status")}')
        if audit.get('status') != 'passed':
            fail(f'{bid}: audit not passed')
        if replay.get('status') != 'passed' or not replay.get('complete_physics_recalculation'):
            fail(f'{bid}: replay not passed')
        if not budget.get('passed'):
            fail(f'{bid}: window budget failed')

        zip_src = qc / f'{bid}.zip'
        if not zip_src.is_file():
            fail(f'{bid}: archive missing')
        digest = sha256(zip_src)
        if digest != summary['archive_sha256']:
            fail(f'{bid}: archive sha256 differs from summary')
        if zip_src.stat().st_size != summary['archive_bytes']:
            fail(f'{bid}: archive size differs from summary')
        with zipfile.ZipFile(zip_src) as zf:
            if zf.testzip() is not None:
                fail(f'{bid}: zip CRC failure')

        dst_zip = PROD / zip_src.name
        if not (dst_zip.is_file() and dst_zip.stat().st_size == zip_src.stat().st_size):
            shutil.copy2(zip_src, dst_zip)
        (PROD / (zip_src.name + '.sha256')).write_text(
            f'{digest}  {zip_src.name}\n', encoding='utf-8')

        target = REPORTS / bid
        target.mkdir(parents=True, exist_ok=True)
        for name in ('audit.json', 'replay.json', 'window_budget.json', 'commands.json', 'summary.json'):
            shutil.copy2(qc / name, target / name)

        with (qc / 'external_record_index.csv').open(encoding='utf-8', newline='') as fh:
            record_rows.extend(list(csv.DictReader(fh)))

        audited += int(audit['spectra_checked'])
        replayed += int(replay['spectra_recalculated'])
        max_diff = max(max_diff, float(replay['maximum_absolute_array_difference']))
        budgets_ok = budgets_ok and bool(budget['passed'])
        archives += 1
        archive_bytes += zip_src.stat().st_size
        rows.append({
            'batch_id': bid,
            'phase': batch['phase'],
            'profile_id': batch['profile_id'],
            'spectra': int(summary['spectra']),
            'archive': zip_src.name,
            'archive_bytes': zip_src.stat().st_size,
            'archive_sha256': digest,
            'audit': audit['status'],
            'replay': replay['status'],
            'window_budget_passed': bool(budget['passed']),
            'freeze_manifest_sha256': summary['freeze_manifest_sha256'],
        })

    if missing:
        fail('missing sealed batches: ' + ', '.join(missing))

    total = sum(r['spectra'] for r in rows)
    if total != expected:
        fail(f'spectra total {total} != frozen expectation {expected}')
    if len(record_rows) != total:
        fail(f'external record index has {len(record_rows)} rows, expected {total}')

    # native ids restart at S000001 inside every batch, so uniqueness is batch-qualified.
    for rec in record_rows:
        rec['record_uid'] = f"{rec['batch_id']}:{rec['native_id']}"
    uids = [r['record_uid'] for r in record_rows]
    if len(set(uids)) != total:
        fail('external record index contains duplicate batch-qualified ids')
    blind = [r['opaque_blind_id'] for r in record_rows]
    if len(set(blind)) != total:
        fail('external record index contains duplicate opaque blind ids')

    recipes = {r['recipe_id'] for r in record_rows}
    families = {r['design_family_id'] for r in record_rows}
    usage_counts: dict[str, int] = {}
    for r in record_rows:
        usage_counts[r['usage']] = usage_counts.get(r['usage'], 0) + 1
    if len(recipes) != 250:
        fail(f'record index covers {len(recipes)} recipes, expected 250')
    if len(families) != 105:
        fail(f'record index covers {len(families)} families, expected 105')
    if sum(usage_counts.values()) != total:
        fail(f'usage split does not cover every record: {usage_counts}')
    challenge_spectra = sum(r['spectra'] for r in rows if r['phase'] == 'challenge')
    if challenge_spectra != 246 or usage_counts.get('internal_holdout', 0) != 492:
        fail(f'unexpected challenge/usage split {usage_counts} challenge={challenge_spectra}')

    index_path = REPORTS / 'external_record_index.csv'
    with index_path.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(record_rows[0].keys()))
        writer.writeheader()
        writer.writerows(record_rows)

    env = {
        'python': sys.version.split()[0],
        'implementation': platform.python_implementation(),
        'system': platform.system(),
        'machine': platform.machine(),
        'packages': package_versions(),
        'freeze_manifest_sha256': sha256(FREEZE / 'freeze_manifest.json'),
        'owner_release_sha256': sha256(RELEASE),
        'runner_sha256': sha256(RUNNER),
        'generator_version': '0.2.1',
        'physics_core_version': '0.2.0',
        'physics_core_sha256': read_json(FREEZE / 'input_identity.json')['physics_core_sha256'],
        'command': 'powershell -NoProfile -File datasets/round3/shared/production_tools/run_member_full.ps1 -Member B -Python python',
        'note': 'Batches executed through run_batch.py with --heldout-qc for T profiles; 2-3 concurrent batches per run, capped by available memory on this host.',
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    }
    (DELIVERY / 'environment.json').write_text(
        json.dumps(env, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    base_total = sum(r['spectra'] for r in rows if r['phase'] != 'challenge')
    t_total = total - base_total

    summary = {
        'status': 'passed_member_full_selfcheck_pending_coordinator_review',
        'member': 'B',
        'round_id': 'round3',
        'candidate_recipes': 250,
        'design_families': 105,
        'actual_recipe_count': len(recipes),
        'actual_family_count': len(families),
        'usage_counts': usage_counts,
        'actual_base_spectra': base_total,
        'pilot_included_in_base': 90,
        'actual_T_spectra': t_total,
        'total_actual_spectra': total,
        'native_sealed_batches': archives,
        'all_spectra_audited': audited,
        'all_spectra_full_physics_replayed': replayed,
        'maximum_absolute_replay_array_difference': max_diff,
        'all_window_budgets_passed': budgets_ok,
        'all_ZIP_SHA_CRC_and_internal_integrity_passed': True,
        'external_record_index_rows': len(record_rows),
        'source_versions': {'generator': '0.2.1', 'physics_core': '0.2.0'},
        'physics_core_sha256': env['physics_core_sha256'],
        'freeze_manifest_sha256': env['freeze_manifest_sha256'],
        'owner_release_sha256': env['owner_release_sha256'],
        'native_generator_split_used_as_research_split': False,
        'eligible_for_training': False,
        'training_inclusion_approved': False,
        'external_independently_blinded': False,
        'concentration_accuracy_verified': False,
        'actual_training_spectra': 0,
        'actual_synthetic_spectra_generated': total,
        'production_started': True,
        'production_complete': True,
        'native_archive_bytes': archive_bytes,
        'unresolved_errors': None,
        'missing_items': None,
        'full_delivery': 'production_v1/README.md',
        'batches': rows,
    }
    (DELIVERY / 'selfcheck_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    files = []
    for path in sorted(DELIVERY.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(DELIVERY).as_posix()
        if rel in ('delivery_manifest.json',):
            continue
        if rel.startswith('repo/'):
            continue
        files.append({
            'path': rel,
            'size_bytes': path.stat().st_size,
            'sha256': sha256(path),
            'role': role_of(rel),
        })
    manifest = {
        'is_template': False,
        'usable_for_generation': False,
        'production_started': True,
        'round_id': 'round3',
        'status': 'complete_pending_coordinator_review',
        'member': 'B',
        'hash_algorithm': 'sha256',
        'path_base': 'datasets/round3/member_B',
        'files': files,
        'file_entry_fields': ['path', 'size_bytes', 'sha256', 'role'],
        'coverage_completed': True,
    }
    (DELIVERY / 'delivery_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    write_readme(summary, env, index_path, len(record_rows))
    print(json.dumps({k: summary[k] for k in (
        'total_actual_spectra', 'actual_base_spectra', 'actual_T_spectra',
        'native_sealed_batches', 'all_spectra_audited', 'all_spectra_full_physics_replayed',
        'maximum_absolute_replay_array_difference')}, ensure_ascii=False, indent=2))
    print('delivered files:', len(files))


def package_versions() -> dict:
    import importlib.metadata as md
    wanted = ('numpy', 'scipy', 'xraylib')
    out = {}
    for name in wanted:
        try:
            out[name] = md.version(name)
        except Exception:
            out[name] = None
    return out


def role_of(rel: str) -> str:
    if rel.endswith('.zip'):
        return 'native_sealed_archive'
    if rel.endswith('.zip.sha256'):
        return 'archive_checksum'
    if rel.startswith('reports/') and rel.endswith('.json'):
        return 'qc_report'
    if rel.endswith('external_record_index.csv'):
        return 'external_record_index'
    if rel == 'selfcheck_summary.json':
        return 'selfcheck_summary'
    if rel == 'environment.json':
        return 'environment_evidence'
    if rel == 'README.md':
        return 'readme'
    if rel.startswith('candidates/') or rel.startswith('inputs/'):
        return 'frozen_candidate_input'
    return 'delivery_document'


def write_readme(summary: dict, env: dict, index_path: Path, index_rows: int) -> None:
    batches = summary['batches']
    usage = summary.get('usage_counts', {})
    usage_train = usage.get('train', 0)
    usage_valid = usage.get('validation', 0)
    usage_hold = usage.get('internal_holdout', 0)
    text = f"""# 第三轮成员 B：全量生产交付

状态：**成员 B 的 1,746 条谱已在本地完成全量生成与自检，等待 owner 统一复核。** 生产放行不等于数据审查通过；`training_inclusion_approved` 仍为 `false`。

## 数量

| 项目 | 数量 |
| --- | --- |
| 候选配方 | 250（硅酸盐/氧化物 150、富铁氧化物 100） |
| 设计族（合并前） | 105 |
| 基础谱 | {summary['actual_base_spectra']:,}（其中 pilot 批次 90 条计入基础谱） |
| 追加 T 挑战谱 | {summary['actual_T_spectra']:,}（41 个留出配方 × 6 谱） |
| 合计 | {summary['total_actual_spectra']:,} |
| 原生密封批次 | {summary['native_sealed_batches']} |

## 执行

冻结依据为已合并 PR #31 的 `owner_release_v3`，配方/族用途/profile/噪声种子/物理核心全部按 `freeze_v1`，未自选家族、未换种子、未加 jitter。

```powershell
# 官方入口（本仓库根目录）
powershell -NoProfile -File datasets/round3/shared/production_tools/run_member_full.ps1 -Member B -Python python
```

本机实际执行：`run_batch.py` 逐批调用（T 批次显式 `--heldout-qc`），每批独立 sealed/QC 目录，2–3 批并发以适配本机可用内存；批次顺序与 `batch_plan.json` 一致，已完成的冻结批次不重跑、不覆盖。

- 冻结清单：`freeze_manifest_sha256 = {env['freeze_manifest_sha256']}`
- owner 放行：`owner_release_sha256 = {env['owner_release_sha256']}`
- 运行器：`runner_sha256 = {env['runner_sha256']}`
- 物理核心：`physics_core_sha256 = {env['physics_core_sha256']}`

## 自检范围与结果

- audit：覆盖 {summary['all_spectra_audited']:,} 条谱，全部 `passed`；
- 完整物理 replay：覆盖 {summary['all_spectra_full_physics_replayed']:,} 条谱，最大绝对数组差 `{summary['maximum_absolute_replay_array_difference']}`；
- 窗外预算：{summary['native_sealed_batches']} 批全部通过 `window_budget.json`；
- 归档：每个原生 ZIP 的 SHA-256 与批内 `summary.json` 一致，CRC 校验通过；
- 外置记录索引：`reports/external_record_index.csv`，{index_rows:,} 行；`record_uid`（`batch_id:native_id`）全局唯一，`opaque_blind_id` 全部唯一。

逐批证据在 `reports/<batch>/`，含 `audit.json`、`replay.json`、`window_budget.json`、`commands.json`（真实命令与退出码）、`summary.json`。

## 环境

- Python {env['python']}（{env['implementation']}），{env['system']} {env['machine']}
- numpy {env['packages'].get('numpy')}、scipy {env['packages'].get('scipy')}、xraylib {env['packages'].get('xraylib')}
- 生成器 0.2.1 / 物理核心 0.2.0

## 目录

```text
production_v1/            {summary['native_sealed_batches']} 个原生无损 ZIP + 各自 .sha256
reports/<batch>/          逐批 audit / replay / window_budget / commands / summary
reports/external_record_index.csv   覆盖全部 {index_rows:,} 条谱的外置索引
delivery_manifest.json    全部交付文件的大小与 SHA-256
selfcheck_summary.json    实际检查范围与结果
environment.json          解释器、依赖与冻结身份
```

## 边界与未决

- T 谱只用于留出物理 QC，**未**用于训练、校正拟合、响应字典或选参；`training_inclusion_approved = false`。
- 原生生成器 split 未当作研究划分；外部盲 ID 由隔离索引映射。用途统计：train {usage_train} 条、validation {usage_valid} 条、internal_holdout {usage_hold} 条（其中 246 条为内部留出的基础谱，另 246 条为 T 挑战谱）。
- 合成数据的自检通过**不代表**真实设备准确度；`scientific_accuracy_verified = false`、`concentration_accuracy_verified = false`。
- 本交付不含展开后的谱目录，只含原生密封 ZIP 与其 QC 证据。
- 已冻结候选、换算/补偿账目与输入身份保持在 `candidates/`、`inputs/`，未重写。

## 批次表

| batch | phase | profile | spectra | zip sha256（前 12 位） |
| --- | --- | --- | ---: | --- |
"""
    for b in batches:
        text += (f"| {b['batch_id']} | {b['phase']} | {b['profile_id']} | {b['spectra']} | "
                 f"`{b['archive_sha256'][:12]}` |\n")
    (DELIVERY / 'README.md').write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
