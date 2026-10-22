# 0.2.1 可追溯数据包整改

本轮修改独立生成器的导出、封存、QC和说明，不改AI Skill/Agent运行能力。core.py、minerals.py、robustness.py与本轮修订前字节相同，摘要见physics_baseline.json；物理模型版本仍为0.2.0，交付版本在version.py中为0.2.1。

## 实施

- batch/API/GUI默认导出每条完整full_results，不再需要队友另加一个未交付的导出补丁。
- 每条manifest增加blind_input_sha256/full_results_sha256，保留sha256兼容别名；全包integrity.json排除自身。
- 封存实际样本、配置、原始CLI输入、recipe、完整源码快照及真实Python/依赖/数值线程环境；原文件未提供时不补造。
- 增加audit、replay、pack命令。audit核查全包与合成流程；replay默认全部物理重算，--limit明确标为抽查；pack拒绝QC失败并提供ZIP/外部摘要。
- 增加可选split_seed，保留默认沿用批次seed的旧抽样行为；配方、批次和子种子作用在README中分开。
- 每条保存能量中心/边界，整批实际统计；窗外计数账目涵盖荧光及散射，比例有明确定义。
- Ba报告仅给线系/窗口统计，不从K线超窗直接断言不能推断含量。
- 导出标签复用物理核心已有的element_support记录，只为未覆盖目标补算，减少重复查询；不改变物理结果。

## 证据边界

同一输入和核心源码的数值复现、历史来源身份、真实含量准确度是三项独立结论。当前保护模块摘要只证明本轮工作区基线保留，不证明此前缺失的队友修改源码是什么。原300条数据和其README/审查记录不覆盖。

验收日志、完整端到端结果见本次交付VALIDATION.md及validation_record.json。失败的验证输出不作为正式样例，临时文件在结果记录后清理。
