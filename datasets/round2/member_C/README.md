# 第二轮 · 成员 C 交付（v2 评审修订版）

- 成员：C（round_id = `round2`），交付版本 `C-r2-v2-20261021`
- 软件：fp_competition **0.2.1**，物理模型 **0.2.0**，xraylib **4.3.0**
- 状态：**v2 全量自检通过，待评审复核；公共输入清单待协调人签认**
- 旧版：v1（提交 `f5d721e`）的 250 配方 / 1,500 谱及其报告、ZIP 全部原样保留，未删除、未改写；本版以 `*_v2*` 文件名并列新增

本版针对 PR #15 评审的三项阻断修改：统一三条件 profile 身份、把 50 条干扰配方改为 10 个完整匹配对照组、修复 QC 失败仍可封装的脚本缺陷并补回归检查。

## 实际数量

| 项 | 数量 |
| --- | ---: |
| 独立配方 | 250（硅酸盐/氧化物 150 = 90 常规 + 30 稀疏/边界 + 30 干扰；富铁氧化物 100 = 60/20/20） |
| 谱 | 1,500（P1/P2/P3 每配方每条件 2 条独立计数噪声） |
| 母族/组标签 | 硅酸盐 35（14 常规 + 15 边界 + 6 对照），富铁 26（8 常规 + 14 边界 + 4 对照） |

组成均为元素质量百分数、保留 O 基体，strict 闭合最大误差 0.0（容差 1e-6 个百分点）；250 个 ID 与 250 个组成摘要均唯一。ppm 原始值经 `1 ppm = 1e-4 wt%` 换算，换算规则与缩放因子逐条写入 provenance。

### 完整干扰对照（50 条 = 10 组 × 5 变体）

- 硅酸盐 6 组、富铁 4 组；每组固定同一基体、同一 parent_family 与同一组内固定痕量背景（Zn/Sr/Zr/Y/Nb，成对元素从背景中剔除，避免混入对照）。
- 五个变体：`absent` / `A_only` / `B_only` / `both_1to1` / `both_5to1`（或 `both_1to5`，按干扰方向选择）；A/B 单点加入量 0.4 wt%，比例变体把主导元素加到 2.0 wt%。
- 每条配方写入 `control_group`、`control_role`、`interference_pair`、`pair_ratio`、`spike_percent`、`control_base_sha256`；`C_r2_formula_registry.csv` 同步登记。
- 自检逐组验证：五变体齐全、基体摘要一致、absent 对两元素为 0、A_only 不含 B、B_only 不含 A、实测比例与声明一致。

| 组 | 基体 | 干扰对（谱线） |
| --- | --- | --- |
| int-SIL-01-As-Pb | 硅酸盐 | As Kα 10.544 / Pb Lα 10.551 |
| int-SIL-02-P-Zr | 硅酸盐 | P Kα 2.013 / Zr Lα 2.043 |
| int-SIL-03-Ti-V | 硅酸盐 | Ti Kβ 4.932 / V Kα 4.952 |
| int-SIL-04-Cr-Mn | 硅酸盐 | Cr Kβ 5.839 / Mn Kα 5.899 |
| int-SIL-05-Se-Pb | 硅酸盐 | Se Kβ 12.598 / Pb Lβ 12.614 |
| int-SIL-06-W-Cu | 硅酸盐 | W Lα 8.397 / Cu Kβ 8.401 |
| int-FE-01-Sr-Zr | 富铁 | Sr Kβ 15.688 / Zr Kα 15.775 |
| int-FE-02-Rb-Mo | 富铁 | Rb Kα 13.395 / Mo L 系 |
| int-FE-03-Sn-Nb | 富铁 | Sn Lα 3.444 / Nb L 系 |
| int-FE-04-Ti-Ba | 富铁 | Ti Kα 4.511 / Ba Lα 4.466 |

## 输入身份

| 文件 | 名称 | SHA-256 |
| --- | --- | --- |
| 生成器 `app.py` | fp_competition 0.2.1 | `6f515db4d5f9d26af9ec261fdb60e62bf1c848b9e7b9ab3930961c8d393159c8` |
| `core.py` | 物理模型 0.2.0 | `e820ecdb5ed5fbceb870f382c8c7c411ba85c65673bc19258fb935f562ed83b0` |
| `profiles/P1.json` | assumed_P1_reference | `e50445c38014adb169d766202df1e84f48b9ea86d72659ca5029ea73bad1f221` |
| `profiles/P2.json` | assumed_P2_low_exposure | `a60fe0c574b7c9e03f0448632ed34b4f19e634aa0be04b59ab5e625430415e03` |
| `profiles/P3.json` | candidate_B_P3_low_voltage_L_systems | `0e866901f7243eaeb51e323535198c17c52f7eb42abe18a4b4e0b0ad691cd351` |

