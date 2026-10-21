"""C 部分：只读地汇报 v2 批次的真实生成进度，供归档说明引用。

绝不下划线式推测：所有数字都来自磁盘上的实际文件与 manifest。
审计/重算/打包是否做过也只看 manifest 与目录内是否存在相应产物，没做就写 not_done。

用法：
    python -B scripts/v2_generation_status.py [数据集目录] [主表]
缺省数据集取 `FP_COMPETITION/P5_dataset_v2`，主表取 `v2/master_samples_v2.json`。
输出：`v2/generation_status_v2.json` 与 `.md`。
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
FP = Path(os.environ.get('FP_COMPETITION',
                         'C:/Users/TianT/Desktop/兴智杯AI/'
                         'fp-spectrum-generator-competition-v0.2.1/fp_competition'))
TARGET = 2000
SECONDS_PER_SPECTRUM = (1.8, 2.5)          # 实测区间，见 P5_check_timings.json


def count(p: Path) -> int:
    return len(list(p.glob('*.json'))) if p.is_dir() else 0


def dir_bytes(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) if p.is_dir() else 0


def main():
    dataset = Path(sys.argv[1]) if len(sys.argv) > 1 else FP / 'P5_dataset_v2'
    master = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / 'v2' / 'master_samples_v2.json'
    out = {'dataset_dir': dataset.name, 'dataset_exists': dataset.is_dir(),
           'target_spectra': TARGET}
    manifest = {}
    if (dataset / 'manifest.json').is_file():
        manifest = json.loads((dataset / 'manifest.json').read_text(encoding='utf-8'))

    blind = count(dataset / 'blind_inputs')
    full = count(dataset / 'full_results')
    truth_lines = len([l for l in (dataset / 'truth.jsonl').read_text(encoding='utf-8')
                       .splitlines() if l.strip()]) if (dataset / 'truth.jsonl').is_file() else 0
    recs = len(manifest.get('records', []))
    fams = len({r.get('family') for r in manifest.get('records', []) if r.get('family')})

    qc = {n: (dataset / n).is_file() for n in
          ('audit.json', 'replay.json', 'integrity.json', 'reproducibility/environment.json')}
    finished = manifest.get('status') == 'complete' and blind >= TARGET

    out.update({
        'master': {'name': master.name,
                   'sha256': hashlib.sha256(master.read_bytes()).hexdigest()
                   if master.is_file() else None},
        'manifest_identity': {k: manifest.get(k) for k in
                              ('schema', 'software_version', 'physical_model_version',
                               'batch_version', 'supersedes', 'seed', 'split_seed',
                               'replicates', 'status', 'acceptance_status',
                               'source_samples_semantic_sha256', 'physics_core_sha256')},
        'progress': {'blind_inputs': blind, 'full_results': full, 'truth_rows': truth_lines,
                     'manifest_records': recs, 'distinct_families': fams,
                     'consistent': blind == full == truth_lines,
                     'percent_of_target': round(100.0 * blind / TARGET, 1)},
        'qc_artifacts_present': qc,
        'qc_stage': ('sealed_complete_batch' if finished and qc['integrity.json']
                     else 'generating' if not finished else 'generated_unsealed'),
        'sealed': bool((dataset / 'integrity.json').is_file()),
        'disk_bytes': dir_bytes(dataset),
        'delivery': {'pushed_to_github': False,
                     'note': '本文件只描述本地批次；是否推送以分支上的提交为准。'},
        'time_budget': {'seconds_per_spectrum_measured': list(SECONDS_PER_SPECTRUM),
                        'remaining_spectra': max(0, TARGET - blind),
                        'remaining_minutes_range': [round(max(0, TARGET - blind) * s / 60, 1)
                                                    for s in SECONDS_PER_SPECTRUM]},
        'finished': finished,
    })
    out['caveats'] = [
        '合成数据；未做真实设备校准，不能据此得出 95%/5% 一类准确率结论。',
        '批次未完成前 manifest.records 只是阶段性清单，不可作为最终交付依据。',
        '本批若最终不用于交付，也仅作为候选试产，不得进入训练/调参入口。']

    (HERE / 'v2').mkdir(exist_ok=True)
    (HERE / 'v2' / 'generation_status_v2.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    p = out['progress']
    lines = ['# v2 批次生成状态（只读快照）', '',
             f'- 数据集目录：`{out["dataset_dir"]}`｜阶段：**{out["qc_stage"]}**｜'
             f'谱数 {p["blind_inputs"]}/{TARGET}（{p["percent_of_target"]}%）',
             f'- 三者一致性：blind {p["blind_inputs"]} / full {p["full_results"]} / '
             f'truth {p["truth_rows"]} → {p["consistent"]}；'
             f'manifest.records {p["manifest_records"]}，独立族 {p["distinct_families"]}',
             f'- 主表：`{out["master"]["name"]}` SHA-256 `{(out["master"]["sha256"] or "—")[:16]}…`',
             f'- 批次身份：{json.dumps(out["manifest_identity"], ensure_ascii=False)}',
             f'- 磁盘占用：{out["disk_bytes"] / 2 ** 30:.2f} GiB｜'
             f'剩余 {out["time_budget"]["remaining_spectra"]} 谱，'
             f'预计 {out["time_budget"]["remaining_minutes_range"][0]}–'
             f'{out["time_budget"]["remaining_minutes_range"][1]} 分钟',
             f'- 质检产物：{json.dumps(out["qc_artifacts_present"], ensure_ascii=False)}',
             f'- 是否已推送 GitHub：否（以分支提交为准）', '',
             '## 说明', '']
    lines += [f'- {c}' for c in out['caveats']]
    (HERE / 'v2' / 'generation_status_v2.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(out['qc_stage'], p['blind_inputs'], '/', TARGET, 'consistent', p['consistent'])


if __name__ == '__main__':
    main()
