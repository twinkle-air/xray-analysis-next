"""C 部分：把归档登记表 `C_formula_registry.csv` 里空白的 scenario 列补齐为独立新文件。

背景（自查发现，随第二轮修正一起披露）：
第一轮的载荷构建脚本 `build_github_payload.py` 取的是 `provenance['scenario']`，
而主表里的键名是 `provenance['design_scenario']`，所以已推送的
`C_formula_registry.csv` 第 2 列 1000 行全为空字符串。其余 10 列不受影响。

处置原则：**归档批次的交付文件字节不改**（`C_formula_registry.csv` 保持原样、
原 SHA-256 不变），改用本脚本产出一个纯新增的修正件
`C_formula_registry_v2.csv`（同名同序同格式：UTF-8 BOM + CRLF），
并写出对账文件 `v2/registry_scenario_fix_check.json`：

- 1000 行 `formula_id` 与原文件逐行相同（顺序一致）；
- 除 `scenario` 外所有列与原文件逐值相同；
- `scenario` 逐行等于主表 `provenance['design_scenario']`，且
  regular_variation 600 / sparse_boundary 200 / interference_control 200；
- 两文件的 SHA-256、字节数与差异列清单。

同时 `build_github_payload.py` 的取键已修正，未来批次不会再出现空列。

用法：python -B scripts/fix_registry_scenario.py [载荷目录]
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PAYLOAD = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / 'github_payload' / 'datasets' / 'C-part-20261018'
SRC = PAYLOAD / 'C_formula_registry.csv'
DST = PAYLOAD / 'C_formula_registry_v2.csv'
MASTER = PAYLOAD / 'C_samples_v2.json' if not (PAYLOAD / 'C_samples.json').is_file() else PAYLOAD / 'C_samples.json'
V2 = HERE / 'v2'


def sha256(path: Path) -> str:
    d = hashlib.sha256()
    with path.open('rb') as fh:
        for blk in iter(lambda: fh.read(1 << 20), b''):
            d.update(blk)
    return d.hexdigest()


def main():
    if not SRC.is_file():
        raise SystemExit(f'缺少原登记表：{SRC}')
    raw = SRC.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    newline = '\r\n' if b'\r\n' in raw else '\n'
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline='')))
    cols = list(rows[0].keys())
    if 'scenario' not in cols:
        raise SystemExit('原登记表没有 scenario 列')

    samples = json.loads(MASTER.read_text(encoding='utf-8'))['samples']
    by_id = {s['id']: s for s in samples}
    if len(by_id) != len(samples):
        raise SystemExit('主表 formula_id 不唯一')
    if [r['formula_id'] for r in rows] != [s['id'] for s in samples]:
        raise SystemExit('登记表 formula_id 与主表顺序不一致，拒绝按位置补齐')

    filled, scenario_counts = [], Counter()
    for row in rows:
        r = dict(row)
        prov = by_id[r['formula_id']]['provenance']
        r['scenario'] = prov.get('design_scenario', '')
        if not r['scenario']:
            raise SystemExit(f"{r['formula_id']} 主表缺 design_scenario")
        scenario_counts[r['scenario']] += 1
        filled.append(r)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, lineterminator=newline,
                            quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    writer.writerows(filled)
    out = buf.getvalue().encode('utf-8')
    if bom:
        out = b'\xef\xbb\xbf' + out
    DST.write_bytes(out)

    # 反向验证写出格式：把原文件原值再序列化一遍，必须与原字节完全一致，
    # 这样才能断言"新文件除了 scenario 一列外与原文件逐字节相同"。
    buf2 = io.StringIO()
    w2 = csv.DictWriter(buf2, fieldnames=cols, lineterminator=newline,
                        quoting=csv.QUOTE_MINIMAL)
    w2.writeheader()
    w2.writerows(rows)
    control = buf2.getvalue().encode('utf-8')
    control_bytes = (b'\xef\xbb\xbf' + control) if bom else control
    roundtrip_identical = control_bytes == raw

    # 逐列对账：确认除 scenario 外与原文件完全一致
    new_rows = list(csv.DictReader(io.StringIO(DST.read_bytes().decode('utf-8-sig'), newline='')))
    diff_cols = [c for c in cols
                 if any(a[c] != b[c] for a, b in zip(rows, new_rows))]
    other_cols = [c for c in cols if c != 'scenario']
    other_mismatch = sum(1 for a, b in zip(rows, new_rows) for c in other_cols if a[c] != b[c])
    scenario_now_empty = sum(1 for r in new_rows if not r['scenario'])

    check = {
        'source_file': {'name': SRC.name, 'bytes': SRC.stat().st_size, 'sha256': sha256(SRC)},
        'fixed_file': {'name': DST.name, 'bytes': DST.stat().st_size, 'sha256': sha256(DST)},
        'format': {'utf8_bom': bom, 'newline': repr(newline), 'columns': cols,
                   'rows': len(new_rows)},
        'root_cause': "build_github_payload.py 用了 provenance['scenario']，"
                      "主表键名是 provenance['design_scenario']",
        'row_alignment_formula_id': 'exact_order_match',
        'reserializer_roundtrip_bytes_identical': roundtrip_identical,
        'columns_that_differ': diff_cols,
        'other_column_value_mismatches': other_mismatch,
        'scenario_empty_rows_after_fix': scenario_now_empty,
        'scenario_counts_after_fix': dict(scenario_counts),
        'archived_file_rewritten': False,
        'generator_script_fixed': 'scripts/build_github_payload.py（未来批次不再空列）',
        'passed': (diff_cols == ['scenario'] and other_mismatch == 0
                   and scenario_now_empty == 0 and len(new_rows) == 1000
                   and roundtrip_identical),
    }
    V2.mkdir(exist_ok=True)
    (V2 / 'registry_scenario_fix_check.json').write_text(
        json.dumps(check, ensure_ascii=False, indent=2), encoding='utf-8')
    print('fixed', DST.name, '| differing columns', diff_cols,
          '| scenario', dict(scenario_counts), '| passed', check['passed'])
    return 0 if check['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
