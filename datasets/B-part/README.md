# 成员 B 交付说明 —— `01_B_design_and_pilot_prompt.md`

- 交付日期：2026-10-19（本机 Windows-11-10.0.26200-SP0，隔离解释器 CPython 3.13.14）
- 判定口径：**`passed` 只用于本机实际跑完、报告已落盘、结论由报告字段导出的项目**。凡依赖 A、C 或三人联合冻结的一律写 `pending` / `blocked`。本交付是单人自检，**不是** A 对 B 的交叉复核，也**不是** C 的主审。
- 红线遵守情况：未改写 XRF 物理求解器（`core.py` / `dataset.py` / `minerals.py` / `robustness.py` 摘要与 A 封存批次逐字节一致，见 §1.3）；只用交付的只读 CLI（`design-mineral`、`convert-components`、`support`、`batch`、`audit`、`replay`、`pack`）；未使用 GUI 逐条手工导出；未把 `启动生成器.cmd` 当作生产命令；未修改 A 目录、两份 PDF 或任何已密封批次。
- 机器可核验的状态清单：`B_delivery_status.json`（21 项：17 passed / 4 blocked）与 `B_delivery_hashes.json`（全部声明产物的 SHA-256，含退出码证据日志，`declared_but_missing` 为空）。

## 0. 一页结论

| 卡片小节 | 状态 | 实测数字 | 证据 |
| --- | --- | --- | --- |
| §0 读文件 + 清点已有/缺失 | passed | 2 份 PDF、A 侧 17 个交付文件、生成器 40 个文件、B 侧提示词均已读取并记录摘要 | `B_preflight.json` |
| §0 隔离环境 + 摘要重录 + 跳环境复现 | passed | 3.13.14 + 15 条精确锁；对 A 封存 P1 前 3 配方 ×2 重复共 6 条谱：期望计数最大绝对差 **0.0**、观测计数与 A 逐位相同、`blind_inputs` 字节相同 | `B_environment.json`、`work/B_source_verification.json`、`B_environment_crosscheck.json` |
| §1 1,500 条富铁氧化物配方 | passed | 900/300/300；两套去重哈希均 1,500 唯一；`Fe2O3T` ∈ [40,75] 全 1,500 行通过；闭合最大绝对误差 1.42e-14 百分点 | `B_samples.json`、`B_formula_registry.csv`、`B_coverage.json`、`B_design_basis.md` |
| §1 零量/低量 ≥50 覆盖 | passed | 31 个适用元素最小 zero = 66（Al）、最小 low = 66（Ca）；`shortfall_counts` 全空 | `B_coverage.json` |
| §2 P3/P4 候选条件 | passed | 每个候选 34 字段全量；P3 相对 A P1 改 6 个字段、P4 改 8 个；`calibration_status=assumed_unverified` | `P3_candidate.json`、`P4_candidate.json`、`B_profile_diff.json` |
| §2 `app.py support` + 逐元素结论 | passed | 3 次 support 运行（P3、P4、A P1 参照）全部退出码 0，逐元素结论 420 行 | `work/runs/run_02/profile_support/*.log`、`B_profile_review.md` |
| §3 100 条 B 配方确定性选择 | passed | 40 常规 + 20 稀疏/边界 + 8 个完整 5 条家族（4×As/Pb、4×S/Pb）= 100；选择种子 2026101823 | `B_pilot_samples.json`、`B_pilot_selection.json`、`B_pilot_family_exposure.csv` |
| §3 `pilot_P3_v1` 生成 | passed | 200 谱、退出码 0、种子 2026101825、无 `--jitter`、`--closure strict`、`--legacy-al reject`、32 目标、`--split-seed 20261018` | `work/pilot_reports/pilot_P3_v1/generate_P3.log` |
| §3 `pilot_P3_v1` 验收 | passed | 200/200 通过，100 对重复全部满足“期望谱相同、仅计数噪声不同”；窗口损失 0.061 %–0.106 %，超自设 1 % 预算者 **0** 条 | `work/pilot_reports/pilot_P3_v1/verification_v4.json` |
| §3 `pilot_P4_v1` 生成 | passed | 200 谱、退出码 0、种子 2026101826 | `work/pilot_reports/pilot_P4_v1/generate_P4.log` |
| §3 `pilot_P4_v1` 验收 | **failed → blocked** | 完整性检查全部通过；但窗口损失 0.611 %–1.440 %，**70/200 超出自设 1 % 预算**，B 不事后放宽先declared阈值 | `work/pilot_reports/pilot_P4_v1/verification_v3.json` |
| §3 audit / 全量 replay / pack | passed ×2 | audit 退出码 0 且在密封目录外；replay 无 `--limit`、用批内密封 `app.py`、重算 200 谱、`same_environment=true`、最大数组差 **0.0**；pack 各 450 成员、CRC 通过 | `work/pilot_reports/*/audit.json`、`*/replay.json`、`pilot_P*_v1_pack.zip.sha256` |
| §4 M1 状态 | **blocked** | 记录状态 `M1_pending_profile`；只做 `make_plan` 干跑（300 job），未生成任何谱 | `B_M1_status.json`、`work/prepare_B_M1.py` |
| prompt 02 正式 20,000 条 | blocked | 缺 5 项输入（冻结 P3/P4、5,000 主表、亲缘索引、M3 结果、墙钟预算授权） | `B_delivery_status.json` |
| §5 本 README | passed | 本文件；逐字保留原提示词打包说明见附录 A | `B_delivery_hashes.json` |

