"""Publish the member-B round-3 delivery as a branch + pull request through the GitHub API.

Never writes to main: it creates one new branch from main, adds only the files under
datasets/round3/member_B/, and opens a PR for the owner to review.

Token is read from GH_TOKEN in the environment (put there by the caller); nothing here
prints or stores it.
"""
from __future__ import annotations
import base64
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

DELIVERY = pathlib.Path(__file__).resolve().parent
REPO = 'twinkle-air/xray-analysis-next'
API = 'https://api.github.com'
BRANCH = 'data/B-round3-production-20261024'
BASE = 'main'
PREFIX = 'datasets/round3/member_B'
TOKEN = os.environ['GH_TOKEN']
LOG = DELIVERY.parent / 'B-part-20261024_work' / 'upload_progress.log'


def log(msg: str) -> None:
    line = f'[{time.strftime("%H:%M:%S")}] {msg}'
    with LOG.open('a', encoding='utf-8') as fh:
        fh.write(line + '\n')
    print(line, flush=True)


def call(method: str, path: str, payload=None, raw: bytes | None = None, attempt: int = 0):
    url = API + path
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', 'Bearer ' + TOKEN)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'dsh-agent')
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as err:
        body = err.read().decode('utf-8', 'replace')
        if err.code in (429, 500, 502, 503, 504) and attempt < 4:
            wait = 2 ** attempt
            log(f'retry {err.code} in {wait}s: {path}')
            time.sleep(wait)
            return call(method, path, payload, raw, attempt + 1)
        raise RuntimeError(f'{method} {path} -> {err.code}: {body[:400]}')


def collect() -> list[tuple[str, pathlib.Path]]:
    """Files to add, as (repo-relative path, local path). candidates/ already exists upstream."""
    entries: list[tuple[str, pathlib.Path]] = []
    for path in sorted(DELIVERY.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(DELIVERY).as_posix()
        if rel.startswith('candidates/'):
            continue  # frozen candidates are already in the repository, unchanged
        entries.append((f'{PREFIX}/{rel}', path))
    return entries


def main() -> None:
    log(f'start: branch={BRANCH} base={BASE}')

    ref = call('GET', f'/repos/{REPO}/git/ref/heads/{BASE}')
    base_commit = ref['object']['sha']
    commit = call('GET', f'/repos/{REPO}/git/commits/{base_commit}')
    base_tree = commit['tree']['sha']
    user = call('GET', '/user')
    log(f'base commit={base_commit[:12]} tree={base_tree[:12]} actor={user["login"]}')

    entries = collect()
    total_bytes = sum(p.stat().st_size for _, p in entries)
    log(f'files={len(entries)} bytes={total_bytes} ({total_bytes/1024/1024:.1f} MB)')

    tree_entries = []
    done_bytes = 0
    started = time.monotonic()
    for index, (repo_path, local_path) in enumerate(entries, 1):
        blob = call('POST', f'/repos/{REPO}/git/blobs',
                    {'content': base64.b64encode(local_path.read_bytes()).decode(), 'encoding': 'base64'})
        tree_entries.append({'path': repo_path, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
        done_bytes += local_path.stat().st_size
        if index % 25 == 0 or index == len(entries):
            rate = done_bytes / max(1e-9, time.monotonic() - started) / 1024 / 1024
            log(f'blobs {index}/{len(entries)} {done_bytes/1024/1024:.0f}MB {rate:.2f}MB/s')

    tree = call('POST', f'/repos/{REPO}/git/trees', {'base_tree': base_tree, 'tree': tree_entries})
    log(f'new tree={tree["sha"]}')

    message = ('data: round3 B complete 1746 spectra and full self-check\n\n'
               '1500 base spectra (including the 90 pilot spectra) + 246 held-out T spectra = 1746\n'
               'records across 50 frozen batches, generated with the sealed generator against\n'
               'owner_release_v3 / freeze_v1. Every batch carries audit, full physics replay,\n'
               'window-budget, ZIP SHA-256 and CRC evidence plus a batch-qualified external\n'
               'record index. T spectra are held-out physical QC only; training inclusion is\n'
               'still unapproved and synthetic self-check is not device accuracy.')
    new_commit = call('POST', f'/repos/{REPO}/git/commits', {
        'message': message,
        'tree': tree['sha'],
        'parents': [base_commit],
        'author': {'name': user.get('name') or user['login'],
                   'email': user.get('email') or f'{user["login"]}@users.noreply.github.com'},
    })
    log(f'commit={new_commit["sha"]}')

    try:
        call('POST', f'/repos/{REPO}/git/refs',
             {'ref': f'refs/heads/{BRANCH}', 'sha': new_commit['sha']})
        log('branch created')
    except RuntimeError as err:
        if '422' not in str(err):
            raise
        call('PATCH', f'/repos/{REPO}/git/refs/heads/{BRANCH}', {'sha': new_commit['sha'], 'force': True})
        log('branch updated')

    summary = json.loads((DELIVERY / 'selfcheck_summary.json').read_text(encoding='utf-8'))
    pr_body = f"""## 成员 B·第三轮全量生产交付

- 基础谱 **{summary['actual_base_spectra']}**（含 pilot 90）+ T 挑战谱 **{summary['actual_T_spectra']}** = **{summary['total_actual_spectra']}** 条
- 原生密封批次 **{summary['native_sealed_batches']}**；候选 250 配方 / 105 设计族
- audit 覆盖 {summary['all_spectra_audited']} 条，全部 passed
- 完整物理 replay 覆盖 {summary['all_spectra_full_physics_replayed']} 条，最大绝对数组差 `{summary['maximum_absolute_replay_array_difference']}`
- 窗外预算全部通过；每个 ZIP 的 SHA-256 与批内 summary 一致，CRC 校验通过
- 外置记录索引 {summary['external_record_index_rows']} 行（`record_uid` 批次限定唯一）

冻结身份：`freeze_manifest_sha256={summary['freeze_manifest_sha256']}`、
`owner_release_sha256={summary['owner_release_sha256']}`、`physics_core_sha256={summary['physics_core_sha256']}`。

边界：T 谱仅用于留出物理 QC，未进入训练/校正/选参；`training_inclusion_approved=false`；
合成自检通过不代表真实设备准确度（`scientific_accuracy_verified=false`）。

目录：`production_v1/`（50 个原生 ZIP + SHA-256）、`reports/<batch>/`（audit/replay/window_budget/commands/summary）、
`reports/external_record_index.csv`、`delivery_manifest.json`、`selfcheck_summary.json`、`environment.json`、`logs/`。
"""
    pr = call('POST', f'/repos/{REPO}/pulls', {
        'title': 'data: round3 B complete 1746 spectra and full self-check',
        'head': BRANCH,
        'base': BASE,
        'body': pr_body,
        'draft': False,
    })
    log(f'PR #{pr["number"]} {pr["html_url"]}')
    print(json.dumps({'branch': BRANCH, 'commit': new_commit['sha'], 'pr': pr['html_url'],
                      'files': len(entries), 'bytes': total_bytes}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
