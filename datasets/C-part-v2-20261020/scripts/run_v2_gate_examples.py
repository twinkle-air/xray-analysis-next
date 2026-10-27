"""PR #56 复核两条阻断项的正/负例实跑，记录**真实退出码**。

复现方式（评审者可原样重跑）：
  python -B scripts/run_v2_gate_examples.py            # 用生成器同一个解释器（3.15）跑

场景：
  A  从"新 clone 的交付布局"默认入口跑 `c_pilot_guard.py`（不显式给 --index）→ 期望退出 0
  B  同一守卫喂一份含可训练行的索引（负例）→ 期望退出 1，且打印 NOT BLOCKED
  C  `check_and_pack_p5_v2.py stub-pass`（合成通过报告走同一判定路径）→ 期望退出 0
  D  `check_and_pack_p5_v2.py stub-fail`（故障注入：failed / 只 1 条 / complete=false / 1 条 error）→ 期望退出 1
  E  用随包的判定函数复核**已交付的真·全量 replay 报告** → 不合格项应为空

产物：C_part/v2_qc/gate_examples.json（随包为 C_qc_gate_report.json）
"""
from __future__ import annotations
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def env_with(**extra):
    return {**os.environ, **extra}

HERE = Path(__file__).resolve().parent.parent                  # C_part
PAYLOAD = HERE / 'github_payload_v2' / 'datasets' / 'C-part-v2-20261020'
SIM = HERE / 'gate_examples' / 'clone_sim'
QC_OUT = HERE / 'v2_qc'
PY = Path(sys.executable)
REPORT = QC_OUT / 'gate_examples.json'

BATCH_DIRNAME = 'datasets/C-part-v2-20261020'


def run(cmd, cwd=None, env=None):
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env)
    return {'cmd': [str(x) for x in cmd], 'cwd': str(cwd), 'exit_code': p.returncode,
            'stdout_tail': (p.stdout or '')[-900:], 'stderr_tail': (p.stderr or '')[-900:]}


def build_clone_sim():
    """只复制索引与两个脚本，目录结构与仓库交付布局一致（脚本在 scripts/ 下）。"""
    if SIM.exists():
        shutil.rmtree(SIM)
    (SIM / 'scripts').mkdir(parents=True)
    shutil.copy2(PAYLOAD / 'C_authoritative_index.csv', SIM / 'C_authoritative_index.csv')
    for name in ('c_pilot_guard.py', 'check_and_pack_p5_v2.py'):
        shutil.copy2(PAYLOAD / 'scripts' / name, SIM / 'scripts' / name)
    return SIM


def make_trainable_index():
    """负例索引：把**全部**行的留出字段改回可训练语义，
    证明自检不是"永远返回通过"——此时三入口应显示 NOT BLOCKED 并以退出码 1 结束。"""
    src = SIM / 'C_authoritative_index.csv'
    dst = SIM / 'index_with_trainable_rows.csv'
    rows = list(csv.DictReader(src.open(encoding='utf-8-sig', newline='')))
    for r in rows:
        r['benchmark_split'] = 'train'
        r['holdout_status'] = 'not_heldout'
        r['usage_policy'] = 'trainable'
        r['batch_version'] = 'production'
    with dst.open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return dst


def main() -> int:
    build_clone_sim()
    result = {'payload': BATCH_DIRNAME, 'interpreter': str(PY), 'cases': {}}

    result['cases']['A_guard_default_entry'] = run([PY, '-B', str(SIM / 'scripts' / 'c_pilot_guard.py')],
                                                   cwd=SIM)
    neg = make_trainable_index()
    result['cases']['B_guard_negative_index'] = run(
        [PY, '-B', str(SIM / 'scripts' / 'c_pilot_guard.py'), '--index', str(neg)], cwd=SIM)
    result['cases']['C_qc_stub_pass'] = run(
        [PY, '-B', str(SIM / 'scripts' / 'check_and_pack_p5_v2.py'), 'stub-pass'],
        cwd=SIM, env=env_with(C_PART_QC_OUT=str(SIM / 'selftest')))
    result['cases']['D_qc_stub_fail'] = run(
        [PY, '-B', str(SIM / 'scripts' / 'check_and_pack_p5_v2.py'), 'stub-fail'],
        cwd=SIM, env=env_with(C_PART_QC_OUT=str(SIM / 'selftest')))

    # E：真报告用随包判定函数复核
    sys.path.insert(0, str(SIM / 'scripts'))
    import check_and_pack_p5_v2 as qc                       # noqa: E402
    delivered = json.loads((PAYLOAD / 'P5_replay.json').read_text(encoding='utf-8'))
    expected = json.loads((PAYLOAD / 'C_coverage.json').read_text(encoding='utf-8'))['spectra']
    result['cases']['E_delivered_replay_report'] = {
        'file': 'P5_replay.json', 'expected_spectra': expected,
        'problems': qc.evaluate_replay(delivered, expected),
        'status_field': delivered.get('status'),
        'spectra_recalculated': delivered.get('spectra_recalculated'),
    }

    want = {'A_guard_default_entry': 0, 'B_guard_negative_index': 1,
            'C_qc_stub_pass': 0, 'D_qc_stub_fail': 1}
    mismatch = {k: result['cases'][k]['exit_code'] for k, v in want.items()
                if result['cases'][k]['exit_code'] != v}
    if result['cases']['E_delivered_replay_report']['problems']:
        mismatch['E_delivered_replay_report'] = result['cases']['E_delivered_replay_report']['problems']
    result['expected_exit_codes'] = want
    result['mismatch'] = mismatch
    result['passed'] = not mismatch
    QC_OUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': result['passed'],
                      'exit_codes': {k: result['cases'][k].get('exit_code', 'n/a')
                                     for k in list(want) + ['E_delivered_replay_report']},
                      'mismatch': mismatch}, ensure_ascii=False, indent=2), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
