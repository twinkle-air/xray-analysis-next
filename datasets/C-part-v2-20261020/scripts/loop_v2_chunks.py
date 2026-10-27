"""C 部分：v2 批次自动续跑循环（目标 2000 谱）。

反复调用 generate_v2_batch.py <每批条数>，直到 P5_dataset_v2 的谱数达到 2000 或出错。
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve()
OUT = Path('C:/Users/TianT/Desktop/兴智杯AI/fp-spectrum-generator-competition-v0.2.1/fp_competition/P5_dataset_v2')
TARGET = 2000
CHUNK = int(sys.argv[1]) if len(sys.argv) > 1 else 250


def count_spectra():
    manifest = OUT / 'manifest.json'
    if not manifest.exists():
        return 0
    return len(json.loads(manifest.read_text(encoding='utf-8')).get('records', []))


def main():
    for attempt in range(1, 100):
        current = count_spectra()
        if current >= TARGET:
            print(f'already {current} >= {TARGET}; done', flush=True)
            return
        size = min(CHUNK, TARGET - current)
        print(f'--- attempt {attempt}: {current}/{TARGET}, chunk {size}', flush=True)
        r = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT.parent / 'generate_v2_batch.py'),
                            str(size)], capture_output=True, text=True)
        print(r.stdout.strip(), flush=True)
        if r.returncode != 0:
            print('FAILED on chunk', size, flush=True)
            print(r.stderr[-2000:], flush=True)
            return
        new = count_spectra()
        print(f'  after chunk: {new} (+{new - current})', flush=True)
        if new <= current:
            print('no progress; aborting', flush=True)
            return
    print('too many attempts', flush=True)


if __name__ == '__main__':
    main()
