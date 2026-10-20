"""Record local generator digests and compare them with A's sealed P1 snapshot.

Read-only: hashes the workspace generator and the generator copy inside
A-part-20261018/P1_pack.zip, then checks both against physics_baseline.json.
"""
from __future__ import annotations
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # ...\兴智杯AI开发大赛
GEN = ROOT / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition'
A_PACK = ROOT / 'datasets' / 'A-part-20261018' / 'P1_pack.zip'
A_PACK2 = ROOT / 'datasets' / 'A-part-20261018' / 'P2_pack.zip'
OUT = Path(__file__).resolve().parent / 'B_source_verification.json'
PREFIX = 'reproducibility/generator/fp_competition/'
KEY_FILES = ('app.py', 'core.py', 'minerals.py', 'dataset.py', 'requirements-lock.txt')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def local_files():
    rows = {}
    for path in sorted(GEN.rglob('*')):
        if path.is_file():
            relative = path.relative_to(GEN).as_posix()
            rows[relative] = {'sha256': sha256_file(path), 'bytes': path.stat().st_size}
    return rows


def sealed_files(pack: Path):
    rows = {}
    with zipfile.ZipFile(pack) as archive:
        for name in archive.namelist():
            if name.startswith(PREFIX) and not name.endswith('/'):
                rows[name[len(PREFIX):]] = sha256_bytes(archive.read(name))
    return rows


def main():
    local = local_files()
    sealed_p1 = sealed_files(A_PACK)
    sealed_p2 = sealed_files(A_PACK2)
    baseline = json.loads((GEN / 'physics_baseline.json').read_text(encoding='utf-8'))
    baseline_files = baseline.get('files', {})
    baseline_check = {}
    for name, digest in sorted(baseline_files.items()):
        candidate = GEN / name
        relative = name.split('fp_competition/')[-1] if 'fp_competition/' in name else name
        actual = sha256_file(candidate) if candidate.is_file() else None
        baseline_check[relative] = {'expected': digest, 'actual_local': actual,
                                    'match': actual == digest}
    compared = sorted(set(local) & set(sealed_p1))
    mismatches = [name for name in compared if local[name]['sha256'] != sealed_p1[name]]
    only_local = sorted(set(local) - set(sealed_p1))
    only_sealed = sorted(set(sealed_p1) - set(local))
    p1_vs_p2 = [name for name in sorted(set(sealed_p1) & set(sealed_p2))
                if sealed_p1[name] != sealed_p2[name]]
    report = {
        'purpose': 'Re-record local generator digests and verify them against the generator '
                   'sealed inside A P1_pack.zip before using the local CLI for production',
        'generator_local_directory': str(GEN),
        'a_sealed_pack': str(A_PACK),
        'a_sealed_pack_sha256': sha256_file(A_PACK),
        'a_sealed_pack_p2_sha256': sha256_file(A_PACK2),
        'local_file_count': len(local),
        'sealed_file_count': len(sealed_p1),
        'compared_count': len(compared),
        'key_files': {name: {'local_sha256': local.get(name, {}).get('sha256'),
                             'sealed_p1_sha256': sealed_p1.get(name),
                             'match': local.get(name, {}).get('sha256') == sealed_p1.get(name)}
                      for name in KEY_FILES},
        'local_files': local,
        'sealed_p1_files': sealed_p1,
        'sealed_p2_files_count': len(sealed_p2),
        'sealed_p1_vs_p2_mismatches': p1_vs_p2,
        'mismatches': mismatches,
        'only_in_local_not_sealed': only_local,
        'only_in_sealed_not_local': only_sealed,
        'physics_baseline_record': baseline,
        'physics_baseline_check': baseline_check,
        'status': 'passed' if not mismatches and not p1_vs_p2 else 'blocked_source_mismatch',
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'local': len(local), 'sealed': len(sealed_p1), 'compared': len(compared),
                      'mismatches': mismatches, 'p1_vs_p2': p1_vs_p2,
                      'baseline_all_match': all(v['match'] for v in baseline_check.values()),
                      'status': report['status']}, ensure_ascii=False))


if __name__ == '__main__':
    raise SystemExit(main())
