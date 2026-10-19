"""C 候选试产批次的隔离守卫（PR #2 要求：从所有训练/调参入口隔离）。

用法：任何读取 C 部分索引的下游入口都应先经过 `training_rows()`。
本批次 2000 条 P5 谱是**留出条件 + 未通过评审的候选试产**，两类身份都禁止进入
训练与调参；守卫只读取索引 CSV 的字段，不接触密封数据本体。

自检：`python c_pilot_guard.py` 会在 v2 索引上验证 train/validation/test 三个入口
全部被拒绝，并写出 `pilot_guard_selftest.json`。
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
BLOCKED_BATCH_VERSIONS = ('review_failed', 'pilot_only')
INDEX_CANDIDATES = ('v2/index_v2.csv', 'C_authoritative_index_v2.csv', 'index_v2.csv')
ISOLATION_CANDIDATES = ('v2/pilot_isolation.json', 'pilot_isolation.json')


def _first_existing(candidates):
    for rel in candidates:
        p = HERE / rel
        if p.is_file():
            return p
    return HERE / candidates[0]


INDEX = _first_existing(INDEX_CANDIDATES)
ISOLATION = _first_existing(ISOLATION_CANDIDATES)


def _pilot_batch_ids():
    ids = {'C-part-20261018'}
    if Path(ISOLATION).is_file():
        ids |= set(json.loads(Path(ISOLATION).read_text(encoding='utf-8'))['blocked_batch_ids'])
    return ids


class PilotIsolationError(RuntimeError):
    pass


def load_index(path=INDEX):
    with Path(path).open(encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh))


def _blocked(row):
    reasons = []
    if row.get('batch_id', '') in _pilot_batch_ids():
        reasons.append('pilot_batch_id=' + row['batch_id'])
    if row.get('benchmark_split', '') == 'heldout':
        reasons.append('condition_heldout')
    if row.get('holdout_status', '') == 'condition_heldout':
        reasons.append('holdout_status=condition_heldout')
    if str(row.get('usage_policy', '')).startswith('pilot_only'):
        reasons.append('pilot_only_batch')
    ver = str(row.get('batch_version', ''))
    if any(t in ver for t in BLOCKED_BATCH_VERSIONS):
        reasons.append('batch_version=' + ver)
    return reasons


def training_rows(rows, split='train'):
    """只放行非留出、非候选批次的行；否则抛错，绝不静默返回 0 行。"""
    if split not in ('train', 'validation', 'test'):
        raise ValueError('split must be train/validation/test')
    blocked = [(r['local_id'], _blocked(r)) for r in rows if _blocked(r)]
    if blocked:
        ids = ', '.join(i for i, _ in blocked[:3])
        raise PilotIsolationError(
            f'{len(blocked)}/{len(rows)} 行属于留出或候选试产批次，禁止用于 {split}：'
            f'示例 {ids}；原因 {blocked[0][1]}。'
            f'请先确认目标批次自身的 usage_policy 与评审状态：本守卫不为任何其他批次'
            f'（包括 A/B 试产批次）的可训练性作背书。')
    return [r for r in rows if r['recipe_family_split'] == split]


def self_test(path=INDEX):
    path = Path(path)
    try:
        shown = path.relative_to(HERE).as_posix()   # 正斜杠：跨平台逐字节一致
    except ValueError:
        shown = path.name        # 只记相对路径/文件名，换布局也能逐字节复现自检结果
    rows = load_index(path)
    result = {'index': shown, 'index_sha256':
              hashlib.sha256(path.read_bytes()).hexdigest(),
              'rows': len(rows),
              'uniform_heldout': all(r['benchmark_split'] == 'heldout' for r in rows)}
    for split in ('train', 'validation', 'test'):
        try:
            n = len(training_rows(rows, split))
            result[f'{split}_entry'] = f'NOT BLOCKED（放行 {n} 行）'
        except PilotIsolationError as exc:
            result[f'{split}_entry'] = 'blocked'
            result[f'{split}_message'] = str(exc)
    result['all_entries_blocked'] = all(result.get(f'{s}_entry') == 'blocked'
                                       for s in ('train', 'validation', 'test'))
    result['passed'] = bool(result['uniform_heldout'] and result['all_entries_blocked'])
    return result


if __name__ == '__main__':
    res = self_test()
    out = Path(os.environ.get('C_GUARD_OUT', str(HERE / 'v2' / 'pilot_guard_selftest.json')))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding='utf-8')
    print('passed', res['passed'], out)
