# 致 A：第三轮 B 候选复核请求（随 PR 提交复核）

B 已按公共设计分配重建 250 个候选配方、105 个完整设计族；原始底板、换算与补偿账目在 `candidates/B_samples.json`，族登记在 `candidates/family_registry.json`，复核索引在 `candidates/formula_registry.csv`。本地自检、历史最近邻和文件哈希分别见 `selfcheck_summary.json`、`candidates/candidate_checks.json`、`candidate_manifest.json`。

请 A 在全局主表中复核并反馈：

1. 将 B 的 250 个实际元素组成与 A/C/D 候选及完整历史快照一起做去重、L1 近邻和母族连通闭包；确认是否有必须并组或重制的配方。
2. 确认每个 B 设计族的最终用途、三开发条件映射、长曝光覆盖，以及新留出配方名单。完整族不得跨用途拆分。
3. 对通过复核的候选发布正式 profile、生成器/依赖身份、每批噪声子种子、split seed 和可执行命令；再安排 90 谱试片与后续生产。T1/T2/T3 仅供留出 QC。

本地核查仅覆盖第一轮 A 2,500 与第二轮 B 250 条；第三轮跨成员和完整历史复核未完成。候选设计种子不代表生产噪声种子。本包没有生成或申报任何第三轮正式谱。

本文件随 B 候选阶段交接包提交至任务分支 PR，供 A 完成全局复核；正式谱仍待生产输入冻结。

