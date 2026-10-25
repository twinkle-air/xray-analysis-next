"""Download the two public-domain USGS sheets, retaining byte hashes.

Run explicitly; importing the generator never initiates network access.
"""
from pathlib import Path
import hashlib
import json
from urllib.request import Request,urlopen

HERE=Path(__file__).resolve().parent
SOURCES={
    'BHVO-2':('https://www.usgs.gov/media/files/bhvo-2-geochemical-reference-material-information-sheet',
              'https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/media/files/USGS-BHVO-2-IS_2022-508.pdf'),
    'BCR-2':('https://www.usgs.gov/media/files/bcr-2-geochemical-reference-material-information-sheet-0',
             'https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/media/files/USGS%20BCR-2%20IS_2022.pdf')
}


def main():
    records=[]
    for material,(page,url) in SOURCES.items():
        path=HERE/(material+'-USGS-2022.pdf')
        if not path.exists():
            with urlopen(Request(url,headers={'User-Agent':'FP-research-generator/0.2.0'}),timeout=45) as response:
                data=response.read(2_000_001)
            if not data.startswith(b'%PDF-') or len(data)>2_000_000:
                raise ValueError('Invalid PDF response for '+material)
            with path.open('xb') as stream:
                stream.write(data)
        data=path.read_bytes()
        records.append({'id':material,'landing_page':page,'download_url':url,'file':path.name,
                        'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
                        'license':'Public Domain (USGS landing page)','sheet_revision':'June 2022',
                        'data_kind':'Published composition estimates; not measured XRF spectra'})
    (HERE/'download_manifest.json').write_text(json.dumps({'sources':records},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(records,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
