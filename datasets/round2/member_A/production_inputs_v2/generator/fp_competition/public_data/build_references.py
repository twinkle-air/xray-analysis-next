"""Make synthetic elemental reconstructions, retaining public-source provenance."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from fp_competition.minerals import components_to_elements

HERE=Path(__file__).resolve().parent


def main():
    raw=json.loads((HERE/'usgs_compositions.json').read_text(encoding='utf-8'))
    sources=json.loads((HERE/'download_manifest.json').read_text(encoding='utf-8'))
    samples=[]
    for material in raw['materials']:
        used,provenance=components_to_elements(material['compounds_percent'],material['trace_ppm'],closure='normalize_explicit')
        provenance.update({'basis':raw['value_status'],'source':next(s for s in sources['sources'] if s['id']==material['id']),
                           'reported_material':material,'uncertainty_basis':raw['uncertainty_basis'],
                           'reconstruction':'Major oxides plus selected traces, explicitly normalized; missing constituents omitted from synthetic composition',
                           'is_actual_reference_material_truth':False})
        samples.append({'id':material['id']+'-synthetic-reconstruction','composition_percent':used,'provenance':provenance})
    output=HERE/'reference_samples.json'
    output.write_text(json.dumps({'samples':samples},ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(output)


if __name__=='__main__':
    main()
