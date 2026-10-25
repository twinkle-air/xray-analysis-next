# 第四轮公共输入与冻结（A维护）

当前未冻结，usable_for_generation=false，production_started=false。先按[方案](../planning/第四轮数据构建方案.md)和[分工](../planning/ABCD分工与数量.json)准备候选，不批量出谱。

A后续实际建立并核对：

1. scope/：32元素顺序、O及其他基体、设计/基体范围、零与加标账目、线表与单位、成员ID预留。
2. profiles/：完整开发条件分布/实例、单独的sealed_QC_only挑战条件、源依据与QA。10个槽位不是10个共享固定profile；实际物理值现在保持pending。
3. historical/：已知round1/2/3含pilot/失败/曝光配方及源哈希，跨轮和跨成员统一亲缘连通证据。
4. freeze_v1/：全局family_assignments、record_plan、batch_plan、条件与阶段映射、record seed与opaque ID、全部输入/源码/依赖哈希。模板不兼容现有runner的假设必须在真实适配后消除。
5. releases/：实际可运行命令、--help及质量样本证据、已放行成员与阶段、真实版本。release不等于训练许可或精度通过。
6. accepted_v1/：仅在各成员真实交付验收后建立统一实际索引、原档恢复指针和必要闭环证据；不能现在填写“已验收100000”。

[模板与表头](templates/README.md) · [验收与封存规则](验收与封存规则.md)

每人只负责自己全量QC一次，A做数量/版本、文件/哈希、自检证据、全局闭环四项必要复核。无额外交叉全量重放要求；发现异常再查。
