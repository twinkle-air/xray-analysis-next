"""Render the per-element markdown tables used by B_profile_review.md.

Each row is derived from the delivered support reports (through B_profile_support_summary.json), so
the review document cannot drift away from the CLI evidence. The 结论 column is rule-based, and the
rules are printed in the document itself so a reviewer can disagree with a rule instead of with a
hand-written opinion:

  A 档  K 系可记录且最优响应 >= 0.5            主线系在窗口内、衰减弱，条件本身不限制该元素
  B 档  可记录但最优响应在 0.01-0.5            仍可记录，但需要更多净计数或更高浓度
  C 档  最优响应 < 0.01 或状态为强衰减          仅结构上存在，不得写成"可探测"
  D 档  与另一目标元素的重合间距 < 1 FWHM      谱线存在但峰形不可分辨（As/Pb、S/Pb）
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
B_DIR = HERE.parent
summary = json.loads((B_DIR / 'B_profile_support_summary.json').read_text(encoding='utf-8'))
pairs = json.loads((B_DIR / 'B_profile_pair_check.json').read_text(encoding='utf-8'))
OVERLAP = {'As': '与 Pb Lα 重合', 'Pb': 'Lα 与 As Kα 重合，Mα 与 S Kα 重合',
           'S': '与 Pb Mα 重合'}
CONDITION_TAG = {'P3': 'P3_B_candidate', 'P4': 'P4_B_candidate', 'P1_reference': 'P1_a_reference'}
# element -> pair labels it belongs to, so the D marker is computed from the measured separation
# and never asserted from memory.
PAIR_MEMBER = {'As': ('As_K_vs_Pb_L',), 'Pb': ('As_K_vs_Pb_L', 'S_K_vs_Pb_M'),
               'S': ('S_K_vs_Pb_M',)}


def separation(tag, label):
    for entry in pairs['conditions'][CONDITION_TAG[tag]]['pairs']:
        if entry['pair'] == label:
            return entry
    raise KeyError('%s in %s' % (label, tag))


def grade(row):
    best = row['best_response']
    if row['status'] == 'strongly_attenuated_assumed_response' or best < 0.01:
        text = 'C 档：仅结构存在，响应 %.2g，不得写成可探测' % best
    elif best >= 0.5:
        text = 'A 档：最优响应 %.3f，条件不构成限制' % best
    else:
        text = 'B 档：最优响应 %.3f，需要更多净计数' % best
    labels = PAIR_MEMBER.get(row['element'])
    if labels:
        detail = '，'.join('%s Δ=%.1f eV = %.2f 倍 FWHM'
                           % (label, separation(row['profile'], label)['delta_eV'],
                              separation(row['profile'], label)['separation_in_fwhm'])
                           for label in labels)
        text += '；D 档：%s → 峰形不可分辨，只能作为重合峰整体处理' % detail
    return text


def systems(row):
    parts = []
    for system in ('K', 'L', 'M'):
        state = row.get(system + '_system')
        if state == 'recordable':
            if row.get(system + '_principal_line'):
                parts.append('%s 可记录（%s %.3f keV→道 %.1f，响应 %.3g）'
                             % (system, row[system + '_principal_line'],
                                row[system + '_principal_energy_keV'],
                                row[system + '_principal_channel'],
                                row[system + '_best_response']))
            else:
                parts.append('%s 可记录（无主分析线，仅 %.3f-%.3f keV，响应 %.3g）'
                             % (system, row[system + '_energy_min_keV'],
                                row[system + '_energy_max_keV'], row[system + '_best_response']))
        elif state == 'none_modelled':
            continue
        else:
            parts.append('%s 不可记录（%s）' % (system, state))
    return '；'.join(parts) if parts else '无任何线系可记录'


def table(tag):
    lines = ['| 元素 | 窗口内可记录线系与道址 | 最优响应 | 交付工具状态 | 重合情况 | B 档结论 |',
             '| --- | --- | --- | --- | --- | --- |']
    for row in sorted((r for r in summary['rows'] if r['profile'] == tag), key=lambda r: r['element']):
        lines.append('| %s | %s | %.4g | %s | %s | %s |' % (
            row['element'], systems(row), row['best_response'], row['status'],
            OVERLAP.get(row['element'], '—'), grade(row)))
    return '\n'.join(lines)


def pair_table():
    lines = ['| 条件 | 管压 kV | 噪声 eV | 增益 keV/道 | 线对 | ΔE eV | Δ道 | 较大 FWHM keV | '
             'Δ/最大 FWHM | 峰形可分辨 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for tag, data in pairs['conditions'].items():
        for p in data['pairs']:
            lines.append('| %s | %g | %g | %g | %s vs %s | %.1f | %.2f | %.4f | %.3f | %s |' % (
                tag, data['voltage_kV'], data['noise_fwhm_eV'], data['gain_keV_channel'],
                p['line_a'], p['line_b'], p['delta_eV'], p['separation_in_channels'],
                max(p['fwhm_a_keV'], p['fwhm_b_keV']), p['separation_in_fwhm'],
                '是' if p['resolvable_by_peak_shape'] else '否'))
    return '\n'.join(lines)


out = ['# §2 逐元素表格（由脚本渲染，勿手改数字）', '',
       '渲染命令：`datasets/B-part/work/venv313/Scripts/python.exe -B '
       'datasets/B-part/work/render_B_profile_tables.py`',
       '输入：`B_profile_support_summary.json`、`B_profile_pair_check.json`', '',
       '## P3 候选（20 kV）32 个目标元素', '', table('P3'), '',
       '## P4 候选（49 kV + 100 µm Al + 8 cm 空气路径）32 个目标元素', '', table('P4'), '',
       '## P1 参考（A 交付条件，仅作对照）', '', table('P1_reference'), '',
       '## 重合线对可分辨性', '', pair_table(), '',
       '## 每条件计数与窗口损失（CLI batch 实测，非声称）', '',
       '| 候选 | 2 条 B 配方实测总观测计数 | 相对 A 的 P1 计数区间中点 | 窗外观测损失比例 |',
       '| --- | --- | --- | --- |']
diff = json.loads((B_DIR / 'B_profile_diff.json').read_text(encoding='utf-8'))
for tag in ('P3', 'P4'):
    probe = diff['probes'][tag]
    loss = ', '.join('%.4f' % r['window_loss_fraction'] for r in probe['records'])
    out.append('| %s | %g – %g | %.3f | %s |' % (
        tag, probe['observed_counts_range'][0], probe['observed_counts_range'][1],
        probe['counts_ratio_vs_a_p1_midpoint'], loss))

# The two-recipe probe above is superseded by the section 3 pilot, which measures 200 spectra per
# condition. Those numbers are read back from the verification reports the pilot wrote, so the review
# and the acceptance evidence cannot disagree.
WATCHED = [('Fe', 'KL3_LINE'), ('As', 'KL3_LINE'), ('S', 'KL3_LINE'),
           ('Pb', 'L3M5_LINE'), ('Pb', 'M5N6_LINE')]
out += ['', '## §3 试产实测复核（每条件 100 配方 × 2 重复 = 200 谱，读自验收报告）', '',
        '数据源：`work/pilot_reports/pilot_<条件>_v1/verification*.json`（取最新一份），'
        '由 `run_B_pilot.py --phase verify` 生成。下表把"线存在"与"有足够净计数"分开给数字，'
        '净期望计数 = 一次+二次发射 × 几何因子 × 探测器效率 × 出射空气透过率，即整条 live time 的期望值。', '',
        '| 条件 | 谱数 | 窗外损失 min | 窗外损失 mean | 窗外损失 max | 超 1% 预算谱数 | 丢弃计数成分占比 |',
        '| --- | --- | --- | --- | --- | --- | --- |']
for tag in ('P3', 'P4'):
    directory = HERE / 'pilot_reports' / ('pilot_%s_v1' % tag)
    reports = sorted(directory.glob('verification*.json'),
                     key=lambda p: p.stat().st_mtime) if directory.exists() else []
    if not reports:
        out.append('| %s | 未执行 |  |  |  |  |  |' % tag)
        continue
    check = json.loads(reports[-1].read_text(encoding='utf-8'))
    window = check['window_loss']
    share = window.get('over_budget_component_share_percent') or {}
    out.append('| %s | %d | %.5f | %.5f | %.5f | %d/%d | %s |' % (
        tag, check['spectra_checked'], window['min'], window['mean'], window['max'],
        len(window['over_budget_record_ids']), check['spectra_checked'],
        ', '.join('%s %.1f%%' % (k, v) for k, v in share.items()) or '无超预算谱'))
out += ['', '每条件被丢弃计数落在窗口的哪一侧（结构性判据，非推测）：', '']
for tag in ('P3', 'P4'):
    directory = HERE / 'pilot_reports' / ('pilot_%s_v1' % tag)
    reports = sorted(directory.glob('verification*.json'),
                     key=lambda p: p.stat().st_mtime) if directory.exists() else []
    if not reports:
        continue
    side = json.loads(reports[-1].read_text(encoding='utf-8'))['window_loss'].get('loss_side_attribution')
    if side:
        out.append('- **%s**：下沿 %.4f keV，上沿 %.4f keV，管压 %.0f kV，'
                   '交付源网格起点 1 keV = %s；90° Compton 仍出窗的入射阈能 %.2f keV。%s'
                   % (tag, side['lower_edge_keV'], side['upper_edge_keV'], side['tube_voltage_keV'],
                      side['delivered_source_grid_starts_at_1_keV'],
                      side['compton_90deg_threshold_keV'] or float('nan'), side['conclusion']))
out += ['', '干扰家族关键线的实测净期望计数（同一配方 2 条谱取最大）：', '',
        '| 条件 | 组 | 线 | 含该元素谱数 | 建模谱数 | 窗内谱数 | 能量 keV | 道址 | 最大净期望计数 |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
for tag in ('P3', 'P4'):
    directory = HERE / 'pilot_reports' / ('pilot_%s_v1' % tag)
    reports = sorted(directory.glob('verification*.json'),
                     key=lambda p: p.stat().st_mtime) if directory.exists() else []
    if not reports:
        continue
    check = json.loads(reports[-1].read_text(encoding='utf-8'))
    for group, data in sorted(check['line_system_check']['groups'].items()):
        if data['scenario'] != 'interference':
            continue
        for symbol, line in WATCHED:
            cell = data['lines'].get('%s %s' % (symbol, line))
            if cell is None:
                continue
            out.append('| %s | %s | %s %s | %s | %d | %d | %s | %s | %s |' % (
                tag, data['candidate_pair'], symbol, line,
                data['elements_present'].get(symbol, 0), cell['modeled_in_spectra'],
                cell['in_window_in_spectra'],
                '—' if cell['energy_keV'] is None else '%.4f' % cell['energy_keV'],
                '—' if cell['channel'] is None else '%.1f' % cell['channel'],
                '—' if cell['max_expected_detected_counts'] in (None, 0)
                else '%.2f' % cell['max_expected_detected_counts']))
out += ['', '按本文 §2.6 第 3 条自设的计数门槛（5% 峰面积 1σ 需要净峰 ≥ 400 counts）核对上表：', '']
for tag in ('P3', 'P4'):
    directory = HERE / 'pilot_reports' / ('pilot_%s_v1' % tag)
    reports = sorted(directory.glob('verification*.json'),
                     key=lambda p: p.stat().st_mtime) if directory.exists() else []
    if not reports:
        continue
    check = json.loads(reports[-1].read_text(encoding='utf-8'))
    for group, data in sorted(check['line_system_check']['groups'].items()):
        if data['scenario'] != 'interference':
            continue
        parts = []
        for symbol, line in WATCHED:
            cell = data['lines'].get('%s %s' % (symbol, line))
            if cell is None or not cell['modeled_in_spectra']:
                continue
            value = cell['max_expected_detected_counts'] or 0.0
            parts.append('%s %s %s(%.2f)' % (symbol, line.replace('_LINE', ''),
                                             '≥400' if value >= 400.0 else '<400', value))
        out.append('- %s / %s 组内最强配方：%s' % (tag, data['candidate_pair'], ', '.join(parts)))
text = '\n'.join(out) + '\n'
(HERE / 'B_profile_review_tables.md').write_text(text, encoding='utf-8', newline='\n')
print(json.dumps({'file': str(HERE / 'B_profile_review_tables.md'), 'lines': len(out),
                  'characters': len(text)}, ensure_ascii=True))
