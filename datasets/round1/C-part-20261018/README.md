# C 部分 · C-part-20261018（铁基合金 1000 配方 / P5 候选留出条件 / 2000 合成谱）

> **状态：未通过独立评审（PR #2 requested changes），仅候选试产（pilot-only），禁止用于训练与调参。** 详见 `C_batch_status.md`。

生成器 fp-spectrum-generator-competition-0.2.1（物理模型 0.2.0）。
与 `datasets/A-part-20261018` 同构平铺；数据集本体在分卷 ZIP 内，逐文件清单见 `C_delivery_hashes.json`。

## 内容

| 文件 | 说明 |
| --- | --- |
| `C_samples.json` | C 负责的 1000 条铁基合金主配方（常规 600 / 稀疏边界 200 / 干扰对照 200，严格闭合、Fe 平衡） |
| `C_formula_registry.csv` | 逐配方登记：情景、母族 parent_family、成分族、双划分、谱号、正元素数、闭合和 |
| `C_authoritative_index.csv` | 2000 条谱的权威索引（batch/local/global id、配方、族、双划分、盲/满双 SHA-256） |
| `C_global_split.csv` | 814 个 parent_family 的权威划分与谱数 |
| `C_coverage.json` | 元素零/低/中/高覆盖、能窗、窗外损失、Ba 统计、数据集逐文件体积 |
| `C_acceptance_summary.json` | 机器可读验收汇总（身份、规模、划分、检查结果、覆盖、时长与存储预算、未验证事项） |
| `C_acceptance_summary.md` | 同上的人读版 |
| `C_production_record.json` | 批次身份：种子、哈希、状态、分卷清单与重建校验命令 |
| `C_delivery_hashes.json` | 本目录逐文件 SHA-256（含 8 个分卷）与原始交付清单 |
| `P5.json` | 条件配置 candidate_holdout_P45_Al50_air1（SHA-256 `e30ba2115f3b…`） |
| `P5_audit.json` | 全量 audit 完整报告（2000 条、0 错误；含逐元素覆盖与容差） |
| `P5_replay.json` / `P5_replay_environment.json` | 全量物理重算报告（最大数组绝对差 0.0、环境一致）与运行环境 |
| `P5_pack.json` / `P5_dataset.zip.sha256` | 打包报告与整包外部校验值 |
| `P5_check_timings.json` | 实测单谱耗时（生成 1.82–2.52 s、replay 2.59 s、audit ≈0.1 s、打包 81.7 s/2000 谱） |
| `P5_pack.zip.part01`…`part08` | 密封数据集目录的 ZIP 分卷（每卷约 41 MiB，合计 344,994,035 B） |
| `scripts/` | 配方设计（v1/v2）、断点续跑生成、外部检查打包、索引构建（v1/v2）、入口守卫与复现对账脚本 |

## 重建与校验数据集

```
copy /b P5_pack.zip.part01+P5_pack.zip.part02+P5_pack.zip.part03+P5_pack.zip.part04+P5_pack.zip.part05+P5_pack.zip.part06+P5_pack.zip.part07+P5_pack.zip.part08 P5_dataset.zip
certutil -hashfile P5_dataset.zip SHA256     # 应等于 P5_dataset.zip.sha256：9178746d90e26e45d64a8a9f15ca35736ba363110d535d787e3e589fbf3bf3f2
tar -xf P5_dataset.zip -C P5_dataset_dir    # 或任意 unzip 工具
python -B P5_dataset_dir/reproducibility/generator/fp_competition/app.py audit --dataset P5_dataset_dir --out P5_qc_after_clone.json
```

分卷按顺序拼接即得原包；ZIP 不含时间戳等易变字段，同一目录内容可确定性地重建出同一 SHA-256（已实测：从交付副本重新 pack 的哈希与原件完全一致）。

## 数据集结构（ZIP 内）

`blind_inputs/`（2000，严格 5 字段：x、counts、axis、signal_unit、synthetic）、`full_results/`（2000，六分量分解与窗外账目）、`truth.jsonl`、`manifest.json`（status=complete，acceptance_status=pending_independent_validation）、`integrity.json`、`inputs/`、`configs/`、`reproducibility/`（源码快照 + 环境 + 依赖锁定 + recipe）。

## 划分与用法（v2 修正）

**本批次未通过独立评审（两轮均为 requested changes），定位为候选试产（pilot-only）并归档，
禁止用于训练与调参。** 状态见 `C_batch_status.md`，可复现的修复代码见第 "v2 可复现代码" 一节。

- 权威字段：每一行 `holdout_status=condition_heldout`、`benchmark_split=heldout`、
  `usage_policy=pilot_only_isolated_from_training_and_tuning`。
- `recipe_family_split`（train/validation/test）只描述配方来源，**不得作为基准划分**。
- 同一 leak_group（实际采用组成 ∪ parent_family ∪ 生成器族 ∪ 噪声重复）不跨集合；
  v1 里 9 组相同组成跨集合的问题在 v2 索引中已消除并逐条断言（断言见
  `C_index_policy_check_v2.md`，可用 `scripts/build_p5_index_v2.py` 重跑）。
