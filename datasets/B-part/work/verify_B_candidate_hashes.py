"""Re-record the P3/P4 candidate digests and explain the discrepancy found in the section 2 records.

While assembling the section 3 evidence, the digests stored in ``B_profile_diff.json`` (and copied into
``B_profile_review.md``) for the two candidate files did not match ``sha256`` of the files on disk. This
script settles it with measurements instead of an edit: it hashes the stored bytes and the
line-ending-normalized bytes, rebuilds the canonical 34-field profile vector, and compares both against
the copies the sealed pilot batches carry, so a reader can see that the *physics values* never moved and
which digest to use for a cross check.

Output: ``datasets/B-part/work/B_candidate_hash_reverification.json``
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent                     # datasets/B-part/work
B_DIR = HERE.parent
ROOT = B_DIR.parents[1]
sys.path.insert(0, str(ROOT / 'fp-spectrum-generator-competition-v0.2.1'))
from fp_competition.core import Profile                    # noqa: E402


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical_vector_sha(document):
    vector = dataclasses.asdict(Profile.from_dict(document))
    return sha256_bytes(json.dumps(vector, sort_keys=True, separators=(',', ':')).encode('utf-8'))


def record_for(tag):
    path = B_DIR / ('%s_candidate.json' % tag)
    raw = path.read_bytes()
    document = json.loads(raw.decode('utf-8'))
    normalized = raw.replace(b'\r\n', b'\n')
    out = {'file': str(path.relative_to(ROOT).as_posix()),
           'bytes_on_disk': len(raw),
           'crlf_line_breaks': raw.count(b'\r\n'),
           'sha256_of_file_as_stored': sha256_bytes(raw),
           'sha256_of_line_ending_normalized_text': sha256_bytes(normalized),
           'sha256_of_canonical_field_vector': canonical_vector_sha(document),
           'field_count': len(document)}
    stale = {}
    diff_path = B_DIR / 'B_profile_diff.json'
    if diff_path.exists():
        diff = json.loads(diff_path.read_text(encoding='utf-8'))
        block = diff.get('config_sha256', {}).get(path.name, {})
        stale = {'recorded_sha256_of_file': block.get('sha256_of_file'),
                 'recorded_sha256_of_canonical_field_vector': block.get('sha256_of_canonical_field_vector'),
                 'recorded_bytes': block.get('bytes')}
        out['section_2_record'] = stale
        out['section_2_record_matches_file_as_stored'] = (
            stale.get('recorded_sha256_of_file') == out['sha256_of_file_as_stored'])
        out['section_2_record_matches_normalized_text'] = (
            stale.get('recorded_sha256_of_file') == out['sha256_of_line_ending_normalized_text'])
        out['section_2_record_matches_canonical_vector'] = (
            stale.get('recorded_sha256_of_canonical_field_vector')
            == out['sha256_of_canonical_field_vector'])
    sealed = {}
    ledger_paths = [B_DIR / 'work' / 'pilot_ledger.json'] + sorted(
        (B_DIR / 'work' / 'ledger').glob('*.json')) if (B_DIR / 'work').exists() else []
    seen = set()
    for ledger_path in ledger_paths:
        if not ledger_path.exists():
            continue
        for entry in json.loads(ledger_path.read_text(encoding='utf-8')).get('batches', []):
            if entry.get('condition') != tag or entry['id'] in seen:
                continue
            seen.add(entry['id'])
            dataset = ROOT / entry['dataset']
            copies = {}
            for name in ('reproducibility/generator/configs/profile.json',
                         'configs/profile.json', 'inputs/original_profile.json'):
                copy = dataset / name
                if copy.exists():
                    copy_document = json.loads(copy.read_text(encoding='utf-8'))
                    copies[name] = {
                        'same_field_for_field_as_candidate': copy_document == document,
                        'same_canonical_vector': (canonical_vector_sha(copy_document)
                                                  == out['sha256_of_canonical_field_vector']),
                        'sha256_of_file_as_stored': sha256_bytes(copy.read_bytes())}
            manifest_file = dataset / 'manifest.json'
            manifest_inputs = {}
            if manifest_file.exists():
                manifest_inputs = (json.loads(manifest_file.read_text(encoding='utf-8'))
                                   .get('original_inputs', {}))
            sealed[entry['id']] = {'ledger_profile_sha256': entry.get('profile_sha256'),
                                   'ledger_matches_file_as_stored':
                                       entry.get('profile_sha256') == out['sha256_of_file_as_stored'],
                                   'sealed_copies': copies,
                                   'sealed_manifest_original_inputs': manifest_inputs}
    out['pilot_batches'] = sealed
    return out


def sample_table_record():
    """The pilot sample file carries the same two-variant problem, so record it beside the profiles."""
    path = B_DIR / 'B_pilot_samples.json'
    raw = path.read_bytes()
    stored = sha256_bytes(raw)
    selection = json.loads((B_DIR / 'B_pilot_selection.json').read_text(encoding='utf-8'))
    recorded = selection.get('files', {}).get('B_pilot_samples.json')
    batches = {}
    for ledger_path in [B_DIR / 'work' / 'pilot_ledger.json'] + sorted(
            (B_DIR / 'work' / 'ledger').glob('*.json')):
        if not ledger_path.exists():
            continue
        for entry in json.loads(ledger_path.read_text(encoding='utf-8')).get('batches', []):
            dataset = ROOT / entry['dataset']
            manifest = json.loads((dataset / 'manifest.json').read_text(encoding='utf-8'))
            copy = dataset / 'inputs' / 'original_samples.json'
            copy_bytes = copy.read_bytes() if copy.exists() else b''
            batches[entry['id']] = {
                'ledger_samples_sha256': entry.get('samples_sha256'),
                'manifest_original_inputs_samples_sha256':
                    manifest.get('original_inputs', {}).get('samples', {}).get('sha256'),
                'sealed_copy_sha256_as_stored': sha256_bytes(copy_bytes) if copy.exists() else None,
                'sealed_copy_equals_delivered_bytes': sha256_bytes(copy_bytes) == stored,
                'sealed_copy_sample_count': (len(json.loads(copy_bytes.decode('utf-8'))['samples'])
                                             if copy.exists() else None)}
    return {'file': str(path.relative_to(ROOT).as_posix()),
            'bytes_on_disk': len(raw),
            'crlf_line_breaks': raw.count(b'\r\n'),
            'sha256_of_file_as_stored': stored,
            'sha256_of_line_ending_normalized_text': sha256_bytes(raw.replace(b'\r\n', b'\n')),
            'recorded_in_B_pilot_selection_json': recorded,
            'recorded_value_is_the_normalized_text_variant': (
                recorded == sha256_bytes(raw.replace(b'\r\n', b'\n'))),
            'pilot_batches': batches}


def main():
    document = {'stage': 'member B candidate profile digest reverification',
               'finding': 'the records written by work/build_B_profiles.py and work/select_B_pilot.py '
                          'hashed the line-ending-normalized text of each file they produced, while the '
                          'files themselves were written in text mode and carry CRLF breaks, so sha256 of '
                          'the delivered bytes never equalled the recorded value. The parsed contents are '
                          'identical, which the canonical 34-field vector hash and the sealed batch copies '
                          'prove',
               'authoritative_for_cross_checks': 'sha256_of_file_as_stored, because that is what any tool '
                                                'hashing the delivered file obtains',
               'affected_records': ['B_profile_diff.json config_sha256 and support_runs profile digests',
                                    'B_profile_review.md section 2.9 hash table',
                                    'B_pilot_selection.json files.B_pilot_samples.json'],
               'generator_fixed': ['work/build_B_profiles.py', 'work/select_B_pilot.py'],
               'consequence_for_the_pilot': 'none physically: the sealed batches carry the same 34 fields, '
                                            'the recorded generation digests equal the stored-file digests, '
                                            'and no spectrum was generated from different values',
               'consequence_for_the_section_2_support_runs': 'still valid as measurements of these profiles; '
                                                             'the profile digests inside those records are '
                                                             'the normalized-text variant and are kept '
                                                             'unchanged as the original evidence',
               'candidates': {tag: record_for(tag) for tag in ('P3', 'P4')},
               'pilot_sample_table': sample_table_record()}
    out = HERE / 'B_candidate_hash_reverification.json'
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'file': str(out.relative_to(ROOT).as_posix()),
                      'p3_stored': document['candidates']['P3']['sha256_of_file_as_stored'][:16],
                      'p3_normalized_match': document['candidates']['P3'].get(
                          'section_2_record_matches_normalized_text'),
                      'p4_stored': document['candidates']['P4']['sha256_of_file_as_stored'][:16],
                      'p4_normalized_match': document['candidates']['P4'].get(
                          'section_2_record_matches_normalized_text'),
                      'vectors_stable': [document['candidates'][t].get(
                          'section_2_record_matches_canonical_vector') for t in ('P3', 'P4')],
                      'ledger_matches_stored': [
                          all(v['ledger_matches_file_as_stored'] for v in
                              document['candidates'][t]['pilot_batches'].values()) for t in ('P3', 'P4')]},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
