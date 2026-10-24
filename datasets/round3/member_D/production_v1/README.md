# 第三轮 D 全量交付

250 配方、105 完整设计族：基础 1,500 谱 + 36 个内部留出配方 × 6 条 T 挑战 = 216 谱，共 **1,716 谱**，分 48 个原生密封批次。原 90 谱试片批次已计入基础 1,500，并在本次完整生产中一次性生成，没有重复计数或中途放行。

所有 48 批均通过预注册窗外预算、完整 audit、完整物理 replay（不传 `--limit`）和 pack；所有谱逐条重算，最大绝对数组差 0.0。ZIP SHA-256/CRC 与内部 integrity 全部核对。每批包含 `blind_inputs`、`truth`、`full_results`、六分量、谱线/窗外账目、输入/配置、生成器/依赖/环境快照与逐批 `commands.json`。

- `actual_record_index.csv`：覆盖 1,716 条唯一记录的外置索引，固定全局 ID、配方/设计族、用途、profile、计数子种子、盲/全结果哈希与所属 ZIP。
- `archives/R3_D_*.zip`：48 个原生无损 ZIP 及 `.sha256`；`archives/D_round3_blind_inputs.zip`：仅 opaque 命名的 2,048 道原始计数和格式说明，不含元素、浓度、族、条件或种子标签。
- `reports/D_all_batch_QC.zip`：逐批 audit/replay/window_budget/summary/pack 日志、命令与退出码、终端日志；`reports/commands_and_environment.json` 和 `frozen_identity.json` 固定环境、版本、冻结输入与放行哈希。
- `reports/failed_attempts/R3_D_base_D5_001`：首次 8 并发 replay 的 MemoryError 证据。失败产物未删除、未放宽预算、未删谱；同一定义在 4 并发下重跑通过，交付的是通过版本。

T1/T2/T3 仅用于内部留出物理 QC，禁止训练、校正、响应字典和选参；`training_inclusion_approved` 与 `eligible_for_training` 均为 false。本轮未验证真实设备浓度准确度，也不是外部独立盲测。

复现（仓库根目录、冻结依赖环境；输出必须是新目录）：

```powershell
powershell -NoProfile -File datasets/round3/shared/production_tools/run_member_full.ps1 -Member D -Python python
```