- 三处配方问题（944 独立组成、干扰对照写死 Ni=8/Fe 参与、548 行越界）的修复位于
  **v2 主表与设计脚本**：`scripts/design_c_alloy_formulas_v2.py` 与
  `v2/master_samples_v2.json`（SHA-256 见 `v2/design_selfcheck_v2.json`）。
  **本归档批次的 2000 条谱仍由 v1 主表生成，数据本身未被改写**；如需按 v2 主表出数，
  必须另起新版本批次重新生成并密封，不能就地修补（本地已按 v2 主表生成出候选
  `P5_dataset_v2` 2000 谱，但**未 audit、未 replay、未打包、未推送**，
  进度与身份只读快照见 `v2/generation_status_v2.json`，不构成可交付数据集）。
- 下游入口请用 `scripts/c_pilot_guard.py::training_rows()`：请求本批次任何划分都会抛
  `PilotIsolationError`，不会静默返回可训练行。
- 不要用其他批次替代本批做基准：任何批次（含 A/B 试产数据）都必须先核对它自己的
  `usage_policy` 与评审状态。本交付不为任何其他批次的可训练性作背书。

## v2 可复现代码与产物（第二轮评审后随包提交）

第二轮评审指出：说明里引用的新脚本与主表当时并未提交，因而"已修复"无法验证。
本次把它们全部放进本目录，评审可在解包后直接复跑。

| 路径 | 内容 |
| --- | --- |
| `scripts/design_c_alloy_formulas_v2.py` | 1000 条铁基主配方的 v2 设计（P2-1 / P2-2 / P2-3 的修复本体） |
| `scripts/build_p5_index_v2.py` | 并查集 leak_group + 统一 heldout 的索引/划分构建器（P1-1 / P1-2） |
| `scripts/c_pilot_guard.py` | 训练/调参入口守卫与三入口拒绝自检 |
| `scripts/reproduce_v2_check.py` | 复刻仓库布局重跑三件事，并与本目录产物逐字节对账 |
| `scripts/pregenerate_dryrun_v2.py`、`scripts/v2_generation_status.py`、`scripts/generate_v2_batch.py` | 生成前预检、只读进度快照、后续批次生成入口 |
| `v2/master_samples_v2.json` | v2 主表（根目录同名重写件：`C_samples_v2.json`） |
| `v2/design_selfcheck_v2.json` / `.md` | 设计自检：1000 行 1000 种独立组成、越界 0 行 0 项，含 v1 基线复算 |
| `v2/index_v2.csv`、`v2/global_split_v2.csv`、`v2/coverage_v2.json`、`v2/index_policy_check_v2.*` | 索引/划分/覆盖与断言结果 |
| `v2/pilot_guard_selftest.json`、`v2/pilot_isolation.json` | 入口隔离自检与被隔离批次清单 |
| `v2/reproduction_check_v2.json` / `.md` | 跨布局逐字节复现对账结果 |
| `v2/generation_status_v2.json` / `.md` | v2 批次数据的真实进度快照（只读磁盘，未密封、未推送） |
| `v2/C_v2_verification_report.md` | 两轮意见的逐条验证报告 |

复现命令（脚本路径已适配本目录布局：主表自动取 `C_samples.json`，输出写到 `v2/`）：

```
python -B scripts/design_c_alloy_formulas_v2.py
python -B scripts/build_p5_index_v2.py <解包后的数据集目录> [主表] [批次标签] [版本] [输出目录]
python -B scripts/c_pilot_guard.py
python -B scripts/reproduce_v2_check.py [数据集目录]
```

## 自查披露：登记表 `C_formula_registry.csv` 的 scenario 列全空

本轮复核载荷时发现：已推送的 `C_formula_registry.csv` 第 2 列 `scenario` 在 1000 行里
全部为空字符串。根因是载荷构建脚本取 `provenance['scenario']`，而主表里的键名是
`provenance['design_scenario']`（其余 10 列不受影响，数值正确）。

处置（不改动归档文件字节）：

- `C_formula_registry.csv` 保持原样、原 SHA-256 不变，作为归档批次的真实交付状态保留；
- 新增 `C_formula_registry_v2.csv`：由 `scripts/fix_registry_scenario.py` 从本目录
  `C_samples.json` 逐行按 `formula_id` 对齐补齐 scenario 列。对账结果
  `v2/registry_scenario_fix_check.json` 断言：行序完全一致、只有 `scenario` 一列不同、
  其他列 0 处差异、补齐后 regular_variation 600 / sparse_boundary 200 /
  interference_control 200、且把原文件按同格式重新序列化可得到与原字节完全相同的结果
  （证明差异只来自这一列）；
- `scripts/build_github_payload.py` 的取键已修正，未来批次不会再产生空列。

该缺陷不影响谱数据、真值、索引与划分，也不改变"本批次禁止训练/调参"的结论。
## 未验证事项

合成数据、未通过真实设备校准；模型不含死时间、堆积、粒度、水分、多层、多次散射与粗糙度；
含量相对误差 ≤5% 的结论不能由本批数据得出；P5 是候选模拟配置而非真实未见设备。
