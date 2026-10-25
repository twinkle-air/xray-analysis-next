第四轮成员B交付入口

实际谱：0；状态：候选组成已提交，等待A的公共范围、条件/profile、freeze_v1 与完整生产 release。目标1,000配方、320个合并前设计族、20,000谱。

B 的主题是重叠峰与吸收/增强干扰（V/Cr、Mn/Fe、Co/Ni、As/Pb 等），逐族用 xraylib 实际线表在 150 eV 候选能窗内核对；能窗本身仍是候选筛选假设，不是已冻结的探测器响应。

当前已交付：candidates/ 下的 1,000 个候选组成、320 个设计族账目、逐条补偿账目、线表证据、历史与跨成员 L1 筛查、候选自检与独立复核。全部记录 requested_role 仅为名义预算，global_role_status=pending_global_freeze，eligible_for_training=false，未分配条件实例、噪声种子或能谱。

目录约定：candidates/（候选、原始组成和族账目）、frozen_inputs/（被批准输入及源摘要）、production_v1/（原生档案指针/传输块、actual_record_index、交付manifest、reports和selfcheck）、sealed_QC_only/（封存指针/索引与QC）。后三者待A冻结后再建。

复核命令（仓库根目录）：

    python datasets/round4/member_B/build_candidates.py
    python datasets/round4/member_B/verify_candidates.py

每次交付PR写明release与stage，使用模板填写真实结果。不得预填通过、真实种子或可执行命令；所有轮次、用途、种子、完整结果等外部元数据不能混入blind_inputs。封存数据默认不具备训练资格。