---

## 1. §0 实际读取与清点

### 1.1 读过的东西

- 两份 PDF 已用 `pdftotext -enc UTF-8 -layout` 抽取为 UTF-8 文本并作为唯一依据：`work/refs/三人训练集产生方案_v1.0.txt`、`work/refs/X射线模拟训练集数据产生要求_v1.0.txt`。PDF 本体摘要：`0be750b96d85558b…`（338,478 B）、`4a3adc44cf38d23d…`（483,939 B）。
- A 侧已读证据：`README.md`、`A_acceptance_summary.json`、`A_coverage.json`、`A_formula_registry.csv`、`A_samples.json`（2,500 条主表）、`build_A.py`、`P1.json`、`P2.json`、`A_pilot_samples.json`、`check_pilot.py`、`production_record.json`、`environment_preflight.json`、`A_delivery_hashes.json`、`P1_pack.zip`、`P2_pack.zip`、`P1_replay.json`、`P1_replay_environment.json`。
- 提示词卡：`01_B_design_and_pilot_prompt.md`（`c0c99e1e…`，11,402 B）、`02_B_formal_production_prompt.md`（`f3fb6d89…`，8,686 B）、`03_prompt_review.md`（见 §1.2）、原 `README.md`（`f60eaa9e…`，800 B）。

### 1.2 输入清点里必须报告的一件事：`03_prompt_review.md` 在 M0 之后消失

`B_preflight.json`（写入时刻 18:07）逐文件清点时，`datasets/B-part/03_prompt_review.md` **确实存在**：SHA-256 `1f0c448de167d9a9fb55eb2acbfa56c09f075fda7963ac99ebcf1b3a86bb8514`、6,265 字节，同批次其余文件（含 800 字节的 `README.md`）现在复核仍逐字节一致。撰写本 README 时（19:46 之后），该文件在整个工作区已不存在：`find` 无任何同名文件，只有 B 自己的三处引用（`B_preflight.json`、原 `README.md`、`work/record_environment_and_preflight.py`）仍提到它。

- B 未删除、未改动提示词包中的任何文件，这是卡片红线；NTFS 目录时间戳被后续写入覆盖，无法据此定位删除时刻，故只报告可证事实：**存在时刻 18:07、缺失时刻 ≥19:46、唯一存活证据是 M0 记录的摘要**。
- 影响评估：`03_prompt_review.md` 是覆盖性/核验记录，不是规格来源；规格来源是两份 PDF + 两张任务卡，三者均在位且摘要已核验。**B 侧任何结论都不依赖该文件的内容。** 请 A/C 核对自己手里的副本，若需要可重新出具。

### 1.3 隔离环境与源码/封存摘要核验

| 项目 | 结果 |
| --- | --- |
| 解释器 | `datasets/B-part/work/venv313/Scripts/python.exe`，CPython 3.13.14（A 记录的是 3.12.14，本机不存在，见 `B_environment_crosscheck.json`） |
| 依赖 | 按 `fp_competition/requirements-lock.txt` 精确安装 15 条 pin，`mismatches = {}` |
| 线程 | `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1` |
| 源码核验 | 本地 40 文件 vs A 密封 35 文件，逐文件比较 35 项，**摘要不一致 0 项**；`app.py = 6f515db4d5f9d26a…`、`core.py = e820ecdb5ed5fbce…` 与 P1/P2 两个 ZIP 内副本一致；`physics_baseline.json` 声明的 3 个物理文件逐一匹配 |
| 仅本地存在（未密封） | `docs/X射线模拟训练集数据产生要求_v1.0.pdf`、`docs/训练集数据产生要求.md`、`generator-tests.log`、`samples_template.csv`、`validation_record.json`（不影响生成路径） |
| 跳环境复现 | 用 A 的密封 profile + A 自己前 3 条配方 + A 的批种子/重复数/切分种子/闭合策略重算 6 条谱：期望计数最大绝对差 0.0、六分量逐位相同、观测计数与 A 完全相同、`blind_inputs` 字节相同；耗时 30.064 s（5.011 s/谱）。该批次只作环境复现证明，不计入 50,000 预算 |

---

## 2. §1 1,500 条富铁氧化物配方：实际数量、覆盖与缺口

### 2.1 数量与唯一性

