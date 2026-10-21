# B 部分 §2：P3 / P4 候选测量条件评审记录

- 撰写人：成员 B　日期：2026-10-19
- 状态：**候选（candidate），未冻结**。`P3_candidate.json` / `P4_candidate.json` 是 B 提交给 A、C 联评的提案，
  不是已生效的正式条件；一旦团队冻结值与候选值有任何字段不同，§3 的试产验收必须用冻结配置重做，
  之后才能进入正式生产。
- `calibration_status = assumed_unverified`：交付版本 `Profile.validate()` 只接受这一个值
  （`core.py` "This release cannot certify a hardware-calibrated profile"），因此本文不含任何硬件标定声明。
- 证据文件：`B_profile_diff.json`（逐字段差异/单位/理由/窗口/哈希/支持表计数/计数探针）、
  `B_profile_support_summary.json` + `.csv`（逐元素派生汇总）、`B_profile_pair_check.json`（重合可分辨性）、
  `work/profile_support/B_profile_support_P3.json` / `_P4.json` / `_P1_reference.json`（交付 CLI 原文）。

## 2.0 本文回答什么、不回答什么

回答：候选值怎么来的、每个改动字段的单位与理由、能量窗口边界与道址、32 个目标元素在两个候选条件下
的 K/L/M 线系可得性、谱线中心道址、窗口占比、探测效率、空气路径透过率、窗外观测损失、设计重合对是否
可分辨、每谱计数水平。

不回答：硬件标定、检出限、方法准确度（例如"5%"）、基体效应的实测大小。交付工具在每份 support 报告里
自己写明 `is_detection_limit = false`、`hardware_validated = false`，并附
"Excitation/window checks do not establish sensitivity, selectivity or a reporting limit"。
本文所有"可记录"只表示**模型结构上支持该线被记录**，不等于"可分辨"，也不等于"可探测"，更不等于"能给到 5%"。

## 2.1 构建方法

1. 基线取 A 交付的 `datasets/A-part-20261018/P1.json`（34 个字段）。先与本地
   `fp-spectrum-generator-competition-v0.2.1/fp_competition/default_profile.json` 逐字段比对：
   **除 `name` 之外 33 个字段完全相同**，所以"A 的 P1"与"本地默认"是同一套物理条件，
   候选值的差异不存在两套基线混用的问题。
2. 在基线上做覆盖式改动（P3 改 5 个数值字段 + `name`；P4 改 7 个数值字段 + `name`），
   其余字段显式保持与 A 的 P1 一致；`work/build_B_profiles.py` 会断言字段集合不缺不多
   （`field_count_profile_dataclass = 34`，`fields_written_per_candidate = {P3: 34, P4: 34}`），
   然后调用交付的 `Profile.from_dict()` 通过 `validate()` 才落盘。**没有缺数字段**这一条是脚本硬检查，不是口头保证。
3. 两个候选都保留 Ag 靶、Si 探测器、2048 道（任务卡要求），`secondary=true`、`scatter=true`、
   `closure` 相关的 `mass_thickness_g_cm2=2.37` 等几何/物理字段一律不动，使每个情景的自由变量尽量少。
4. 之后用交付 CLI（只读、不改求解器）跑 `support` 与一次 2 条配方的 `batch` 计数探针；
   `--out` 全部指向新目录（CLI 拒绝覆盖已存在路径），因此本文产物按 `work/runs/run_NN` 版本化保存，
   `run_01` 是初版曝光设定的证据，`run_02` 是当前的候选值。

## 2.2 P3 候选：20 kV 低压、L 系主导

改动字段（完整 34 字段逐项对照见 `B_profile_diff.json` 的 `per_field_diff`）：

| 字段 | 单位 | A 的 P1 / 本地默认 | P3 候选 | 理由 |
| --- | --- | --- | --- | --- |
| `name` | 标签 | `assumed_P1_reference` | `candidate_B_P3_low_voltage_L_systems` | 标明是 B 候选而非 A 条件 |
| `voltage_kV` | kV | 49.0 | **20.0** | 任务卡指定的低压情景 |
| `gain_keV_channel` | keV/道 | 0.0138393 | **0.0080** | 与零位一起把 2048 道压到 0.296–16.680 keV，提高 3–13 keV 的 L 系采样密度 |
| `zero_keV` | keV | 0.61339 | **0.30** | 窗口下沿降低，避免低压软线被窗口切掉 |
| `noise_fwhm_eV` | eV | 55.0 | **90.0** | 假定更差的电子学噪声底 |
| `live_time_s` | s | 150.0 | **60.0** | 与 P4 共用同一入射注量 6.0e8 photons，使两情景计数差只来自物理条件 |

未改动的关键项：`current_uA=196.1`（管流不是本情景变量）、`incident_photons_s=1.0e7`、
`filter_Al_um=0`（滤波片是 P4 的主题）、`incident_air_path_cm=exit_air_path_cm=0`、
`channels=2048`、`target=Ag`、`detector_si_um=500`、`detector_be_um=12.5`、`scatter_angle_deg=90`。

结构后果（必须让 A/C 确认这就是团队想要的"P3 低压"含义）：

- 交付源模型只在**线能量 < 管压**时保留离散靶线（`core.source_spectrum`）。20 kV 下 Ag 的 K 系
  21.708/21.990/22.163/24.797–25.511 keV 全部被丢弃，**一次激发只剩连续谱 + Ag L 系**
  （2.634–3.803 keV 共 30 条 L 线，全部落在窗口内）。模型不报错，也不产生"源被完全吸收"异常。
- 窗口上限 16.680 keV 使 **7 个目标元素的 K 系不可记录**：Ba、Cd、Mo、Pb、Sb、Sn、W。
  其中 Ba/Cd/Pb/Sb/Sn/W 的 K 系同时"在 20 kV 下不可激发"（K 壳层结合能 26.71–88.00 keV，全部高于管压）与"出窗"；
  Mo 是"可激发标记但出窗"（Kα 17.479 > 16.680）。这 7 个元素改由 L 系记录，Ba/Pb/W 还额外有 M 系。
  任务卡要求的"Ba 的 K 出窗仍要检查 L/M"已落实：Ba L3M5 4.466 keV → 道 520.8、响应 0.994，
  Ba M 系记录带 1.033–1.278 keV、响应 0.511。
- 尽管 7 个元素失去 K 系，**两个候选条件下"无任何可记录线系"的元素数都是 0**，
  所以 B 的 32 维标签维度不会因条件选择而缺失（`B_profile_support_summary.json`
  → `per_profile.*.recordable_system_counts`）。

## 2.3 P4 候选：49 kV + 100 µm Al 滤片 + 8 cm 空气路径 + 140 eV 噪声

