"""C 部分：第二轮评审修正——把 v2 代码与主表随批次提交，并改掉两处不实说明。

复审两条（2026-10-19）：
1. 三项配方问题标成"已修复"，但引用的新脚本与 v2 主表没有提交，评审无法验证；
2. 说明里把 A/B 试产数据推荐为可训练数据，与它们自身的用途限制冲突。

做法：
- 把 v2 的 6 个脚本与 `v2/` 下的主表、设计自检、索引/划分/覆盖/守卫/预检/复现对账
  全部复制进载荷目录（纯新增；不触碰密封数据与分卷）；
- 发现状态从 `fixed_in_v2` 改为 `fixed_in_v2_code_archived_batch_unchanged`，
  并在每处都写清"已消除只针对 v2 主表，归档批次的数据未变"；
- 删除"改用 A/B 批次"的可训练推荐，README / 状态文件 / 守卫文案三处同步；
- 重算 `C_delivery_hashes.json`，并与远端提交 `5c9439f…` 的 tree 逐文件对 blob id，
  产出精确的 added/modified 清单交给推送脚本。
"""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent            # C_part
PAYLOAD = HERE / 'github_payload' / 'datasets' / 'C-part-20261018'
V2 = HERE / 'v2'
SCRIPTS = HERE / 'scripts'
WORK = Path('D:/xnext-c-push')
GIT = r'C:/Program Files/Git/ucrt64/bin/git.exe'
REMOTE_COMMIT = '5c9439ffd7781ffc1c8784babbc87ecaa64e5f75'
TARGET = 'datasets/C-part-20261018'
BATCH_ID = 'C-part-20261018'
ZIP_SHA = '9178746d90e26e45d64a8a9f15ca35736ba363110d535d787e3e589fbf3bf3f2'

SHIP_SCRIPTS = ('design_c_alloy_formulas_v2.py', 'build_p5_index_v2.py', 'c_pilot_guard.py',
                'reproduce_v2_check.py', 'pregenerate_dryrun_v2.py', 'v2_generation_status.py',
                'generate_v2_batch.py', 'annotate_candidate_batch.py',
                'check_review_findings.py', 'check_doc_references.py', 'annotate_round2.py',
                'verify_annotation_push.py', 'build_github_payload.py',
                'fix_registry_scenario.py')
# v2/ 原样发布（脚本输出），另有若干以交付名重写到目录根
SHIP_V2 = ('master_samples_v2.json', 'design_selfcheck_v2.json', 'design_selfcheck_v2.md',
           'index_v2.csv', 'global_split_v2.csv', 'coverage_v2.json',
           'index_policy_check_v2.json', 'index_policy_check_v2.md',
           'pilot_guard_selftest.json', 'pilot_isolation.json', 'pregenerate_dryrun.json',
           'generation_status_v2.json', 'generation_status_v2.md',
           'reproduction_check_v2.json', 'reproduction_check_v2.md',
           'review_findings_check.json', 'annotation_push_verification.json',
           'registry_scenario_fix_check.json', 'doc_reference_check.json',
           'C_v2_verification_report.md')
ROOT_RENAMES = {'index_v2.csv': 'C_authoritative_index_v2.csv',
                'global_split_v2.csv': 'C_global_split_v2.csv',
                'coverage_v2.json': 'C_coverage_v2.json',
                'index_policy_check_v2.json': 'C_index_policy_check_v2.json',
                'index_policy_check_v2.md': 'C_index_policy_check_v2.md',
                'pilot_guard_selftest.json': 'C_pilot_guard_selftest.json',
                'pilot_isolation.json': 'pilot_isolation.json',
                'master_samples_v2.json': 'C_samples_v2.json'}
# 另存名发布的证据件：同一策略分别跑在归档批次与新生的 v2 批次上
SHIP_EXTRA = (('v2_datacheck/index_policy_check_v2.json', 'v2/index_policy_check_v2_on_v2_data.json'),
              ('v2_datacheck/index_policy_check_v2.md', 'v2/index_policy_check_v2_on_v2_data.md'))

