# 批次状态 · C-part-20261018

**未通过独立评审（PR #2：requested changes，未合并）；本批次定位为候选试产（workflow pilot-only），禁止用于训练与调参。**

## 密封批次身份（保留，不重写）

- 分支 `c-part-20261018`，提交 `cdc4f739c01446e24c0f3701a94cf2e04a15fbdf`，基线 `64f4bfd7…`，落点 `datasets/C-part-20261018`
- 数据集 ZIP SHA-256：`9178746d90e26e45d64a8a9f15ca35736ba363110d535d787e3e589fbf3bf3f2`
- 主表语义摘要：`6673fb80fb961c6700dc223ddfe0d419a3b9cc3d5b858eceb28390736e4ccaff`
- `truth.jsonl` / `manifest.json` / 分卷：未改动。失败批次身份保留以便追溯。

## 评审发现与修复状态

| 编号 | 级别 | 问题 | 证据 | v2 状态 |
| --- | --- | --- | --- | --- |
| P1-1 | P1 | 留出批次被标成可训练划分 | v1 索引 benchmark_split = train 1402 / validation 302 / test 296；交付 README 写"下游只按 benchmark_split 读取训练数据"。 | fixed_in_v2 |
| P1-2 | P1 | 相同采用组成跨集合（泄漏） | 9 组完全相同的组成落在不同集合；根因是划分按设计族 parent_family，而生成器族按实际采用组成。 | fixed_in_v2 |
| P2-1 | P2 | 1000 行配方仅 944 种独立组成 | v1 主表复算：distinct=944，重复组 34；稀疏/边界的 Fe 变化被 100% 闭合归一化抹平，"元素=0" 在只存非零元素的采用组成里不留痕。 | fixed_in_v2 |
| P2-2 | P2 | 干扰对照被写死的 Ni=8 与 Fe 平衡破坏 | v1 每行 `close_percent({**vals, "Ni": 8.0, "Fe": fe})`：对含 Ni 时目标被覆盖，含 Fe 的 3 对里 Fe 既是基体又是对照变量。 | fixed_in_v2 |
| P2-3 | P2 | 548/600 常规配方越出自身声明范围 | v1 主表复算：常规情景 548 行越界（如 C=1.397% 声明上限 0.8%、W=5.04% 声明上限 2%），合计 1334 项；采样时只校验 Fe。 | fixed_in_v2 |

## v2 修复要点（代码与自检已完成，数据未重生成）

- 配方设计：1000 行 → **独立采用组成 1000**、**越出自身声明范围的行 0**、干扰族 40 × 5 变体、含 Fe 干扰对 无（自检 passed=True）
- 索引/划分：全部行 `benchmark_split=heldout`；并查集 leak_group 801 个；相同组成跨集合 []（passed=True）
- 入口隔离：`scripts/c_pilot_guard.py` train/validation/test 三入口全部拒绝（passed=True）
- 重生成尚未启动，等待验证报告获批。

## 下游使用规则

1. 不要把本批次任何谱用于训练、调参或阈值挑选；请改用已通过评审的 A/B 批次。
2. 读取本批次请走 `c_pilot_guard.training_rows()`，它会拒绝而非静默放行。
3. `README.md` 里"按 benchmark_split 读取训练数据"的旧说法已作废（该段已改写）。
