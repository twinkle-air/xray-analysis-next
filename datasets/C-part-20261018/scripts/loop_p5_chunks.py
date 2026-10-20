"""C 部分：P5 批次自动续跑循环。

反复调用 resume_p5_batch.py <每批条数>，直到谱数达到 2000 或出错。
"""
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve()
TARGET = 2000
CHUNK = int(sys.argv[1]) if len(sys.argv) > 1 else 250


def count_spectra():
    import json
    manifest = SCRIPT.parent.parent.parent / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition' / 'P5_dataset' / 'manifest.json'
    if not manifest.exists():
        return 0
    return len(json.loads(manifest.read_text(encoding='utf-8')).get('records', []))


def main():
    for attempt in range(1, 100):
        current = count_spectra()
        if current >= TARGET:
            print(f'already {current} >= {TARGET}; done')
            return
        remaining = TARGET - current
        size = min(CHUNK, remaining)
        print(f'--- attempt {attempt}: {current}/{TARGET} target, running chunk {size}')
        r = subprocess.run([sys.executable, str(SCRIPT.parent / 'resume_p5_batch.py'), str(size)],
                           capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode != 0:
            print('FAILED on chunk', size)
            print(r.stderr[-1500:])
            return
        new = count_spectra()
        print(f'  after chunk: {new} ({new - current} added)')
        if new <= current:
            print('no progress; aborting')
            return
    print('too many attempts')


if __name__ == '__main__':
    main()