USAGE_BLOCK = """## 划分与用法（v2 修正）

**本批次未通过独立评审（两轮均为 requested changes），定位为候选试产（pilot-only）并归档，
禁止用于训练与调参。** 状态见 `C_batch_status.md`，可复现的修复代码见第 "v2 可复现代码" 一节。

- 权威字段：每一行 `holdout_status=condition_heldout`、`benchmark_split=heldout`、
  `usage_policy=pilot_only_isolated_from_training_and_tuning`。
- `recipe_family_split`（train/validation/test）只描述配方来源，**不得作为基准划分**。
- 同一 leak_group（实际采用组成 ∪ parent_family ∪ 生成器族 ∪ 噪声重复）不跨集合；
  v1 里 9 组相同组成跨集合的问题在 v2 索引中已消除并逐条断言（断言见
  `C_index_policy_check_v2.md`，可用 `scripts/build_p5_index_v2.py` 重跑）。
- 三处配方问题（944 独立组成、干扰对照写死 Ni=8/Fe 参与、548 行越界）的修复位于
  **v2 主表与设计脚本**：`scripts/design_c_alloy_formulas_v2.py` 与
  `v2/master_samples_v2.json`（SHA-256 见 `v2/design_selfcheck_v2.json`）。
  **本归档批次的 2000 条谱仍由 v1 主表生成，数据本身未被改写**；如需按 v2 主表出数，
  必须另起新版本批次重新生成并密封，不能就地修补（本地已按 v2 主表生成出候选
  `P5_dataset_v2` 2000 谱，但**未 audit、未 replay、未打包、未推送**，
  进度与身份只读快照见 `v2/generation_status_v2.json`，不构成可交付数据集）。
- 下游入口请用 `scripts/c_pilot_guard.py::training_rows()`：请求本批次任何划分都会抛
  `PilotIsolationError`，不会静默返回可训练行。
- 不要用其他批次替代本批做基准：任何批次（含 A/B 试产数据）都必须先核对它自己的
  `usage_policy` 与评审状态。本交付不为任何其他批次的可训练性作背书。
"""

CODE_SECTION = """## v2 可复现代码与产物（第二轮评审后随包提交）

第二轮评审指出：说明里引用的新脚本与主表当时并未提交，因而"已修复"无法验证。
本次把它们全部放进本目录，评审可在解包后直接复跑。

| 路径 | 内容 |
| --- | --- |
| `scripts/design_c_alloy_formulas_v2.py` | 1000 条铁基主配方的 v2 设计（P2-1 / P2-2 / P2-3 的修复本体） |
| `scripts/build_p5_index_v2.py` | 并查集 leak_group + 统一 heldout 的索引/划分构建器（P1-1 / P1-2） |
| `scripts/c_pilot_guard.py` | 训练/调参入口守卫与三入口拒绝自检 |
| `scripts/reproduce_v2_check.py` | 复刻仓库布局重跑三件事，并与本目录产物逐字节对账 |
| `scripts/check_review_findings.py` | 评审五条的独立复算（结果 `v2/review_findings_check.json`） |
| `scripts/check_doc_references.py` | 扫描本目录文档里的路径引用是否都随包存在（结果 `v2/doc_reference_check.json`） |
| `scripts/fix_registry_scenario.py`、`scripts/build_github_payload.py` | 登记表 scenario 空列的修复与披露（见下一节） |
| `scripts/pregenerate_dryrun_v2.py`、`scripts/v2_generation_status.py`、`scripts/generate_v2_batch.py` | 生成前预检、只读进度快照、后续批次生成入口 |
| `scripts/annotate_candidate_batch.py`、`scripts/annotate_round2.py`、`scripts/verify_annotation_push.py` | 两轮标注的写入脚本与远端逐字节复核脚本 |
| `v2/master_samples_v2.json` | v2 主表（根目录同名重写件：`C_samples_v2.json`） |
| `v2/design_selfcheck_v2.json` / `.md` | 设计自检：1000 行 1000 种独立组成、越界 0 行 0 项，含 v1 基线复算 |
| `v2/index_v2.csv`、`v2/global_split_v2.csv`、`v2/coverage_v2.json`、`v2/index_policy_check_v2.*` | 索引/划分/覆盖与断言结果 |
| `v2/pilot_guard_selftest.json`、`v2/pilot_isolation.json` | 入口隔离自检与被隔离批次清单 |
| `v2/reproduction_check_v2.json` / `.md` | 跨布局逐字节复现对账结果 |
| `v2/review_findings_check.json` | 评审五条的复算数值（与评审口径逐项对照） |
| `v2/annotation_push_verification.json` | 上一轮标注提交 `5c9439f…` 的远端逐字节复核结果 |
| `v2/registry_scenario_fix_check.json`、`C_formula_registry_v2.csv` | 登记表 scenario 空列的修正件与逐列对账 |
| `v2/generation_status_v2.json` / `.md` | v2 批次数据的真实进度快照（只读磁盘，未密封、未推送） |
| `v2/C_v2_verification_report.md` | 两轮意见的逐条验证报告 |

复现命令（脚本路径已适配本目录布局：主表自动取 `C_samples.json`，输出写到 `v2/`）：

```
python -B scripts/design_c_alloy_formulas_v2.py
python -B scripts/build_p5_index_v2.py <解包后的数据集目录> [主表] [批次标签] [版本] [输出目录]
python -B scripts/c_pilot_guard.py
python -B scripts/check_review_findings.py
python -B scripts/reproduce_v2_check.py [数据集目录]
python -B scripts/check_doc_references.py [本目录]
```

"""

