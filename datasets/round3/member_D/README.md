# 第三轮 D：全量1,716谱已交付

完成 250 配方 / 105 设计族的基础 1,500 谱和 36 个内部留出配方 × 6 条 T 挑战谱 = 216 谱，共 **1,716 谱**，分 48 个原生密封批次；原 90 谱试片批次已计入基础 1,500，本次一次性生成，无重复计数。[完整交付与逐批验收证据](production_v1/README.md) 包含外置记录索引、48 个原生 ZIP/SHA、盲输入包、完整 audit/replay/window_budget 与失败重跑证据；候选阶段文件与来源字节不改写。

- [当前自检汇总](selfcheck_summary.json) · [本目录完整交付清单](delivery_manifest.json)
- [250 个原始候选与转换账目](candidates/D_samples.json) · [105 设计族](candidates/family_registry.json)
- [全局固定输入](../shared/freeze_v1/README.md) · [owner release v3](../shared/releases/owner_release_v3.json)
- [候选检查与历史/跨成员筛查](candidates/candidate_checks.json) · [候选阶段验证](reports/verification.json)

全局索引使用固定族用途与 profile；计数重复不算新配方，native split 不算研究划分。T1/T2/T3 仅用于内部留出物理 QC，禁止训练、校正、响应字典和选参；`training_inclusion_approved`、`eligible_for_training` 均为 false。本轮未验证真实设备浓度准确度，也不是外部独立盲测。

首批 `R3_D_base_D5_001` 在 8 并发下 replay 内存不足，失败产物与日志已保留；同一定义在 4 并发下重跑通过，交付的是通过版本，未放宽窗外预算、未删除难谱。详见 `production_v1/reports/failed_attempts/`。