| 指标 | 声明值 | 实际值 |
| --- | --- | --- |
| 总数 / 常规 / 稀疏边界 / 干扰 | 1,500 / 900 / 300 / 300 | **1,500 / 900 / 300 / 300** |
| 按 A 规则哈希去重 | 1,500 唯一 | 1,500 唯一 |
| 按统一 12 位小数 33 元素向量去重 | 1,500 唯一 | 1,500 唯一 |
| 闭合（严格，元素和=100） | 误差 ≤ 1e-6 百分点 | 最大绝对误差 **1.4210854715202004e-14** |
| 富铁判据（先声明的数值口径） | `Fe2O3T` ∈ [40,75] 且 Fe 严格大于其他任一靶元素 | 1,500/1,500 行通过；`Fe2O3T` 实测 40.0–75.0，Fe 27.977–52.458，脉石 25.0–60.0 |
| 与 A 主表（2,500 条）重复 | 0 | **0**（两套哈希均为 0）；`formula_id` 冲突 0、`parent_family` 冲突 0；最近邻距离在 0.05/0.10/0.50/1.00/5.00 百分点阈值下均为 0 对（矩阵分离：B 全部是富铁氧化物） |
| 区块构造违规 | 0 | 0（`routine` 900、`sparse_exact_zero` 132、`sparse_low` 132、`declared_maximum_spike` 31、`boundary` 5、`interference_control` 300） |
| 种子 | 设计 2026101820；`design-mineral` 池 2026101821（1,000 条矿物配方） | 同 |

32 个靶元素固定为 `Na Mg Al Si P S Cl K Ca Ti V Cr Mn Fe Co Ni Cu Zn As Se Rb Sr Y Zr Nb Mo Cd Sn Sb Ba W Pb`。S 由 `CaSO4` 引入，因此 B 在 `provenance.design_detail.sulfur_note` 中把 150 行 S/Pb 对照显式记为“Ca 与 O 随之共变，不是严格的单变量 S 对照”，未把它伪装成单变量。

### 2.2 零量 / 低量覆盖（先声明的判据：每适用元素 ≥50 条独立配方）

- 适用元素 31 个（32 靶元素去掉 Fe）；`Fe` 与 `O` 豁免：Fe 是本设计的强制矩阵元素，O 是化学计量记账而非本模型版本的荧光靶元素。
- 实测：**最小 zero 计数 66（Al）、最小 low 计数 66（Ca）**，两者均 ≥50；`B_coverage.json` 中不存在 zero 或 low 短板的元素（`elements_below_50_in_zero_or_low = []`）。
- 低量档定义为 `0 < 质量分数 ≤ 0.1 %`，是**报告用的分箱约定，不是检出限，也不是对真实样品的判定**。
- 缺口（`B_coverage.json` 的 `gaps`，13 个元素：As、Cd、Co、Cu、Mo、Nb、Ni、Rb、Sb、Se、Sn、W、Y）：全部为 `band_definition_degenerate = true` 且 `shortfall_counts = {}`。算术原因逐条写明：这些元素声明最大值的一半（如 Co 0.15/2 = 0.075、Ni/Cu/As 0.2/2 = 0.1）≤ 低量档上限 0.1，因此“中量档”在定义上为空，凡高于低量档即落入高量档。**B 没有为凑数填充配方**，也没有把空档解释成覆盖成功。

### 2.3 家族与近邻规则

- 近邻判据（先声明）：统一 33 元素向量上逐元素绝对差的最大值（L∞）≤ **0.10 百分点**即判为近邻，用 union-find 传递合并到同一 `parent_family`，标签取最小者。
- 结果：家族总数 1,120；规模直方图 `{1:945, 2:110, 3:2, 4:1, 5:61, 20:1}`；跳家族近邻对 39 对（全部为 sparse_boundary 之间），其中 B-S0110 因传递合并成 20 行链。传递合并只会让全局亲缘切分更保守，**不会把一组构造出来的对照拆到不同折**。
- 干扰配方（卡片要求 60 母家族 × 5 完整对照，As/Pb 与 S/Pb 各 30 家族）：实测 **60 个家族、全部规模 5**，`As/Pb` 30 个 + `S/Pb` 30 个；五类对照各 60 行，倍率组合为 `(0,0) 双零`、`(1,0) 仅前者`、`(0,1) 仅 Pb`、`(1,1) 共同低量`、`(10,1) 不同含量比`，同一母家族共用氧化物背景，由 `Fe2O3T` 重新闭合质量。

---

## 3. §2 P3 / P4 候选条件

### 3.1 字段差异（34 字段全量写入，逐字段附单位与理由见 `B_profile_diff.json` → `per_field_diff`）

| 字段 | 单位 | A P1 | B P3 候选 | B P4 候选 |
| --- | --- | --- | --- | --- |
| `name` | 标签 | `assumed_P1_reference` | `candidate_B_P3_low_voltage_L_systems` | `candidate_B_P4_hard_filter_long_air_path` |
| `voltage_kV` | kV | 49.0 | **20.0** | 49.0（保持） |
| `live_time_s` | s | 150.0 | **60.0** | **60.0** |
| `gain_keV_channel` | keV/道 | 0.0138393 | **0.008** | **0.0125** |
| `zero_keV` | keV | 0.6133929 | **0.3** | **0.45** |
| `noise_fwhm_eV` | eV | 55.0 | **90.0** | **140.0** |
| `filter_Al_um` | µm | 0.0 | 0.0 | **100.0** |
| `incident_air_path_cm` / `exit_air_path_cm` | cm | 0.0 / 0.0 | 0.0 / 0.0 | **4.0 / 4.0** |

