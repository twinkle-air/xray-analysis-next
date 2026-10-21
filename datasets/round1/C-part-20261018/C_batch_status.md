# 批次状态 · C-part-20261018

**未通过独立评审（PR #2 两轮 requested changes，未合并）；本批次定位为候选试产（workflow pilot-only）并归档，禁止用于训练与调参。**

## 密封批次身份（保留，不重写）

- 数据提交 `cdc4f739…`（基线 `64f4bfd7…`）+ 候选标注提交 `5c9439f…`，落点 `datasets/C-part-20261018`
- 数据集 ZIP SHA-256：`9178746d90e26e45d64a8a9f15ca35736ba363110d535d787e3e589fbf3bf3f2`
- 主表语义摘要：`6673fb80fb961c6700dc223ddfe0d419a3b9cc3d5b858eceb28390736e4ccaff`
- `truth.jsonl` / `manifest.json` / 分卷：未改动。失败批次身份保留以便追溯。

## 评审发现与修复位置

| 编号 | 级别 | 问题 | 证据 | 状态 |
| --- | --- | --- | --- | --- |
| P1-1 | P1 | 留出批次被标成可训练划分 | v1 索引 benchmark_split = train 1402 / validation 302 / test 296；交付 README 写"下游只按 benchmark_split 读取训练数据"。 | `fixed_in_v2_code_archived_batch_unchanged` |
| P1-2 | P1 | 相同采用组成跨集合（泄漏） | 9 组完全相同的组成落在不同集合；根因是划分按设计族 parent_family，而生成器族按实际采用组成。 | `fixed_in_v2_code_archived_batch_unchanged` |
| P2-1 | P2 | 1000 行配方仅 944 种独立组成 | v1 主表复算：distinct=944，重复组 34；稀疏/边界的 Fe 变化被 100% 闭合归一化抹平，"元素=0" 在只存非零元素的采用组成里不留痕。 | `fixed_in_v2_code_archived_batch_unchanged` |
| P2-2 | P2 | 干扰对照被写死的 Ni=8 与 Fe 平衡破坏 | v1 每行 `close_percent({**vals, "Ni": 8.0, "Fe": fe})`：对含 Ni 时目标被覆盖，含 Fe 的 3 对里 Fe 既是基体又是对照变量。 | `fixed_in_v2_code_archived_batch_unchanged` |
| P2-3 | P2 | 548/600 常规配方越出自身声明范围 | v1 主表复算：常规情景 548 行越界（如 C=1.397% 声明上限 0.8%、W=5.04% 声明上限 2%），合计 1334 项；采样时只校验 Fe。 | `fixed_in_v2_code_archived_batch_unchanged` |

> `fixed_in_v2_code_archived_batch_unchanged` = 修复位于 **v2 代码与 v2 主表**，本归档批次数据未变；要按 v2 出数需另起批次重新生成并密封。

## 第二轮意见与本次处置

- **R2-1 三项配方问题标成"已修复"，但引用的新脚本与主表未提交，无法验证**
  处置：v2 设计/索引/守卫/预检/复现脚本与 v2 主表、全部自检产物随包提交；发现状态措辞改为 fixed_in_v2_code_archived_batch_unchanged，并写明归档批次数据未变。
- **R2-2 把 A/B 试产数据推荐为可训练数据，与其用途限制不符**
  处置：删除"改用已通过评审的 A/B 批次"推荐（README、C_batch_status、c_pilot_guard 文案三处同步），改为要求核对目标批次自身 usage_policy 与评审状态；本交付不为其他批次作背书。

## 复现（评审可直接跑）

```
python -B scripts/design_c_alloy_formulas_v2.py
python -B scripts/build_p5_index_v2.py <解包后的数据集目录> [主表] [批次] [版本] [输出]
python -B scripts/c_pilot_guard.py
python -B scripts/check_review_findings.py
python -B scripts/fix_registry_scenario.py
python -B scripts/reproduce_v2_check.py [数据集目录]
python -B scripts/check_doc_references.py [本目录]
```

- 复现对账：`v2/reproduction_check_v2.json`（产物逐字节一致 = True，passed = True）
- 文档引用自检：`v2/doc_reference_check.json`（本目录文档引用的脚本/产物是否都随包存在）
- 评审五条复算：`v2/review_findings_check.json`（P2_1 distinct 944、P2_3 常规越界 548 行 / 1334 项）
- v2 主表：`v2/master_samples_v2.json` SHA-256 `78ca94780021c17915565d152cffb234976e2d007d796126d84cbf4ce3d1a9b3`；独立组成 1000/1000，越界 0 行 / 0 项
- v1 基线复算：{"available": true, "rows": 1000, "distinct_compositions": 944, "duplicate_groups": 34, "rows_with_range_violations": 891, "range_violation_items": 1750, "violations_by_scenario": {"regular_variation": 548, "sparse_boundary": 200, "interference_control": 143}}
- 索引断言：leak_group 801、全部行 heldout = True、跨集合 0（passed=True）
- 入口守卫：3 个入口被拒（passed=True）
- 同一策略跑在新生成的 v2 批次上（`v2/index_policy_check_v2_on_v2_data.json`，数据集 `P5_dataset_v2`）：2000 行全 heldout、独立采用组成 1000/1000、重复组 0、leak_group 680 个（尺寸分布 {"1": 600, "5": 80}）、跨集合 0（passed=True）
- v2 数据批次（**不随本批交付**）：阶段 sealed_complete_batch，谱数 2000/2000，一致性 True；已生成器密封、未做 audit/replay/打包/推送，故不构成可交付数据集（快照 `v2/generation_status_v2.json`，1.30 GiB）

## 自查披露（本次一并修正，非评审提出）

- **SD-1（P3）归档登记表 `C_formula_registry.csv` 的 `scenario` 列 1000 行全空**。根因：build_github_payload.py 用了 provenance['scenario']，主表键名是 provenance['design_scenario']。
  归档文件字节未改（原 SHA-256 `06494e43fba09bf3…`）；新增修正件 `C_formula_registry_v2.csv`（`5869e7ca6b6c9f1b…`），逐列对账只有 `scenario` 一列不同、其他列差异 0 处，补齐后 {"regular_variation": 600, "sparse_boundary": 200, "interference_control": 200}；对账文件 `v2/registry_scenario_fix_check.json`（passed=True）。构建脚本 `scripts/build_github_payload.py` 的取键同步修正。此缺陷不影响谱、真值、索引与划分。

## 下游使用规则

1. 不要把本批次任何谱用于训练、调参或阈值挑选。
2. 读取本批次请走 `c_pilot_guard.training_rows()`，它会拒绝而非静默放行。
3. `README.md` 里"按 benchmark_split 读取训练数据"的旧说法已作废（该段已改写）。
4. 不要以"改用 A/B 批次"作为替代方案：每个批次（含 A/B 试产数据）都要各自核对其 `usage_policy` 与评审状态，本交付不为其他批次作背书。
