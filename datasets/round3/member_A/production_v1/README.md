# 第三轮 A 全量交付

250配方、105完整设计族：基础1,500谱（包含PR #28已封存的90谱试片）+42个内部留出配方×6条T挑战=252谱，共1,752。只新增39个原生密封ZIP；其余8个试片ZIP保持原字节，由archive_index引用，不重复计数。

全部47批、1,752条谱实际通过预注册窗外预算、完整audit、完整物理replay（不传--limit）及pack；最大数值数组差见selfcheck_summary。ZIP SHA-256/CRC与内部integrity全部核对。每批含blind_inputs、truth、full_results、六分量、谱线/窗外账目、inputs/configs、生成器/依赖/环境快照。物理核心和模型没有修改。

actual_record_index.csv是唯一A外置记录索引，固定全球ID、配方/设计族、用途、profile、子种子和blind/full/archive哈希；不能递归把试片、盲包、解压目录或旧轮混在一起加载。原生generator_split仅生成器账目，不是研究划分。archives/A_round3_blind_inputs.zip包含1,752个opaque命名的原始2048道计数文件和格式说明，标签/条件/族/种子只在隔离索引与truth内。

所有实际命令、退出码、环境、耗时和窗口结果无损保存在reports/A_all_batch_QC.zip，按batch_id分目录；archive_index记录每批audit/replay的ZIP成员路径。actual_record_index覆盖基础与T。T仅供内部留出完整性/物理QC，未用于模型、字典、校正或选参。当前仅成员数据交付通过；全局四成员合库验收与训练入库仍待其余成员实际交付，不宣称真实设备准确度或外部独立盲测。