- 改动字段数：P3 相对 A P1 **6** 个，P4 **8** 个；P3 与 P4 之间差异 8 个字段。两者共用同一入射通量 6.0e8 光子（`incident_photons_s=1.0e7` × `live_time_s=60`），以便比较只反映条件差异。
- 能量窗（交付工具由 profile 推导，不可手工指定）：P3 = **0.296–16.680 keV**，P4 = **0.4438–26.0438 keV**（各 2048 道）。
- `calibration_status` 两个候选均为 `assumed_unverified`：**没有仪器标定，任何“可测/准确度 5 %”之类结论都不成立**。
- 计数水平预检：第一次探测（`work/runs/run_01`）用的是 P3 `live_time_s=240`、P4 `3e7 × 300 s`，实测单谱总计数落在 A 记录 P1 区间的 3–29 倍，于是重定为统一 6.0e8 通量（`work/runs/run_02`）。`run_01` 作为决策证据保留，未被覆盖（交付 CLI 不允许复用 `--out`）。

### 3.2 `support` 运行与逐元素结论（`B_profile_review.md`）

| profile | 退出码 | 元素数 | 状态分布 | 记录到的线系 |
| --- | --- | --- | --- | --- |
| P3 候选 | 0 | 32 | `structurally_supported_unvalidated` 32 | K 25 / L 17 / M 3 可记录线系 |
| P4 候选 | 0 | 32 | `structurally_supported_unvalidated` 29、`strongly_attenuated_assumed_response` 3 | 同表见 `B_profile_support_summary.json` |
| A P1 参照 | 0 | 32 | `structurally_supported_unvalidated` 32 | — |

结论分层（卡片要求的四层区分，B 全程照此表述）：**谱线在窗口内存在 ≠ 可分辨 ≠ 可检出 ≠ 达到 5 % 准确度**。Ba 的 K 系在两个候选下都不在窗口内，但 L 系与 M 系中心均落在窗口内（试产批次 134 条含 Ba 的谱中，L/M 中心在窗者各 134 条），故“K 系出窗”继不等于“Ba 不可测”。

### 3.3 摘要勘误（诚实记录，不改历史报告）

`B_profile_diff.json` 与 `B_pilot_selection.json` 早期记录的“文件 SHA-256”是对**换行归一化后的字符串**求哈希，而 Windows 文本模式写出的文件带 CRLF，因此任何工具对交付字节求哈希都得不到该值。`work/verify_B_candidate_hashes.py` 已出具重核记录 `work/B_candidate_hash_reverification.json`：

| 文件 | 交付字节 SHA-256（跳检查以此刻为准） | 换行归一化文本 SHA-256（§2 早期记录值） | 34 字段规范向量 SHA-256（值身份证明） |
| --- | --- | --- | --- |
| `P3_candidate.json`（987 B，36 处 CRLF） | `5bb3aeb948145c58…f1ac6c` | `4b533155c69ccc1a…39a69f` | `0a0b5e0276b7e0d0…37ea42` |
| `P4_candidate.json`（996 B，36 处 CRLF） | `e62cec80bbead625…8618f7ef3a`（见 `B_delivery_hashes.json`） | `5e696944ba972d68…abd1f32` | `197182623607a1fd…6482a0` |

- 物理后果：**无**。密封批次内的 `configs/profile.json`、`inputs/original_profile.json` 与候选文件逐字节相同，`profile_sha256` 台账值 = 交付字节值 = `5bb3aeb9…` / `e62cec80…`，规范向量哈希不变 ⇒ 解析后的 34 个值从未改变，没有任何谱是用不同参数生成的。
- 处置：原始 §2 报告**未改写**；`B_profile_review.md` §2.9 增加勘误段并给出跳检查应采用的值；`work/build_B_profiles.py`、`work/select_B_pilot.py`、`work/render_B_profile_tables.py` 已改为按交付字节求哈希并以 LF 写出，正式生产阶段不会再产生这一歧义。

---

## 4. §3 试产：100 条配方 × 2 条件 × 2 重复 = 400 条谱

### 4.1 配方选择（确定性，种子 2026101823）

100 条 = 常规 40 + 跳密/边界 20（精确零 7、低量 7、声明最大值尖峰 3、边界 3）+ 干扰 40（`As/Pb` 家族 B-I0000/B-I0015/B-I0016/B-I0020，`S/Pb` 家族 B-I0031/B-I0041/B-I0050/B-I0057，每族完整 5 条对照）。两个条件使用**同一个** `B_pilot_samples.json`（807,612 B，`ed3c26bc…`）。

已暴露给试产的 **68 个母家族**列在 `B_pilot_family_exposure.csv`，每行 `blind_test_use_forbidden=yes`，供 C 在做全局亲缘划分时永久排除出盲测折。

