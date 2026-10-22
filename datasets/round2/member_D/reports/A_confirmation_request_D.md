# D 任务冻结输入与 seed 确认请求

- 发起人：D
- 收件人：A（第二轮协调人）
- 日期：2026-10-22
- 主题：请确认 D 使用的冻结输入、D 专用 seed，以及后续跨成员去重流程

## 1. 冻结输入

D 已按 SHA-256 复核 A 的 `freeze_manifest.json`，D 实际使用的 40 个文件全部匹配，0 个不一致：

- 生成器源码与配置：35/35 匹配（`fp_competition 0.2.1`，物理模型 `0.2.0`）
- P1/P2/P3：3/3 匹配
- `design_ranges.json`：匹配
- `A_run_config.json`：匹配
- `physics_baseline.json` 保护模块：3/3 匹配

关键哈希：

| 文件 | SHA-256 |
|---|---|
| P1.json | `e50445c38014adb169d766202df1e84f48b9ea86d72659ca5029ea73bad1f221` |
| P2.json | `a60fe0c574b7c9e03f0448632ed34b4f19e634aa0be04b59ab5e625430415e03` |
| P3.json | `0e866901f7243eaeb51e323535198c17c52f7eb42abe18a4b4e0b0ad691cd351` |
| design_ranges.json | `5f347d179830f7e9c64e0d98fd02397582f263171e83c773513347d5090c9c6d` |
| A_run_config.json | `4ddfc93fa2c308cb565fabcc28b58c0f569fd3e48d81a064c515f16db56ffae3` |

A 的 `freeze_manifest.json` 当前 scope 为 `A-only production freeze; global use pending`，`cross_member_confirmation: pending`。D 不声称这些输入已全局冻结。

**请求 A 确认：** P1/P2/P3、`design_ranges.json` 和 `fp_competition 0.2.1` / 物理模型 `0.2.0` 可作为 D 的共同基线。

## 2. D 专用 seed

D 未复用 A 的 `202610210101/102/103` 与 split seed `20261021`。建议如下：

| 项目 | 值 |
|---|---|
| 硅酸盐常规 design seed | 2026102201 |
| 硅酸盐稀疏/边界 design seed | 2026102202 |
| 硅酸盐干扰基座 seed | 2026102203 |
| 富铁常规 design seed | 2026102204 |
| 富铁稀疏/边界 design seed | 2026102205 |
| 富铁干扰基座 seed | 2026102206 |
| P1 batch root | 202610220101 |
| P2 batch root | 202610220102 |
| P3 batch root | 202610220103 |
| split seed | 20261022 |
| 每片 batch seed | batch root ×100 + 片号（S01=…01，S10=…10） |
| replicates | 2 |
| jitter | 无 |

**请求 A 确认：** 接受上述 seed，或给出 D 应使用的 seed 清单。

## 3. 设计与生产范围

- 250 配方：150 硅酸盐/氧化物（90 常规 + 30 稀疏/边界 + 30 干扰）+ 100 富铁氧化物（60 + 20 + 20）。
- 10 个整家族 shard（S01–S06 硅酸盐，S07–S10 富铁），每片 25 配方。
- 每片 × P1/P2/P3 ×2 replicates = 150 谱；30 批共 1,500 谱。
- 干扰对照：10 组 ×5 变体（absent / A-only / B-only / 1:1 / 5:1）。
- D 先生成候选配方和检查报告，提交 A 做跨成员去重/排除亲缘；**A 确认前不生成任何谱**。

**请求 A 确认：** 上述配额、shard 结构和“先候选去重、后出谱”的顺序。

## 4. 建议的回复格式

```text
1. 冻结输入：确认 / 需修改（说明）
2. D seed：接受 / 替换为（列出）
3. 候选去重：请 D 提交 candidate_samples_D.json + formula_registry_D.csv + 检查报告
4. 其他约束：
```

A 的回复将写入 `A_confirmation_D.json`，作为 D 进入候选定稿和生产的前置条件。
