"""Summarise the delivered ``support`` reports into one row per target element per profile.

A support JSON lists every modelled line with its own excitation / window / efficiency / air flags,
which is too wide to read. This script keeps the facts member B and the reviewers need to judge a
measurement condition: which line systems a profile can record, where the principal line of each
system sits on the channel scale, how much detector-and-air transmission it survives, and, when a
system is unusable, *why* (no line excitable at the tube voltage, or every line outside the window).

Evidence only: it reads the CLI reports and ``B_profile_diff.json`` and never calls the solver.
Output: B_profile_support_summary.csv and B_profile_support_summary.json (member B directory).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent            # datasets/B-part/work
B_DIR = HERE.parent
ROOT = B_DIR.parents[1]
SUPPORT = HERE / 'profile_support'
TAGS = ('P3', 'P4', 'P1_reference')
PROFILE_KEY = {'P3': 'P3_candidate', 'P4': 'P4_candidate', 'P1_reference': 'P1'}
FIELD_KEY = {'P3': 'B_P3_candidate', 'P4': 'B_P4_candidate', 'P1_reference': 'a_P1'}
SYSTEMS = ('K', 'L', 'M', 'N')
# The principal analytical line per system, as named by the delivered line table.
PRINCIPAL = {'K': 'KL3_LINE', 'L': 'L3M5_LINE', 'M': 'M5N6_LINE', 'N': 'N_LINE'}


def recordable(line, threshold=0.5):
    return bool(line['excitable_at_voltage']) and float(line['recorded_window_fraction']) > threshold


def channel_of(energy, zero, gain, channels):
    index = (energy - zero) / gain
    return round(index, 1) if -0.5 <= index <= channels - 0.5 else None


def main():
    diff = json.loads((B_DIR / 'B_profile_diff.json').read_text(encoding='utf-8'))
    rows = []
    for tag in TAGS:
        report_path = SUPPORT / ('B_profile_support_%s.json' % tag)
        report = json.loads(report_path.read_text(encoding='utf-8'))
        per = diff['per_field_diff']
        gain = per['gain_keV_channel'][FIELD_KEY[tag]]
        zero = per['zero_keV'][FIELD_KEY[tag]]
        channels = per['channels'][FIELD_KEY[tag]]
        window = diff['energy_window_keV'][PROFILE_KEY[tag]]
        voltage = per['voltage_kV'][FIELD_KEY[tag]]
        filter_um = per['filter_Al_um'][FIELD_KEY[tag]]
        air = per['exit_air_path_cm'][FIELD_KEY[tag]]
        for symbol, element in sorted(report['elements'].items()):
            lines = element['lines']
            row = {'profile': tag, 'element': symbol, 'tube_voltage_kV': voltage,
                   'filter_Al_um': filter_um, 'exit_air_path_cm': air,
                   'window_keV': '%.3f-%.3f' % (window['lower_edge'], window['upper_edge']),
                   'status': element['status'],
                   'max_window_detector_air_response':
                       element['maximum_window_detector_air_response'],
                   'lines_modelled': len(lines),
                   'lowest_modelled_line_keV': min(l['energy_keV'] for l in lines)}
            for system in SYSTEMS:
                members = [l for l in lines if l['line'].startswith(system)]
                kept = [l for l in members if recordable(l)]
                excitable = [l for l in members if l['excitable_at_voltage']]
                in_window = [l for l in members
                             if float(l['recorded_window_fraction']) > 0.5]
                if not members:
                    row[system + '_system'] = 'none_modelled'
                    continue
                row[system + '_lines'] = len(members)
                row[system + '_lines_excitable'] = len(excitable)
                row[system + '_lines_in_window'] = len(in_window)
                row[system + '_lines_recordable'] = len(kept)
                if kept:
                    row[system + '_system'] = 'recordable'
                    row[system + '_energy_min_keV'] = round(min(l['energy_keV'] for l in kept), 4)
                    row[system + '_energy_max_keV'] = round(max(l['energy_keV'] for l in kept), 4)
                    top = max(kept, key=lambda l: l['detector_efficiency']
                              * l['exit_air_transmission'])
                    row[system + '_best_response_line'] = top['line'].replace('_LINE', '')
                    row[system + '_best_response'] = round(
                        top['detector_efficiency'] * top['exit_air_transmission'], 8)
                    principal = next((l for l in members
                                      if l['line'] == PRINCIPAL.get(system)), None)
                    if principal is not None:
                        row[system + '_principal_line'] = principal['line'].replace('_LINE', '')
                        row[system + '_principal_energy_keV'] = round(principal['energy_keV'], 4)
                        row[system + '_principal_channel'] = channel_of(
                            principal['energy_keV'], zero, gain, channels)
                        row[system + '_principal_window_fraction'] = round(
                            principal['recorded_window_fraction'], 4)
                        row[system + '_principal_excitable'] = bool(principal['excitable_at_voltage'])
                        row[system + '_principal_detector_efficiency'] = round(
                            principal['detector_efficiency'], 5)
                        row[system + '_principal_exit_air_transmission'] = round(
                            principal['exit_air_transmission'], 9)
                        row[system + '_principal_response'] = round(
                            principal['detector_efficiency']
                            * principal['exit_air_transmission'], 9)
                else:
                    reasons = []
                    if not excitable:
                        reasons.append('no_line_excitable_at_voltage')
                    if not in_window:
                        reasons.append('no_line_inside_window')
                    if not reasons:
                        reasons.append('no_single_line_both_excitable_and_in_window')
                    row[system + '_system'] = '+'.join(reasons)
            kept_systems = [s for s in SYSTEMS if row.get(s + '_system') == 'recordable']
            row['recordable_systems'] = ','.join(kept_systems) if kept_systems else 'NONE'
            primary = max(kept_systems, key=lambda s: row[s + '_best_response']) if kept_systems \
                else ''
            row['best_system'] = primary
            row['best_response'] = row.get(primary + '_best_response') if primary else 0.0
            row['k_system_recordable'] = 'K' in kept_systems
            rows.append(row)

    columns = ['profile', 'element', 'status', 'recordable_systems', 'best_system', 'best_response',
               'max_window_detector_air_response', 'k_system_recordable', 'lines_modelled',
               'lowest_modelled_line_keV', 'window_keV', 'tube_voltage_kV', 'filter_Al_um',
               'exit_air_path_cm']
    for system in SYSTEMS:
        columns += [system + '_system', system + '_lines', system + '_lines_excitable',
                    system + '_lines_in_window', system + '_lines_recordable',
                    system + '_energy_min_keV', system + '_energy_max_keV',
                    system + '_principal_line', system + '_principal_energy_keV',
                    system + '_principal_channel', system + '_principal_window_fraction',
                    system + '_principal_excitable', system + '_principal_detector_efficiency',
                    system + '_principal_exit_air_transmission', system + '_principal_response',
                    system + '_best_response_line', system + '_best_response']
    with (B_DIR / 'B_profile_support_summary.csv').open('w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    out = {
        'stage': 'member B section 2 per-element support summary',
        'derived_from': {tag: str((SUPPORT / ('B_profile_support_%s.json' % tag))
                                  .relative_to(ROOT).as_posix()) for tag in TAGS},
        'field_source': 'datasets/B-part/B_profile_diff.json per_field_diff and energy_window_keV',
        'definitions': {
            'recordable': 'delivered tool: a line counts as compatible when its fluorescence cross '
                          'section at the tube voltage is > 0 AND recorded_window_fraction > 0.5; '
                          'this script reuses the same rule',
            'excitable_at_voltage': 'core.line_cs() calls xraylib CS_FluorLine_Kissel_Cascade with '
                                    'the electron energy set to voltage_kV, and xraylib raises for '
                                    'transitions below their shell threshold, so the flag does '
                                    'respect the absorption edge. core.py:226 states it is '
                                    '"necessary excitation availability only, not flux"',
            'response': 'detector_efficiency x exit_air_transmission of one line. Per '
                        'core.detector_efficiency the exit-path terms are the Be window and the Si '
                        'dead layer only; the Al filter multiplies the PRIMARY beam inside '
                        'core.source_spectrum, so filter_Al_um never appears in this response and a '
                        'filter effect on a line must be argued from the excitation side, not here',
            'no_line_inside_window': 'every modelled line of that system falls outside the fitted '
                                      'energy window of the profile',
            'channel': '(energy_keV - zero_keV) / gain_keV_channel, the centre channel the '
                       'delivered binning would place the line in',
            'principal_line': 'K = KL3 (K-alpha1), L = L3M5 (L-alpha1); M4/M5 -> N transitions are '
                              'not in the delivered LINE_NAMES table, so for the M system no '
                              'principal line is reported and only the recorded energy band and the '
                              'best-response line are meaningful'},
        'tool_level_flags': {tag: {'minimum_modeled_line_keV': report['minimum_modeled_line_keV'],
                                   'is_detection_limit': report['is_detection_limit'],
                                   'hardware_validated': report['hardware_validated']}
                             for tag in ('P3', 'P4')},
        'tool_notes': 'the delivered notes block is copied verbatim into every support JSON; see '
                      'work/profile_support/B_profile_support_P3.json root key "notes"',
        'per_profile': {},
        'rows': rows}
    for tag in TAGS:
        subset = [r for r in rows if r['profile'] == tag]
        out['per_profile'][tag] = {
            'element_count': len(subset),
            'status_counts': {},
            'recordable_system_counts': {},
            'k_not_recordable_elements': sorted(r['element'] for r in subset
                                                if not r['k_system_recordable']),
            'strongly_attenuated_elements': sorted(r['element'] for r in subset
                                                   if r['status']
                                                   == 'strongly_attenuated_assumed_response'),
            'response_below_10_percent': sorted(r['element'] for r in subset
                                                if r['best_response'] < 0.10),
            'response_below_1_percent': sorted(r['element'] for r in subset
                                               if r['best_response'] < 0.01),
            'elements_by_descending_best_response': sorted(
                subset, key=lambda r: -r['best_response'])[:8],
        }
        for row in subset:
            out['per_profile'][tag]['status_counts'][row['status']] = \
                out['per_profile'][tag]['status_counts'].get(row['status'], 0) + 1
            for system in row['recordable_systems'].split(','):
                if system == 'NONE':
                    continue
                counts = out['per_profile'][tag]['recordable_system_counts']
                counts[system] = counts.get(system, 0) + 1
    (B_DIR / 'B_profile_support_summary.json').write_text(json.dumps(out, ensure_ascii=False,
                                                                    indent=2), encoding='utf-8')
    print(json.dumps({tag: {k: v for k, v in summary.items()
                            if k in ('status_counts', 'k_not_recordable_elements',
                                     'strongly_attenuated_elements', 'response_below_10_percent',
                                     'recordable_system_counts')}
                      for tag, summary in out['per_profile'].items()},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