| 字段 | 单位 | A 的 P1 / 本地默认 | P4 候选 | 理由 |
| --- | --- | --- | --- | --- |
| `name` | 标签 | `assumed_P1_reference` | `candidate_B_P4_hard_filter_long_air_path` | 标明是 B 候选 |
| `filter_Al_um` | µm | 0.0 | **100.0** | 硬滤波，专门压低低能端（任务卡指定 100 µm） |
| `incident_air_path_cm` | cm | 0.0 | **4.0** | 入射侧空气路径，比 A 的 P2（0.5 cm）长 8 倍 |
| `exit_air_path_cm` | cm | 0.0 | **4.0** | 出射侧空气路径，只压制低能荧光 |
| `gain_keV_channel` | keV/道 | 0.0138393 | **0.0125** | 窗口 0.4438–26.0438 keV，覆盖 Ag K 系与 Sn/Sb K 系，避免窗损失被窗口选择掩盖 |
| `zero_keV` | keV | 0.61339 | **0.45** | 与增益共同定义边界窗 |
| `noise_fwhm_eV` | eV | 55.0 | **140.0** | 故意用最差分辨率，考察 As/Pb、S/Pb 近重合线的容忍度 |
| `live_time_s` | s | 150.0 | **60.0** | 与 P3 共用同一入射注量 6.0e8 photons |

未改动：`voltage_kV=49.0`（与 A 的 P1/P2 相同，使变量集中在衰减与噪声）、`target=Ag`、
`incident_photons_s=1.0e7`、`current_uA=196.1`。

**滤波片与空气路径在模型里的作用位置不同**，这点直接决定怎么读支持表：

- `filter_Al_um` 只出现在 `core.source_spectrum`（乘在韧致连续谱与靶线上，作用在**激发端**）；
  它**不进入** `element_support` 的响应项。
- `detector_efficiency` 只含探测器 Be 窗（12.5 µm）与 Si 灵敏层（500 µm）；
  `exit_air_transmission` 只含出射空气路径（此处 4.0 cm）。
- 因此支持表里的低端抑制**全部来自 4 cm 出射空气路径**，实测逐线透过率：
  Na Kα 1.041 keV → 1.7e-07，Mg Kα 1.254 → 8.21e-05，Al Kα 1.487 → 2.79e-03，
  Si Kα 1.740 → 2.27e-02，P Kα 2.010 → 8.14e-02，S Kα 2.308 → 1.85e-01，
  Cl Kα 2.622 → 3.13e-01，K Kα 3.314 → 5.23e-01，Ca Kα 3.692 → 6.22e-01。
  滤波片的影响体现在激发端（吸收 1.56 keV 以下的一次光子、硬化连续谱），
  在支持表中不可见，只能通过生成的谱来观察。
- 交付工具把响应 < 0.01 的三个元素标为 `strongly_attenuated_assumed_response`：**Na、Mg、Al**。
  这就是任务卡要求重点报告的"低能衰减"结果。Si 响应 0.031、P 0.106、S 0.227 属"能记录但需要更多净计数"。
- **Na/Mg 灵敏度结论**：在 P4 下 Na 的 K 线道址只有第 47.3 道、响应 5e-08，Mg 第 64.3 道、响应 4e-05；
  这两个元素在 P4 的谱里几乎不可能有可拟合的净峰面积，B 的配方对它们只应作为"标签存在但条件不支持定量"
  的困难样本处理；若团队需要 Na/Mg 的可学习信号，应保留 P1/P3 这类无空气路径条件，或把出射路径缩短到
  ≤1 cm（该结论需要试产谱实测支持，本文不声称具体检出限）。

## 2.4 窗口边界与道址口径

定义：道 i 的中心能量 = `zero_keV + gain_keV_channel * i`；窗口下沿 = 首道中心 − 半个增益，
上沿 = 末道中心 + 半个增益（`dataset.energy_window`）。

| 条件 | gain keV/道 | zero keV | 窗口 keV | 首/末中心道 |
| --- | --- | --- | --- | --- |
| A 的 P1（= 本地默认） | 0.0138393 | 0.61339 | 0.6065 – 28.9493 | 0 / 2047 |
| A 的 P2 | 0.0140000 | 0.55000 | 0.5430 – 29.2150 | 0 / 2047 |
| B 的 P3 候选 | 0.0080000 | 0.30000 | 0.2960 – 16.6800 | 0 / 2047 |
| B 的 P4 候选 | 0.0125000 | 0.45000 | 0.4438 – 26.0438 | 0 / 2047 |

P3 的 0.008 keV/道把 10–13 keV 的 L/K 系拉开到 ~125–1600 道区间，代价是上限只有 16.68 keV；
P4 的 0.0125 keV/道把 Ag Kα（22.163 keV，道 1733）与 Sn Kα（25.271，道 1985.7）保留在窗内。

## 2.5 逐元素结论口径

- **可记录（recordable）**：沿用交付 `element_support` 的判据 —— 该线 `excitable_at_voltage` 为真
  **且** `recorded_window_fraction > 0.5`；`recorded_window_fraction` 是按 `Profile.fwhm_keV(E)` 展宽后
  落在窗口内的比例（高斯分箱权重求和）。
- **响应（response）** = 该线的 `detector_efficiency × exit_air_transmission`。
  它**不含**一次线强度、不含滤片、不含基体吸收、不含峰重合，工具自评"低于 1% 只是启发式标记"。
- 分档规则（写在 `work/render_B_profile_tables.py` 顶部，评审时请针对规则提出异议而不是针对措辞）：
  A 档 最优响应 ≥ 0.5；B 档 0.01 ≤ 最优响应 < 0.5；C 档 最优响应 < 0.01 或工具状态为强衰减；
  D 档 与另一目标元素的设计重合间距 < 1 倍 FWHM（用 `B_profile_pair_check.json` 实测值标注）。
  D 档与 A/B/C 档可叠加：一条线可以"响应充裕但不可分辨"。

# §2 逐元素表格（由脚本渲染，勿手改数字）

渲染命令：`datasets/B-part/work/venv313/Scripts/python.exe -B datasets/B-part/work/render_B_profile_tables.py`
输入：`B_profile_support_summary.json`、`B_profile_pair_check.json`

## P3 候选（20 kV）32 个目标元素

