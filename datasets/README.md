# 数据集按轮次管理

- [round1：第一轮原始交付归档](round1/README.md)：保留 A/B/C 原件、密封谱及历史检查。归档不表示正式训练验收。
- [round2：第二轮工作区](round2/README.md)：当前 10 GB、1,000 独立配方/6,000 谱计划及四人任务说明；尚未生成第二轮谱。

新任务必须明确 round_id、dataset_version 和 usage_policy。不要递归扫描 datasets/ 混合加载全部 JSON/ZIP，也不要将 round1 的 pilot、失败谱或旧 split 自动拼入 round2。
第二轮训练只读已冻结且通过本轮复核的权威开发索引；索引未发布前不能开始训练。
历史路径迁移见 [round1/path_migration.json](round1/path_migration.json)。
