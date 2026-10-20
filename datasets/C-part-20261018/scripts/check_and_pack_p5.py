"""C 部分：P5 批次的外部全量 audit、全量物理重算与打包。

全部报告写在数据集目录之外；pack 执行 audit 并产出 ZIP + 外部 SHA-256。
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

FP = Path('C:/Users/TianT/Desktop/兴智杯AI/fp-spectrum-generator-competition-v0.2.1/fp_competition')
DATASET = FP / 'P5_dataset'
OUT = Path('C:/Users/TianT/Desktop/兴智杯AI/C_part')
SNAPSHOT_APP = FP / 'P5_dataset' / 'reproducibility' / 'generator' / 'fp_competition' / 'app.py'
PYTHON = sys.executable


def report(name, status, **extra):
    payload = {'check': name, 'status': status, **extra}
    (OUT / (name + '.json')).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                        encoding='utf-8')
    print(name, status)


def main():
    if not (DATASET / 'manifest.json').exists():
        raise SystemExit('dataset not present: ' + str(DATASET))

    # 1. audit：用封存源码快照全量遍历
    if SNAPSHOT_APP.exists():
        cmd = [PYTHON, '-B', str(SNAPSHOT_APP), 'audit', '--dataset', str(DATASET),
               '--out', str(OUT / 'P5_qc.json')]
    else:
        cmd = [PYTHON, '-B', str(FP / 'app.py'), 'audit', '--dataset', str(DATASET),
               '--out', str(OUT / 'P5_qc.json')]
    print('audit:', ' '.join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-600:] if r.stdout else '')
    if r.returncode != 0:
        print('audit stderr:', r.stderr[-1200:])
    try:
        qc = json.loads((OUT / 'P5_qc.json').read_text(encoding='utf-8'))
        report('P5_qc', qc.get('status', 'errored'),
               spectra_checked=qc.get('spectra_checked'), errors=len(qc.get('errors', [])))
    except Exception as exc:
        report('P5_qc', 'errored', message=str(exc))
        print('audit report unavailable:', exc)
        raise SystemExit('audit failed; cannot replay or pack')

    # 2. 全量物理重算（不加 --limit）
    if SNAPSHOT_APP.exists():
        cmd = [PYTHON, '-B', str(SNAPSHOT_APP), 'replay', '--dataset', str(DATASET),
               '--out', str(OUT / 'P5_replay.json')]
    else:
        cmd = [PYTHON, '-B', str(FP / 'app.py'), 'replay', '--dataset', str(DATASET),
               '--out', str(OUT / 'P5_replay.json')]
    print('replay:', ' '.join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-600:] if r.stdout else '')
    if r.returncode != 0:
        print('replay stderr:', r.stderr[-1200:])
    try:
        replay = json.loads((OUT / 'P5_replay.json').read_text(encoding='utf-8'))
        report('P5_replay', replay.get('status', 'errored'),
               scope=replay.get('scope'), spectra_recalculated=replay.get('spectra_recalculated'),
               same_environment=replay.get('same_environment'),
               maximum_absolute_array_difference=replay.get('maximum_absolute_array_difference'),
               errors=len(replay.get('errors', [])))
    except Exception as exc:
        report('P5_replay', 'errored', message=str(exc))

    # 3. 打包：ZIP + 外部 SHA-256（pack 内部先执行 audit）
    zip_out = OUT / 'P5_dataset.zip'
    if zip_out.exists():
        zip_out.unlink()
    if SNAPSHOT_APP.exists():
        cmd = [PYTHON, '-B', str(SNAPSHOT_APP), 'pack', '--dataset', str(DATASET),
               '--out', str(zip_out)]
    else:
        cmd = [PYTHON, '-B', str(FP / 'app.py'), 'pack', '--dataset', str(DATASET),
               '--out', str(zip_out)]
    print('pack:', ' '.join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-600:] if r.stdout else '')
    if r.returncode != 0:
        print('pack stderr:', r.stderr[-1200:])
        report('P5_pack', 'errored', message=r.stderr[-800:])
    else:
        try:
            pack = json.loads(r.stdout)
            sha = (OUT / (str(zip_out) + '.sha256')).read_text(encoding='ascii').strip()
            report('P5_pack', 'passed', archive=pack.get('archive'), sha256=sha,
                   zip_size=zip_out.stat().st_size)
        except Exception as exc:
            report('P5_pack', 'errored', message=str(exc))


if __name__ == '__main__':
    main()