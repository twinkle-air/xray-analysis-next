# 第四轮成员 A 交付入口

2026-10-27：A 的 40,000 条合成谱已完成本地生成及成员完整自检，交付见 [production_v1](production_v1/README.md)。训练用途 32,000、验证 4,000、密封测试 4,000；400 个原生批次，当前待负责人验收，不自动准入训练。

正式生产已按项目负责人 2026-10-25 的授权放行，A 一次生成完整配额，不做试片。当前生产准入依据 [production_release_v1.json](../shared/releases/production_release_v1.json)，冻结输入保持不变。

候选 v1：2,000 个组成、640 个合并前设计族；候选来源、重建步骤及证据见 [候选说明](candidates_README.md)、[候选注册表](candidates_v1/candidate_registry.csv)、[独立复核](candidates_v1/independent_verification.json) 和 [候选文件哈希](candidates_v1/delivery_manifest.json)。

生产任务与数量依据 [本人任务](../planning/A_任务清单.md) 和 [共同方案](../planning/第四轮数据构建方案.md)。已保留内存故障现场哈希及同冻结种子重算说明，最终索引不重复计数。完整盲包因单文件大小拆分，须先按 production_v1/blind/RESTORE.md 恢复后校验。

完整审查和物理重算证明合成流程可复现，不证明真实仪器准确度；密封用途不可用于训练/字典/校正/选参，训练纳入须另核准。
