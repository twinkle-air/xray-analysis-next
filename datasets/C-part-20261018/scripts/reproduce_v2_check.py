"""C 部分：把"v2 修复已完成"变成评审可自行复现的证据。

在一个临时目录里复刻仓库载荷布局（`<batch>/C_samples.json` + `<batch>/scripts/*.py`），
只跑设计/索引/守卫三件事，然后与已提交到仓库的同名产物逐字节比 SHA-256：

- 设计脚本：`master_samples_v2.json` 必须与仓库副本完全一致（种子写死，无时间戳）；
- 索引脚本：需要已解包的密封数据集；缺失时跳过并如实标注 `skipped`，不谎报通过；
- 守卫脚本：在仓库布局的索引上重跑三入口拒绝自检，比对已提交的自检结果 JSON
  （只比较断言字段，索引文件名一栏允许不同——本地叫 master_samples.json，
   仓库副本叫 C_samples.json，两者的 SHA-256 相同）。

用法：
    python -B scripts/reproduce_v2_check.py [数据集目录]
数据集目录缺省时尝试 fp_competition/P5_dataset。
输出：`v2/reproduction_check_v2.json` 与 `.md`。
"""
from __future__ import annotations
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # C_part 或 datasets/<batch>
SCRIPTS = HERE / 'scripts'
PAYLOAD = HERE / 'github_payload' / 'datasets' / 'C-part-20261018'
BATCH = PAYLOAD if PAYLOAD.is_dir() else HERE          # 仓库布局下产物就在本目录
DATASET_DEFAULT = (HERE.parent / 'fp-spectrum-generator-competition-v0.2.1'
                   / 'fp_competition' / 'P5_dataset')
CHECK_FILES = ['v2/master_samples_v2.json', 'v2/design_selfcheck_v2.json',
               'v2/design_selfcheck_v2.md',
               'v2/index_v2.csv', 'v2/global_split_v2.csv', 'v2/coverage_v2.json',
               'v2/index_policy_check_v2.json', 'v2/index_policy_check_v2.md',
               'v2/pilot_guard_selftest.json']
DESIGN_KEYS = ('rows', 'distinct_compositions', 'duplicate_groups',
               'rows_with_range_violations', 'range_violation_items', 'passed',
               'scenario_counts', 'interference_families', 'interference_family_has_5_variants',
               'interference_pairs_containing_Fe', 'zero_recipe_target_actually_absent',
               'v1_baseline_recomputed')
GUARD_KEYS = ('rows', 'uniform_heldout', 'train_entry', 'validation_entry', 'test_entry',
              'all_entries_blocked', 'passed')


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(script: Path, cwd: Path, *args):
    r = subprocess.run([sys.executable, '-X', 'utf8', '-B', script.name, *[str(a) for a in args]],
                       cwd=str(cwd), capture_output=True, text=True, encoding='utf-8',
                       errors='replace')
    return {'rc': r.returncode, 'stdout': r.stdout.strip()[-400:], 'stderr': r.stderr.strip()[-400:]}