- 三个 profile 与 `datasets/round2/member_A/production_inputs_v2/profiles/*.json` 逐字节一致，消除了 v1 的 P2/P3 参数差异（P2 196.1 µA / 30 s / 0.014 / 0.55 / 70 eV / 5e6；P3 20 kV / 60 s / 0.008 / 0.3 / 90 eV / 0 空气路径）。
- **身份状态（如实记录）**：A 的 `freeze_manifest` 明写 A-only；评审时 `datasets/round2/shared/` 仅有 README，没有协调人签认的公共输入/种子清单。本版按评审列名的 A 封存参数统一，只作为**可复核的统一条件候选**，不声称已获公共冻结。协调人发布公共清单后若与上表不同，将另出新版本，不回改本版 sealed truth/manifest。
- 设计 seed `2026102101`；batch seed P1 `2026102111`、P2 `2026102112`、P3 `2026102113`；split seed `2026102110`（三条件一致）。
- 无 jitter；`--closure strict`、`--legacy-al reject`、32 目标固定；三条件共用同一 250 配方全集，每配方 2 重复。

## 文件清单

- `C_r2_samples.json`、`C_r2_formula_registry.csv`、`C_r2_candidate_selfcheck.json`：v2 配方、对照登记账目、候选范围/去重/覆盖自检
- `common_inputs_v2.json`：三条件 profile/seed/目标/哈希与身份状态
- `qc/C_r2_P{1,2,3}_v2_dataset.zip` + `.sha256`：v2 密封批次（blind_inputs、truth、full_results、inputs/configs、manifest/integrity、reproducibility 源码/依赖快照）
- `qc/C_r2_P{1,2,3}_v2_audit.json` / `_v2_replay.json` / `_v2_gate.json` + `.txt`/`.log`：包外 audit、全量物理 replay、封装前门禁；命令未传 `--limit`
- `qc/C_r2_v2_structure_check.json`：跨批次结构、样本集、重复、profile 与组成一致性核对
- `selfcheck_summary_v2.json`：v2 通过/失败/缺项汇总（含命令、耗时、容量、回归结果）
- `scripts/`：配方构建、批量生成、`run_qc.sh`（失败不封装且返回非零）、`qc_gate.py`、`qc_gate_regression.sh`、`structure_check.py`、环境与封存源码哈希、`requirements-lock.txt`
- 旧版 v1 的 `qc/C_r2_P{1,2,3}_dataset.zip`、`_audit/_replay/_pack` 文件原样保留；其小体积报告副本另存于 `qc/superseded_v1/`

## 自检结果（v2）

| 批次 | 谱数 | audit | replay（全量） | 门禁 | ZIP SHA-256（前 16 位） | ZIP 体积 |
| --- | ---: | --- | --- | --- | --- | ---: |
| P1 | 500 | passed，errors 0 | passed，500/500，同环境，最大数组差 0 | passed | `aa546bcfa56f934b` | 80.3 MB |
| P2 | 500 | passed，errors 0 | passed，500/500，同环境，最大数组差 0 | passed | `614e4767972c4903` | 82.6 MB |
| P3 | 500 | passed，errors 0 | passed，500/500，同环境，最大数组差 0 | passed | `401561c7e388afe5` | 82.5 MB |

audit 报告 `complete_physics_recalculation=false`（audit 本身不含物理重算），物理重算由 replay 单独完成；replay `scope=all_records`、覆盖 500/500、`errors=[]`、冻结容差 `rtol=1e-12 / atol=1e-8 counts`、同环境声明保留。门禁脚本按这些字段拒绝封装，缺一即跳过 pack 并返回非零。

`qc_gate_regression.sh` 用 mock 覆盖 5 种路径：audit 失败、replay 失败、报告状态非法、覆盖不足、全部通过；前四种均不调用 pack，脚本整体返回非零，第五种正常封装。

## 评审响应

1. **统一输入身份**：P1/P2/P3 改为与 A `production_inputs_v2` 逐字节一致的 profile，SHA-256 见上表；`common_inputs_v2.json` 记录来源与“待公共签认”状态，不再把 A-only 文件写成公共冻结。
2. **完整干扰对照**：50 条改为 10 组 × 5 变体，同基体、同 parent_family、固定背景，带对照标识与实际含量；组内自检八项全过，登记表可逐条追溯。
3. **QC 失败不得封装**：`run_qc.sh` 逐批检查 audit/replay 退出码与报告字段（status、errors、500 全覆盖、scope、冻结容差、环境说明），任一失败跳过该批 pack 且整体 exit 1；新增 `qc_gate_regression.sh` 五路径回归。

## 未完成 / 待办

- `datasets/round2/shared/` 公共输入/种子/候选放行清单：协调人签认（本版不代办、不冒充）
- 跨成员完整组成去重、母族/近邻连通组与全局划分：由协调人合库时执行
- 真实设备校准、实测含量准确度：本规范明确不认证，未验证
- PR #15：v2 提交后请求复核；未自行合并

命令与环境详见 `scripts/run_batches.sh`、`scripts/run_qc.sh`、`scripts/env_record.json`，耗时与容量见 `selfcheck_summary_v2.json`。