### 4.2 命令与退出码（逐条；`<PY>` = `datasets/B-part/work/venv313/Scripts/python.exe`，均带 §1.3 的四项线程前缀）

| 阶段 | 命令 | 退出码 | 落盘证据 |
| --- | --- | --- | --- |
| §0 | `<PY> -B work/verify_generator_source.py` | 0（会话内观察；stdout 落盘） | `work/B_source_verification.json` |
| §0 | `python -m venv work/venv313` + `pip install -r requirements-lock.txt` | 0（会话内观察） | `B_environment.json` |
| §0 | `<PY> -B work/check_environment_reproducibility.py` | 0；内部 CLI 调用 `exit_code: 0` | `B_environment_crosscheck.json`、`work/envcheck/batch_command.log` |
| §0 | `<PY> -B work/record_environment_and_preflight.py` | 0 | `B_preflight.json` |
| §1 | `<PY> -B app.py design-mineral --ranges <abs>/B_design_ranges.json --count 1000 --out work/B_design_mineral_pool.json --seed 2026101821` | **0（`exit_code: 0` 落盘）** | `work/design_mineral_cli.log` |
| §1 | `<PY> -B build_B.py` | 0（日志只存 JSON 摘要，退出码为会话内观察） | `work/build_B_run.log`、`work/B_recipe_checks.json` |
| §2 | `<PY> -B work/build_B_profiles.py` | 0 | `B_profile_diff.json` |
| §2 | `app.py support --profile P3_candidate.json …`（run_01，`--out` 已存在） | **2**（交付 CLI 拒绝覆盖，随后改用新目录） | `work/runs/run_01/profile_support/B_profile_support_P3.log` |
| §2 | `app.py support`（P1 参照、P4，run_01） | 0 / 0 | 同目录对应 `.log` |
| §2 | `app.py batch`（P3/P4 计数预检，run_01 与 run_02） | 0 ×4 | `work/runs/run_0*/profile_probe/batch_probe_P*.log` |
| §2 | `app.py support`（P1 参照、P3、P4，run_02 最终值） | 0 ×3 | `work/runs/run_02/profile_support/*.log` |
| §2 | `<PY> -B work/summarize_B_profile_support.py`、`work/B_interference_pair_check.py`、`work/render_B_profile_tables.py` | 0 ×3 | `B_profile_support_summary.json`、`B_profile_pair_check.json`、`work/B_profile_review_tables.md` |
| §3 勘误 | `<PY> -B work/verify_B_candidate_hashes.py` | 0 | `work/B_candidate_hash_reverification.json` |
| §3 | `<PY> -B work/select_B_pilot.py` | 0 | `B_pilot_selection.json` |
| §3 | 验收脚本自测（6 条探测批喂给同一验收器） | 0，报告 `status=failed`（证明不合格批次确实会被判失败） | `work/pilot_ledger_selftest.json` |
| §3 | `app.py batch … --out pilot_P3_v1 --seed 2026101825 --replicates 2 --split-seed 20261018 --closure strict --legacy-al reject --targets <32> --design-ranges B_design_ranges.json` | **0** | `work/pilot_reports/pilot_P3_v1/generate_P3.log` |
| §3 | 同上，`--out pilot_P4_v1 --seed 2026101826` | **0** | `work/pilot_reports/pilot_P4_v1/generate_P4.log` |
| §3 | `<PY> -B work/run_B_pilot.py verify`（P3 v1→v4、P4 v1→v3） | 0（脚本把判定写进报告 `status`） | `verification*.json` |
| §3 | `app.py audit`（报告写在密封目录**外**） | **0** ×2 | `work/pilot_reports/*/audit.log`、`audit.json` |
| §3 | 用批内密封 `app.py replay`（无 `--limit`） | **0** ×2 | `work/pilot_reports/*/replay.log`、`replay.json` |
| §3 | `app.py pack` + 外部 ZIP SHA-256 + CRC 校验 | **0** ×2 | `*/pilot_P*_v1_pack.log`、`pilot_P*_v1_pack.zip.sha256`、`work/ledger/*.json` |
| §4 | `<PY> -B work/prepare_B_M1.py`（只干跑规划，不出谱） | 0 | `B_M1_status.json` |
| §5 | `<PY> -B work/write_B_delivery_status.py` | 0 | `B_delivery_status.json`、`B_delivery_hashes.json` |

种子登记（互不冲突，正式生成的 2026101803/04 **未**用于试产）：A 试产 2026101801/02；B 设计 2026101820、矿物池 2026101821、§2 预检 2026101822、选择 2026101823、试产 P3 2026101825、P4 2026101826；M1 建议（待 A 确认）2026101827；切分种子统一 20261018。

### 4.3 验收结果（两批各 200 谱）