| 元素 | 窗口内可记录线系与道址 | 最优响应 | 交付工具状态 | 重合情况 | B 档结论 |
| --- | --- | --- | --- | --- | --- |
| Al | K 可记录（KL3 1.487 keV→道 148.4，响应 0.689） | 0.6888 | structurally_supported_unvalidated | — | A 档：最优响应 0.689，条件不构成限制 |
| As | K 可记录（KL3 10.544 keV→道 1280.4，响应 0.966）；L 可记录（L3M5 1.282 keV→道 122.7，响应 0.673） | 0.9659 | structurally_supported_unvalidated | 与 Pb Lα 重合 | A 档：最优响应 0.966，条件不构成限制；D 档：As_K_vs_Pb_L Δ=7.6 eV = 0.04 倍 FWHM → 峰形不可分辨，只能作为重合峰整体处理 |
| Ba | K 不可记录（no_line_excitable_at_voltage+no_line_inside_window）；L 可记录（L3M5 4.466 keV→道 520.8，响应 0.994）；M 可记录（无主分析线，仅 1.033-1.278 keV，响应 0.511） | 0.9941 | structurally_supported_unvalidated | — | A 档：最优响应 0.994，条件不构成限制 |
| Ca | K 可记录（KL3 3.692 keV→道 424.0，响应 0.98） | 0.9803 | structurally_supported_unvalidated | — | A 档：最优响应 0.980，条件不构成限制 |
| Cd | K 不可记录（no_line_excitable_at_voltage+no_line_inside_window）；L 可记录（L3M5 3.134 keV→道 354.2，响应 0.98） | 0.9804 | structurally_supported_unvalidated | — | A 档：最优响应 0.980，条件不构成限制 |
| Cl | K 可记录（KL3 2.622 keV→道 290.3，响应 0.942） | 0.9419 | structurally_supported_unvalidated | — | A 档：最优响应 0.942，条件不构成限制 |
| Co | K 可记录（KL3 6.930 keV→道 828.8，响应 0.997） | 0.9969 | structurally_supported_unvalidated | — | A 档：最优响应 0.997，条件不构成限制 |
| Cr | K 可记录（KL3 5.415 keV→道 639.3，响应 0.994） | 0.994 | structurally_supported_unvalidated | — | A 档：最优响应 0.994，条件不构成限制 |
| Cu | K 可记录（KL3 8.048 keV→道 968.5，响应 0.997）；L 可记录（无主分析线，仅 1.022-1.095 keV，响应 0.344） | 0.9969 | structurally_supported_unvalidated | — | A 档：最优响应 0.997，条件不构成限制 |
| Fe | K 可记录（KL3 6.404 keV→道 763.0，响应 0.996） | 0.9963 | structurally_supported_unvalidated | — | A 档：最优响应 0.996，条件不构成限制 |
| K | K 可记录（KL3 3.314 keV→道 376.7，响应 0.972） | 0.9723 | structurally_supported_unvalidated | — | A 档：最优响应 0.972，条件不构成限制 |
| Mg | K 可记录（KL3 1.254 keV→道 119.2，响应 0.491） | 0.4909 | structurally_supported_unvalidated | — | B 档：最优响应 0.491，需要更多净计数 |
| Mn | K 可记录（KL3 5.899 keV→道 699.8，响应 0.995） | 0.9954 | structurally_supported_unvalidated | — | A 档：最优响应 0.995，条件不构成限制 |
| Mo | K 不可记录（no_line_inside_window）；L 可记录（L3M5 2.293 keV→道 249.2，响应 0.945） | 0.9448 | structurally_supported_unvalidated | — | A 档：最优响应 0.945，条件不构成限制 |
| Na | K 可记录（KL3 1.041 keV→道 92.6，响应 0.29） | 0.2899 | structurally_supported_unvalidated | — | B 档：最优响应 0.290，需要更多净计数 |
| Nb | K 可记录（KL3 16.615 keV→道 2039.4，响应 0.596）；L 可记录（L3M5 2.166 keV→道 233.2，响应 0.934） | 0.9337 | structurally_supported_unvalidated | — | A 档：最优响应 0.934，条件不构成限制 |
| Ni | K 可记录（KL3 7.478 keV→道 897.3，响应 0.997）；L 可记录（无主分析线，仅 1.004-1.004 keV，响应 0.252） | 0.9968 | structurally_supported_unvalidated | — | A 档：最优响应 0.997，条件不构成限制 |
| P | K 可记录（KL3 2.010 keV→道 213.8，响应 0.868） | 0.8685 | structurally_supported_unvalidated | — | A 档：最优响应 0.868，条件不构成限制 |
| Pb | K 不可记录（no_line_excitable_at_voltage+no_line_inside_window）；L 可记录（L3M5 10.551 keV→道 1281.4，响应 0.992）；M 可记录（M5N6 2.343 keV→道 255.4，响应 0.977） | 0.9918 | structurally_supported_unvalidated | Lα 与 As Kα 重合，Mα 与 S Kα 重合 | A 档：最优响应 0.992，条件不构成限制；D 档：As_K_vs_Pb_L Δ=7.6 eV = 0.04 倍 FWHM，S_K_vs_Pb_M Δ=35.0 eV = 0.30 倍 FWHM → 峰形不可分辨，只能作为重合峰整体处理 |
| Rb | K 可记录（KL3 13.395 keV→道 1636.9，响应 0.817）；L 可记录（L3M5 1.694 keV→道 174.3，响应 0.852） | 0.8524 | structurally_supported_unvalidated | — | A 档：最优响应 0.852，条件不构成限制 |
| S | K 可记录（KL3 2.308 keV→道 251.0，响应 0.913） | 0.9134 | structurally_supported_unvalidated | 与 Pb Mα 重合 | A 档：最优响应 0.913，条件不构成限制；D 档：S_K_vs_Pb_M Δ=35.0 eV = 0.30 倍 FWHM → 峰形不可分辨，只能作为重合峰整体处理 |
| Sb | K 不可记录（no_line_excitable_at_voltage+no_line_inside_window）；L 可记录（L3M5 3.605 keV→道 413.1，响应 0.988） | 0.9879 | structurally_supported_unvalidated | — | A 档：最优响应 0.988，条件不构成限制 |
| Se | K 可记录（KL3 11.222 keV→道 1365.2，响应 0.941）；L 可记录（L3M5 1.379 keV→道 134.9，响应 0.732） | 0.941 | structurally_supported_unvalidated | — | A 档：最优响应 0.941，条件不构成限制 |
| Si | K 可记录（KL3 1.740 keV→道 180.0，响应 0.799） | 0.799 | structurally_supported_unvalidated | — | A 档：最优响应 0.799，条件不构成限制 |
| Sn | K 不可记录（no_line_excitable_at_voltage+no_line_inside_window）；L 可记录（L3M5 3.444 keV→道 393.0，响应 0.986） | 0.9858 | structurally_supported_unvalidated | — | A 档：最优响应 0.986，条件不构成限制 |
| Sr | K 可记录（KL3 14.165 keV→道 1733.1，响应 0.764）；L 可记录（L3M5 1.806 keV→道 188.3，响应 0.879） | 0.8787 | structurally_supported_unvalidated | — | A 档：最优响应 0.879，条件不构成限制 |
| Ti | K 可记录（KL3 4.511 keV→道 526.4，响应 0.99） | 0.9895 | structurally_supported_unvalidated | — | A 档：最优响应 0.990，条件不构成限制 |
| V | K 可记录（KL3 4.952 keV→道 581.5，响应 0.992） | 0.9922 | structurally_supported_unvalidated | — | A 档：最优响应 0.992，条件不构成限制 |
| W | K 不可记录（no_line_excitable_at_voltage+no_line_inside_window）；L 可记录（L3M5 8.398 keV→道 1012.2，响应 0.997）；M 可记录（M5N6 1.771 keV→道 183.9，响应 0.94） | 0.9969 | structurally_supported_unvalidated | — | A 档：最优响应 0.997，条件不构成限制 |
| Y | K 可记录（KL3 14.958 keV→道 1832.3，响应 0.708）；L 可记录（L3M5 1.923 keV→道 202.8，响应 0.903） | 0.9029 | structurally_supported_unvalidated | — | A 档：最优响应 0.903，条件不构成限制 |
| Zn | K 可记录（KL3 8.639 keV→道 1042.4，响应 0.996）；L 可记录（L3M5 1.012 keV→道 89.0，响应 0.431） | 0.9956 | structurally_supported_unvalidated | — | A 档：最优响应 0.996，条件不构成限制 |
| Zr | K 可记录（KL3 15.775 keV→道 1934.4，响应 0.651）；L 可记录（L3M5 2.042 keV→道 217.8，响应 0.92） | 0.9198 | structurally_supported_unvalidated | — | A 档：最优响应 0.920，条件不构成限制 |

## P4 候选（49 kV + 100 µm Al + 8 cm 空气路径）32 个目标元素

