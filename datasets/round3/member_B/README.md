# 第三轮 B：候选阶段本地交接包

状态：**250 个候选配方和 105 个设计族已重建并通过本地自检；正式谱 0 条；等待 A 全局复核与生产冻结。** 本目录作为候选阶段交接包，通过任务分支 PR 提交给 A 复核；是否合并由仓库协作者审查决定。

## 候选与依据

- 配额：90 梯度、50 干扰、60 负例/加标配对、50 常规；硅酸盐/氧化物 150、富铁氧化物 100。
- `candidates/B_samples.json` 保留全部完整元素质量百分数、原始底板化合物/痕量 ppm、原始元素组成、控制元素、换算、补偿和族关系。氧作为基体元素参与模拟；32 个目标元素均保留。
- `candidates/family_registry.json` 保留 A 分配的 B 族 ID、设计种子、底板种子、完整族成员。`candidates/formula_registry.csv` 为供复核的配方索引。
- `inputs/design_allocation.json` 来自仓库 `datasets/round3/shared/preparation_v1/design_allocation.json`；`inputs/design_ranges.json` 来自 `datasets/round3/member_A/inputs/design_ranges.json`。参照 A 的第三轮候选构建方法，使用本地 `fp-spectrum-generator-competition-v0.2.1` 的化合物到元素换算和底板采样函数。仓库检查时 `main` 为 `1131a44969825dd424e38d3a487e1eb53eef2b77`。
- 分配中的 `design_seed` 和记录中的 `background_seed` 只用于候选设计，**不是**已冻结的计数噪声种子。

## 本地检查

`selfcheck_summary.json` 给出汇总；`candidates/candidate_checks.json` 保留每条候选的历史最近邻及全部检查结果。250 个配方均完成严格闭合、原始与采用组成的独立重算、控制浓度和范围检查；105 族完整，32 个目标元素均至少有一个正值候选。两次独立复建的六份候选文件字节一致，见 `rebuild_verification.json`。

历史近邻目前只覆盖本地可用的第一轮 A 2,500 条与第二轮 B 250 条，合计 2,750 条；最小完整元素组成 L1 距离约 2.935606 百分点，未发现 L1≤0.5 的匹配。**这不是全局去重结论**：A 仓库的完整历史快照、第三轮 A/C/D 候选和未记录的亲缘关系仍须 A 统一复核。

## 文件与复建

- `build_candidates.py`：从两份输入构建 B 候选，遇到已存在输出目录会拒绝覆盖。
- `finalize_candidates.py`：生成自检汇总和 `candidate_manifest.json`，其中列出交接文件大小与 SHA-256。
- `A_review_request.md`：交给 A 的具体复核事项及待冻结项。

在工作区根目录、使用本地已有 Python 环境运行：

```powershell
& 'datasets/B-part/work/venv313/Scripts/python.exe' -B 'datasets/B-part-20261023/build_candidates.py' --out 'datasets/B-part-20261023/candidates_rebuild_new'
```

正式 90 谱试片、1,500 基础谱和 T 留出谱尚未开始。A 需先确认全局候选闭包、用途/条件与噪声种子、profile、源码/依赖身份和真实命令；不得把本地候选自检写成训练谱验收或真实设备精度验证。