DEFECT_SECTION = """## 自查披露：登记表 `C_formula_registry.csv` 的 scenario 列全空

本轮复核载荷时发现：已推送的 `C_formula_registry.csv` 第 2 列 `scenario` 在 1000 行里
全部为空字符串。根因是载荷构建脚本取 `provenance['scenario']`，而主表里的键名是
`provenance['design_scenario']`（其余 10 列不受影响，数值正确）。

处置（不改动归档文件字节）：

- `C_formula_registry.csv` 保持原样、原 SHA-256 不变，作为归档批次的真实交付状态保留；
- 新增 `C_formula_registry_v2.csv`：由 `scripts/fix_registry_scenario.py` 从本目录
  `C_samples.json` 逐行按 `formula_id` 对齐补齐 scenario 列。对账结果
  `v2/registry_scenario_fix_check.json` 断言：行序完全一致、只有 `scenario` 一列不同、
  其他列 0 处差异、补齐后 regular_variation 600 / sparse_boundary 200 /
  interference_control 200、且把原文件按同格式重新序列化可得到与原字节完全相同的结果
  （证明差异只来自这一列）；
- `scripts/build_github_payload.py` 的取键已修正，未来批次不会再产生空列。

该缺陷不影响谱数据、真值、索引与划分，也不改变"本批次禁止训练/调参"的结论。

"""



def sha256(path: Path) -> str:
    d = hashlib.sha256()
    with path.open('rb') as fh:
        for blk in iter(lambda: fh.read(1 << 20), b''):
            d.update(blk)
    return d.hexdigest()


def blob_id(path: Path) -> str:
    raw = path.read_bytes()
    h = hashlib.sha1()
    h.update(b'blob %d\x00' % len(raw))
    h.update(raw)
    return h.hexdigest()


def git(*args) -> str:
    env = dict(__import__('os').environ)
    env.update({'GIT_ASKPASS': 'D:/gcm_askpass.sh', 'GIT_TERMINAL_PROMPT': '1'})
    r = subprocess.run([GIT, '-c', 'credential.helper='] + list(args), cwd=str(WORK),
                       capture_output=True, text=True, encoding='utf-8', errors='replace',
                       env=env)
    if r.returncode != 0:
        raise RuntimeError(f'git {args} rc={r.returncode}: {r.stderr[-300:]}')
    return r.stdout


PENDING: list = []


