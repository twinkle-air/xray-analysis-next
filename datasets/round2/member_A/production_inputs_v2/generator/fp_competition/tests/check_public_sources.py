"""Optional source audit using bundled pypdf; not a generator dependency."""
from pathlib import Path
import hashlib
import json
import re
from pypdf import PdfReader

def main():
    root=Path(__file__).resolve().parents[1]/'public_data'
    manifest=json.loads((root/'download_manifest.json').read_text(encoding='utf-8'))
    raw=json.loads((root/'usgs_compositions.json').read_text(encoding='utf-8'))
    verified=0
    for material in raw['materials']:
        record=next(s for s in manifest['sources'] if s['id']==material['id'])
        path=root/record['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
        text=PdfReader(path).pages[1].extract_text()
        for name,values,uncertainties in [
            ('major',material['compounds_percent'],material['compound_uncertainty_percent']),
            ('trace',material['trace_ppm'],material['trace_uncertainty_ppm'])]:
            for symbol,value in values.items():
                found=re.search(r'(?m)^\s*'+re.escape(symbol)+r'\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+\d',text)
                assert found,(material['id'],symbol,'missing row')
                assert float(found[1])==value,(material['id'],symbol,'value mismatch')
                assert float(found[2])==uncertainties[symbol],(material['id'],symbol,'uncertainty mismatch')
                verified+=2
    print(json.dumps({'verified_transcribed_values_and_uncertainties':verified,'pdf_hashes_match':True}))

if __name__=='__main__': main()
