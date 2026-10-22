# 填写模板（非执行配置、非验收结果）

所有JSON的is_template=true、usable_for_generation=false、production_started=false；null表示未知，pending表示未完成。它们是文档交接模板，没有配套自动schema校验器，不保证直接兼容生成器或索引加载器。

- [候选登记CSV表头](candidate_registry.template.csv)：一行对应一个实际采用配方，完整组成与原始配方另存JSON并填写路径。保留历史来源、母族/控制关系；名义浓度不能替代实际组成标签。记录ppm和百分数转换、O闭合及非目标补偿。
- [公共冻结清单](freeze_checklist.template.json)：A补齐全部配置/哈希、全局分组、用途/条件、种子、源依赖、试片和运行命令后评审；不能只把pending改成passed而无证据。
- [成员自检汇总](selfcheck_summary.template.json)：复制到本人目录后据实际全量audit/replay填写；不能提前填写expected=actual或零差异。
- [外部文件清单](delivery_manifest.template.json)：files逐项记录实际相对路径、字节数和SHA-256，覆盖完整结果、盲输入、配置/源码、报告和包；勿把清单自身哈希递归写入自身，另存于PR证据或外部摘要。

CSV只有表头，没有假配方、假种子或假通过记录。表中相对路径以本人交付目录为基准；公共冻结证据路径以round3为基准。涉及用途和条件的登记不放进blind_inputs。模板复制后仍须按真实契约完善，最终命名和机器格式在冻结时确认。
