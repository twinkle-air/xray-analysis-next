# 第二轮 · 成员 C 交付

- 成员：C（round_id = `round2`）
- 软件：fp_competition **0.2.1**，物理模型 **0.2.0**，xraylib **4.3.0**
- 状态：**自检通过，待协调人复核**（数量/版本、完整性、实际自检报告、合库分组四项由协调人 A 核对）

## 实际数量

| 项 | 数量 |
| --- | ---: |
| 独立配方 | 250（硅酸盐/氧化物 150 = 90 常规 + 30 稀疏/边界 + 30 干扰；富铁氧化物 100 = 60/20/20） |
| 谱 | 1,500（P1/P2/P3 每配方每条件 2 条独立计数噪声） |
| 母族 | 硅酸盐 29、富铁 22（逐配方登记于 `C_r2_formula_registry.csv`） |

组成均为元素质量百分数、保留 O 基体，strict 闭合最大误差 0.0（容差 1e-6 个百分点）；250 个 ID 与 250 个组成摘要均唯一。ppm 原始值经 `1 ppm = 1e-4 wt%` 换算，换算规则与缩放因子逐条写入 provenance。

## 输入身份

| 文件 | SHA-256 |
| --- | --- |
| 生成器 `app.py` | `6f515db4…393159c8` |
| `core.py` | `e820ecdb…62ed83b0` |
| `profiles/P1.json`（reference_P49_150s_default） | `9814cf45…aa7e18` |
| `profiles/P2.json`（low_count_P49_30s_response_shift） | `16d5792a…8dd096` |
| `profiles/P3.json`（low_voltage_P20_response_shift） | `7b8e58a9…a63813` |

- 设计 seed：`2026102101`；batch seed：P1 `2026110301`、P2 `2026110302`、P3 `2026110303`；split seed：`20261103`（三条件一致）
- 无 jitter；`--closure strict`、`--legacy-al reject`、32 目标固定
- 三个条件共用同一 250 配方全集；每配方 2 重复；同族划分 350 train / 76 validation / 74 test（三条件一致，生成器 split 仅供协调人合并时参考，不作为全局划分）

## 文件清单

- `C_r2_samples.json`、`C_r2_formula_registry.csv`、`C_r2_candidate_selfcheck.json`：配方、登记账目、候选范围/去重/覆盖自检
- `qc/C_r2_P{1,2,3}_dataset.zip` + 同名 `.sha256`：密封批次（含 blind_inputs、truth、full_results、inputs/configs、manifest/integrity、reproducibility 源码/依赖快照）
- `qc/C_r2_P{1,2,3}_audit.json`、`qc/C_r2_P{1,2,3}_replay.json` + 同名 .txt 终端日志：包外 audit 与全量物理 replay（未传 `--limit`）
- `qc/C_r2_structure_check.json`：跨批次结构与重复数核对
- `selfcheck_summary.json`：通过/失败/缺项汇总（含命令、耗时、容量）
- `scripts/`：配方构建、批量生成、audit/replay/pack 脚本、环境与封存源码哈希、`requirements-lock.txt`

## 自检结果

| 批次 | 谱数 | audit | replay（全量） | ZIP SHA-256（前 16 位） |
| --- | ---: | --- | --- | --- |
| P1 | 500 | passed，errors 0 | passed，500/500，同环境，最大数组差 0.0 | `4470be8a91586956` |
| P2 | 500 | passed，errors 0 | passed，500/500，同环境，最大数组差 0.0 | `dd5afece5a868b29` |
| P3 | 500 | passed，errors 0 | passed，500/500，同环境，最大数组差 0.0 | `2a9adbf69c865069` |

audit 报告 `complete_physics_recalculation=false`（audit 本身不含物理重算），物理重算由 replay 单独完成；报告未声称硬件标定或真实含量准确度。

## 未完成 / 待办

- 跨成员完整组成去重、母族/近邻连通组与全局划分：由协调人 A 合库时执行（本目录不含全局索引）
- 推送分支 `data/C-round2-20261021` 并创建 PR：已推送，待其他队员审查合并
- 真实设备校准、实测含量准确度：本规范明确不认证，未验证

命令与环境详见 `scripts/run_batches.sh`、`scripts/run_qc.sh`、`scripts/env_record.json`，耗时与容量见 `selfcheck_summary.json`。