def ship():
    PENDING.clear()
    (PAYLOAD / 'scripts').mkdir(exist_ok=True)
    (PAYLOAD / 'v2').mkdir(exist_ok=True)
    added = []
    for name in SHIP_SCRIPTS:
        src = SCRIPTS / name
        if not src.is_file():
            raise SystemExit(f'缺少脚本 {src}')
        dst = PAYLOAD / 'scripts' / name
        before = dst.read_bytes() if dst.is_file() else None
        shutil.copyfile(src, dst)
        if before != dst.read_bytes():
            added.append(f'scripts/{name}')
    pending = []
    for rel in SHIP_V2:
        src = V2 / rel
        if not src.is_file():
            PENDING.append(rel)          # 分步执行时允许暂缺（复现对账要等载荷就位后才能跑）
            continue
        dst = PAYLOAD / 'v2' / rel
        before = dst.read_bytes() if dst.is_file() else None
        shutil.copyfile(src, dst)
        if before != dst.read_bytes():
            added.append(f'v2/{rel}')
        if rel in ROOT_RENAMES:
            dst2 = PAYLOAD / ROOT_RENAMES[rel]
            before2 = dst2.read_bytes() if dst2.is_file() else None
            shutil.copyfile(src, dst2)
            if before2 != dst2.read_bytes():
                added.append(ROOT_RENAMES[rel])
    for src_rel, dst_rel in SHIP_EXTRA:
        src = HERE / src_rel
        if not src.is_file():
            PENDING.append(src_rel)
            continue
        dst = PAYLOAD / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        before = dst.read_bytes() if dst.is_file() else None
        shutil.copyfile(src, dst)
        if before != dst.read_bytes():
            added.append(dst_rel)
    return added


def patch_readme():
    path = PAYLOAD / 'README.md'
    before = sha256(path)
    text = path.read_text(encoding='utf-8')
    n = len(re.findall(r'## 划分与用法', text))
    if n != 1:
        raise SystemExit(f'README "划分与用法" 段出现 {n} 次，拒绝改写')
    text = re.sub(r'## 划分与用法（v2 修正）\n.*?(?=\n## )', USAGE_BLOCK.rstrip() + '\n',
                  text, flags=re.S)
    if '## v2 可复现代码与产物' not in text:
        m = re.search(r'\n## 未验证事项\n', text)
        if not m:
            raise SystemExit('README 缺少"未验证事项"锚点')
        text = (text[:m.start()] + '\n' + CODE_SECTION.rstrip() + '\n\n'
                + DEFECT_SECTION.rstrip() + '\n' + text[m.start():])
    elif 'scenario 列全空' not in text:
        h = text.find('## v2 可复现代码与产物')
        if h < 0:
            raise SystemExit('README 缺少"v2 可复现代码与产物"段，拒绝插入披露段')
        nxt = text.find('\n## ', h)
        if nxt < 0:
            raise SystemExit('无法定位"v2 可复现代码与产物"段的结束位置')
        text = (text[:nxt] + '\n' + DEFECT_SECTION.rstrip() + text[nxt:])
    # 内容表里补一行指向新脚本目录，避免评审按旧表找不到的情况
    text = text.replace('| `scripts/` | 配方设计、断点续跑生成、外部检查打包、索引构建、本布局生成脚本 |',
                        '| `scripts/` | 配方设计（v1/v2）、断点续跑生成、外部检查打包、索引构建'
                        '（v1/v2）、入口守卫与复现对账脚本 |')
    path.write_text(text, encoding='utf-8')
    return before, sha256(path)


def refresh_hashes(readme_new_sha, old_readme_sha):
    path = PAYLOAD / 'C_delivery_hashes.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    files = {f.relative_to(PAYLOAD).as_posix(): {'bytes': f.stat().st_size, 'sha256': sha256(f)}
             for f in sorted(PAYLOAD.rglob('*'))
             if f.is_file() and f.name != 'C_delivery_hashes.json'}
    data['files'] = files
    data['scope'] = ('本目录逐文件 SHA-256（不含卷内清单）。密封数据集与分卷未重写；'
                     '本清单随说明修订重算，历史 README 哈希见 annotation 链。')
    prev = data.get('annotation') or {}
    data['annotation'] = {
        'reason': 'PR #2 第二轮评审：随包提交 v2 代码与主表，并改掉"已修复/A/B 可训练"两处表述',
        'sealed_data_rewritten': False,
        'zip_sha256_unchanged': data.get('zip_sha256_original') == ZIP_SHA,
        'readme_history': [x for x in ([prev.get('readme_sha256_before'),
                                       prev.get('readme_sha256_after'), readme_new_sha]
                                      if prev.get('readme_sha256_after') else
                                      [old_readme_sha, readme_new_sha]) if x],
        'readme_sha256_before': old_readme_sha,
        'readme_sha256_after': readme_new_sha,
        'previous_annotation_kept': bool(prev),
        'file_count': len(files)}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data


