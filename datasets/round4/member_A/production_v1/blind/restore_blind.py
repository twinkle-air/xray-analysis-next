"""Restore the opaque blind ZIP from ordered parts, validating SHA-256 and CRC."""
import argparse,hashlib,json,pathlib,re,zipfile

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()
def verify_zip(path,records):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=records or len(set(names))!=records or any(not re.fullmatch(r'[0-9a-f]{24}\.json',n) for n in names):raise ValueError('Blind ZIP record count or opaque filename check failed')
        if z.testzip() is not None:raise ValueError('ZIP CRC check failed')
def restore(manifest_path,output=None):
    manifest_path=pathlib.Path(manifest_path).resolve();m=json.loads(manifest_path.read_text(encoding='utf-8'));root=manifest_path.parent
    name=m['original_name']
    if pathlib.PurePath(name).name!=name or not name.endswith('.zip'):raise ValueError('Invalid restored filename')
    out=pathlib.Path(output).resolve() if output else root.parent/name
    if out.exists():
        if out.stat().st_size!=m['original_bytes'] or sha(out)!=m['original_sha256']:raise FileExistsError('Existing output differs; refusing to overwrite')
        verify_zip(out,m['records']);return out
    parts=m['parts']
    if not parts or len({x['name'] for x in parts})!=len(parts):raise ValueError('Missing or duplicate parts')
    for x in parts:
        if pathlib.PurePath(x['name']).name!=x['name'] or '/' in x['name'] or '\\' in x['name']:raise ValueError('Unsafe part name')
        p=root/x['name']
        if not p.is_file() or p.stat().st_size!=x['bytes']:raise ValueError('Missing or wrong-sized part: '+x['name'])
    out.parent.mkdir(parents=True,exist_ok=True);tmp=out.with_name(out.name+'.assembling');created=False
    try:
        with tmp.open('xb') as target:
            created=True;whole=hashlib.sha256();total=0
            for x in parts:
                digest=hashlib.sha256()
                with (root/x['name']).open('rb') as f:
                    for block in iter(lambda:f.read(1024**2),b''):
                        target.write(block);digest.update(block);whole.update(block);total+=len(block)
                if digest.hexdigest()!=x['sha256']:raise ValueError('Part SHA-256 mismatch: '+x['name'])
        if total!=m['original_bytes'] or whole.hexdigest()!=m['original_sha256']:raise ValueError('Restored ZIP size/SHA-256 mismatch')
        verify_zip(tmp,m['records']);tmp.rename(out);return out
    except BaseException:
        if created and tmp.exists():tmp.unlink()
        raise
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=pathlib.Path,default=pathlib.Path(__file__).with_name('transport_manifest.json'));p.add_argument('--output',type=pathlib.Path);a=p.parse_args();result=restore(a.manifest,a.output);print('Restored and verified:',result)
