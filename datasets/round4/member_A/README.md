# 第四轮成员A交付入口

候选 v1：2,000 个组成、640 个合并前设计族；A 本地闭合/补偿/历史近邻复核已通过。实际谱：0；全局候选闭环已通过，完整用途/条件/种子名册已准备待审查，生产release未放行。先读[本人任务](../planning/A_任务清单.md)及[共同方案](../planning/第四轮数据构建方案.md)。

候选范围、重建步骤及证据见[候选说明](candidates_README.md)、[候选注册表](candidates_v1/candidate_registry.csv)、[独立复核](candidates_v1/independent_verification.json)和[文件哈希清单](candidates_v1/delivery_manifest.json)。

后续本人目录组织为candidates/（候选、原始组成和族账目）、frozen_inputs/（被批准输入及源摘要）、production_v1/（原生档案指针/传输块、actual_record_index、交付manifest、reports和selfcheck）、sealed_QC_only/（封存指针/索引与QC）。这些是待建目录约定，不代表现有文件或已完成交付。

每次交付PR写明release与stage，使用[模板](../shared/templates/README.md)填写真实结果。不得预填通过、真实种子或可执行命令；所有轮次、用途、种子、完整结果等外部元数据不能混入blind_inputs。封存数据默认不具备训练资格。


当前下一步：按[公共生产工具说明](../shared/production_tools/README.md)做无产谱预检。完整记录计划已备齐；公共release经审查放行后一次生成本人完整配额。预检不生成试片，当前release尚未放行。