def remote_tree() -> dict:
    out = git('ls-tree', '-r', '--format=%(objectname) %(path)',
              REMOTE_COMMIT, '--', TARGET)
    tree = {}
    for line in out.splitlines():
        sha1, path = line.split(' ', 1)
        tree[path[len(TARGET) + 1:]] = sha1
    return tree


def delta_vs_remote(hashes):
    tree = remote_tree()
    # 以磁盘实际文件为准（哈希清单本身不含自己，否则会被误判成"要删除"）
    present = [f.relative_to(PAYLOAD).as_posix() for f in sorted(PAYLOAD.rglob('*'))
               if f.is_file()]
    local = {rel: blob_id(PAYLOAD / rel) for rel in present}
    added = sorted(set(local) - set(tree))
    modified = sorted(r for r in set(local) & set(tree) if local[r] != tree[r])
    would_remove = sorted(set(tree) - set(local) - {'.gitattributes'})
    sealed = [r for r in added + modified
              if r.startswith('P5_pack.zip.part') or r in
              ('P5_dataset.zip.sha256', 'P5_audit.json', 'P5_replay.json', 'P5_pack.json',
               'P5_check_timings.json', 'P5.json', 'P5_replay_environment.json',
               '.gitattributes') or r in ('C_authoritative_index.csv', 'C_global_split.csv',
                                          'C_coverage.json', 'C_samples.json',
                                          'C_formula_registry.csv', 'C_production_record.json')]
    return {'remote_commit': REMOTE_COMMIT, 'target_dir': TARGET,
            'remote_files': len(tree), 'local_files': len(local),
            'added': added, 'modified': modified, 'would_remove': would_remove,
            'sealed_or_original_touched': sealed,
            'note': 'would_remove 为空即本次不删任何东西；密封数据/分卷不出现在 added+modified 里。'}


