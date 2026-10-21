"""Check whether the two designed interference pairs are actually resolvable per condition.

Member B's recipe design deliberately co-dopes As/Pb and S/Pb, and member A's report states that
As/Pb stays unresolvable in the delivered P1/P2 conditions. Whether that is true, and whether the
B candidate conditions make it better or worse, is a numbers question, not an opinion question, so
this script answers it with the shipped model itself: line energies from ``core.line_data``
(xraylib), peak widths from ``Profile.fwhm_keV`` (electronic noise + Fano term), and channel
positions from the same zero/gain pair the binning uses.

Read-only: it imports the delivered package, it does not modify or re-derive any physics.
Output: datasets/B-part/B_profile_pair_check.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent            # datasets/B-part/work
B_DIR = HERE.parent
ROOT = B_DIR.parents[1]
GEN = ROOT / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition'
A_DIR = ROOT / 'datasets' / 'A-part-20261018'
SUPPORT = HERE / 'profile_support'
sys.path.insert(0, str(GEN.parent))
import xraylib                                                    # noqa: E402
from fp_competition.core import Profile, line_data                # noqa: E402

# (label, element A, line code, element B, line code) using the delivered xraylib code names.
PAIRS = (
    ('As_K_vs_Pb_L', 'As', 'KL3_LINE', 'Pb', 'L3M5_LINE'),
    ('S_K_vs_Pb_M', 'S', 'KL3_LINE', 'Pb', 'M5N6_LINE'),
)
CONDITIONS = (('P1_a_reference', A_DIR / 'P1.json'), ('P2_a_reference', A_DIR / 'P2.json'),
              ('P3_B_candidate', B_DIR / 'P3_candidate.json'),
              ('P4_B_candidate', B_DIR / 'P4_candidate.json'))


def energies(profile_path):
    profile = Profile.from_dict(json.loads(profile_path.read_text(encoding='utf-8')))
    table = {}
    for symbol in ('As', 'Pb', 'S'):
        z = xraylib.SymbolToAtomicNumber(symbol)
        for name, code, energy in line_data(z):
            table[(symbol, name)] = energy
    return profile, table


def support_state(tag, element):
    report = json.loads((SUPPORT / ('B_profile_support_%s.json' % tag)).read_text(encoding='utf-8'))
    row = report['elements'][element]
    lines = {l['line']: l for l in row['lines']}
    return row['status'], lines


def main():
    out = {'stage': 'member B section 2 interference pair resolution check',
           'definition': {
               'delta_keV': 'energy gap between the two line centres',
               'fwhm_keV': 'delivered Profile.fwhm_keV at each line energy: '
                           'sqrt(noise_fwhm_eV^2 + 2.35482^2 * Fano * pair_creation_eV * E)/1000',
               'separation_in_fwhm': 'delta_keV divided by the larger of the two FWHM values. '
                                      'Below ~1 means the two Gaussians share one peak maximum, '
                                      "i.e. 'structurally both present' but not resolvable by "
                                      'peak shape alone',
               'separation_in_channels': 'delta_keV / gain_keV_channel',
               'status_note': 'this is a peak-shape statement only. It is not a detection limit, '
                              'not a concentration accuracy claim, and not a fit that was actually '
                              'run on a generated spectrum'},
           'conditions': {}}
    for tag, path in CONDITIONS:
        profile, table = energies(path)
        support_tag = {'P1_a_reference': 'P1_reference', 'P2_a_reference': None,
                       'P3_B_candidate': 'P3', 'P4_B_candidate': 'P4'}[tag]
        rows = []
        for label, el_a, line_a, el_b, line_b in PAIRS:
            e_a = table[(el_a, line_a)]
            e_b = table[(el_b, line_b)]
            f_a = float(profile.fwhm_keV(e_a))
            f_b = float(profile.fwhm_keV(e_b))
            ch_a = (e_a - profile.zero_keV) / profile.gain_keV_channel
            ch_b = (e_b - profile.zero_keV) / profile.gain_keV_channel
            state = {}
            if support_tag:
                status_a, lines_a = support_state(support_tag, el_a)
                status_b, lines_b = support_state(support_tag, el_b)
                state = {'element_a_status': status_a, 'element_b_status': status_b,
                         'line_a_excitable': lines_a[line_a]['excitable_at_voltage'],
                         'line_a_window_fraction': round(
                             lines_a[line_a]['recorded_window_fraction'], 6),
                         'line_b_excitable': lines_b[line_b]['excitable_at_voltage'],
                         'line_b_window_fraction': round(
                             lines_b[line_b]['recorded_window_fraction'], 6)}
            rows.append({
                'pair': label,
                'line_a': '%s %s' % (el_a, line_a.replace('_LINE', '')), 'energy_a_keV': e_a,
                'channel_a': round(ch_a, 2), 'fwhm_a_keV': round(f_a, 5),
                'line_b': '%s %s' % (el_b, line_b.replace('_LINE', '')), 'energy_b_keV': e_b,
                'channel_b': round(ch_b, 2), 'fwhm_b_keV': round(f_b, 5),
                'delta_keV': round(abs(e_a - e_b), 5),
                'delta_eV': round(abs(e_a - e_b) * 1000, 1),
                'separation_in_channels': round(abs(e_a - e_b) / profile.gain_keV_channel, 2),
                'separation_in_fwhm': round(abs(e_a - e_b) / max(f_a, f_b), 4),
                'resolvable_by_peak_shape': bool(abs(e_a - e_b) / max(f_a, f_b) >= 1.0),
                'support_state': state})
        out['conditions'][tag] = {
            'profile_file': str(path.relative_to(ROOT).as_posix()),
            'voltage_kV': profile.voltage_kV, 'noise_fwhm_eV': profile.noise_fwhm_eV,
            'fano_factor': profile.fano_factor, 'gain_keV_channel': profile.gain_keV_channel,
            'zero_keV': profile.zero_keV, 'filter_Al_um': profile.filter_Al_um,
            'incident_air_path_cm': profile.incident_air_path_cm,
            'exit_air_path_cm': profile.exit_air_path_cm,
            'pairs': rows}
    (B_DIR / 'B_profile_pair_check.json').write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                                     encoding='utf-8')
    print(json.dumps({tag: [{p['pair']: {'delta_eV': p['delta_eV'],
                                         'sep_fwhm': p['separation_in_fwhm'],
                                         'sep_channels': p['separation_in_channels'],
                                         'resolvable': p['resolvable_by_peak_shape']}}
                            for p in data['pairs']]
                      for tag, data in out['conditions'].items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
