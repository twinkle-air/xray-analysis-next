# 第四轮成员C交付入口

正式放行（2026-10-25）：项目负责人已明确授权ABCD完整生产，追加协作者审查已由负责人豁免。A 40,000谱，B/C/D各20,000谱，不做试片。当前准入以[production_release_v1.json](../shared/releases/production_release_v1.json)为准；封存输入内的待审查文字是形成时的历史状态。


实际谱：0；状态：候选阶段已完成（PR #47），公共范围、条件和freeze_v1审查版已准备，等待协作者审查及完整生产release放行。目标1,000配方、20,000谱。先读[本人任务](../planning/C_任务清单.md)及[共同方案](../planning/第四轮数据构建方案.md)。

候选交付见[candidates/](candidates/README.md)：1,000配方/320合并前族、核验0错误；不含能谱、条件实例或噪声种子。A release通过后按冻结名册一次生成全部20,000谱，不做试片。

后续本人目录组织为candidates/（候选、原始组成和族账目）、frozen_inputs/（被批准输入及源摘要）、production_v1/（原生档案指针/传输块、actual_record_index、交付manifest、reports和selfcheck）、sealed_QC_only/（封存指针/索引与QC）。这些是待建目录约定，不代表现有文件或已完成交付。

每次交付PR写明release与stage，使用[模板](../shared/templates/README.md)填写真实结果。不得预填通过、真实种子或可执行命令；所有轮次、用途、种子、完整结果等外部元数据不能混入blind_inputs。封存数据默认不具备训练资格。


当前下一步：按[公共生产工具说明](../shared/production_tools/README.md)做无产谱预检。完整记录计划已备齐；公共release经审查放行后一次生成本人完整配额。预检不生成试片，当前release已正式放行。

## 已归档的 P5 历史留出数据（2026-10-27）

[imported_P5_v2_20261020/](imported_P5_v2_20261020/RELOCATION.md) 从原 `datasets/C-part-v2-20261020/` 原样迁入，包含 2,000 条 P5 条件留出谱。负责人确认保留留出用途；不用于训练、调参或模型选择，不计入冻结方案 C 部分的 20,000 条生产配额。

此次迁移时 `production_v1/` 正式交付仍未提供。上文“实际谱：0”指冻结方案的正式生产交付；历史归档与正式生产分开记账。
