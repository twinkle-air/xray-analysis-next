"""C 部分：把已推送的 P5 批次标注为"未通过评审、仅候选试产"（PR #2 要求）。

不动密封数据：`truth.jsonl`、`manifest.json`、ZIP 与分卷一律不重写，批次身份保留。
只在包外目录新增/修订说明性文件，并同步 `C_delivery_hashes.json` 的逐文件哈希
（把原 README 的哈希留在审计记录里）。

写入（payload 目录 `github_payload/datasets/C-part-20261018/`）：
  - `C_batch_status.json` / `C_batch_status.md`：状态、评审发现、隔离策略、修复方向
  - `README.md`：修正"划分与用法"段（原文把 train/validation/test 说成可读训练数据）
  - `C_delivery_hashes.json`：重算逐文件 SHA-256，附 `annotation` 审计块
"""
from __future__ import annotations
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PAYLOAD = HERE / 'github_payload' / 'datasets' / 'C-part-20261018'
V2 = HERE / 'v2'

BATCH_ID = 'C-part-20261018'
BRANCH = 'c-part-20261018'
COMMIT = 'cdc4f739c01446e24c0f3701a94cf2e04a15fbdf'
BASE = '64f4bfd7'
PR_NUMBER = 2
PR_URL = 'https://github.com/twinkle-air/xray-analysis-next/pull/2'
ZIP_SHA = '9178746d90e26e45d64a8a9f15ca35736ba363110d535d787e3e589fbf3bf3f2'

FINDINGS = [
    {'id': 'P1-1', 'severity': 'P1',
     'title': '留出批次被标成可训练划分',
     'evidence': 'v1 索引 benchmark_split = train 1402 / validation 302 / test 296；'
                 '交付 README 写"下游只按 benchmark_split 读取训练数据"。',
     'status': 'fixed_in_v2',
     'fix': '全部 2000 行改为 holdout_status=condition_heldout、benchmark_split=heldout、'
            'usage_policy=pilot_only_isolated_from_training_and_tuning；原训练语义降级为'
            '描述性字段 recipe_family_split。见 v2/index_policy_check_v2.md。'},
    {'id': 'P1-2', 'severity': 'P1',
     'title': '相同采用组成跨集合（泄漏）',
     'evidence': '9 组完全相同的组成落在不同集合；根因是划分按设计族 parent_family，'
                 '而生成器族按实际采用组成。',
     'status': 'fixed_in_v2',
     'fix': '并查集把「实际采用组成 ∪ parent_family ∪ 生成器族 ∪ 噪声重复」合成 leak_group，'
            '划分只在 leak_group 粒度进行并断言不跨集合。'},
    {'id': 'P2-1', 'severity': 'P2',
     'title': '1000 行配方仅 944 种独立组成',
     'evidence': 'v1 主表复算：distinct=944，重复组 34；稀疏/边界的 Fe 变化被 100% 闭合归一化抹平，'
                 '"元素=0" 在只存非零元素的采用组成里不留痕。',
     'status': 'fixed_in_v2',
     'fix': '低含量档由元素自身上限推导；零配方带唯一共存签名；全局去重并断言 1000 行 1000 种。'},
    {'id': 'P2-2', 'severity': 'P2',
     'title': '干扰对照被写死的 Ni=8 与 Fe 平衡破坏',
     'evidence': 'v1 每行 `close_percent({**vals, "Ni": 8.0, "Fe": fe})`：对含 Ni 时目标被覆盖，'
                 '含 Fe 的 3 对里 Fe 既是基体又是对照变量。',
     'status': 'fixed_in_v2',
     'fix': '干扰对去掉全部含 Fe 组合；背景母配方不含 a/b/Fe 且同族两档共用；'
            '逐 variant 断言存在性、背景值不被改写与 equal/1:5/5:1 实际比值。'},
    {'id': 'P2-3', 'severity': 'P2',
     'title': '548/600 常规配方越出自身声明范围',
     'evidence': 'v1 主表复算：常规情景 548 行越界（如 C=1.397% 声明上限 0.8%、'
                 'W=5.04% 声明上限 2%），合计 1334 项；采样时只校验 Fe。',
     'status': 'fixed_in_v2',
     'fix': '按每元素冻结上下限先验采样，闭合后逐字段按该行 ranges_percent 断言，'
            'v2 主表 1000 行越界 0 项。'},
]

USAGE_BLOCK = """## 划分与用法（v2 修正）

**本批次未通过独立评审，定位为候选试产（pilot-only），并从所有训练/调参入口隔离。**
状态见 `C_batch_status.md`；评审意见见 PR #2。

- 权威字段：每一行 `holdout_status=condition_heldout`、`benchmark_split=heldout`、
  `usage_policy=pilot_only_isolated_from_training_and_tuning`。
- `recipe_family_split`（train/validation/test）只描述配方来源，**不得作为基准划分**。
- 同一 leak_group（实际采用组成 ∪ parent_family ∪ 生成器族 ∪ 噪声重复）不跨集合；
  v1 里 9 组相同组成跨集合的问题在 v2 索引中已消除并逐条断言。
- 下游入口请用 `scripts/c_pilot_guard.py::training_rows()`：请求本批次任何划分都会抛
  `PilotIsolationError`，不会静默返回可训练行。
- 需要可训练数据请使用已通过评审的批次（A/B 部分）。
"""


