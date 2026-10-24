# 第三轮成员 B：全量生产交付

状态：**成员 B 的 1,746 条谱已在本地完成全量生成与自检，等待 owner 统一复核。** 生产放行不等于数据审查通过；`training_inclusion_approved` 仍为 `false`。

## 数量

| 项目 | 数量 |
| --- | --- |
| 候选配方 | 250（硅酸盐/氧化物 150、富铁氧化物 100） |
| 设计族（合并前） | 105 |
| 基础谱 | 1,500（其中 pilot 批次 90 条计入基础谱） |
| 追加 T 挑战谱 | 246（41 个留出配方 × 6 谱） |
| 合计 | 1,746 |
| 原生密封批次 | 50 |

## 执行

冻结依据为已合并 PR #31 的 `owner_release_v3`，配方/族用途/profile/噪声种子/物理核心全部按 `freeze_v1`，未自选家族、未换种子、未加 jitter。

```powershell
# 干净工作树上的官方全量入口（不做续跑判定，已完成的批次会因目录存在而失败）
powershell -NoProfile -File datasets/round3/shared/production_tools/run_member_full.ps1 -Member B -Python python

# 本次交付实际使用的驱动：跳过前校验完整 QC，失败以非零退出；-VerifyOnly 只判定不生成
powershell -NoProfile -File datasets/round3/member_B/run_B_production.ps1 -Member B -Python python
```

本机实际执行：`run_batch.py` 逐批调用（T 批次显式 `--heldout-qc`），每批独立 sealed/QC 目录，2–3 批并发以适配本机可用内存；批次顺序与 `batch_plan.json` 一致，已完成的冻结批次不重跑、不覆盖。

- 冻结清单：`freeze_manifest_sha256 = 4931661432f0a1e0cd4526053499509f978f86f2d59a6b0acc404c3360b85817`
- owner 放行：`owner_release_sha256 = 653bff0957d3f9d8a0a506934976aff06d36756777bb3a0095106ff302ca47b2`
- 运行器：`runner_sha256 = ece61e9afaa264f716d0fa2f34d29b422b0c65f9214de186fda6982f650c38ca`
- 物理核心：`physics_core_sha256 = e820ecdb5ed5fbceb870f382c8c7c411ba85c65673bc19258fb935f562ed83b0`

## 自检范围与结果

- audit：覆盖 1,746 条谱，全部 `passed`；
- 完整物理 replay：覆盖 1,746 条谱，最大绝对数组差 `0.0`；
- 窗外预算：50 批全部通过 `window_budget.json`；
- 归档：每个原生 ZIP 的 SHA-256 与批内 `summary.json` 一致，CRC 校验通过；
- 外置记录索引：`reports/external_record_index.csv`，1,746 行；`record_uid`（`batch_id:native_id`）全局唯一，`opaque_blind_id` 全部唯一。
- 续跑判定：`verify_batch_qc.py` 只在 summary、audit、完整 replay、窗口预算、谱数、归档 SHA-256 与 CRC、外置记录索引全部通过时才把批次当作完成；缺项的 sealed 目录会让驱动脚本以非零退出并保留证据。成功、失败、不完整 sealed 三类路径的复现记录见 `reports/resume_validation/resume_validation_summary.json`。

逐批证据在 `reports/<batch>/`，含 `audit.json`、`replay.json`、`window_budget.json`、`commands.json`（真实命令与退出码）、`summary.json`。

## 环境

- Python 3.14.7（CPython），Windows AMD64
- numpy 2.5.1、scipy 1.18.1、xraylib 4.3.0
- 生成器 0.2.1 / 物理核心 0.2.0

## 目录

```text
production_v1/            50 个原生无损 ZIP + 各自 .sha256
reports/<batch>/          逐批 audit / replay / window_budget / commands / summary
reports/external_record_index.csv   覆盖全部 1,746 条谱的外置索引
reports/resume_validation/           成功 / 失败 / 不完整 sealed 三类续跑验证证据
verify_batch_qc.py        批次完成度判定（续跑跳过与失败停止共用）
delivery_manifest.json    全部交付文件的大小与 SHA-256
selfcheck_summary.json    实际检查范围与结果
environment.json          解释器、依赖与冻结身份
```

## 边界与未决

- T 谱只用于留出物理 QC，**未**用于训练、校正拟合、响应字典或选参；`training_inclusion_approved = false`。
- 原生生成器 split 未当作研究划分；外部盲 ID 由隔离索引映射。用途统计：train 1014 条、validation 240 条、internal_holdout 492 条（其中 246 条为内部留出的基础谱，另 246 条为 T 挑战谱）。
- 合成数据的自检通过**不代表**真实设备准确度；`scientific_accuracy_verified = false`、`concentration_accuracy_verified = false`。
- 本交付不含展开后的谱目录，只含原生密封 ZIP 与其 QC 证据。
- 已冻结候选、换算/补偿账目与输入身份保持在 `candidates/`、`inputs/`，未重写。