| 元素 | 窗口内可记录线系与道址 | 最优响应 | 交付工具状态 | 重合情况 | B 档结论 |
| --- | --- | --- | --- | --- | --- |
| Al | K 可记录（KL3 1.487 keV→道 83.0，响应 0.0038） | 0.003801 | strongly_attenuated_assumed_response | — | C 档：仅结构存在，响应 0.0038，不得写成可探测 |
| As | K 可记录（KL3 10.544 keV→道 807.5，响应 0.945）；L 可记录（L3M5 1.282 keV→道 66.6，响应 0.00277） | 0.9455 | structurally_supported_unvalidated | 与 Pb Lα 重合 | A 档：最优响应 0.945，条件不构成限制；D 档：As_K_vs_Pb_L Δ=7.6 eV = 0.04 倍 FWHM → 峰形不可分辨，只能作为重合峰整体处理 |
| Ba | K 不可记录（no_line_inside_window）；L 可记录（L3M5 4.466 keV→道 321.3，响应 0.887）；M 可记录（无主分析线，仅 1.033-1.278 keV，响应 6.82e-05） | 0.8868 | structurally_supported_unvalidated | — | A 档：最优响应 0.887，条件不构成限制 |
| Ca | K 可记录（KL3 3.692 keV→道 259.3，响应 0.676） | 0.6759 | structurally_supported_unvalidated | — | A 档：最优响应 0.676，条件不构成限制 |
| Cd | K 可记录（KL3 23.174 keV→道 1817.9，响应 0.294）；L 可记录（L3M5 3.134 keV→道 214.7，响应 0.676） | 0.6765 | structurally_supported_unvalidated | — | A 档：最优响应 0.676，条件不构成限制 |
| Cl | K 可记录（KL3 2.622 keV→道 173.8，响应 0.367） | 0.3665 | structurally_supported_unvalidated | — | B 档：最优响应 0.367，需要更多净计数 |
| Co | K 可记录（KL3 6.930 keV→道 518.4，响应 0.944） | 0.9439 | structurally_supported_unvalidated | — | A 档：最优响应 0.944，条件不构成限制 |
| Cr | K 可记录（KL3 5.415 keV→道 397.2，响应 0.885） | 0.8853 | structurally_supported_unvalidated | — | A 档：最优响应 0.885，条件不构成限制 |
| Cu | K 可记录（KL3 8.048 keV→道 607.8，响应 0.96）；L 可记录（无主分析线，仅 1.022-1.095 keV，响应 4.2e-07） | 0.9601 | structurally_supported_unvalidated | — | A 档：最优响应 0.960，条件不构成限制 |
| Fe | K 可记录（KL3 6.404 keV→道 476.3，响应 0.929） | 0.9295 | structurally_supported_unvalidated | — | A 档：最优响应 0.929，条件不构成限制 |
| K | K 可记录（KL3 3.314 keV→道 229.1，响应 0.581） | 0.5811 | structurally_supported_unvalidated | — | A 档：最优响应 0.581，条件不构成限制 |
| Mg | K 可记录（KL3 1.254 keV→道 64.3，响应 4.03e-05） | 4.028e-05 | strongly_attenuated_assumed_response | — | C 档：仅结构存在，响应 4e-05，不得写成可探测 |
| Mn | K 可记录（KL3 5.899 keV→道 435.9，响应 0.91） | 0.9104 | structurally_supported_unvalidated | — | A 档：最优响应 0.910，条件不构成限制 |
| Mo | K 可记录（KL3 17.479 keV→道 1362.3，响应 0.54）；L 可记录（L3M5 2.293 keV→道 147.5，响应 0.385） | 0.5398 | structurally_supported_unvalidated | — | A 档：最优响应 0.540，条件不构成限制 |
| Na | K 可记录（KL3 1.041 keV→道 47.3，响应 5e-08） | 5e-08 | strongly_attenuated_assumed_response | — | C 档：仅结构存在，响应 5e-08，不得写成可探测 |
| Nb | K 可记录（KL3 16.615 keV→道 1293.2，响应 0.592）；L 可记录（L3M5 2.166 keV→道 137.3，响应 0.319） | 0.5924 | structurally_supported_unvalidated | — | A 档：最优响应 0.592，条件不构成限制 |
| Ni | K 可记录（KL3 7.478 keV→道 562.2，响应 0.954）；L 可记录（无主分析线，仅 1.004-1.004 keV，响应 1e-08） | 0.9543 | structurally_supported_unvalidated | — | A 档：最优响应 0.954，条件不构成限制 |
| P | K 可记录（KL3 2.010 keV→道 124.8，响应 0.106） | 0.1055 | structurally_supported_unvalidated | — | B 档：最优响应 0.106，需要更多净计数 |
| Pb | K 不可记录（no_line_excitable_at_voltage+no_line_inside_window）；L 可记录（L3M5 10.551 keV→道 808.1，响应 0.961）；M 可记录（M5N6 2.343 keV→道 151.4，响应 0.639） | 0.9608 | structurally_supported_unvalidated | Lα 与 As Kα 重合，Mα 与 S Kα 重合 | A 档：最优响应 0.961，条件不构成限制；D 档：As_K_vs_Pb_L Δ=7.6 eV = 0.04 倍 FWHM，S_K_vs_Pb_M Δ=35.0 eV = 0.22 倍 FWHM → 峰形不可分辨，只能作为重合峰整体处理 |
| Rb | K 可记录（KL3 13.395 keV→道 1035.6，响应 0.808）；L 可记录（L3M5 1.694 keV→道 99.5，响应 0.0799） | 0.808 | structurally_supported_unvalidated | — | A 档：最优响应 0.808，条件不构成限制 |
| S | K 可记录（KL3 2.308 keV→道 148.6，响应 0.227） | 0.2267 | structurally_supported_unvalidated | 与 Pb Mα 重合 | B 档：最优响应 0.227，需要更多净计数；D 档：S_K_vs_Pb_M Δ=35.0 eV = 0.22 倍 FWHM → 峰形不可分辨，只能作为重合峰整体处理 |
| Sb | K 不可记录（no_single_line_both_excitable_and_in_window）；L 可记录（L3M5 3.605 keV→道 252.4，响应 0.782） | 0.7819 | structurally_supported_unvalidated | — | A 档：最优响应 0.782，条件不构成限制 |
| Se | K 可记录（KL3 11.222 keV→道 861.8，响应 0.924）；L 可记录（L3M5 1.379 keV→道 74.3，响应 0.00891） | 0.9244 | structurally_supported_unvalidated | — | A 档：最优响应 0.924，条件不构成限制 |
| Si | K 可记录（KL3 1.740 keV→道 103.2，响应 0.031） | 0.031 | structurally_supported_unvalidated | — | B 档：最优响应 0.031，需要更多净计数 |
| Sn | K 可记录（KL3 25.271 keV→道 1985.7，响应 0.239）；L 可记录（L3M5 3.444 keV→道 239.5，响应 0.751） | 0.7512 | structurally_supported_unvalidated | — | A 档：最优响应 0.751，条件不构成限制 |
| Sr | K 可记录（KL3 14.165 keV→道 1097.2，响应 0.757）；L 可记录（L3M5 1.806 keV→道 108.5，响应 0.126） | 0.7565 | structurally_supported_unvalidated | — | A 档：最优响应 0.757，条件不构成限制 |
| Ti | K 可记录（KL3 4.511 keV→道 324.9，响应 0.808） | 0.8084 | structurally_supported_unvalidated | — | A 档：最优响应 0.808，条件不构成限制 |
| V | K 可记录（KL3 4.952 keV→道 360.2，响应 0.852） | 0.8522 | structurally_supported_unvalidated | — | A 档：最优响应 0.852，条件不构成限制 |
| W | K 不可记录（no_line_excitable_at_voltage+no_line_inside_window）；L 可记录（L3M5 8.398 keV→道 635.8，响应 0.961）；M 可记录（M5N6 1.771 keV→道 105.7，响应 0.354） | 0.9608 | structurally_supported_unvalidated | — | A 档：最优响应 0.961，条件不构成限制 |
| Y | K 可记录（KL3 14.958 keV→道 1160.7，响应 0.702）；L 可记录（L3M5 1.923 keV→道 117.8，响应 0.19） | 0.7022 | structurally_supported_unvalidated | — | A 档：最优响应 0.702，条件不构成限制 |
| Zn | K 可记录（KL3 8.639 keV→道 655.1，响应 0.96）；L 可记录（L3M5 1.012 keV→道 44.9，响应 7.54e-06） | 0.9597 | structurally_supported_unvalidated | — | A 档：最优响应 0.960，条件不构成限制 |
| Zr | K 可记录（KL3 15.775 keV→道 1226.0，响应 0.647）；L 可记录（L3M5 2.042 keV→道 127.4，响应 0.253） | 0.647 | structurally_supported_unvalidated | — | A 档：最优响应 0.647，条件不构成限制 |

