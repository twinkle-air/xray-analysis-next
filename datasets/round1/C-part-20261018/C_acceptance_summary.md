# C 部分验收汇总 · P5 留出条件批次

## 身份
- 生成器版本：0.2.1；物理模型版本：0.2.0
- 条件配置：candidate_holdout_P45_Al50_air1（`configs/profile.json`，SHA-256: e30ba2115f3b3507b835cda8f5e21209e615348e87ef7f6a7a32999d424cb280）
- 主配方表：`master_samples.json`，语义摘要 6673fb80fb961c6700dc223ddfe0d419a3b9cc3d5b858eceb28390736e4ccaff
- 物理核心快照摘要：e820ecdb5ed5fbceb870f382c8c7c411ba85c65673bc19258fb935f562ed83b0
- 种子：批次 2026101805，划分 20261018；每谱子种子见 truth.jsonl
- 本次产出全部为合成数据，未通过真实设备校准，不证明真实含量准确度。

## 规模与划分
- 配方数：1000（常规 600、稀疏/边界 200、干扰对照 200）
- 谱数：2000，每配方 2 次独立泊松噪声
- 成分族（generator_split）：{'train': 1400, 'validation': 292, 'test': 308}
- 权威划分（benchmark_split，按 parent_family）：{'train': 1402, 'validation': 302, 'test': 296}
- 同一母配方的对照变体与噪声重复均未跨集合。
- 数据集目录大小：1457.2 MiB；ZIP：329.0 MiB。

## 工程检查
- 全量 audit：passed，检查 2000 条
- 全量物理重算：passed，all_records，2000 条
- 最大数组绝对差异：0.0
- 环境一致：True
- ZIP 与外部 SHA-256：9178746d90e26e45d64a8a9f15ca35736ba363110d535d787e3e589fbf3bf3f2  P5_dataset.zip
- 错误：0 项
无错误。

## 覆盖情况
- 能窗：{"unit": "keV", "first_center_range": [0.6, 0.6], "last_center_range": [29.258000000000003, 29.258000000000003], "lower_edge_range": [0.593, 0.593], "upper_edge_range": [29.265000000000004, 29.265000000000004]}
- 窗外损失比例范围：{"definition": "sum(outside_window_counts) / detected_signal_before_window_counts, excludes artificial background", "range": [0.0007244562965419613, 0.010505917474488273]}
- Ba 窗口统计：{"present": 1246, "L_center_in_window": 1246, "M_center_in_window": 1246}
- 元素零/低/中/高覆盖见 `P5_coverage_statistics.json`。

## 未验证事项
- P5 是候选模拟配置，不是真实未见设备；保留真实设备/真实样品的科学验证。
- 模型未包含死时间、堆积、粒度、水分、多层、多次散射与粗糙度。
- 含量相对误差 ≤5% 的结论不能由本批合成数据得出。

## 存储与时长（实测，供后续批次预算）
- 单谱落盘 0.729 MiB；本批数据集目录 1457.2 MiB，ZIP 329.0 MiB（压缩比 0.226）。
- 生成实测 1.8–2.5 s/谱（`secondary_layers=32`，单进程）；全量物理重算 2.6 s/谱；全量 audit 约 0.1 s/谱；打包 1.46 GiB→329 MiB 实测 81.7 s。
- 外推：单批上限 10 000 谱约需 7.1 GiB 目录 + 1.6 GiB ZIP、生成 5–7 h；B 阶段预算 50 000 谱（5 批）约需 36 GiB + 8 GiB ZIP、生成 25–35 h（不含检查与打包）。

## 交付副本
推送用本地仓库 `D:\xray-analysis-next-c-part`（分支 main，工作树 1.46 GiB，.git 打包 281 MiB）。
副本 4061 个文件与原件逐文件 SHA-256 比对 0 处不一致；已用包内快照独立复核：`P5_delivery_copy_qc.json`，passed，2000 条，0 项错误。
用副本重新 `pack` 得到的 ZIP 与原件 SHA-256 相同（9178746d90e26e45d64a8a9f15ca35736ba363110d535d787e3e589fbf3bf3f2  P5_dataset.zip），归档可确定性重建。
`.gitattributes` 关闭文本转换，clone 后的逐记录 SHA-256 与索引一致；329 MiB 的 ZIP 超 GitHub 单文件上限，
按 `PUSH_TO_GITHUB.md` 走 Release 资产或 Git LFS。