def main():
    dataset = Path(sys.argv[1]) if len(sys.argv) > 1 else DATASET_DEFAULT
    tmp = Path(tempfile.mkdtemp(prefix='c_v2_repro_'))
    batch = tmp / 'batch'
    (batch / 'scripts').mkdir(parents=True)
    shutil.copy2(SCRIPTS / 'design_c_alloy_formulas_v2.py', batch / 'scripts')
    shutil.copy2(SCRIPTS / 'build_p5_index_v2.py', batch / 'scripts')
    shutil.copy2(SCRIPTS / 'c_pilot_guard.py', batch / 'scripts')
    shutil.copy2(BATCH / 'C_samples.json', batch / 'C_samples.json')   # 仓库里的 v1 主表

    report = {'repo_layout_root': 'datasets/C-part-20261018',
              'v1_master': {'name': 'C_samples.json', 'sha256': sha(BATCH / 'C_samples.json')},
              'steps': {}}
    try:
        scripts = batch / 'scripts'
        report['steps']['design'] = run(scripts / 'design_c_alloy_formulas_v2.py', scripts)
        report['steps']['index'] = (run(scripts / 'build_p5_index_v2.py', scripts,
                                         dataset, batch / 'C_samples.json',
                                         'C-part-20261018',
                                         'C-recipes-v1(review_failed,pilot_only)',
                                         batch / 'v2')
                                    if (dataset / 'manifest.json').is_file()
                                    else {'rc': None, 'stdout': 'skipped',
                                          'stderr': f'数据集不可用：{dataset}（可从分卷 ZIP 解包后传入）'})
        report['steps']['guard'] = run(scripts / 'c_pilot_guard.py', scripts)

        checks = {}
        for rel in CHECK_FILES:
            produced, shipped = batch / rel, BATCH / rel
            if not produced.is_file():
                checks[rel] = {'status': 'not_produced'}
                continue
            if not shipped.is_file():
                checks[rel] = {'status': 'not_in_repo',
                               'reproduced_sha256': sha(produced)}
                continue
            same = sha(produced) == sha(shipped)
            checks[rel] = {'status': 'identical' if same else 'differs',
                           'reproduced_sha256': sha(produced), 'repo_sha256': sha(shipped),
                           'bytes': produced.stat().st_size}
        # 唯一允许的差异：报告里"v1 主表文件名"一栏。仓库里 v1 主表叫 C_samples.json，
        # 本地叫 master_samples.json，两者 SHA-256 相同（下面把两个名字归一后再比）。
        def norm(text: str) -> str:
            return text.replace('master_samples.json', '<master>').replace('C_samples.json',
                                                                            '<master>')

        for rel in ('v2/index_policy_check_v2.json', 'v2/index_policy_check_v2.md',
                    'v2/design_selfcheck_v2.json', 'v2/design_selfcheck_v2.md'):
            c = checks.get(rel)
            if not c or c['status'] == 'identical':
                continue
            a_txt = (batch / rel).read_text(encoding='utf-8')
            b_txt = (BATCH / rel).read_text(encoding='utf-8')
            same_after_norm = norm(a_txt) == norm(b_txt)
            sha_pairs_equal = True
            if rel.endswith('.json'):
                x, y = json.loads(a_txt), json.loads(b_txt)
                flat_x = json.dumps(x, sort_keys=True, ensure_ascii=False)
                flat_y = json.dumps(y, sort_keys=True, ensure_ascii=False)
                # 归一后必须完全一致，且报告里记录的 SHA-256 两栏相等
                import re as _re
                sx = set(_re.findall(r'"(?:master_sha256|sha256)": "([0-9a-f]{64})"', flat_x))
                sy = set(_re.findall(r'"(?:master_sha256|sha256)": "([0-9a-f]{64})"', flat_y))
                sha_pairs_equal = norm(flat_x) == norm(flat_y) and (not sx or sx == sy)
            if same_after_norm and sha_pairs_equal:
                c['status'] = 'identical_except_master_name'
                c['note'] = ('主表在仓库里名为 C_samples.json、本地名为 master_samples.json，'
                             'SHA-256 相同，故报告仅此一栏不同（文件名归一后逐字符一致）。')
        # 设计结论逐字段对账（不依赖文件字节）
        rep = batch / 'v2' / 'design_selfcheck_v2.json'
        if rep.is_file():
            new = json.loads(rep.read_text(encoding='utf-8'))
            old = json.loads((BATCH / 'v2' / 'design_selfcheck_v2.json').read_text(encoding='utf-8'))
            report['design_field_compare'] = {
                'identical_on_assertions': all(new.get(k) == old.get(k) for k in DESIGN_KEYS),
                'differing_fields': [k for k in DESIGN_KEYS if new.get(k) != old.get(k)],
                'v2': {k: new.get(k) for k in ('rows', 'distinct_compositions',
                                               'rows_with_range_violations',
                                               'range_violation_items', 'passed')},
                'v1_recomputed': new.get('v1_baseline_recomputed')}
        gp = batch / 'v2' / 'pilot_guard_selftest.json'
        if gp.is_file() and (BATCH / 'v2' / 'pilot_guard_selftest.json').is_file():
            new = json.loads(gp.read_text(encoding='utf-8'))
            old = json.loads((BATCH / 'v2' / 'pilot_guard_selftest.json').read_text(encoding='utf-8'))
            report['guard_field_compare'] = {
                'identical_on_assertions': all(new.get(k) == old.get(k) for k in GUARD_KEYS),
                'differing_fields': [k for k in GUARD_KEYS if new.get(k) != old.get(k)],
                'blocked_entries': [k for k in GUARD_KEYS if k.endswith('_entry')
                                    and new.get(k) == 'blocked']}
        report['file_checks'] = checks
        hard = [c for c in checks.values() if c['status'] in ('differs', 'not_in_repo')]
        report['all_identical'] = not hard
        report['passed'] = bool(
            report['steps']['design']['rc'] == 0 and report['steps']['guard']['rc'] == 0
            and not hard and report.get('design_field_compare', {}).get(
                'identical_on_assertions', False))
        report['note'] = ('索引步骤需要解包后的密封数据集；未提供时该步 skipped 且不计入 passed。'
                          '三处配方问题的结论只针对 v2 主表，已归档的 P5 批次数据未重生成。')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    out_json = HERE / 'v2' / 'reproduction_check_v2.json'
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# v2 修复的可复现校验', '',
             f'- 结论：**{"通过" if report["passed"] else "未通过"}**；'
             f'产物字节对账 {"全部一致" if report["all_identical"] else "存在差异"}',
             f'- v1 主表（仓库副本 C_samples.json）SHA-256：`{report["v1_master"]["sha256"]}`', '',
             '## 复跑方式', '', '```',
             'python -B scripts/design_c_alloy_formulas_v2.py      # 只写 v2/，不碰密封批次',
             'python -B scripts/build_p5_index_v2.py <解包后的数据集目录>   # 只读数据集',
             'python -B scripts/c_pilot_guard.py                   # 三入口拒绝自检',
             'python -B scripts/reproduce_v2_check.py [数据集目录]  # 本校验', '```', '',
             '## 与仓库产物逐字节比对', '', '| 文件 | 状态 | SHA-256（复现 / 仓库） |',
             '| --- | --- | --- |']
    for rel, c in report['file_checks'].items():
        lines.append(f"| `{rel}` | {c['status']} | "
                     f"`{c.get('reproduced_sha256', '—')[:12]}` / "
                     f"`{c.get('repo_sha256', '—')[:12]}` |")
    if 'design_field_compare' in report:
        d = report['design_field_compare']
        lines += ['', f"- 设计断言字段一致：{d['identical_on_assertions']}；"
                  f"差异字段 {d['differing_fields'] or '无'}",
                  f"- v2 主表：{json.dumps(d['v2'], ensure_ascii=False)}",
                  f"- v1 主表复算：{json.dumps(d['v1_recomputed'], ensure_ascii=False)}"]
    if 'guard_field_compare' in report:
        g = report['guard_field_compare']
        lines += ['', f"- 守卫自检字段一致：{g['identical_on_assertions']}；"
                  f"被拒入口 {g['blocked_entries']}"]
    lines += ['', f"- 索引步骤：{report['steps']['index'].get('stdout') or '—'}",
              f"- 说明：{report['note']}"]
    (out_json.parent / 'reproduction_check_v2.md').write_text('\n'.join(lines) + '\n',
                                                              encoding='utf-8')
    print('passed', report['passed'], '| all_identical', report['all_identical'],
          '|', {k: v['status'] for k, v in report['file_checks'].items()})


if __name__ == '__main__':
    main()
