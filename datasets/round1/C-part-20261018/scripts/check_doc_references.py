"""检查载荷文档里引用的脚本/产物路径是否真的随包存在。

第二轮评审的第一条就是"说明里引用的新脚本、主表未提交"。这个检查把这类断言
变成机器可验证的：扫描载荷目录里所有 .md/.json 中出现的 `scripts/xxx.py`、
`v2/xxx` 与 `C_*.csv/json/md` 相对路径引用，逐个确认文件在本目录内存在。

用法：python -B scripts/check_doc_references.py [载荷目录]
输出：v2/doc_reference_check.json（同时打印缺失清单）
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PAYLOAD = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / 'github_payload' / 'datasets' / 'C-part-20261018'
PATTERNS = [
    re.compile(r'scripts/[A-Za-z0-9_.\-]+\.py'),
    re.compile(r'v2/[A-Za-z0-9_.\-]+\.(?:json|md|csv)'),
    re.compile(r'C_[A-Za-z0-9_\-]+\.(?:json|md|csv)'),
]


def main():
    refs = {}
    for f in sorted(PAYLOAD.rglob('*')):
        if not f.is_file() or f.suffix not in ('.md', '.json'):
            continue
        text = f.read_text(encoding='utf-8', errors='replace')
        for pat in PATTERNS:
            for m in pat.findall(text):
                # 前置字符不是标识符字符才算一次独立引用
                for mo in pat.finditer(text):
                    prev = text[max(0, mo.start() - 1)]
                    if prev.isalnum() or prev in '_-/':
                        continue
                    refs.setdefault(mo.group(), set()).add(f.relative_to(PAYLOAD).as_posix())
                break
    # 去掉"更完整路径的后缀"造成的假阳性：README_C_deliverables.md 不是 C_deliverables.md
    refs = {r: v for r, v in refs.items()
            if not any(o != r and o.endswith('/' + r) for o in refs)}
    missing = {}
    for ref, sources in sorted(refs.items()):
        target = PAYLOAD / ref
        if not target.is_file():
            # 允许指向包外/上游的引用（生成器内部文件、解包后的数据集路径）
            missing[ref] = sorted(sources)
    report = {'payload': PAYLOAD.name, 'references_found': len(refs),
              'missing': missing, 'passed': not missing,
              'checked_suffixes': ['.md', '.json'],
              'note': '只检查载荷目录内的相对路径引用；外部生成器源码与解包目录不计入。'}
    out = HERE / 'v2' / 'doc_reference_check.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('references', len(refs), 'missing', len(missing))
    for k, v in missing.items():
        print('  MISSING', k, '<-', v)


if __name__ == '__main__':
    main()
