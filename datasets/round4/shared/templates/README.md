# 第四轮填写模板（不可执行）

CSV仅提供表头，不含假配方、种子或通过记录。JSON标明is_template=true、usable_for_generation=false、production_started=false；null是未知，pending是未完成。没有自动校验器，不保证直接兼容旧生成器或模型加载器。

- candidate_registry.template.csv：一行一种实际组成；完整used_percent、原始底板、母族、补偿账目另存JSON。最终用途由A冻结。
- actual_record_index.template.csv：一行一条实际谱，外部保存家族/用途/stage/条件/种子以及blind/full/原档路径和哈希；不能作为盲输入。
- freeze_checklist.template.json：公共冻结的证据路径和批准状态，A填写。
- selfcheck_summary.template.json：成员真实交付数量、全量QC命令/证据和失败，不能预填expected=actual。

交付manifest还须逐个覆盖真实文件大小/SHA，排除清单自身递归哈希。相对路径以实际成员交付根目录为准，公共证据相对round4根目录。模板文件名中的template须在实际交付后按契约替换。