## 批次表

| batch | phase | profile | spectra | zip sha256（前 12 位） |
| --- | --- | --- | ---: | --- |
| R3_B_base_D1_001 | base | D1 | 40 | `25823a76de19` |
| R3_B_base_D1_002 | base | D1 | 48 | `4b4cace73d29` |
| R3_B_base_D1_003 | base | D1 | 38 | `40e15bce16a6` |
| R3_B_base_D2_001 | base | D2 | 42 | `56d2c1f47a9d` |
| R3_B_base_D2_002 | base | D2 | 48 | `664879c67262` |
| R3_B_base_D2_003 | base | D2 | 34 | `01069a5ee8ba` |
| R3_B_base_D3_001 | base | D3 | 42 | `a06da31ca1b3` |
| R3_B_base_D3_002 | base | D3 | 48 | `b91a64a88fcb` |
| R3_B_base_D3_003 | base | D3 | 50 | `f42e4e4259cb` |
| R3_B_base_D3_004 | base | D3 | 10 | `4753141d7689` |
| R3_B_base_D4_001 | base | D4 | 50 | `0444f28527fe` |
| R3_B_base_D4_002 | base | D4 | 50 | `fe19a514c08c` |
| R3_B_base_D4_003 | base | D4 | 14 | `dc666f6cb0df` |
| R3_B_base_D5_001 | base | D5 | 46 | `6f02414201a2` |
| R3_B_base_D5_002 | base | D5 | 48 | `a1d7f1d7aa93` |
| R3_B_base_D5_003 | base | D5 | 50 | `d8f2e00b2d08` |
| R3_B_base_D5_004 | base | D5 | 6 | `4e505b4e8327` |
| R3_B_base_D6_001 | base | D6 | 48 | `b7f61cec7768` |
| R3_B_base_D6_002 | base | D6 | 50 | `b4dfc5ba3324` |
| R3_B_base_D6_003 | base | D6 | 14 | `c89e530a944c` |
| R3_B_base_P1_001 | base | P1 | 40 | `c92df1d4e097` |
| R3_B_base_P1_002 | base | P1 | 48 | `fb7074e333a2` |
| R3_B_base_P1_003 | base | P1 | 48 | `bad5f435cff1` |
| R3_B_base_P1_004 | base | P1 | 50 | `8701aa75b878` |
| R3_B_base_P1_005 | base | P1 | 36 | `ffdca7d255cf` |
| R3_B_base_P2_001 | base | P2 | 42 | `3ee2d53f46d6` |
| R3_B_base_P2_002 | base | P2 | 48 | `76d56abe68c8` |
| R3_B_base_P2_003 | base | P2 | 48 | `0bead240b312` |
| R3_B_base_P2_004 | base | P2 | 50 | `212a7ef63a73` |
| R3_B_base_P2_005 | base | P2 | 18 | `796073643988` |
| R3_B_base_P3_001 | base | P3 | 40 | `59ce984d0312` |
| R3_B_base_P3_002 | base | P3 | 48 | `647079df5e60` |
| R3_B_base_P3_003 | base | P3 | 48 | `77cd684b4465` |
| R3_B_base_P3_004 | base | P3 | 50 | `53b9e8a6fa9f` |
| R3_B_base_P3_005 | base | P3 | 20 | `f2c0300f7cc2` |
| R3_B_challenge_T1_001 | challenge | T1 | 50 | `0cf270152bbe` |
| R3_B_challenge_T1_002 | challenge | T1 | 32 | `ee62ac4e09c7` |
| R3_B_challenge_T2_001 | challenge | T2 | 50 | `a244913310b8` |
| R3_B_challenge_T2_002 | challenge | T2 | 32 | `5b6056a32aeb` |
| R3_B_challenge_T3_001 | challenge | T3 | 50 | `02d3140d8986` |
| R3_B_challenge_T3_002 | challenge | T3 | 32 | `4a1e7272bc4f` |
| R3_B_pilot_D1_001 | pilot | D1 | 10 | `7e6ab03f93d8` |
| R3_B_pilot_D2_001 | pilot | D2 | 4 | `6a2a1d5019c8` |
| R3_B_pilot_D3_001 | pilot | D3 | 22 | `103b99728acb` |
| R3_B_pilot_D4_001 | pilot | D4 | 4 | `b29e5fb60f35` |
| R3_B_pilot_D5_001 | pilot | D5 | 14 | `5002fe45ca36` |
| R3_B_pilot_D6_001 | pilot | D6 | 6 | `9ff9e0855818` |
| R3_B_pilot_P1_001 | pilot | P1 | 14 | `845aa51e5776` |
| R3_B_pilot_P2_001 | pilot | P2 | 6 | `1e4f0c6baf90` |
| R3_B_pilot_P3_001 | pilot | P3 | 10 | `b6c81865210e` |