## P1 参考（A 交付条件，仅作对照）

| 元素 | 窗口内可记录线系与道址 | 最优响应 | 交付工具状态 | 重合情况 | B 档结论 |
| --- | --- | --- | --- | --- | --- |
| Al | K 可记录（KL3 1.487 keV→道 63.1，响应 0.689） | 0.6888 | structurally_supported_unvalidated | — | A 档：最优响应 0.689，条件不构成限制 |
| As | K 可记录（KL3 10.544 keV→道 717.5，响应 0.966）；L 可记录（L3M5 1.282 keV→道 48.3，响应 0.673） | 0.9659 | structurally_supported_unvalidated | 与 Pb Lα 重合 | A 档：最优响应 0.966，条件不构成限制；D 档：As_K_vs_Pb_L Δ=7.6 eV = 0.05 倍 FWHM → 峰形不可分辨，只能作为重合峰整体处理 |
| Ba | K 不可记录（no_line_inside_window）；L 可记录（L3M5 4.466 keV→道 278.4，响应 0.994）；M 可记录（无主分析线，仅 1.033-1.278 keV，响应 0.511） | 0.9941 | structurally_supported_unvalidated | — | A 档：最优响应 0.994，条件不构成限制 |
| Ca | K 可记录（KL3 3.692 keV→道 222.4，响应 0.98） | 0.9803 | structurally_supported_unvalidated | — | A 档：最优响应 0.980，条件不构成限制 |
| Cd | K 可记录（KL3 23.174 keV→道 1630.2，响应 0.294）；L 可记录（L3M5 3.134 keV→道 182.1，响应 0.98） | 0.9804 | structurally_supported_unvalidated | — | A 档：最优响应 0.980，条件不构成限制 |
| Cl | K 可记录（KL3 2.622 keV→道 145.2，响应 0.942） | 0.9419 | structurally_supported_unvalidated | — | A 档：最优响应 0.942，条件不构成限制 |
| Co | K 可记录（KL3 6.930 keV→道 456.4，响应 0.997） | 0.9969 | structurally_supported_unvalidated | — | A 档：最优响应 0.997，条件不构成限制 |
| Cr | K 可记录（KL3 5.415 keV→道 346.9，响应 0.994） | 0.994 | structurally_supported_unvalidated | — | A 档：最优响应 0.994，条件不构成限制 |
| Cu | K 可记录（KL3 8.048 keV→道 537.2，响应 0.997）；L 可记录（无主分析线，仅 1.022-1.095 keV，响应 0.344） | 0.9969 | structurally_supported_unvalidated | — | A 档：最优响应 0.997，条件不构成限制 |
| Fe | K 可记录（KL3 6.404 keV→道 418.4，响应 0.996） | 0.9963 | structurally_supported_unvalidated | — | A 档：最优响应 0.996，条件不构成限制 |
| K | K 可记录（KL3 3.314 keV→道 195.1，响应 0.972） | 0.9723 | structurally_supported_unvalidated | — | A 档：最优响应 0.972，条件不构成限制 |
| Mg | K 可记录（KL3 1.254 keV→道 46.3，响应 0.491） | 0.4909 | structurally_supported_unvalidated | — | B 档：最优响应 0.491，需要更多净计数 |
| Mn | K 可记录（KL3 5.899 keV→道 381.9，响应 0.995） | 0.9954 | structurally_supported_unvalidated | — | A 档：最优响应 0.995，条件不构成限制 |
| Mo | K 可记录（KL3 17.479 keV→道 1218.7，响应 0.543）；L 可记录（L3M5 2.293 keV→道 121.4，响应 0.945） | 0.9448 | structurally_supported_unvalidated | — | A 档：最优响应 0.945，条件不构成限制 |
| Na | K 可记录（KL3 1.041 keV→道 30.9，响应 0.29） | 0.2899 | structurally_supported_unvalidated | — | B 档：最优响应 0.290，需要更多净计数 |
| Nb | K 可记录（KL3 16.615 keV→道 1156.3，响应 0.596）；L 可记录（L3M5 2.166 keV→道 112.2，响应 0.934） | 0.9337 | structurally_supported_unvalidated | — | A 档：最优响应 0.934，条件不构成限制 |
| Ni | K 可记录（KL3 7.478 keV→道 496.0，响应 0.997）；L 可记录（无主分析线，仅 1.004-1.004 keV，响应 0.252） | 0.9968 | structurally_supported_unvalidated | — | A 档：最优响应 0.997，条件不构成限制 |
| P | K 可记录（KL3 2.010 keV→道 100.9，响应 0.868） | 0.8685 | structurally_supported_unvalidated | — | A 档：最优响应 0.868，条件不构成限制 |
| Pb | K 不可记录（no_line_excitable_at_voltage+no_line_inside_window）；L 可记录（L3M5 10.551 keV→道 718.1，响应 0.992）；M 可记录（M5N6 2.343 keV→道 125.0，响应 0.977） | 0.9918 | structurally_supported_unvalidated | Lα 与 As Kα 重合，Mα 与 S Kα 重合 | A 档：最优响应 0.992，条件不构成限制；D 档：As_K_vs_Pb_L Δ=7.6 eV = 0.05 倍 FWHM，S_K_vs_Pb_M Δ=35.0 eV = 0.38 倍 FWHM → 峰形不可分辨，只能作为重合峰整体处理 |
| Rb | K 可记录（KL3 13.395 keV→道 923.6，响应 0.817）；L 可记录（L3M5 1.694 keV→道 78.1，响应 0.852） | 0.8524 | structurally_supported_unvalidated | — | A 档：最优响应 0.852，条件不构成限制 |
| S | K 可记录（KL3 2.308 keV→道 122.4，响应 0.913） | 0.9134 | structurally_supported_unvalidated | 与 Pb Mα 重合 | A 档：最优响应 0.913，条件不构成限制；D 档：S_K_vs_Pb_M Δ=35.0 eV = 0.38 倍 FWHM → 峰形不可分辨，只能作为重合峰整体处理 |
| Sb | K 可记录（KL3 26.359 keV→道 1860.3，响应 0.216）；L 可记录（L3M5 3.605 keV→道 216.1，响应 0.988） | 0.9879 | structurally_supported_unvalidated | — | A 档：最优响应 0.988，条件不构成限制 |
| Se | K 可记录（KL3 11.222 keV→道 766.6，响应 0.941）；L 可记录（L3M5 1.379 keV→道 55.3，响应 0.732） | 0.941 | structurally_supported_unvalidated | — | A 档：最优响应 0.941，条件不构成限制 |
| Si | K 可记录（KL3 1.740 keV→道 81.4，响应 0.799） | 0.799 | structurally_supported_unvalidated | — | A 档：最优响应 0.799，条件不构成限制 |
| Sn | K 可记录（KL3 25.271 keV→道 1781.7，响应 0.24）；L 可记录（L3M5 3.444 keV→道 204.5，响应 0.986） | 0.9858 | structurally_supported_unvalidated | — | A 档：最优响应 0.986，条件不构成限制 |
| Sr | K 可记录（KL3 14.165 keV→道 979.2，响应 0.764）；L 可记录（L3M5 1.806 keV→道 86.2，响应 0.879） | 0.8787 | structurally_supported_unvalidated | — | A 档：最优响应 0.879，条件不构成限制 |
| Ti | K 可记录（KL3 4.511 keV→道 281.6，响应 0.99） | 0.9895 | structurally_supported_unvalidated | — | A 档：最优响应 0.990，条件不构成限制 |
| V | K 可记录（KL3 4.952 keV→道 313.5，响应 0.992） | 0.9922 | structurally_supported_unvalidated | — | A 档：最优响应 0.992，条件不构成限制 |
| W | K 不可记录（no_line_excitable_at_voltage+no_line_inside_window）；L 可记录（L3M5 8.398 keV→道 562.5，响应 0.997）；M 可记录（M5N6 1.771 keV→道 83.7，响应 0.94） | 0.9969 | structurally_supported_unvalidated | — | A 档：最优响应 0.997，条件不构成限制 |
| Y | K 可记录（KL3 14.958 keV→道 1036.5，响应 0.708）；L 可记录（L3M5 1.923 keV→道 94.6，响应 0.903） | 0.9029 | structurally_supported_unvalidated | — | A 档：最优响应 0.903，条件不构成限制 |
| Zn | K 可记录（KL3 8.639 keV→道 579.9，响应 0.996）；L 可记录（L3M5 1.012 keV→道 28.8，响应 0.431） | 0.9956 | structurally_supported_unvalidated | — | A 档：最优响应 0.996，条件不构成限制 |
| Zr | K 可记录（KL3 15.775 keV→道 1095.6，响应 0.651）；L 可记录（L3M5 2.042 keV→道 103.3，响应 0.92） | 0.9198 | structurally_supported_unvalidated | — | A 档：最优响应 0.920，条件不构成限制 |

