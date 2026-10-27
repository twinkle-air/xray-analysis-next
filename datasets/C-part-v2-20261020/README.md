# C 部分 · C-part-v2-20261020（铁基合金 1000 配方 / P5 留出条件 / 2000 合成谱，v2）

生成器 fp-spectrum-generator-competition-0.2.1（物理模型 0.2.0）。
本批替代 `datasets/C-part-20261018`（PR #2 评审 requested changes 的归档批次，
`C-part-20261018 (C-recipes-v1, PR #2 review_failed)`）；归档批次原样保留、未改动，其定位仍是失败批次。

## 这一批改了什么（对着首轮评审 5 条）

| 评审条 | v1 归档批次 | 本批实测 | 证据 |
| --- | --- | --- | --- |
| P1-1 留出批次被标成可训练划分 | benchmark_split = train/validation/test | 2000 行全部 `benchmark_split=heldout` + `holdout_status=condition_heldout` + `usage_policy=pilot_only_isolated_from_training_and_tuning`；训练语义降级为仅描述来源的 `recipe_family_split` | `C_index_policy_check_v2.json` |
| P1-2 相同组成跨集合 | 9 组 | 跨集合组数 0（划分粒度 = 并查集 `leak_group`） | 同上 |
| P2-1 1000 行仅 944 独立组成 | 944 | **1000/1000**，重复组成组 0，leak_group 680 组（ sizes {"1": 600, "5": 80}） | 同上 |
| P2-2 干扰对照写死 Ni=8、Fe 参与对照 | 是 | Ni/Cr/Mo/Cu 按情景区间采样，Fe 只作基体 | `scripts/design_c_alloy_formulas_v2.py` |
| P2-3 548 行越出自身声明范围 | 常规 548 行/1334 项 | 逐情景区间校验，越界 0 | 同上 + `C_batch_status.json` |

## 内容

| 文件 | 说明 |
| --- | --- |
| `C_samples.json` | 1000 条铁基合金主配方（常规 600 / 稀疏边界 200 / 干扰对照 200），SHA-256 `78ca94780021…` |
| `C_formula_registry.csv` | 逐配方登记：情景、母族、实际采用组成键、leak_group、双划分、谱号、正元素数、闭合和 |
| `C_authoritative_index.csv` | 2000 条谱的权威索引（留出字段 + 盲/满双 SHA-256） |
| `C_global_split.csv` | leak_group 粒度的划分表 |
| `C_coverage.json` | 元素覆盖、能窗、窗外损失、身份哈希 |
| `C_index_policy_check_v2.json/.md` | 划分与泄漏策略的机器自检（`passed: true`） |
| `C_batch_status.json` | 批次身份、规模、评审条目对照、QC 结果、用法限制、未验证事项 |
| `P5.json` | 条件配置 candidate_holdout_P45_Al50_air1 |
| `P5_audit.json` | 全量 audit 报告（2000 条、错误 0） |
| `P5_dataset.zip.sha256` | 整包外部校验值：`0176c90109473ed03a499edcb6fd12e6405b0dcb6879acba04951f544103c54a` |
| `P5_pack.zip.part01`…`part08` | 密封数据集目录的 ZIP 分卷（每卷 < 43 MiB，合计 333,143,877 B） |
| `scripts/` | v2 设计、生成、索引/划分、守卫、密封补齐、QC 与本布局生成脚本 |

## 重建与校验

```
copy /b P5_pack.zip.part01+P5_pack.zip.part02+P5_pack.zip.part03+P5_pack.zip.part04+P5_pack.zip.part05+P5_pack.zip.part06+P5_pack.zip.part07+P5_pack.zip.part08 P5_dataset.zip
certutil -hashfile P5_dataset.zip SHA256     # 应等于 P5_dataset.zip.sha256
tar -xf P5_dataset.zip -C P5_dataset_v2
python -B P5_dataset_v2/reproducibility/generator/fp_competition/app.py audit --dataset P5_dataset_v2 --out P5_qc_after_clone.json
```

## 划分与用法

- 每一行 `benchmark_split=heldout`、`holdout_status=condition_heldout`、
  `usage_policy=pilot_only_isolated_from_training_and_tuning`。本批 2000 谱禁止训练、调参与阈值挑选。
- `recipe_family_split`（train/validation/test）只描述配方来源，不得作为基准划分。
- 划分粒度为并查集 `leak_group`（实际采用组成 ∪ parent_family ∪ 生成器族 ∪ 噪声重复），同组不跨集合。
- 下游入口请用 `scripts/c_pilot_guard.py::training_rows()`，它会抛 `PilotIsolationError` 而非静默放行。
- 不使用其他批次替代本批做基准：任何批次（含 A/B 试产数据）都要各自核对其 `usage_policy` 与评审状态。

## QC 结果

- audit：`passed`，检查 2000 条谱，错误 0 条
  （逐谱校验盲/满双哈希、通道轴、分量求和、窗口账目、泊松重放、闭合与来源一致性）。
- 全量物理重算：`passed`，重算 2000 条，
  最大数组绝对差 0.0，环境一致 True。
- 打包：确定性 ZIP 333,143,877 B，SHA-256 `0176c90109473ed03a499edcb6fd12e6405b0dcb6879acba04951f544103c54a`。

## 未验证事项

合成数据、未做真实设备校准；模型不含死时间、堆积、粒度、水分、多层、多次散射与粗糙度；
含量相对误差 ≤5% 的结论不能由本批数据得出；`acceptance_status = pending_independent_validation`。
