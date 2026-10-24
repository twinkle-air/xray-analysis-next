# 第三轮已合并数据：协调人实际索引 v1

数据源main `67a215a4c169d7ba6ac010e79a565dfbda9489a1`（已合并A #30、B #35、C #33、D #34）。1000配方、420设计族、6000基础+900T=6900谱，193原生密封ZIP。每条记录的批次/native ID、配方/族/用途、profile/repeat/seed逐字段符合freeze_v1/record_plan.csv；全局ID、opaque ID、noise seed唯一；用途数量train4200/validation900/internal_holdout1800，其中留出包含900T。

- actual_record_index.csv：协调人统一实际登记，保留blind/full/archive SHA、ZIP内部成员路径及固定用途；B的原record_uid规范化为batch/native形式的global_record_id。
- archive_index.json：193个已审查原生ZIP的仓库路径、大小、SHA-256与Git blob身份，引用原件而不重复上传数据。
- closure_verification.json：四份main源索引的Git blob/SHA与全量核验结果。源indices字段全部对照实际main身份。
- manifest.json：本目录文件大小/SHA；排除manifest自身。

本目录不改配方、profile、种子、冻结输入或原生generator_split；研究用途遵循外置冻结整族分配。索引含分组/真值关联元数据，须与盲推理输入隔离，不能作为推理特征。T只留出物理QC，禁止训练、校正、字典、选参；每条eligible_for_training=false，training_inclusion_approved=false，未启动训练或宣称模型就绪。

核验复用四名成员已审查的完整audit/replay/窗外预算/ZIP证据；本次只做协调人实际索引合库与身份/数量/分组复核，未重复全库物理计算。历史范围限freeze_v1已知记录，不认定外部独立盲测或真实仪器准确度。
