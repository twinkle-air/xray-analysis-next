"""Restore byte-identical original delivery files from repository transport parts."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def safe(root,relative):
    if not isinstance(relative,str) or '\\' in relative:
        raise ValueError('Expected relative POSIX path')
    p=PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or ':' in relative or not p.parts:
        raise ValueError('Unsafe path: '+relative)
    target=(root/relative).resolve()
    if not target.is_relative_to(root.resolve()):raise ValueError('Path escapes delivery')
    return target


def restore(root):
    manifest=json.loads((root/'transport_manifest.json').read_text(encoding='utf-8'))
    restored=existing=0
    for item in manifest['files']:
        target=safe(root,item['target'])
        if target.exists():
            if not target.is_file() or sha(target)!=item['sha256']:
                raise ValueError('Refusing to overwrite conflicting file: '+item['target'])
            existing+=1
            continue
        paths=[]
        for part in item['parts']:
            p=safe(root,part['path'])
            if p.stat().st_size!=part['bytes'] or sha(p)!=part['sha256']:
                raise ValueError('Part damaged: '+part['path'])
            paths.append(p)
        target.parent.mkdir(parents=True,exist_ok=True)
        pending=target.with_name(target.name+'.restore-pending')
        if pending.exists():raise FileExistsError(pending)
        try:
            with pending.open('xb') as f:
                for p in paths:
                    with p.open('rb') as source:
                        for block in iter(lambda:source.read(1024*1024),b''):f.write(block)
            if pending.stat().st_size!=item['bytes'] or sha(pending)!=item['sha256']:
                raise ValueError('Restored file hash mismatch: '+item['target'])
            # Hard-link creation refuses an existing target even in a race.
            os.link(pending,target)
            pending.unlink()
        except BaseException:
            if pending.exists():pending.unlink()
            raise
        restored+=1
        print('Restored '+item['target'],flush=True)
    aliases=manifest.get('original_file_aliases',{})
    original=json.loads(safe(root,manifest['original_delivery_manifest']).read_text(encoding='utf-8'))
    for name,digest in original['files'].items():
        if sha(safe(root,aliases.get(name,name)))!=digest:
            raise ValueError('Original delivery checksum mismatch: '+name)
    return {'restored':restored,'already_present':existing,
            'original_files_verified':len(original['files']),
            'all_original_sha256_passed':True}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args()
    print(json.dumps(restore(args.root.resolve()),ensure_ascii=False))


if __name__=='__main__':main()
