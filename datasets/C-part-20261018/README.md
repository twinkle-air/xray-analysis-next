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
| `scripts/` | 配方设计、断点续跑生成、外部检查打包、索引构建、本布局生成脚本 |

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

**本批次未通过独立评审，定位为候选试产（pilot-only），并从所有训练/调参入口隔离。**
状态见 `C_batch_status.md`；评审意见见 PR #2。

- 权威字段：每一行 `holdout_status=condition_heldout`、`benchmark_split=heldout`、
  `usage_policy=pilot_only_isolated_from_training_and_tuning`。
- `recipe_family_split`（train/validation/test）只描述配方来源，**不得作为基准划分**。
- 同一 leak_group（实际采用组成 ∪ parent_family ∪ 生成器族 ∪ 噪声重复）不跨集合；
  v1 里 9 组相同组成跨集合的问题在 v2 索引中已消除并逐条断言。
- 下游入口请用 `scripts/c_pilot_guard.py::training_rows()`：请求本批次任何划分都会抛
  `PilotIsolationError`，不会静默返回可训练行。
- 需要可训练数据请使用已通过评审的批次（A/B 部分）。

## 未验证事项

合成数据、未通过真实设备校准；模型不含死时间、堆积、粒度、水分、多层、多次散射与粗糙度；
含量相对误差 ≤5% 的结论不能由本批数据得出；P5 是候选模拟配置而非真实未见设备。