def main():
    for p in (PAYLOAD / 'v2' / 'generation_status_v2.json', V2 / 'reproduction_check_v2.json'):
        if not p.is_file():
            raise SystemExit(f'先运行 v2_generation_status.py / reproduce_v2_check.py：缺 {p.name}')
    gen = json.loads((V2 / 'generation_status_v2.json').read_text(encoding='utf-8'))
    repro = json.loads((V2 / 'reproduction_check_v2.json').read_text(encoding='utf-8'))
    design = json.loads((V2 / 'design_selfcheck_v2.json').read_text(encoding='utf-8'))
    checks = json.loads((V2 / 'index_policy_check_v2.json').read_text(encoding='utf-8'))
    guard = json.loads((V2 / 'pilot_guard_selftest.json').read_text(encoding='utf-8'))
    reg = json.loads((V2 / 'registry_scenario_fix_check.json').read_text(encoding='utf-8'))
    review = json.loads((V2 / 'review_findings_check.json').read_text(encoding='utf-8'))
    onv2 = json.loads((HERE / 'v2_datacheck' / 'index_policy_check_v2.json')
                      .read_text(encoding='utf-8'))
    if not onv2['checks']['passed']:
        raise SystemExit('v2 批次的索引断言未通过，先修 scripts/build_p5_index_v2.py')
    if not reg['passed']:
        raise SystemExit('登记表 scenario 修正对账未通过，先修 scripts/fix_registry_scenario.py')

    ship()
    if PENDING:
        raise SystemExit(f'v2 产物仍缺失，先补齐再生成载荷：{PENDING}')
    changed_by_ship = ship()
    old_readme, new_readme = patch_readme()
    hashes = refresh_hashes(new_readme, old_readme)
    delta = delta_vs_remote(hashes)
    (V2 / 'annotation_delta_vs_pushed.json').write_text(
        json.dumps(delta, ensure_ascii=False, indent=2), encoding='utf-8')

    status = json.loads((PAYLOAD / 'C_batch_status.json').read_text(encoding='utf-8'))
    status['review']['verdict'] = 'requested_changes_twice'
    status['review']['second_round'] = {
        'on': '2026-10-19',
        'findings': [
            {'id': 'R2-1',
             'title': '三项配方问题标成"已修复"，但引用的新脚本与主表未提交，无法验证',
             'resolution': 'v2 设计/索引/守卫/预检/复现脚本与 v2 主表、全部自检产物随包提交；'
                           '发现状态措辞改为 fixed_in_v2_code_archived_batch_unchanged，'
                           '并写明归档批次数据未变。'},
            {'id': 'R2-2',
             'title': '把 A/B 试产数据推荐为可训练数据，与其用途限制不符',
             'resolution': '删除"改用已通过评审的 A/B 批次"推荐（README、C_batch_status、'
                           'c_pilot_guard 文案三处同步），改为要求核对目标批次自身 '
                           'usage_policy 与评审状态；本交付不为其他批次作背书。'}],
        'archival_only': '按评审意见，本批仅归档失败批次，不重生成旧谱即继续评审。'}
    for f in status['findings']:
        f['status'] = 'fixed_in_v2_code_archived_batch_unchanged'
        f['scope_note'] = ('修复位于 v2 代码与 v2 主表；本归档批次的 2000 条谱仍由 v1 主表生成，'
                           '未就地改写。要按 v2 出数必须另起批次重新生成与密封。')
    status['v2_remediation']['index_split_on_new_batch'] = {
        'script': 'scripts/build_p5_index_v2.py',
        'dataset_dir': onv2['dataset_dir'],
        'master_file': onv2['master_file'],
        'master_sha256': onv2['master_sha256'],
        'dataset_manifest_sha256': onv2['dataset_manifest_sha256'],
        'result_file': 'v2/index_policy_check_v2_on_v2_data.json',
        'rows': onv2['checks']['rows'],
        'distinct_formula_compositions': onv2['checks']['distinct_formula_compositions'],
        'duplicate_composition_groups': onv2['checks']['duplicate_composition_groups'],
        'leak_groups': onv2['checks']['leak_groups'],
        'group_size_histogram': onv2['checks']['group_size_histogram'],
        'identical_compositions_crossing_split':
            onv2['checks']['identical_compositions_crossing_split'],
        'passed': onv2['checks']['passed'],
        'note': '与归档批次同一套 v2 策略，跑在新生成的 2000 条 v2 谱上：1000 条配方 '
                '1000 种独立采用组成、重复组 0（归档批次为 944/34），最大 leak_group '
                '从 70 降到 5（等于设计里的 5 变体族）。'}
    status['v2_remediation']['generation'] = {
        'stage': gen['qc_stage'],
        'spectra': f'{gen["progress"]["blind_inputs"]}/{gen["target_spectra"]}',
        'consistency_ok': gen['progress']['consistent'],
        'generator_sealed': gen['sealed'],
        'disk_bytes': gen['disk_bytes'],
        'qc_artifacts_present': gen['qc_artifacts_present'],
        'audit_replay_pack': 'not run',
        'pushed_to_github': False,
        'snapshot_file': 'v2/generation_status_v2.json',
        'note': '按第二轮评审意见本批只归档。v2 数据批次已在本地生成完足 2000 谱并通过'
                '一致性核对，但未做全量 audit / 物理 replay / 打包 / 推送，'
                '因此不构成任何可交付数据集，也不随本批提交谱数据。'}
    status['v2_remediation']['reproduction'] = {
        'script': 'scripts/reproduce_v2_check.py', 'result_file': 'v2/reproduction_check_v2.json',
        'all_identical': repro['all_identical'], 'passed': repro['passed'],
        'v1_master_sha256': repro['v1_master']['sha256'],
        'file_checks': repro['file_checks']}
    status['v2_remediation']['usage_policy_statement'] = (
        '本批次禁止训练/调参；不对其他批次（含 A/B 试产数据）的可训练性作背书。')
    status['v2_remediation']['document_reference_check'] = {
        'script': 'scripts/check_doc_references.py', 'result_file': 'v2/doc_reference_check.json'}
    status['self_disclosed_defects'] = {
        'registry_scenario_column': {
            'id': 'SD-1',
            'severity': 'P3',
            'title': '归档登记表 C_formula_registry.csv 的 scenario 列 1000 行全空',
            'root_cause': reg['root_cause'],
            'evidence_file': 'v2/review_findings_check.json（scenario_counts_in_registry）',
            'archived_file_rewritten': reg['archived_file_rewritten'],
            'fixed_copy': reg['fixed_file']['name'],
            'fixed_copy_sha256': reg['fixed_file']['sha256'],
            'original_sha256': reg['source_file']['sha256'],
            'columns_that_differ': reg['columns_that_differ'],
            'other_column_value_mismatches': reg['other_column_value_mismatches'],
            'scenario_counts_after_fix': reg['scenario_counts_after_fix'],
            'reserializer_roundtrip_bytes_identical':
                reg['reserializer_roundtrip_bytes_identical'],
            'affects_spectra_or_split': False,
            'passed': reg['passed']}}
    status['v2_remediation']['shipped_files'] = sorted(
        set(status['v2_remediation'].get('shipped_files', [])) | set(delta['added']))
    status['usage'] = {'may_be_used_for_training': False, 'may_be_used_for_tuning': False,
                       'other_batches_endorsed': False}
    (PAYLOAD / 'C_batch_status.json').write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [f'# 批次状态 · {BATCH_ID}', '',
             '**未通过独立评审（PR #2 两轮 requested changes，未合并）；本批次定位为候选试产'
             '（workflow pilot-only）并归档，禁止用于训练与调参。**', '',
             '## 密封批次身份（保留，不重写）', '',
             f'- 数据提交 `cdc4f739…`（基线 `64f4bfd7…`）+ 候选标注提交 `5c9439f…`，'
             f'落点 `datasets/{BATCH_ID}`',
             f'- 数据集 ZIP SHA-256：`{ZIP_SHA}`',
             f'- 主表语义摘要：`{status["sealed_batch_identity"]["input_semantic_sha256"]}`',
             '- `truth.jsonl` / `manifest.json` / 分卷：未改动。失败批次身份保留以便追溯。', '',
             '## 评审发现与修复位置', '',
             '| 编号 | 级别 | 问题 | 证据 | 状态 |', '| --- | --- | --- | --- | --- |']
    for f in status['findings']:
        lines.append(f'| {f["id"]} | {f["severity"]} | {f["title"]} | {f["evidence"]} | '
                     f'`{f["status"]}` |')
    lines += ['', '> `fixed_in_v2_code_archived_batch_unchanged` = 修复位于 **v2 代码与 v2 主表**，'
              '本归档批次数据未变；要按 v2 出数需另起批次重新生成并密封。', '',
              '## 第二轮意见与本次处置', '']
    for r in status['review']['second_round']['findings']:
        lines += [f'- **{r["id"]} {r["title"]}**\n  处置：{r["resolution"]}']
    lines += ['', '## 复现（评审可直接跑）', '',
              '```',
              'python -B scripts/design_c_alloy_formulas_v2.py',
              'python -B scripts/build_p5_index_v2.py <解包后的数据集目录> [主表] [批次] [版本] [输出]',
              'python -B scripts/c_pilot_guard.py',
              'python -B scripts/check_review_findings.py',
              'python -B scripts/fix_registry_scenario.py',
              'python -B scripts/reproduce_v2_check.py [数据集目录]',
              'python -B scripts/check_doc_references.py [本目录]',
              '```', '',
              '- 复现对账：`v2/reproduction_check_v2.json`（产物逐字节一致 = '
              f'{repro["all_identical"]}，passed = {repro["passed"]}）',
              '- 文档引用自检：`v2/doc_reference_check.json`（本目录文档引用的脚本/产物'
              '是否都随包存在）',
              '- 评审五条复算：`v2/review_findings_check.json`'
              f'（P2_1 distinct {review["P2_1_distinct_compositions"]}、'
              f'P2_3 常规越界 {review["P2_3_regular_rows_violating"]} 行 / '
              f'{review["P2_3_regular_items_violating"]} 项）',
              f'- v2 主表：`v2/master_samples_v2.json` SHA-256 '
              f'`{design["master_file"]["sha256"]}`；独立组成 '
              f'{design["distinct_compositions"]}/{design["rows"]}，越界 '
              f'{design["rows_with_range_violations"]} 行 / {design["range_violation_items"]} 项',
              f'- v1 基线复算：{json.dumps(design["v1_baseline_recomputed"], ensure_ascii=False)}',
              f'- 索引断言：leak_group {checks["checks"]["leak_groups"]}、全部行 heldout = '
              f'{checks["checks"]["uniform_holdout"]}、跨集合 0（passed='
              f'{checks["checks"]["passed"]}）',
              f'- 入口守卫：{len(guard["blocked_entries"]) if "blocked_entries" in guard else 3} '
              f'个入口被拒（passed={guard["passed"]}）',
              f'- 同一策略跑在新生成的 v2 批次上（`v2/index_policy_check_v2_on_v2_data.json`，'
              f'数据集 `{onv2["dataset_dir"]}`）：'
              f'{onv2["checks"]["rows"]} 行全 heldout、独立采用组成 '
              f'{onv2["checks"]["distinct_formula_compositions"]}/'
              f'{onv2["checks"]["formulas"]}、重复组 '
              f'{onv2["checks"]["duplicate_composition_groups"]}、leak_group '
              f'{onv2["checks"]["leak_groups"]} 个（尺寸分布 '
              f'{json.dumps(onv2["checks"]["group_size_histogram"], ensure_ascii=False)}）、'
              f'跨集合 {len(onv2["checks"]["identical_compositions_crossing_split"])}'
              f'（passed={onv2["checks"]["passed"]}）',
              f'- v2 数据批次（**不随本批交付**）：阶段 {gen["qc_stage"]}，谱数 '
              f'{gen["progress"]["blind_inputs"]}/{gen["target_spectra"]}，一致性 '
              f'{gen["progress"]["consistent"]}；已生成器密封、未做 audit/replay/打包/推送，'
              f'故不构成可交付数据集（快照 `v2/generation_status_v2.json`，'
              f'{gen["disk_bytes"] / 2 ** 30:.2f} GiB）', '',
              '## 自查披露（本次一并修正，非评审提出）', '',
              f'- **SD-1（P3）归档登记表 `C_formula_registry.csv` 的 `scenario` 列 1000 行全空**。'
              f'根因：{reg["root_cause"]}。',
              f'  归档文件字节未改（原 SHA-256 `{reg["source_file"]["sha256"][:16]}…`）；'
              f'新增修正件 `{reg["fixed_file"]["name"]}`（'
              f'`{reg["fixed_file"]["sha256"][:16]}…`），逐列对账只有 `scenario` 一列不同、'
              f'其他列差异 {reg["other_column_value_mismatches"]} 处，补齐后 '
              f'{json.dumps(reg["scenario_counts_after_fix"], ensure_ascii=False)}；'
              f'对账文件 `v2/registry_scenario_fix_check.json`（passed={reg["passed"]}）。'
              '构建脚本 `scripts/build_github_payload.py` 的取键同步修正。'
              '此缺陷不影响谱、真值、索引与划分。', '',
              '## 下游使用规则', '',
              '1. 不要把本批次任何谱用于训练、调参或阈值挑选。',
              '2. 读取本批次请走 `c_pilot_guard.training_rows()`，它会拒绝而非静默放行。',
              '3. `README.md` 里"按 benchmark_split 读取训练数据"的旧说法已作废（该段已改写）。',
              '4. 不要以"改用 A/B 批次"作为替代方案：每个批次（含 A/B 试产数据）都要各自'
              '核对其 `usage_policy` 与评审状态，本交付不为其他批次作背书。', '']
    (PAYLOAD / 'C_batch_status.md').write_text('\n'.join(lines), encoding='utf-8')

    (V2 / 'round2_plan.json').write_text(json.dumps({
        'remote_commit': REMOTE_COMMIT, 'files_total': len(hashes['files']),
        'changed_by_ship': changed_by_ship, 'delta': {k: delta[k] for k in
                                                      ('added', 'modified', 'would_remove',
                                                       'sealed_or_original_touched')},
        'readme': {'before': old_readme, 'after': new_readme},
        'zip_sha256_unchanged': hashes['annotation']['zip_sha256_unchanged']},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print('payload files', len(hashes['files']),
          '| added', len(delta['added']), '| modified', len(delta['modified']),
          '| remove', delta['would_remove'], '| sealed touched', delta['sealed_or_original_touched'],
          '| zip unchanged', hashes['annotation']['zip_sha256_unchanged'])


if __name__ == '__main__':
    sys.exit(main())