| 检查项 | pilot_P3_v1 | pilot_P4_v1 |
| --- | --- | --- |
| 重复对身份（同配方两谱：组分/ profile / 能量轴 / 完整期望谱 / 六分量期望谱相同，仅计数噪声不同；种子互异） | 100/100 通过，期望谱最大绝对差 **0.0**；单道观测最大差 680 | 100/100 通过，期望谱最大绝对差 **0.0**；单道观测最大差 787 |
| 观测总计数区间 | 502,503 – 682,510 | 476,844 – 857,364（A 的 P1 记录区间 270,981 – 823,275） |
| 六分量恒等式（`Σcomponents = Σexpected_counts`；`Σcomponents + Σoutside = detected_signal_before_window_counts`，相对容差 1e-6） | 200/200 成立 | 200/200 成立 |
| profile / 能量窗与候选文件一致（逐字段、逐边界） | 200/200 一致 | 200/200 一致 |
| `element_support` 与交付规则一致（`original_percent − {Als, Alt} ∪ 实际用量>0 的键`；唯一非靶键 O，200/200） | 200/200 一致；靶元素覆盖直方图 `{32:146, 31:40, 23:14}` | 同 |
| 窗口外损失占比 | 0.061 % – 0.106 %（均值 0.079 %），超预算 0 条 | 0.611 % – 1.440 %（均值 0.924 %），**超预算 70 条** |
| 完整性问题清单 | `[]` | `[]` |
| 报告 `status` | `passed` | `failed`（唯一问题即预算超限） |
| audit（密封目录外，完整性+合成流） | `passed`，200 谱，`errors=[]`，`complete_physics_recalculation=false` | 同 |
| replay（批内 `app.py`，`limit=null`） | `passed`、`scope=all_records`、重算 200 谱、`complete_physics_recalculation=true`、`same_environment=true`、最大数组差 **0.0** | 同 |
| pack | 450 成员，CRC 通过，ZIP SHA-256 `50c82cc4e1365ac1…ea4467f`（40.3 MB） | 450 成员，CRC 通过，ZIP SHA-256 `d585a87fb08e27c1…b2502077e2`（44.0 MB） |

干扰线系实测（期望净探测计数，几何因子 11,268,379.6；“建模且落在窗内”的谱数）：

| 线 | P3 | P4 | 读法 |
| --- | --- | --- | --- |
| As `KL3_LINE`（As/Pb 组，24 谱） | 782.63 | 3,199.95 | 两条件下均有可用计数 |
| Pb `L3M5_LINE`（24 谱） | 31.10 | 193.83 | 弱；P4 改善 6 倍但仍是痕量级 |
| Pb `M5N6_LINE`（24 谱） | 1.32 | **0.05** | 基本不可用，M 系在 P4 下几乎消失 |
| S `KL3_LINE`（As/Pb 组 40 谱） | 1,170.56 | **15.66** | P4 的 100 µm Al + 8 cm 空气路径把 S Kα 压到连 B 自设的“≥400 计数”必要条件都不满足 |
| Fe `KL3_LINE`（40 谱） | 332,307.19 | 414,786.79 | 基体强线，As Kα(10.54 keV)/S Kα(2.31 keV) 与 Pb M 系的逃逸/和峰干扰需按 `B_profile_review.md` §2.6 逐条判读 |

**结论交给 A/C**：P3 能同时保住 S Kα 与 As Kα；P4 换取了 Pb L 系与更高能量覆盖，代价是 S 与 Pb-M 在该曝光预算下不可用。这是先声明阈值下的**权衡事实**，不是脚本错误。

### 4.4 P4 未通过自设预算（不做“事后放宽”）

窗口损失 70/200 超 1 %，被丢弃计数的成分占比：**Compton 72.91 %、Rayleigh 23.85 %、初级 2.46 %、逃逸 0.79 %、次级荧光 0.00 %**。损失侧归因是结构性证据，不是猜测：交付模型的源网格从 1 keV 起（密封 manifest 的 2 条 warning 之一），下边界 0.4438 keV 不构成损失来源；因此被丢弃的是 **26.0438 keV 上边界以上**的高能连续谱及其 Rayleigh/Compton 尾（90° 康普顿阈值 27.44 keV，P3 为 17.24 keV）。这是候选条件的属性，与配方、与求解器无关。

阈值是跑之前声明的（`declared_checks.window_loss_budget`），所以 B **不改阈值**，把失败留在报告里，并把决定权提交为 §2.8 的第 4 项冻结决策：(a) 接受实测损失并把预算正式改成 2 %，或 (b) 重排窗口/增益后重做整条试产验收。若联合冻结的 P4 与候选值不同，`pilot_P4_v1` 的验收结论不作数（卡片要求，已写入台账 `purpose_note`）。

### 4.5 本阶段四次自我修正（全部保留原始报告，不覆盖）

