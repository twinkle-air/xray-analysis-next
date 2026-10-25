# 第四轮公共输入与冻结（A维护）

正式放行（2026-10-25）：项目负责人已明确授权ABCD完整生产，追加协作者审查已由负责人豁免。A 40,000谱，B/C/D各20,000谱，不做试片。当前准入以[production_release_v1.json](releases/production_release_v1.json)为准；封存输入内的待审查文字是形成时的历史状态。


ABCD共5,000个候选已经合并，全局1,600族亲缘和已登记历史组成检查通过。完整条件/用途/种子/记录计划及生成器包装层已准备为[freeze_v1审查版](freeze_v1/README.md)。当前usable_for_generation=true，完整配额生产已由负责人放行；实际生成进度以各成员记录为准。

- [全局亲缘报告](freeze_v1/global_closure.json)、[整族用途](freeze_v1/family_assignments.json)、[来源与哈希](freeze_v1/input_identity.json)
- [条件定义与覆盖限制](freeze_v1/profile_distribution_development.json)、[完整数量](freeze_v1/plan_summary.json)、[无产谱核验](freeze_v1/independent_static_verification.json)
- [四人预检与失败路径核验](reviews/20261025/verification_summary.json)
- [真实生产工具与命令](production_tools/README.md)、[生产release](releases/production_release_v1.json)

本轮不安排试片。A一次生成40,000谱，B/C/D各20,000谱；stage1/2/3只用于后续学习曲线。所有成员各自完整audit/replay/QC一次，A核对数量/版本、文件及哈希、自检证据、全局闭环四项必要证据。封存条件/谱仅供生成、物理QC和锁定模型后的评价，不进入训练、字典、校正或选参。

已补齐A候选交付中遗漏的delivery_manifest文件，候选配方本身字节未变；B的pending历史标记由本次真实全局近邻证据解释，不能代替用途名册。细节见全局报告notes。

[验收规则](验收与封存规则.md) · [填写模板](templates/README.md)
