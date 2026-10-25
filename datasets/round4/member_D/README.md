# 第四轮成员D交付入口

实际谱：0；状态：候选阶段已完成（PR #48），公共范围、条件和freeze_v1审查版已准备，等待协作者审查及完整生产release放行。目标1,000配方、20,000谱。先读[本人任务](../planning/D_任务清单.md)及[共同方案](../planning/第四轮数据构建方案.md)。

候选交付见[candidates/](candidates/README.md)：1,000配方/320合并前族、独立复核0错误；已完成与已合并A、C第四轮候选的逐对筛分，四方候选现已全部合并，本次完整全局亲缘检查通过，见公共冻结报告。不含能谱、条件实例或噪声种子。A release通过后按冻结名册一次生成全部20,000谱，不做试片。

后续本人目录组织为candidates/（候选、原始组成和族账目）、frozen_inputs/（被批准输入及源摘要）、production_v1/（原生档案指针/传输块、actual_record_index、交付manifest、reports和selfcheck）、sealed_QC_only/（封存指针/索引与QC）。这些是待建目录约定，不代表现有文件或已完成交付。

每次交付PR写明release与stage，使用[模板](../shared/templates/README.md)填写真实结果。不得预填通过、真实种子或可执行命令；所有轮次、用途、种子、完整结果等外部元数据不能混入blind_inputs。封存数据默认不具备训练资格。


当前下一步：按[公共生产工具说明](../shared/production_tools/README.md)做无产谱预检。完整记录计划已备齐；公共release经审查放行后一次生成本人完整配额。预检不生成试片，当前release尚未放行。
