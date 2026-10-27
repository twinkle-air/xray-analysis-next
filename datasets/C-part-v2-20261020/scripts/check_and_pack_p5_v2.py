"""C 部分：v2 批次（P5_dataset_v2）QC。

stage 参数：
  quick      —— audit（逐谱完整性/一致性/泊松重放）+ pack（确定性 ZIP + 外部 SHA-256）
  replay     —— 全量物理重算（2.6 s/谱，约 1.5 h），可后台补跑
  stub-pass  —— 用一份"应当通过"的合成报告走同一条判定/退出路径（不需要 GPU/物理库）
  stub-fail  —— 用一份故障注入报告（status=failed、只重算 1 条、complete=false、1 条 error）
                走同一条路径；用于证明失败必然非零退出

退出约定（PR #56 复核第 2 条）：**只有本批完整 2000 条全量重算满足约定才退出 0**。
`replay` 分支无论判定结果如何都先把原始报告落盘（证据不丢），再做门禁：
status/scope/重算条数/complete_physics_recalculation/same_environment/errors
任一项不符即以退出码 1 结束，"报告写完"绝不等于"重放通过"。

路径可用环境变量覆盖（默认是本机开发目录）：
  C_PART_FP（生成器根）、C_PART_DATASET（数据集目录）、C_PART_QC_OUT（报告输出目录）
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

FP = Path(os.environ.get('C_PART_FP',
    'C:/Users/TianT/Desktop/兴智杯AI/fp-spectrum-generator-competition-v0.2.1/fp_competition'))
DATASET = Path(os.environ.get('C_PART_DATASET', str(FP / 'P5_dataset_v2')))
OUT = Path(os.environ.get('C_PART_QC_OUT',
    'C:/Users/TianT/Desktop/兴智杯AI/C_part/v2_qc'))
ZIP_OUT = OUT / 'P5_v2_dataset.zip'
STUB_OUT = OUT / 'selftest'
STAGE = (sys.argv[1] if len(sys.argv) > 1 else 'quick')

REQUIRED_SCOPE = 'all_records'

# 合成报告：只走判定路径，绝不写入正式报告文件名
STUB_PASS = {'status': 'passed', 'scope': REQUIRED_SCOPE, 'spectra_recalculated': 2000,
             'complete_physics_recalculation': True, 'same_environment': True,
             'maximum_absolute_array_difference': 0.0, 'rtol': 1e-12, 'atol_counts': 1e-08,
             'errors': []}
STUB_FAIL = {'status': 'failed', 'scope': REQUIRED_SCOPE, 'spectra_recalculated': 1,
             'complete_physics_recalculation': False, 'same_environment': True,
             'maximum_absolute_array_difference': 0.0, 'rtol': 1e-12, 'atol_counts': 1e-08,
             'errors': [{'id': 'S000002', 'reason': 'injected failure'}]}


def save(name, payload, directory=OUT):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (name + '.json')).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                              encoding='utf-8')
    print(name, payload.get('status'), flush=True)


def expected_spectra():
    """期望条数取自密封 manifest 本身，并与 records 逐项对齐；不一致直接失败。"""
    manifest = json.loads((DATASET / 'manifest.json').read_text(encoding='utf-8'))
    count = manifest.get('spectrum_count')
    records = len(manifest.get('records', []))
    if count != records:
        raise SystemExit(f'expected-count mismatch: manifest.spectrum_count={count} '
                         f'!= len(records)={records}')
    return int(count)


def evaluate_replay(report, expected):
    """全量物理重算的门禁：返回不合格项列表（空即通过）。"""
    problems = []
    if report.get('status') != 'passed':
        problems.append(f"status={report.get('status')!r} 应为 'passed'")
    if report.get('scope') != REQUIRED_SCOPE:
        problems.append(f"scope={report.get('scope')!r} 应为 {REQUIRED_SCOPE!r}（全量，不是抽样）")
    got = report.get('spectra_recalculated')
    if got != expected:
        problems.append(f'spectra_recalculated={got!r} 应为本批全量 {expected}')
    if report.get('complete_physics_recalculation') is not True:
        problems.append('complete_physics_recalculation 不为 true（未做完整物理重算）')
    if report.get('same_environment') is not True:
        problems.append('same_environment 不为 true（重算环境与生成环境不一致）')
    errors = report.get('errors') or []
    if errors:
        problems.append(f'errors 非空：{len(errors)} 条，示例 {errors[0]}')
    diff = report.get('maximum_absolute_array_difference')
    if not isinstance(diff, (int, float)):
        problems.append(f'maximum_absolute_array_difference 非数值：{diff!r}')
    return problems


def evaluate_audit(report, expected):
    problems = []
    if report.get('status') not in ('passed', 'passed_with_environment_differences'):
        problems.append(f"audit status={report.get('status')!r}")
    if report.get('spectra_checked') != expected:
        problems.append(f"audit spectra_checked={report.get('spectra_checked')!r} 应为 {expected}")
    if report.get('errors'):
        problems.append(f"audit errors 非空：{len(report['errors'])} 条")
    return problems


def gate(kind, report, expected):
    """判定后统一走这里：不合格 → 保留报告 + 非零退出。"""
    problems = evaluate_replay(report, expected) if kind == 'replay' else evaluate_audit(report, expected)
    if problems:
        print(f'{kind} 判定不合格：\n  - ' + '\n  - '.join(problems), flush=True)
        raise SystemExit(1)
    print(f'{kind} 判定通过：全量 {expected} 条、0 错误', flush=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    if STAGE in ('stub-pass', 'stub-fail'):
        report = dict(STUB_PASS if STAGE == 'stub-pass' else STUB_FAIL)
        save(f'{STAGE}_replay', report, STUB_OUT)          # 只进 selftest 目录，不碰正式报告
        gate('replay', report, 2000)                       # 期望条数固定为本批全量 2000
        return

    if not (DATASET / 'manifest.json').exists():
        raise SystemExit('dataset not present: ' + str(DATASET))
    expected = expected_spectra()

    sys.path.insert(0, str(FP))
    import dataset as ds          # noqa: E402  生成器自身模块

    if STAGE == 'replay':
        t = time.time()
        replay = ds.replay_dataset(DATASET, None, lambda i, n: print(f'replay {i}/{n}', flush=True)
                                   if i % 200 == 0 else None)
        save('P5_v2_replay', replay)                       # 先落盘，证据不丢
        print('replay seconds', round(time.time() - t, 1), 'errors',
              len(replay.get('errors', [])), flush=True)
        gate('replay', replay, expected)                   # 不合格 → 退出码 1
        return

    t0 = time.time()
    audit = ds.audit_dataset(DATASET)
    save('P5_v2_audit', audit)
    print('audit seconds', round(time.time() - t0, 1), 'errors',
          len(audit.get('errors', [])), flush=True)
    gate('audit', audit, expected)

    t1 = time.time()
    if ZIP_OUT.exists():
        ZIP_OUT.unlink()
    pack = ds.pack_dataset(DATASET, ZIP_OUT)
    save('P5_v2_pack', pack)
    print('pack seconds', round(time.time() - t1, 1),
          json.dumps(pack, ensure_ascii=False)[:300], flush=True)
    if pack.get('status') not in (None, 'passed', 'complete'):
        raise SystemExit(f"pack status={pack.get('status')!r}，非零退出")
    if not ZIP_OUT.is_file() or ZIP_OUT.stat().st_size != pack.get('zip_size'):
        raise SystemExit('pack 产物与报告体积不符，非零退出')

    sha_path = Path(str(ZIP_OUT) + '.sha256')
    replay_path = OUT / 'P5_v2_replay.json'
    replay = (json.loads(replay_path.read_text(encoding='utf-8'))
              if replay_path.exists() else {'status': 'not_run_yet'})
    summary = {
        'expected_spectra': expected,
        'audit': {k: audit.get(k) for k in ('status', 'spectra_checked',
                                            'complete_physics_recalculation')},
        'audit_errors': len(audit.get('errors', [])),
        'audit_seconds': round(time.time() - t0, 1),
        'pack': {'status': pack.get('status'), 'zip_bytes': ZIP_OUT.stat().st_size,
                 'sha256': sha_path.read_text(encoding='ascii').strip() if sha_path.exists() else ''},
        'pack_seconds': round(time.time() - t1, 1),
        'replay': replay.get('status'),
        'replay_problems': evaluate_replay(replay, expected) if replay.get('status') != 'not_run_yet' else ['not_run_yet'],
    }
    save('P5_v2_qc_summary', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