1. **P3 验收器过严误判**：`verification.json` 报 54 条“support 缺少靶元素”，原因是我假定每条谱都应覆盖全部 32 靶元素。按交付实现 `core.py:406` 的真实规则（逐配方 `original_percent − {Als, Alt} ∪ 用量>0 的键`）改写后，60/60 抽查逐条复现，v2/v3/v4 均为 `passed`。
2. **P4 验收器漏判**：`verification.json` 曾报 `passed`，因为它声明了 1 % 预算却没把超预算写进 `problems`。修正后 v2/v3 如实 `failed`，并补充成分占比与损失侧结构证明。
3. **摘要勘误**：CRLF/LF 导致的“文件哈希≠记录值”，见 §3.3。
4. **`--out` 复用被拒**：run_01 的 P3 `support` 退出码 2（“Output directory already exists”），改为按 run 版本化输出目录，`run_01` 作为重定通量决策的证据保留；探测批 `work/runs/probe_pilot_v1` 同样保留，6 条谱仅用于验证验收器会正确判失败。

### 4.6 正式生产规划数字（供墙钟预算决策，非承诺）

由 `full_results` 写入时间跳度实测（单线程 pin）：P3 200 谱 17.9 分钟 = **5.37 s/谱**，20,000 条单线程约 **29.8 小时**；P4 200 谱 13.5 分钟 = **4.05 s/谱**，约 **22.5 小时**；A 侧环境复现参照 5.011 s/谱。两批试产共 400 谱标记 `workflow_pilot_only`，**不计入** 20,000 / 50,000 预算。

---

## 5. §4 M1 状态：`M1_pending_profile`（blocked）

M1 = A 给 100 条配方、B 每条生成 3 谱（300 条新谱）、C 主审、A 复核。它与 §3 的 400 条 B 试产谱、与 A 自己的 P1/P2 试产谱是**不同的任务，不能互相替代**（`A_production_record.json` 也把 A 试产标为 `workflow_pilot_only`、`independent_person_review=pending`）。

- 已核查磁盘证据：`A_pilot_samples.json`（100 条配方，`687df28e…`；语义哈希 `9dd151ae…`）存在；A 的方案 §5 M1 行只规定了分工与 300 规模，**没有规定 profile、种子或输出目录**；工作区里不存在任何 A 冻结的 M1 条件，也不存在 C 的主审记录。
- 因此 B **未生成任何 M1 谱**，也没有把 P3/P4 候选猜成 M1 条件（`B_M1_status.json.not_guessed` 四项全 false）。
- 就维性只用交付的 `dataset.make_plan()` 干跑证明：以 A 的 100 条配方 + `--replicates 3`，在 P1 与 P2 两种 profile 下均得 300 job、100 家族、300 个互异种子、切分 210/45/45、每条配方重复 0/1/2 各 100 次，profile 由交付规划器校验通过。
- 待 A 冻结后建议：样本 `A_pilot_samples.json`、种子 `2026101827`（与已登记种子无冲突，需 A 确认）、`--replicates 3 --split-seed 20261018 --closure strict --legacy-al reject`、**不传 `--jitter`**、输出到新目录 `datasets/B-part/M1_<condition>_v1`；随后 audit（写在密封目录外）→ 批内 `app.py` 全量 replay（无 `--limit`）→ pack + 外部 ZIP SHA-256 + CRC → 交 C 主审、A 复核。
- 阻塞项 3 条：A 冻结的 M1 条件（profile 文件 + 哈希）、C 的 M1 主审指派、确认 A 的 100 条试产文件即 M1 输入（或有更新版本）。

---

## 6. 交给 A / C 的文件

| 收件人 | 文件 | 用途 |
| --- | --- | --- |
| A（跳叉复核） | `pilot_P3_v1_pack.zip` + `.sha256`、`pilot_P4_v1_pack.zip` + `.sha256` | 400 条试产谱的可搬运封装；批内含 `reproducibility/`，A 可用同一环境 replay |
| A | `work/pilot_reports/pilot_P*_v1/verification_v*.json`、`audit.json`、`replay.json` | 逐条验收证据（含 P4 的失败判定） |
| A、C | `P3_candidate.json`、`P4_candidate.json`、`B_profile_diff.json`、`B_profile_review.md`、`work/B_profile_review_tables.md` | 联合冻结所需的 34 字段全量、逐字段理由与单位、逐元素结论、§2.8 的 4 项待决 |
| A | `B_samples.json`、`B_formula_registry.csv`、`B_coverage.json`、`B_design_basis.md`、`B_design_ranges.json`、`build_B.py`、`B_cross_A_overlap.json` | 1,500 条配方、家族与近邻规则、与 A 主表的 0 重复证明 |
| C（亲缘划分） | `B_pilot_family_exposure.csv`（68 行，`blind_test_use_forbidden=yes`）、`B_pilot_samples.json`、`B_pilot_selection.json` | 已暴露家族必须永久排除出盲测折 |
| C | `B_M1_status.json`、`work/pilot_ledger.json`、`work/ledger/pilot_P*_v1.json` | M1 就维性与逐阶段命令/退出码台账 |
| A、C | `B_environment.json`、`B_environment_crosscheck.json`、`B_preflight.json`、`work/B_source_verification.json`、`work/B_candidate_hash_reverification.json` | 环境一致性（含 3.12.14 缺失的实测替代）与摘要勘误 |
| A、C | `B_delivery_status.json`、`B_delivery_hashes.json` | 机器可读的逐项状态与全部产物摘要 |