def sha256(path: Path):
    d = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            d.update(block)
    return d.hexdigest()


def patch_readme():
    path = PAYLOAD / 'README.md'
    original = path.read_text(encoding='utf-8')
    old_hash = sha256(path)
    banner = (f'\n> **状态：未通过独立评审（PR #{PR_NUMBER} requested changes），'
              f'仅候选试产（pilot-only），禁止用于训练与调参。** 详见 `C_batch_status.md`。\n')
    text = original
    if 'C_batch_status.md' not in text:
        m = re.search(r'^(#[^\n]*\n)', text)
        text = text[:m.end()] + banner + text[m.end():]
    text = re.sub(r'## 划分与用法\n.*?(?=\n## )', USAGE_BLOCK.rstrip() + '\n', text, flags=re.S)
    path.write_text(text, encoding='utf-8')
    return old_hash, sha256(path)


def refresh_hashes(readme_new_sha):
    path = PAYLOAD / 'C_delivery_hashes.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    files = {f.relative_to(PAYLOAD).as_posix(): {'bytes': f.stat().st_size, 'sha256': sha256(f)}
             for f in sorted(PAYLOAD.rglob('*'))
             if f.is_file() and f.name != 'C_delivery_hashes.json'}
    data['files'] = files
    data['scope'] = ('本目录逐文件 SHA-256（不含卷内清单）。密封数据集与分卷未重写；'
                     '本清单在候选标注后重算，原 README 哈希见 annotation。')
    data['annotation'] = {
        'annotated_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'reason': 'PR #2 requested changes：批次定位改为 review_failed / workflow_pilot_only',
        'sealed_data_rewritten': False,
        'zip_sha256_unchanged': data.get('zip_sha256_original') == ZIP_SHA,
        'readme_sha256_before': None,
        'readme_sha256_after': readme_new_sha,
        'file_count': len(files),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data


def ship_v2_artifacts():
    """把 v2 的纠正索引/划分/覆盖/守卫随批次目录一起发布（原文件保留供审计）。"""
    (PAYLOAD / 'scripts').mkdir(exist_ok=True)
    pairs = {
        'index_v2.csv': 'C_authoritative_index_v2.csv',
        'global_split_v2.csv': 'C_global_split_v2.csv',
        'coverage_v2.json': 'C_coverage_v2.json',
        'index_policy_check_v2.json': 'C_index_policy_check_v2.json',
        'index_policy_check_v2.md': 'C_index_policy_check_v2.md',
        'pilot_guard_selftest.json': 'C_pilot_guard_selftest.json',
        'pilot_isolation.json': 'pilot_isolation.json',
    }
    copied = []
    for src, dst in pairs.items():
        p = V2 / src
        if p.is_file():
            shutil.copyfile(p, PAYLOAD / dst)
            copied.append(dst)
    shutil.copyfile(HERE / 'scripts' / 'c_pilot_guard.py',
                    PAYLOAD / 'scripts' / 'c_pilot_guard.py')
    copied.append('scripts/c_pilot_guard.py')
    return copied


def main():
    checks = json.loads((V2 / 'index_policy_check_v2.json').read_text(encoding='utf-8'))
    guard = json.loads((V2 / 'pilot_guard_selftest.json').read_text(encoding='utf-8'))
    design = json.loads((V2 / 'design_selfcheck_v2.json').read_text(encoding='utf-8'))
    shipped = ship_v2_artifacts()
    old_readme, new_readme = patch_readme()

    status = {
        'batch_id': BATCH_ID,
        'status': 'review_failed',
        'positioning': 'workflow_pilot_only',
        'may_be_used_for_training': False,
        'may_be_used_for_tuning': False,
        'heldout_condition': True,
        'review': {'pr_number': PR_NUMBER, 'pr_url': PR_URL, 'verdict': 'requested_changes',
                   'merged': False, 'reviewed_on': '2026-10-19'},
        'branch': {'name': BRANCH, 'commit': COMMIT, 'base_prefix': BASE,
                   'landing_directory': f'datasets/{BATCH_ID}'},
        'sealed_batch_identity': {
            'preserved': True, 'rewritten': False,
            'zip_sha256': ZIP_SHA,
            'input_semantic_sha256': checks['coverage']['input_semantic_sha256'],
            'physics_core_sha256': checks['coverage']['physics_core_sha256'],
            'dataset_manifest_status': 'complete（未改动）',
            'note': '失败批次的 truth/manifest/ZIP/分卷均不重写，身份保留以便追溯。'},
        'findings': FINDINGS,
        'v2_remediation': {
            'design': {'script': 'scripts/design_c_alloy_formulas_v2.py',
                       'master': 'v2/master_samples_v2.json',
                       'rows': design['rows'],
                       'distinct_compositions': design['distinct_compositions'],
                       'rows_with_range_violations': design['rows_with_range_violations'],
                       'passed': design['passed']},
            'index_split': {'script': 'scripts/build_p5_index_v2.py',
                            'leak_groups': checks['checks']['leak_groups'],
                            'uniform_holdout': checks['checks']['uniform_holdout'],
                            'identical_compositions_crossing_split':
                                checks['checks']['identical_compositions_crossing_split'],
                            'passed': checks['checks']['passed']},
            'isolation_guard': {'script': 'scripts/c_pilot_guard.py',
                                'blocked_entries': [k for k, v in guard.items()
                                                    if k.endswith('_entry') and v == 'blocked'],
                                'passed': guard['passed']},
            'generation': {'started': False,
                           'reason': '按要求先出验证报告，用户批准后再启动 2000 谱重生成。'},
            'shipped_files': shipped},
        'v1_baseline_recomputed': design['v1_baseline_recomputed'],
    }
    (PAYLOAD / 'C_batch_status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2),
                                                 encoding='utf-8')

    lines = [f'# 批次状态 · {BATCH_ID}', '',
             f'**未通过独立评审（PR #{PR_NUMBER}：requested changes，未合并）；'
             f'本批次定位为候选试产（workflow pilot-only），禁止用于训练与调参。**', '',
             '## 密封批次身份（保留，不重写）', '',
             f'- 分支 `{BRANCH}`，提交 `{COMMIT}`，基线 `{BASE}…`，落点 `datasets/{BATCH_ID}`',
             f'- 数据集 ZIP SHA-256：`{ZIP_SHA}`',
             f'- 主表语义摘要：`{status["sealed_batch_identity"]["input_semantic_sha256"]}`',
             '- `truth.jsonl` / `manifest.json` / 分卷：未改动。失败批次身份保留以便追溯。', '',
             '## 评审发现与修复状态', '',
             '| 编号 | 级别 | 问题 | 证据 | v2 状态 |', '| --- | --- | --- | --- | --- |']
    for f in FINDINGS:
        lines.append(f'| {f["id"]} | {f["severity"]} | {f["title"]} | {f["evidence"]} | {f["status"]} |')
    lines += ['', '## v2 修复要点（代码与自检已完成，数据未重生成）', '',
              f'- 配方设计：1000 行 → **独立采用组成 {design["distinct_compositions"]}**、'
              f'**越出自身声明范围的行 {design["rows_with_range_violations"]}**、'
              f'干扰族 {design["interference_families"]} × 5 变体、含 Fe 干扰对 '
              f'{design["interference_pairs_containing_Fe"] or "无"}（自检 passed={design["passed"]}）',
              f'- 索引/划分：全部行 `benchmark_split=heldout`；并查集 leak_group '
              f'{checks["checks"]["leak_groups"]} 个；相同组成跨集合 '
              f'{checks["checks"]["identical_compositions_crossing_split"]}（'
              f'passed={checks["checks"]["passed"]}）',
              f'- 入口隔离：`scripts/c_pilot_guard.py` train/validation/test 三入口全部拒绝'
              f'（passed={guard["passed"]}）',
              '- 重生成尚未启动，等待验证报告获批。', '',
              '## 下游使用规则', '',
              '1. 不要把本批次任何谱用于训练、调参或阈值挑选；请改用已通过评审的 A/B 批次。',
              '2. 读取本批次请走 `c_pilot_guard.training_rows()`，它会拒绝而非静默放行。',
              '3. `README.md` 里"按 benchmark_split 读取训练数据"的旧说法已作废（该段已改写）。',
              '']
    (PAYLOAD / 'C_batch_status.md').write_text('\n'.join(lines), encoding='utf-8')

    hashes = refresh_hashes(new_readme)
    hashes['annotation']['readme_sha256_before'] = old_readme
    (PAYLOAD / 'C_delivery_hashes.json').write_text(json.dumps(hashes, ensure_ascii=False, indent=2),
                                                    encoding='utf-8')
    changed = [k for k in ('README.md', 'C_batch_status.json', 'C_batch_status.md',
                           'C_delivery_hashes.json') if k in hashes['files']]
    (V2 / 'annotation_plan.json').write_text(json.dumps({
        'payload': str(PAYLOAD), 'files_total': len(hashes['files']),
        'changed_or_added': changed, 'shipped_v2_files': shipped,
        'unchanged_guarantee': {'zip_parts': 8, 'sealed_dataset': 'not in this directory',
                                'zip_sha256': ZIP_SHA},
        'push_next': '待用户批准后：向分支 c-part-20261018 追加一次仅文档改动，并在 PR #2 回复逐条要点。'},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print('annotated', len(hashes['files']), 'files;', changed)


if __name__ == '__main__':
    main()