## 重合线对可分辨性

| 条件 | 管压 kV | 噪声 eV | 增益 keV/道 | 线对 | ΔE eV | Δ道 | 较大 FWHM keV | Δ/最大 FWHM | 峰形可分辨 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1_a_reference | 49 | 55 | 0.0138393 | As KL3 vs Pb L3M5 | 7.6 | 0.55 | 0.1661 | 0.046 | 否 |
| P1_a_reference | 49 | 55 | 0.0138393 | S KL3 vs Pb M5N6 | 35.0 | 2.53 | 0.0921 | 0.380 | 否 |
| P2_a_reference | 49 | 70 | 0.014 | As KL3 vs Pb L3M5 | 7.6 | 0.54 | 0.1716 | 0.044 | 否 |
| P2_a_reference | 49 | 70 | 0.014 | S KL3 vs Pb M5N6 | 35.0 | 2.50 | 0.1017 | 0.344 | 否 |
| P3_B_candidate | 20 | 90 | 0.008 | As KL3 vs Pb L3M5 | 7.6 | 0.95 | 0.1807 | 0.042 | 否 |
| P3_B_candidate | 20 | 90 | 0.008 | S KL3 vs Pb M5N6 | 35.0 | 4.38 | 0.1164 | 0.301 | 否 |
| P4_B_candidate | 49 | 140 | 0.0125 | As KL3 vs Pb L3M5 | 7.6 | 0.61 | 0.2101 | 0.036 | 否 |
| P4_B_candidate | 49 | 140 | 0.0125 | S KL3 vs Pb M5N6 | 35.0 | 2.80 | 0.1583 | 0.221 | 否 |

## 每条件计数与窗口损失（CLI batch 实测，非声称）

| 候选 | 2 条 B 配方实测总观测计数 | 相对 A 的 P1 计数区间中点 | 窗外观测损失比例 |
| --- | --- | --- | --- |
| P3 | 620022 – 647033 | 1.158 | 0.0007, 0.0007 |
| P4 | 682544 – 787328 | 1.343 | 0.0070, 0.0080 |

## §3 试产实测复核（每条件 100 配方 × 2 重复 = 200 谱，读自验收报告）

数据源：`work/pilot_reports/pilot_<条件>_v1/verification*.json`（取最新一份），由 `run_B_pilot.py --phase verify` 生成。下表把"线存在"与"有足够净计数"分开给数字，净期望计数 = 一次+二次发射 × 几何因子 × 探测器效率 × 出射空气透过率，即整条 live time 的期望值。

| 条件 | 谱数 | 窗外损失 min | 窗外损失 mean | 窗外损失 max | 超 1% 预算谱数 | 丢弃计数成分占比 |
| --- | --- | --- | --- | --- | --- | --- |
| P3 | 200 | 0.00061 | 0.00079 | 0.00106 | 0/200 | 无超预算谱 |
| P4 | 200 | 0.00611 | 0.00924 | 0.01440 | 70/200 | compton 72.9%, rayleigh 23.8%, primary 2.5%, escape 0.8%, secondary 0.0% |

每条件被丢弃计数落在窗口的哪一侧（结构性判据，非推测）：

- **P3**：下沿 0.2960 keV，上沿 16.6800 keV，管压 20 kV，交付源网格起点 1 keV = True；90° Compton 仍出窗的入射阈能 17.24 keV。the discarded band is the high-energy side, from 16.680 keV to the 20 keV tube voltage (unscattered continuum plus its Rayleigh and Compton tail; a photon above 17.2 keV Compton-scattered at 90 degrees still lands above the window). Nothing can sit below the 0.296 keV lower edge because the delivered source grid starts at 1 keV
- **P4**：下沿 0.4438 keV，上沿 26.0438 keV，管压 49 kV，交付源网格起点 1 keV = True；90° Compton 仍出窗的入射阈能 27.44 keV。the discarded band is the high-energy side, from 26.044 keV to the 49 keV tube voltage (unscattered continuum plus its Rayleigh and Compton tail; a photon above 27.4 keV Compton-scattered at 90 degrees still lands above the window). Nothing can sit below the 0.444 keV lower edge because the delivered source grid starts at 1 keV

