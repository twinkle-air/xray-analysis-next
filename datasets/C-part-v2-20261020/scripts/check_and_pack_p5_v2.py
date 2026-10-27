"""C 部分：v2 批次（P5_dataset_v2）QC。

stage 参数：
  quick  —— audit（逐谱完整性/一致性/泊松重放）+ pack（确定性 ZIP + 外部 SHA-256）
  replay —— 全量物理重算（2.6 s/谱，约 1.5 h），可后台补跑

直接用生成器 dataset 模块，避开 CLI 的 --out 全新路径限制；报告写在数据集目录之外。
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

FP = Path('C:/Users/TianT/Desktop/兴智杯AI/fp-spectrum-generator-competition-v0.2.1/fp_competition')
DATASET = FP / 'P5_dataset_v2'
OUT = Path('C:/Users/TianT/Desktop/兴智杯AI/C_part/v2_qc')
ZIP_OUT = OUT / 'P5_v2_dataset.zip'
STAGE = (sys.argv[1] if len(sys.argv) > 1 else 'quick')

sys.path.insert(0, str(FP))
import dataset as ds          # noqa: E402


def save(name, payload):
    (OUT / (name + '.json')).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                        encoding='utf-8')
    print(name, payload.get('status'), flush=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if not (DATASET / 'manifest.json').exists():
        raise SystemExit('dataset not present: ' + str(DATASET))

    if STAGE == 'replay':
        t = time.time()
        replay = ds.replay_dataset(DATASET, None, lambda i, n: print(f'replay {i}/{n}', flush=True)
                                   if i % 200 == 0 else None)
        save('P5_v2_replay', replay)
        print('replay seconds', round(time.time() - t, 1), 'errors',
              len(replay.get('errors', [])), flush=True)
        return

    t0 = time.time()
    audit = ds.audit_dataset(DATASET)
    save('P5_v2_audit', audit)
    print('audit seconds', round(time.time() - t0, 1), 'errors',
          len(audit.get('errors', [])), flush=True)
    if audit.get('status') not in ('passed', 'passed_with_environment_differences'):
        raise SystemExit('audit failed; cannot pack')

    t1 = time.time()
    if ZIP_OUT.exists():
        ZIP_OUT.unlink()
    pack = ds.pack_dataset(DATASET, ZIP_OUT)
    print('pack seconds', round(time.time() - t1, 1),
          json.dumps(pack, ensure_ascii=False)[:300], flush=True)

    sha_path = Path(str(ZIP_OUT) + '.sha256')
    replay_path = OUT / 'P5_v2_replay.json'
    summary = {
        'audit': {k: audit.get(k) for k in ('status', 'spectra_checked',
                                            'complete_physics_recalculation')},
        'audit_errors': len(audit.get('errors', [])),
        'audit_seconds': round(time.time() - t0, 1),
        'pack': {'status': pack.get('status'), 'zip_bytes': ZIP_OUT.stat().st_size,
                 'sha256': sha_path.read_text(encoding='ascii').strip() if sha_path.exists() else ''},
        'pack_seconds': round(time.time() - t1, 1),
        'replay': (json.loads(replay_path.read_text(encoding='utf-8')).get('status')
                   if replay_path.exists() else 'not_run_yet'),
    }
    save('P5_v2_qc_summary', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
