"""Build and pre-flight the member B P3/P4 candidate measurement conditions.

Every field of the shipped Profile dataclass is written out explicitly, validated by the
delivered ``Profile.from_dict`` (which rejects unknown or missing-with-wrong-type fields), and
compared field by field against the local ``default_profile.json`` and against A's delivered
P1/P2. Then the delivered CLI is used read-only for the structure support table and for a
one-spectrum probe per candidate, so the pilot is not the first time B sees the counting level.

Outputs: P3_candidate.json, P4_candidate.json, B_profile_diff.json (B-part root), and per-run CLI
evidence under work/runs/run_NN/{profile_support,profile_probe} plus stable copies of the newest
support reports in work/profile_support/ (the delivered CLI refuses to reuse an --out path, so
outputs are versioned instead of overwritten).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent                        # datasets/B-part/work
B_DIR = HERE.parent
ROOT = B_DIR.parents[1]
GEN = ROOT / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition'
A_DIR = ROOT / 'datasets' / 'A-part-20261018'
sys.path.insert(0, str(GEN.parent))

from fp_competition.core import Profile, TARGET_ELEMENTS, line_data   # noqa: E402
import xraylib                                                        # noqa: E402

UNITS = {
    'name': 'label', 'voltage_kV': 'kV', 'current_uA': 'uA', 'reference_current_uA': 'uA',
    'target': 'element symbol (X-ray tube anode)', 'live_time_s': 's',
    'incident_photons_s': 'photons/s at 1 uA-equivalent before the specified incident air path',
    'channels': 'count', 'gain_keV_channel': 'keV/channel', 'zero_keV': 'keV',
    'noise_fwhm_eV': 'eV (electronic noise floor of the FWHM model)',
    'fano_factor': 'dimensionless', 'pair_creation_eV': 'eV per electron-hole pair',
    'detector_area_cm2': 'cm^2', 'detector_distance_cm': 'cm', 'detector_si_um': 'um (Si dead layer)',
    'detector_be_um': 'um (detector Be window)', 'tube_be_um': 'um (tube Be window)',
    'filter_Al_um': 'um (Al filter in the beam)',
    'incident_air_path_cm': 'cm', 'exit_air_path_cm': 'cm', 'air_density_g_cm3': 'g/cm^3',
    'incident_angle_deg': 'deg', 'exit_angle_deg': 'deg', 'scatter_angle_deg': 'deg',
    'mass_thickness_g_cm2': 'g/cm^2 (sample areal thickness)',
    'tube_line_fraction': 'fraction of the total flux placed in the discrete tube lines',
    'escape_fraction': 'fraction of Si K escapes for lines above the Si K edge',
    'source_step_keV': 'keV (continuum quadrature step)',
    'secondary_layers': 'count (finite-slab secondary-fluorescence discretisation)',
    'secondary': 'boolean', 'scatter': 'boolean',
    'background_counts_channel': 'counts/channel (flat background)',
    'calibration_status': 'enum; this release only accepts assumed_unverified',
}

# ---------------------------------------------------------------- candidate overrides
P3_OVERRIDES = {
    'name': 'candidate_B_P3_low_voltage_L_systems',
    'voltage_kV': 20.0,
    'gain_keV_channel': 0.0080,
    'zero_keV': 0.30,
    'noise_fwhm_eV': 90.0,
    'live_time_s': 60.0,
}
P4_OVERRIDES = {
    'name': 'candidate_B_P4_hard_filter_long_air_path',
    'voltage_kV': 49.0,
    'filter_Al_um': 100.0,
    'incident_air_path_cm': 4.0,
    'exit_air_path_cm': 4.0,
    'gain_keV_channel': 0.0125,
    'zero_keV': 0.45,
    'noise_fwhm_eV': 140.0,
    'incident_photons_s': 10000000.0,
    'live_time_s': 60.0,
}
REASONS = {
    'P3': {
        'voltage_kV': '20 kV 是任务卡指定的低压情景：Ag 的 K 系(22.16 keV)在 20 kV 下不被激发，'
                      '一次线只剩连续谱与 Ag L 系(约 2.98 keV)，重元素只能靠 L/M 系与连续谱尾部'
                      '激发，用来检验模型与标签在低激发效率条件下是否仍然可用',
        'gain_keV_channel': '与零位一起把 2048 道压到 0.30-16.68 keV，提高 3-13 keV 的 L 系采样密度',
        'zero_keV': '把窗口下沿从 0.613 keV 降到 0.30 keV，避免低压软线被窗口切掉',
        'noise_fwhm_eV': '低压通道假定更差的电子学：90 eV 噪声底(相对 A 的 P1 55 eV)',
        'live_time_s': '取 60 s，使总入射注量为 6.0e8 photons，与 P4 候选相同；两情景每谱净计数之差'
                       '因此只来自管压/刻度/噪声等物理条件，而不来自曝光设置。20 kV 下主要靠连续谱'
                       '激发，产额低于 49 kV，故注量不再进一步下调以免低端统计过差',
        'current_uA': '沿用 A 的 196.1 uA，使管流不是本情景的自由变量',
        'incident_photons_s': '沿用 A 的 P1 的 1e7 photons/s，与 P4 候选一致，只允许 live time '
                              '定义本情景的曝光量',
        'filter_Al_um': '保持 0，低压情景不引入滤波片变量(滤波片是 P4 的主题)',
        'incident_air_path_cm': '保持 0，空气路径是 P4 的变量',
        'exit_air_path_cm': '保持 0，空气路径是 P4 的变量',
    },
    'P4': {
        'voltage_kV': '49 kV 由任务卡指定，与 A 的 P1/P2 相同，使本情景的变量集中在衰减与噪声',
        'filter_Al_um': '100 um Al 硬滤波：Al K 边 1.56 keV 以下几乎全被吸收，专门压 Na/Mg/Al/Si/P/S/Cl '
                        '等轻元素线，检验低端衰减建模',
        'incident_air_path_cm': '入射侧空气路径 4.0 cm(比 A 的 P2 0.5 cm 长 8 倍)，与滤波片叠加低能吸收',
        'exit_air_path_cm': '出射侧空气路径 4.0 cm，同样只压制低能荧光线',
        'gain_keV_channel': '0.0125 keV/道，把窗口拉到 0.45-26.04 keV，覆盖 Ag 韧致极限与 Sn/Sb K 系，'
                            '避免"出窗损失"被窗口选择掩盖',
        'zero_keV': '零位 0.45 keV，与增益一起定义边界窗',
        'noise_fwhm_eV': '140 eV 噪声底：本情景故意用最差的分辨率，考察近重合线(As/Pb、S/Pb)的容忍度',
        'incident_photons_s': '沿用 A 的 P1 的 1e7 photons/s，不用提高管通量去抵消 100 um Al 滤波与 '
                              '8 cm 空气路径造成的通量损失，让低能衰减作为可观测量保留在谱形里',
        'live_time_s': '60 s，与 P3 候选共用同一总入射注量 6.0e8 photons，使两个情景的计数统计水平'
                       '可直接比较；滤波与空气路径造成的实际净计数差异由探针实测记录',
        'target': '仍为 Ag 靶(任务卡要求两个候选条件都用 Ag 靶)',
    },
}

FIELD_ORDER = [f.name for f in dataclasses.fields(Profile)]


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sha256_bytes(payload):
    # Always the stored bytes: hashing a string that was then written in text mode silently diverges
    # from the file on Windows, where write_text() converts every LF break to CRLF.
    return hashlib.sha256(payload).hexdigest()


def canonical(profile_dict):
    return json.dumps({k: profile_dict[k] for k in FIELD_ORDER}, sort_keys=True,
                      separators=(',', ':'))


def build(base, overrides):
    candidate = dict(base)
    candidate.update(overrides)
    missing = [name for name in FIELD_ORDER if name not in candidate]
    extra = [name for name in candidate if name not in FIELD_ORDER]
    if missing or extra:
        raise RuntimeError('candidate field set incomplete: missing=%s extra=%s' % (missing, extra))
    Profile.from_dict(candidate)                     # delivered validator, rejects illegal values
    return candidate


def tube_lines(profile):
    z = xraylib.SymbolToAtomicNumber(profile['target'])
    out = []
    for name, code, energy in line_data(z):
        out.append({'line': name, 'energy_keV': energy,
                    'below_voltage': energy < profile['voltage_kV'],
                    'inside_window': profile['zero_keV'] <= energy <=
                    profile['zero_keV'] + (profile['channels'] - 1) * profile['gain_keV_channel']})
    return out


def run_cli(args, log_path):
    done = subprocess.run([sys.executable, '-B', 'app.py'] + args, cwd=GEN,
                          capture_output=True, text=True)
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text('command: python -B app.py %s\ncwd: %s\nexit_code: %d\nstdout:\n%s\n'
                        'stderr:\n%s\n'
                        % (' '.join(args), GEN, done.returncode, done.stdout, done.stderr),
                        encoding='utf-8')
    if done.returncode != 0:
        raise RuntimeError('CLI %s failed, see %s' % (args[0], log_path))
    return done


def next_run_dir(base):
    """Give every CLI invocation a fresh output tree.

    The delivered CLI refuses any --out path that already exists, so runs are versioned under
    work/runs/run_NN instead of being overwritten or deleted; the numbers stay comparable because
    each run keeps its own recipe, profile and environment copies.
    """
    base.mkdir(parents=True, exist_ok=True)
    used = [int(path.name[4:]) for path in base.glob('run_*') if path.name[4:].isdigit()]
    return base / ('run_%02d' % (max(used, default=0) + 1))


def main():
    default = json.loads((GEN / 'default_profile.json').read_text(encoding='utf-8'))
    a_p1 = json.loads((A_DIR / 'P1.json').read_text(encoding='utf-8'))
    a_p2 = json.loads((A_DIR / 'P2.json').read_text(encoding='utf-8'))
    a_summary = json.loads((A_DIR / 'A_acceptance_summary.json').read_text(encoding='utf-8'))
    a_bands = {tag: a_summary['pilots'][tag]['total_observed_counts_range']
               for tag in ('P1', 'P2')}
    from fp_competition import dataset as dataset_tools

    p3 = build(a_p1, P3_OVERRIDES)
    p4 = build(a_p1, P4_OVERRIDES)
    written = {}
    for name, profile in (('P3_candidate.json', p3), ('P4_candidate.json', p4)):
        text = json.dumps({k: profile[k] for k in FIELD_ORDER}, ensure_ascii=False, indent=2)
        (B_DIR / name).write_text(text + '\n', encoding='utf-8', newline='\n')
        payload = (B_DIR / name).read_bytes()
        written[name] = {'sha256_of_file': sha256_bytes(payload),
                         'sha256_of_canonical_field_vector': sha256_text(canonical(profile)),
                         'bytes': len(payload)}

    diff = {}
    for field in FIELD_ORDER:
        diff[field] = {
            'unit': UNITS[field],
            'local_default': default.get(field),
            'a_P1': a_p1.get(field),
            'a_P2': a_p2.get(field),
            'B_P3_candidate': p3[field],
            'B_P4_candidate': p4[field],
            'P3_changed_vs_a_P1': p3[field] != a_p1.get(field),
            'P4_changed_vs_a_P1': p4[field] != a_p1.get(field),
            'P3_changed_vs_local_default': p3[field] != default.get(field),
            'P4_changed_vs_local_default': p4[field] != default.get(field),
            'reason_P3': REASONS['P3'].get(field, '与 A 的 P1 保持一致，本情景不引入该变量'),
            'reason_P4': REASONS['P4'].get(field, '与 A 的 P1 保持一致，本情景不引入该变量'),
        }
    windows = {'P1': dataset_tools.energy_window(a_p1), 'P2': dataset_tools.energy_window(a_p2),
               'local_default': dataset_tools.energy_window(default),
               'P3_candidate': dataset_tools.energy_window(p3),
               'P4_candidate': dataset_tools.energy_window(p4)}
    for key, profile in (('P1', a_p1), ('P2', a_p2), ('local_default', default),
                         ('P3_candidate', p3), ('P4_candidate', p4)):
        windows[key]['channels'] = profile['channels']
        windows[key]['channel_of_edge'] = {'lower_edge_channel': -0.5,
                                           'first_center_channel': 0,
                                           'last_center_channel': profile['channels'] - 1,
                                           'upper_edge_channel': profile['channels'] - 0.5}

    record = {
        'stage': 'member B section 2 candidate conditions (P3/P4)',
        'status': 'candidate_built_and_preflighted, awaiting the joint freeze',
        'non_authoritative': 'these two files are B proposals. They are NOT frozen conditions: '
                             'formal P3/P4 production may only start after the team freezes them '
                             '(or replaces them); if the frozen values differ, the pilot '
                             'acceptance must be redone with the frozen files',
        'calibration_status': p3['calibration_status'],
        'calibration_note': 'the delivered release refuses any calibration_status other than '
                            'assumed_unverified, so no hardware calibration is claimed for P3/P4',
        'field_count_profile_dataclass': len(FIELD_ORDER),
        'fields_written_per_candidate': {name: len(profile) for name, profile in
                                         (('P3', p3), ('P4', p4))},
        'config_sha256': written,
        'energy_window_keV': windows,
        'window_definition': 'channel i centre energy = zero_keV + gain_keV_channel * i; the '
                             'window edges are one half gain below the first centre and one half '
                             'gain above the last centre (dataset.energy_window)',
        'per_field_diff': diff,
        'changed_field_names': {
            'P3_vs_a_P1': sorted(f for f in FIELD_ORDER if diff[f]['P3_changed_vs_a_P1']),
            'P4_vs_a_P1': sorted(f for f in FIELD_ORDER if diff[f]['P4_changed_vs_a_P1']),
            'P3_vs_local_default': sorted(f for f in FIELD_ORDER
                                          if diff[f]['P3_changed_vs_local_default']),
            'P4_vs_local_default': sorted(f for f in FIELD_ORDER
                                          if diff[f]['P4_changed_vs_local_default'])},
        'target_tube_lines': {'P3_candidate': tube_lines(p3), 'P4_candidate': tube_lines(p4),
                              'note': 'the delivered source model only keeps a discrete tube line '
                                      'when its energy is below the tube voltage, so at 20 kV the '
                                      'Ag K system (22.16/24.94 keV) is absent by construction and '
                                      'primary excitation comes from the continuum plus Ag L'},
        'exposure_arithmetic': {
            'P3': '1.0e7 photons/s * 60 s * (196.1/196.1) = 6.0e8 <= 1e14 numeric cap',
            'P4': '1.0e7 photons/s * 60 s * (196.1/196.1) = 6.0e8 <= 1e14 numeric cap',
            'validator': 'Profile.validate() of the delivered release enforces the cap and was '
                         'run on both candidates',
            'fluence_design': 'both candidates deliberately share one incident fluence (6.0e8 '
                              'photons) so a counts gap between P3 and P4 is attributable to the '
                              'tube voltage, filter, air path and calibration, not to exposure',
            'counting_level_reference': {
                'a_p1_total_observed_counts_range': a_bands['P1'],
                'a_p2_total_observed_counts_range': a_bands['P2'],
                'source': 'datasets/A-part-20261018/A_acceptance_summary.json '
                          'pilots.<P1|P2>.total_observed_counts_range',
                'use': 'B targets the same order of magnitude per spectrum; the realised value per '
                       'candidate is measured by the probes below and is not asserted here'}},
        'support_runs': {},
        'probes': {},
        'handed_to': 'A and C for the joint condition freeze; B pilot batches use exactly these '
                     'two files and no other numbers',
    }

    support_dir = next_run_dir(HERE / 'runs') / 'profile_support'
    canonical_support = HERE / 'profile_support'
    canonical_support.mkdir(parents=True, exist_ok=True)
    record['cli_output_run_directory'] = str(support_dir.parent.relative_to(ROOT).as_posix())
    record['run_directory_note'] = (
        'the delivered CLI will not overwrite an existing --out path, so each run writes '
        'work/runs/run_NN and the newest reports are additionally copied byte for byte to the '
        'stable deliverable names under work/profile_support/')
    for tag, name in (('P3', 'P3_candidate.json'), ('P4', 'P4_candidate.json'),
                      ('P1_reference', 'P1.json')):
        profile_path = (B_DIR / name) if tag != 'P1_reference' else (A_DIR / name)
        out_path = support_dir / ('B_profile_support_%s.json' % tag)
        run_cli(['support', '--profile', str(profile_path), '--elements']
                + list(TARGET_ELEMENTS) + ['--out', str(out_path)],
                support_dir / (out_path.stem + '.log'))
        stable = canonical_support / out_path.name
        shutil.copyfile(out_path, stable)
        report = json.loads(out_path.read_text(encoding='utf-8'))
        record['support_runs'][tag] = {
            'profile_file': str(profile_path.relative_to(ROOT).as_posix()),
            'profile_sha256': sha256_bytes(profile_path.read_bytes()),
            'support_file': str(out_path.relative_to(ROOT).as_posix()),
            'support_sha256': hashlib.sha256(out_path.read_bytes()).hexdigest(),
            'stable_copy': str(stable.relative_to(ROOT).as_posix()),
            'stable_copy_sha256': hashlib.sha256(stable.read_bytes()).hexdigest(),
            'stable_copy_identical': hashlib.sha256(stable.read_bytes()).hexdigest()
            == hashlib.sha256(out_path.read_bytes()).hexdigest(),
            'command': 'python -B app.py support --profile %s --elements <32 targets> --out %s'
                       % (profile_path.name, out_path.name),
            'element_count': len(report.get('elements', report)),
            'status_counts': {},
            'log': str((support_dir / (out_path.stem + '.log')).relative_to(ROOT).as_posix())}
        elements = report.get('elements', report)
        counts = {}
        for symbol, row in elements.items():
            counts[row['status']] = counts.get(row['status'], 0) + 1
        record['support_runs'][tag]['status_counts'] = counts

    # one-spectrum counting probe per candidate on two real B recipes (fresh dirs, CLI batch)
    samples_all = json.loads((B_DIR / 'B_samples.json').read_text(encoding='utf-8'))['samples']
    spike = next(s for s in samples_all
                 if s['provenance']['design_detail']['block'] == 'declared_maximum_spike')
    probe_samples = [samples_all[0], spike]
    probe_file = support_dir.parent / 'profile_probe'
    probe_file.mkdir(parents=True, exist_ok=True)
    probe_path = probe_file / 'probe_samples.json'
    probe_path.write_text(json.dumps({'samples': probe_samples}, ensure_ascii=False),
                          encoding='utf-8')
    for tag, name in (('P3', 'P3_candidate.json'), ('P4', 'P4_candidate.json')):
        out_dir = probe_file / ('dataset_probe_%s' % tag)
        started = time.time()
        run_cli(['batch', '--samples', str(probe_path), '--profile', str(B_DIR / name),
                 '--out', str(out_dir), '--seed', '2026101822', '--replicates', '1',
                 '--closure', 'strict', '--legacy-al', 'reject', '--targets']
                + list(TARGET_ELEMENTS) + ['--design-ranges', str(B_DIR / 'B_design_ranges.json')],
                probe_file / ('batch_probe_%s.log' % tag))
        manifest = json.loads((out_dir / 'manifest.json').read_text(encoding='utf-8'))
        totals = []
        for path in sorted((out_dir / 'full_results').glob('*.json')):
            full = json.loads(path.read_text(encoding='utf-8'))
            before = float(full['detected_signal_before_window_counts'])
            lost = float(sum(full['outside_window_counts'].values()))
            totals.append({'record': path.stem,
                           'formula_id': manifest['records'][len(totals)]['id'],
                           'total_expected_counts': float(sum(full['expected_counts'])),
                           'total_observed_counts': float(sum(full['counts'])),
                           'detected_before_window_counts': before,
                           'outside_window_counts': lost,
                           'window_loss_fraction': lost / before if before > 0 else None})
        record['probes'][tag] = {
            'purpose': 'counting-level and window-loss pre-flight only; not part of any pilot, '
                       'not counted in the 20,000 or 50,000 budget',
            'recipes': [s['id'] for s in probe_samples],
            'seed': 2026101822,
            'elapsed_seconds': round(time.time() - started, 2),
            'seconds_per_spectrum': round((time.time() - started) / max(len(totals), 1), 2),
            'records': totals,
            'observed_counts_range': [min(x['total_observed_counts'] for x in totals),
                                      max(x['total_observed_counts'] for x in totals)],
            'a_p1_reference_range': a_bands['P1'],
            'counts_ratio_vs_a_p1_midpoint': round(
                (sum(x['total_observed_counts'] for x in totals) / len(totals))
                / (sum(a_bands['P1']) / 2.0), 3),
            'spectrum_count': manifest['spectrum_count']}
    (B_DIR / 'B_profile_diff.json').write_text(json.dumps(record, ensure_ascii=False, indent=2),
                                               encoding='utf-8')
    print(json.dumps({'run_directory': record['cli_output_run_directory'],
                      'P3_changed': record['changed_field_names']['P3_vs_a_P1'],
                      'P4_changed': record['changed_field_names']['P4_vs_a_P1'],
                      'windows': {k: [round(v['lower_edge'], 4), round(v['upper_edge'], 4)]
                                  for k, v in windows.items()},
                      'support': {t: r['status_counts'] for t, r in record['support_runs'].items()},
                      'probe_totals': {t: [(x['total_observed_counts'],
                                            round(x['window_loss_fraction'] or 0, 4))
                                           for x in r['records']]
                                       for t, r in record['probes'].items()},
                      'probe_counts_ratio_vs_a_p1_midpoint': {
                          t: r['counts_ratio_vs_a_p1_midpoint'] for t, r in
                          record['probes'].items()},
                      'probe_seconds_per_spectrum': {t: r['seconds_per_spectrum']
                                                     for t, r in record['probes'].items()}},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
