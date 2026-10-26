# 第四轮 A 全量交付：40,000 条合成谱

2026-10-27 完成本地生成与成员完整自检，当前状态是待负责人验收，eligible_for_training=false。训练用途 32,000 条，验证 4,000 条，密封测试 4,000 条；400 批，每批 100 条。正式 release 为 shared/releases/production_release_v1.json，全局冻结 SHA-256 为 25deee3198281d033641ca45817a40727461269df11d653df5ca842b908fa519。

## 文件与恢复

- archives/：400 个原生批次 ZIP 及逐包 SHA-256，含盲谱、真值、完整结果、六分量、窗外账目、输入、配置、源码和依赖快照。
- actual_record_index.csv：40,000 行权威实际索引，批次限定 global_record_id，不将 native 局部编号当全局编号。
- blind/：整合盲包的无损分片；按 [恢复说明](blind/RESTORE.md) 重建根目录 A_round4_blind_inputs.zip，校验整体 SHA-256、CRC 和 40,000 个 opaque 文件名。
- reports/A_all_batch_QC.zip：400 批全量审查、物理 replay、窗口账目、实际索引及命令记录。
- reports/exact_kernel_execution_v4.zip：精确积分缓存性能适配器、对照验证、逐批缓存及独立重算前清空证据。
- reports/A_execution_recovery_sources.zip：补充原始调度/恢复/性能验证源码和同批 100 条完整流程提速实测；物理核心文件未改动，执行时明确加载性能适配器，逐条原 simulate 及全量 replay 保留。
- reports/A_failed_attempt_recovery.zip：内存故障报告、现场逐文件哈希及同批重算说明；失败原谱本地保留，不重复计入 40,000 条。

delivery_manifest.json 保留原始逻辑交付清单（恢复盲包后文件完整）；publication_manifest.json 记录 Git 中实际运输文件及 SHA-256，自身不递归记账。archive_index.json、自检汇总与原始清单均未篡改。不要把压缩档、盲包、分片或隔离现场重复算作额外谱。

## 自检与边界

全部 400 批完整 audit/replay、预注册窗口预算和 ZIP 核验通过，无未解决最终失败。上传前逐项核实原交付文件大小/SHA、全局冻结身份、实际索引与冻结所有列一致、唯一全局/opaque ID 和 noise seed，以及全部 QC 覆盖范围。盲包已实际从运输分片恢复并通过校验。恢复脚本编译与缺片、损坏片、已有不同输出拒绝覆盖检查通过。

用途与 stage 以 shared/freeze_v1 和本实际索引为准。密封数据仅供 QC，禁止训练、字典、校正与选参；发布不自动构成训练准入。工程核验不等于真实仪器校准或 95%/5% 独立盲测准确度验收。跨成员闭环由负责人另行汇总，不能将 A 成员自检当成 ABCD 全局最终验收。
