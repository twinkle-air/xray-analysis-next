# 第四轮成员B交付入口

实际谱：0；状态：等待公共范围和全局冻结。目标1,000配方、20,000谱。先读[本人任务](../planning/B_任务清单.md)及[共同方案](../planning/第四轮数据构建方案.md)。

后续本人目录组织为candidates/（候选、原始组成和族账目）、frozen_inputs/（被批准输入及源摘要）、production_v1/（原生档案指针/传输块、actual_record_index、交付manifest、reports和selfcheck）、sealed_QC_only/（封存指针/索引与QC）。这些是待建目录约定，不代表现有文件或已完成交付。

每次交付PR写明release与stage，使用[模板](../shared/templates/README.md)填写真实结果。不得预填通过、真实种子或可执行命令；所有轮次、用途、种子、完整结果等外部元数据不能混入blind_inputs。封存数据默认不具备训练资格。