干扰家族关键线的实测净期望计数（同一配方 2 条谱取最大）：

| 条件 | 组 | 线 | 含该元素谱数 | 建模谱数 | 窗内谱数 | 能量 keV | 道址 | 最大净期望计数 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P3 | As/Pb | Fe KL3_LINE | 40 | 40 | 40 | 6.4039 | 763.0 | 332307.19 |
| P3 | As/Pb | As KL3_LINE | 24 | 24 | 24 | 10.5436 | 1280.5 | 782.63 |
| P3 | As/Pb | S KL3_LINE | 40 | 40 | 40 | 2.3078 | 251.0 | 1170.56 |
| P3 | As/Pb | Pb L3M5_LINE | 24 | 24 | 24 | 10.5512 | 1281.4 | 31.10 |
| P3 | As/Pb | Pb M5N6_LINE | 24 | 24 | 24 | 2.3428 | 255.3 | 1.32 |
| P3 | S/Pb | Fe KL3_LINE | 40 | 40 | 40 | 6.4039 | 763.0 | 313022.44 |
| P3 | S/Pb | As KL3_LINE | 0 | 0 | 0 | — | — | — |
| P3 | S/Pb | S KL3_LINE | 24 | 24 | 24 | 2.3078 | 251.0 | 872.04 |
| P3 | S/Pb | Pb L3M5_LINE | 24 | 24 | 24 | 10.5512 | 1281.4 | 31.04 |
| P3 | S/Pb | Pb M5N6_LINE | 24 | 24 | 24 | 2.3428 | 255.3 | 1.26 |
| P4 | As/Pb | Fe KL3_LINE | 40 | 40 | 40 | 6.4039 | 476.3 | 414786.79 |
| P4 | As/Pb | As KL3_LINE | 24 | 24 | 24 | 10.5436 | 807.5 | 3199.95 |
| P4 | As/Pb | S KL3_LINE | 40 | 40 | 40 | 2.3078 | 148.6 | 15.66 |
| P4 | As/Pb | Pb L3M5_LINE | 24 | 24 | 24 | 10.5512 | 808.1 | 193.83 |
| P4 | As/Pb | Pb M5N6_LINE | 24 | 24 | 24 | 2.3428 | 151.4 | 0.05 |
| P4 | S/Pb | Fe KL3_LINE | 40 | 40 | 40 | 6.4039 | 476.3 | 385293.81 |
| P4 | S/Pb | As KL3_LINE | 0 | 0 | 0 | — | — | — |
| P4 | S/Pb | S KL3_LINE | 24 | 24 | 24 | 2.3078 | 148.6 | 11.22 |
| P4 | S/Pb | Pb L3M5_LINE | 24 | 24 | 24 | 10.5512 | 808.1 | 193.39 |
| P4 | S/Pb | Pb M5N6_LINE | 24 | 24 | 24 | 2.3428 | 151.4 | 0.05 |

按本文 §2.6 第 3 条自设的计数门槛（5% 峰面积 1σ 需要净峰 ≥ 400 counts）核对上表：

- P3 / As/Pb 组内最强配方：Fe KL3 ≥400(332307.19), As KL3 ≥400(782.63), S KL3 ≥400(1170.56), Pb L3M5 <400(31.10), Pb M5N6 <400(1.32)
- P3 / S/Pb 组内最强配方：Fe KL3 ≥400(313022.44), S KL3 ≥400(872.04), Pb L3M5 <400(31.04), Pb M5N6 <400(1.26)
- P4 / As/Pb 组内最强配方：Fe KL3 ≥400(414786.79), As KL3 ≥400(3199.95), S KL3 <400(15.66), Pb L3M5 <400(193.83), Pb M5N6 <400(0.05)
- P4 / S/Pb 组内最强配方：Fe KL3 ≥400(385293.81), S KL3 <400(11.22), Pb L3M5 <400(193.39), Pb M5N6 <400(0.05)

## 2.6 三条必须交给 A/C 的模型限制

1. **`excitable_at_voltage` 的判据是"电子能量 = 管压"的荧光截面**。`core.line_cs()` 调用
   `xraylib.CS_FluorLine_Kissel_Cascade(z, code, voltage_kV)`，xraylib 对低于壳层阈值的跃迁抛异常并被
   折算为 0，所以该标记**确实尊重吸收边**；但 `core.py` 第 226 行自述这是
   "necessary excitation availability only, not flux"。实际风险点：Mo 的 K 壳层结合能 20.00 keV 与
   P3 管压相等，工具仍把 Mo K 线标为可激发，而 20 kV 韧致谱在 20.00 keV 处已无光子。
   本情景 Mo 的 K 系同时出窗（17.479 > 16.680），结论不受影响；
   **但若有人把 P3 窗口上限拉到 17.5 keV 以上，就会误认为 Mo K 在 20 kV 可用**。
2. **1 keV 以下全部截断**：`core.line_data()` 只保留能量 ≥ 1 keV 的线（`minimum_modeled_line_keV = 1.0`）。
   后果：Cu 的 L3 结合能 0.9311 keV、Ni 的 0.8547 keV 都低于 1 keV，其 Lα 主分析线必然也在 1 keV 以下，
   因此支持表中 Cu/Ni 的"L 系"只剩 1.022–1.095 keV / 1.004 keV 的弱线（响应 0.344 与 0.252），
   `L3M5` 在两者的线列表中直接为 None；重元素的 M 系同理（Pb M5N6 2.3428 keV 存在，更软的 M 线被切）。
   所以"L/M 可记录"必须逐元素看能量带，不能当成"有合适定量分析线"。
3. **支持表不是方法验证**：不含强度、基体吸收、峰重合与拟合误差，工具 notes 原文包括
   "Response excludes incident flux, matrix absorption and peak overlap; values below 1% are a heuristic flag"。
   因此本文不给任何检出限或 5% 准确度结论。作为必要条件，仅计数统计而言 5%（1σ）需要净峰面积 ≥ 400 counts
   （5% 峰面积对总计数则需 ≥1e4），实际还须叠加拟合与基线误差 —— 该数值条件是否在试产谱里被满足，
   由 §3 的逐元素峰面积实测回答，不由本文声称。
   **§3 已实测并回填**（见上"§3 试产实测复核"表的最后一段）：P3 只有 As Kα（最强配方 782.63 counts）
   与 S Kα（1170.56）跨过 400 门槛，Pb Lα 最大 31.10、Pb Mα 最大 1.32 都在门槛之下两个数量级；
   P4 里 As Kα 升到 3199.95，而 S Kα 跌到 11.22–15.66、Pb Mα 跌到 0.05，
   即**在 P4 条件下 S 与 Pb 的 M 系连计数统计的必要条件都不满足**，
   任何"S 在 49 kV + 100 µm Al + 8 cm 空气下可定量"的写法都是错的。这仍然只是必要条件，不是检出限结论。

## 2.7 与 A 交付条件的对比结论

- A 的 P1/P2 都是 49 kV、Ag 靶、无滤片、空气路径 0/0.5 cm；B 的 P3 提供"低压 + L 系主导 + 细增益"分布，
  P4 提供"强衰减低端 + 最差分辨率"分布。两个候选都保证 32 个目标至少有一条可记录线（`NONE` 元素数 = 0），
  因此 B 配方与标签维度不会因为条件选择而降维。
