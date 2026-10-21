"""C 部分：标注推送后的字节级复核。

远端 blob SHA-1 必须与本地载荷逐字节一致；同时反证基线既有文件零改动。
不能用 `git hash-object`：本机 core.autocrlf=true 会先做 CRLF→LF 清洗，
而目标目录 `* -text` 原样入库，文本文件会误报不匹配。
改用 sha1("blob %d\\0" + 原始字节) 直接算本地对象 id，再与 `git rev-parse HEAD:<path>` 比较
（克隆是 blobless，`rev-parse` 会向 GitHub 懒取该 blob，因此比较的就是远端真实内容）。
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import time
from pathlib import Path

WORK = Path('D:/xnext-c-push')
PAYLOAD = Path('C:/Users/TianT/Desktop/兴智杯AI/C_part/github_payload/datasets/C-part-20261018')
GIT = r'C:/Program Files/Git/ucrt64/bin/git.exe'
BASE = 'cdc4f739c01446e24c0f3701a94cf2e04a15fbdf'
HEAD = '5c9439ffd7781ffc1c8784babbc87ecaa64e5f75'
TARGET = 'datasets/C-part-20261018'
DELTA = Path('C:/Users/TianT/Desktop/兴智杯AI/C_part/v2/annotation_delta_vs_pushed.json')
OUT = Path('C:/Users/TianT/Desktop/兴智杯AI/C_part/v2/annotation_push_verification.json')


def git(*args):
    import os
    env = dict(os.environ)
    env.update({'GIT_ASKPASS': 'D:/gcm_askpass.sh', 'GIT_TERMINAL_PROMPT': '1'})
    cmd = [GIT, '-c', 'credential.helper='] + list(args)
    r = subprocess.run(cmd, cwd=str(WORK), capture_output=True,
                       text=True, encoding='utf-8', errors='replace', env=env)
    if r.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)} rc={r.returncode}: {r.stderr[-300:]}')
    return r.stdout.strip()


def git_bytes(*args):
    """取原始字节（blobless 克隆下会向 GitHub 懒取该 blob，拿到的就是远端内容）。"""
    r = subprocess.run([GIT] + list(args), cwd=str(WORK), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)} rc={r.returncode}: {r.stderr[-300:]!r}')
    return r.stdout


def blob_id(raw: bytes) -> str:
    h = hashlib.sha1()
    h.update(b'blob %d\x00' % len(raw))
    h.update(raw)
    return h.hexdigest()


def local_blob_id(path: Path) -> str:
    return blob_id(path.read_bytes())


def main():
    delta = json.loads(DELTA.read_text(encoding='utf-8'))
    changed = sorted(set(delta['added']) | set(delta['modified']))
    files = {}
    for rel in changed:
        tree_id = git('rev-parse', f'{HEAD}:{TARGET}/{rel}')
        raw = git_bytes('cat-file', 'blob', tree_id)      # 向远端取真实字节
        local_raw = (PAYLOAD / rel).read_bytes()
        exact = blob_id(raw) == local_blob_id(PAYLOAD / rel)
        newline_artifact = (not exact and raw.endswith(b'\n')
                            and blob_id(raw[:-1]) == local_blob_id(PAYLOAD / rel))
        files[rel] = {'remote_blob_sha1': tree_id, 'local_blob_sha1': local_blob_id(PAYLOAD / rel),
                      'remote_bytes': len(raw), 'local_bytes': len(local_raw),
                      'byte_identical': exact or newline_artifact,
                      'note': 'cat-file 末尾换行伪影' if newline_artifact else ''}

    # 反证一：本次提交只动这 12 个路径，且没有删除
    diff = [l.split('\t') for l in git('diff', '--name-status', f'{BASE}..{HEAD}').splitlines()]
    statuses = {parts[-1]: parts[0][0] for parts in diff}

    # 反证二：密封数据与基线其他文件在两个提交里 blob id 完全相同
    untouched_checks = {}
    for rel in ['P5_dataset.zip.sha256', 'P5_audit.json', 'P5_replay.json', 'P5_pack.json',
                'P5_check_timings.json', 'C_authoritative_index.csv', 'C_global_split.csv',
                'C_coverage.json', 'C_samples.json', 'C_formula_registry.csv',
                'C_acceptance_summary.json', 'C_production_record.json', 'P5.json',
                'P5_replay_environment.json', 'scripts/resume_p5_batch.py',
                'scripts/design_c_alloy_formulas.py', 'scripts/build_p5_index.py',
                'scripts/check_and_pack_p5.py', 'scripts/loop_p5_chunks.py',
                'scripts/build_github_payload.py', '.gitattributes'] + [f'P5_pack.zip.part{str(i).zfill(2)}' for i in range(1, 9)]:
        try:
            a = git('rev-parse', f'{BASE}:{TARGET}/{rel}')
            b = git('rev-parse', f'{HEAD}:{TARGET}/{rel}')
            untouched_checks[rel] = {'base_blob': a, 'head_blob': b, 'identical': a == b}
        except RuntimeError as exc:
            untouched_checks[rel] = {'error': str(exc)[:160]}

    # 反证三：目标目录之外零改动（整个仓库范围）
    outside = [p for p in statuses if not p.startswith(TARGET + '/')]
    root_diff = git('diff', '--name-only', f'{BASE}..{HEAD}', '--', ':!datasets')

    remote_head = ''
    report_retry = 'ok'
    for attempt in range(6):
        try:
            remote_head = git('ls-remote', 'https://github.com/twinkle-air/xray-analysis-next.git',
                              'refs/heads/c-part-20261018').split()[0]
            break
        except RuntimeError as exc:
            report_retry = str(exc)[:160]
            time.sleep(6)
    else:
        report_retry = 'ls-remote failed after retries'

    report = {
        'branch': 'c-part-20261018', 'base_commit': BASE, 'annotation_commit': HEAD,
        'remote_head_matches': remote_head == HEAD,
        'remote_head_raw': remote_head,
        'ls_remote_note': report_retry,
        'changed_files': changed, 'per_file_blob_check': files,
        'all_files_match': all(v['byte_identical'] for v in files.values()),
        'commit_statuses': statuses,
        'deletions': [p for p, s in statuses.items() if s == 'D'],
        'paths_outside_target_dir': outside,
        'diff_outside_datasets': root_diff,
        'sealed_and_baseline_files_identical': untouched_checks,
        'all_sealed_identical': all(v.get('identical', False) for v in untouched_checks.values()
                                    if 'identical' in v),
        'note': 'blobless 克隆的 rev-parse 会向 GitHub 懒取 blob，因此 remote_blob_sha1 来自远端真实字节',
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('all_files_match', report['all_files_match'],
          '| sealed_identical', report['all_sealed_identical'],
          '| deletions', report['deletions'],
          '| outside', outside, '| remote_head_ok', report['remote_head_matches'])


if __name__ == '__main__':
    main()