## 7. 未完成的冻结依赖（B 不能自行推进的 5 件事）

1. **P3/P4 联合冻结**：候选不是最终条件；若冻结值与候选不同，试产验收必须对新条件重做（含 §4.4 的窗口损失决策与 §2.8 四项）。
2. **5,000 条主表（含 C 的 1,000 条）**：B 只有自己的 1,500 条，无法验证总量与配比。
3. **权威亲缘/全局切分索引**（`authoritative_index.csv` / `global_split.csv` 不存在）：B 未给任何配方贴上 train/validation/test 标签，批内 manifest 的 70/15/15 切分是工具自带的、非亲缘感知的近似切分，不能当作团队索引。
4. **A 对 B 的跳叉复核**、**C 对两批试产的主审**：本交付只是单人自检。
5. **M1 条件与墙钟预算授权**：见 §5 与 §4.6。

## 8. 复现要点

```
# 统一前缀与解释器（所有 Python 步骤）
cd "C:/Users/Lenovo/Desktop/兴智杯AI开发大赛"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PY="datasets/B-part/work/venv313/Scripts/python.exe"

# 配方与产物（幂等，输出摘要哈希）
"$PY" -B datasets/B-part/build_B.py
"$PY" -B datasets/B-part/work/build_B_profiles.py
"$PY" -B datasets/B-part/work/summarize_B_profile_support.py
"$PY" -B datasets/B-part/work/render_B_profile_tables.py
"$PY" -B datasets/B-part/work/verify_B_candidate_hashes.py
"$PY" -B datasets/B-part/work/select_B_pilot.py
"$PY" -B datasets/B-part/work/write_B_delivery_status.py

# 生成/验收（必须换新的 --out 目录，CLI 拒绍覆盖）
cd fp-spectrum-generator-competition-v0.2.1/fp_competition
"$PY" -B app.py batch --samples <abs>/B_pilot_samples.json --profile <abs>/P3_candidate.json \
  --out <abs>/pilot_P3_v2 --seed <新种子> --replicates 2 --split-seed 20261018 \
  --closure strict --legacy-al reject --targets Na Mg Al Si P S Cl K Ca Ti V Cr Mn Fe Co Ni Cu Zn \
  As Se Rb Sr Y Zr Nb Mo Cd Sn Sb Ba W Pb --design-ranges <abs>/B_design_ranges.json
```

完整命令原文与逐阶段退出码见 `work/pilot_ledger.json` 与 `work/ledger/pilot_P*_v1.json`；ZIP 完整性可用 `certutil -hashfile pilot_P3_v1_pack.zip SHA256` 与 sidecar 比对，并用 `python -m zipfile -t` 复验 CRC。

## 9. 哈希

全部声明产物（配方、候选、profile 支持、试产谱、日志、脚本、ZIP sidecar，含退出码证据日志）的 SHA-256 见 **`B_delivery_hashes.json`**；该文件由 `work/write_B_delivery_status.py` 在本 README 写完后最后运行，因此包含本 README 自身的摘要，`declared_but_missing = []`。密封批次目录的完整性由批内 `integrity.json` + 外部 ZIP 摘要双重覆盖。

---

## 附录 A：交付目录原有的提示词打包说明（逐字保留）

以下为本目录交付前 `README.md`（800 字节，SHA-256 `f60eaa9e4cb222c6c56ff111f03b07e699ba885ab6665ccbd326985c77292876`）的原文，未作任何改动；代码块内容 + 结尾换行已用哈希复核为**逐字节相同**，同一段字节另存为 `work/README_prompt_packaging_original.md`。交付时该原文就是 `README.md` 的全部内容，本次交付把它逐字保留在此附录中，B 的交付说明写在前面各节。原文最后一句“当前目录只有提示词和审查记录，不代表 B 数据或试产谱已生成”在**当时是正确的告警**，现已被本文件的 §2/§3/§4 实测结果取代（1,500 条配方与 400 条试产谱均已生成并验收，其中 P4 验收未通过自设预算）；原文中的 `03_prompt_review.md` 蓡见 §1.2 的消失事件。

```
# 成员 B：交给执行 Agent 的任务提示词

1. 先发送 `01_B_design_and_pilot_prompt.md`：直接使用工作区 `fp-spectrum-generator-competition-v0.2.1/fp_competition/app.py`，完成 1,500 条 B 配方、P3/P4 候选条件，并先生成/验收 400 条 B 配方试产谱；同时核查三人方案 M1 状态。
2. 待 A/C 冻结 5,000 条主表、P3/P4 最终配置、亲缘划分与索引规则，再发送 `02_B_formal_production_prompt.md`：先过门禁与 M3，随后正式生成 P3/P4 共 20,000 条谱，交 A 跳叉复核；之后按冻结条件复核 C 的 P5。
3. `03_prompt_review.md` 记录覆盖性、本地生成器与 A 封存版本的逐文件核验，以及当前阻塞条件。

当前目录只有提示词和审查记录，不代表 B 数据或试产谱已生成。
```