- **设计重合对在四个条件下都不可分辨**（`B_profile_pair_check.json`，用交付的 `Profile.fwhm_keV` 计算）：
  As Kα1 10.5436 keV vs Pb Lα1 10.5512 keV，Δ=7.6 eV，Δ/最大 FWHM = 0.046(P1)/0.044(P2)/0.042(P3)/0.036(P4)；
  S Kα1 2.3078 keV vs Pb Mα1 2.3428 keV，Δ=35.0 eV，Δ/最大 FWHM = 0.380/0.344/0.301/0.221。
  P3 虽然增益更细（Δ=0.95 道），但 FWHM 也随之变小，比值没有改善；P4 的 140 eV 噪声让两个比值进一步恶化。
  结论与 A 的报告一致：**As/Pb 仍是不可分辨**，B 的配方把这两对按"重合峰整体"设计是正确的，
  不能宣称任何条件能分开它们。
- **计数水平与窗口损失为实测**（2 条真实 B 配方、CLI `batch`、seed 2026101822、`--replicates 1`）：
  P3 每谱总观测计数 620,022–647,033，窗外观测损失 0.07%；P4 为 682,544–787,328，窗口损失 0.70%–0.80%。
  A 的 P1 记录区间为 270,981–823,275（`A_acceptance_summary.json`），
  两候选的比值分别是 1.158 与 1.343（相对 P1 区间中点），即**与 A 同一数量级**，
  跨条件比较不会被计数统计差异掩盖。这是初版曝光（P3 240 s、P4 3e7 photons/s×300 s，实测 2.5e6/1.1e7 counts）
  被下调后的结果，旧证据保留在 `work/runs/run_01/`。

## 2.8 冻结依赖与下一步

1. P3/P4 现为候选，等待 A、C 联评冻结。需要团队明确决定的项：
   P3 的 20 kV 是否接受"Ag K 系被源模型丢弃、只剩连续谱 + Ag L"这一后果；
   P4 的 100 µm Al + 8 cm 空气路径是否接受 Na/Mg/Al 进入强衰减档（若不接受，需缩短空气路径或去滤片）；
   两候选的 `live_time_s=60` 是否与团队算力预算匹配（实测 4.43 与 5.01 秒/谱，400 谱 ≈ 30–35 分钟，
   完整复演另计）。
   **§3 试产后新增的第 4 个待决项**：P4 的窗外计数损失实测 mean 0.92%、max 1.44%，
   有 70/200 条谱超过 B 在试产前声明的 1% 预算（`verification_v3.json` → `window_loss`），
   被丢弃计数的 72.9% 是 Compton、23.8% 是 Rayleigh、2.5% 是一次连续谱，全部落在 26.04–49 keV 的高能侧。
   该阈值是 B 自设的报告口径而不是赛题要求，B 不在看到结果后自行放宽；
   请 A/C 在冻结时二选一：接受 P4 的窗外损失并把预算改记为 2%（附本文理由），
   或把 P4 的 `channels/gain/zero` 调整为能覆盖到 49 keV 的窗（这会改动候选条件，需按第 2 条重做试产验收）。
   P3 同项实测 0.061%–0.106%，0/200 超预算。
2. 若冻结值与候选值不同，**必须用冻结配置重做 §3 试产验收**（含 replay）后才能进入正式生产。
3. P3/P4 候选与本文的计数探针都**不得**用作 M1 条件；M1 由 A 提供 100 条配方、B 每条生成 3 谱共 300 谱，
   单独计数、单独记录（见 `README.md` 的 M1 小节）。
4. 本文产物与探针谱**不计入** 20,000 / 50,000 正式预算。

## 2.9 复现命令与哈希

```
cd "C:\Users\Lenovo\Desktop\兴智杯AI开发大赛"
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  ./datasets/B-part/work/venv313/Scripts/python.exe -B datasets/B-part/work/build_B_profiles.py
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  ./datasets/B-part/work/venv313/Scripts/python.exe -B datasets/B-part/work/summarize_B_profile_support.py
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  ./datasets/B-part/work/venv313/Scripts/python.exe -B datasets/B-part/work/B_interference_pair_check.py
./datasets/B-part/work/venv313/Scripts/python.exe -B datasets/B-part/work/render_B_profile_tables.py
# §3 试产完成后，把实测复核表并入本文的渲染块（同一命令，读 work/pilot_reports/*/verification*.json）
./datasets/B-part/work/venv313/Scripts/python.exe -B datasets/B-part/work/verify_B_candidate_hashes.py
```

`render_B_profile_tables.py` 生成的表格块在本文下方原样贴出；若候选条件被改动，请重新渲染整段，
不要手改数字。

| 文件 | SHA256 |
| --- | --- |
| `P3_candidate.json`（按磁盘字节，交叉复核用这个） | `5bb3aeb948145c587c5c25f7f7a7eab321804be556c06e0edb6e26b1e8f1ac6c` |
| `P4_candidate.json`（按磁盘字节，交叉复核用这个） | `e62cec80bbead62568225bcfafbe51f48ee12d5965609edb5957408618f7ef3a` |
| `P3_candidate.json` 34 字段规范向量 | `0a0b5e0276b7e0d0a347c501dbfa9c5f26f4bf26c439341b481a14aae837ea42` |
| `P4_candidate.json` 34 字段规范向量 | `197182623607a1fd5570b3365ac63e3050259793bac00b77795d27951b6482a0` |

**哈希勘误（§3 试产完成后补记，原文不改）**：本表原先记的 `P3_candidate.json` = `4b533155…`、
`P4_candidate.json` = `5e696944…` 与磁盘文件字节的 sha256 不相等。原因是
`work/build_B_profiles.py` 当时对"文本内容"取哈希，而 `write_text()` 在 Windows 上把换行写成 CRLF；
`4b533155…`/`5e696944…` 是 LF 归一化文本的哈希（同一文件 987/996 字节，36 个 CRLF）。
两份候选的 **34 字段规范向量哈希与上表一致**，且两个试产批次内 `inputs/original_profile.json`、
`configs/profile.json` 与当前候选逐字段相同、封存 manifest 记的 `original_inputs.profile.sha256`
等于按磁盘字节取的哈希，所以 support 运行与 §3 试产用的物理值从未改变，结论仍然有效；
变的只是"该用哪个摘要做交叉复核"。同一问题也存在于 `B_pilot_selection.json` 记录的
`B_pilot_samples.json` 摘要（`18ab59b9…` 为 LF 变体，交付字节为 `ed3c26bc…`，
两个批次内密封副本与交付字节逐字节相同、各 100 条配方）。
完整度量与判据见 `work/B_candidate_hash_reverification.json`
（生成命令 `work/verify_B_candidate_hashes.py`，退出码 0）；两个生成脚本已改为写 LF 并对磁盘字节取哈希，
正式生产阶段不会再出现该分裂。`B_profile_diff.json` 与原 support 记录按"保留原始报告"的原则不改写。

CLI 原文（support）与探针目录：`work/runs/run_02/profile_support/`、`work/runs/run_02/profile_probe/`，
稳定副本在 `work/profile_support/`（逐文件 SHA256 见 `B_profile_diff.json` → `support_runs`，
其中 `stable_copy_identical` 记录副本与 CLI 原文哈希一致）。

---
