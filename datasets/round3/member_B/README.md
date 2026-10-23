# 第三轮 B：候选阶段交接包

状态：**250 个候选配方和 105 个设计族已重建并通过本地自检；正式谱 0 条；等待 A 全局复核与生产冻结。** 本目录作为候选阶段交接包，通过任务分支 PR 提交给 A 复核；是否合并由仓库协作者审查决定。

## 候选与依据

- 配额：90 梯度、50 干扰、60 负例/加标配对、50 常规；硅酸盐/氧化物 150、富铁氧化物 100。
- `candidates/B_samples.json` 保留全部完整元素质量百分数、原始底板化合物/痕量 ppm、原始元素组成、控制元素、换算、补偿和族关系。氧作为基体元素参与模拟；32 个目标元素均保留。
- `candidates/family_registry.json` 保留 A 分配的 B 族 ID、设计种子、底板种子、完整族成员。`candidates/formula_registry.csv` 为供复核的配方索引。
- `inputs/design_allocation.json` 来自仓库 `datasets/round3/shared/preparation_v1/design_allocation.json`；`inputs/design_ranges.json` 来自 `datasets/round3/member_A/inputs/design_ranges.json`。复建脚本固定使用仓库内 `datasets/round3/member_A/inputs/generator/fp_competition` 的封存源码与 `datasets/round3/member_A/inputs/historical_compositions.json` 的历史快照，并逐项校验 SHA-256。设计输入对应的 `main` 提交为 `1131a44969825dd424e38d3a487e1eb53eef2b77`。
- 分配中的 `design_seed` 和记录中的 `background_seed` 只用于候选设计，**不是**已冻结的计数噪声种子。

## 本地检查

`selfcheck_summary.json` 给出汇总；`candidates/candidate_checks.json` 保留每条候选的历史最近邻及全部检查结果。250 个配方均完成严格闭合、原始与采用组成的独立重算、控制浓度和范围检查；105 族完整，32 个目标元素均至少有一个正值候选。在隔离的仓库目录结构中，从正式 `member_B` 路径两次执行复建；更新后的六份候选文件分别与两次输出字节一致，见 `rebuild_verification.json`。该验证使用与仓库封存文件 SHA-256 一致的输入副本，未将本地镜像误写为完整 Git 克隆。

历史近邻现使用 A 封存的 3,800 条历史组成快照（SHA-256 `8a4461df5020c07a89603adfab164873e854a03498cf62358c5cf80fe1fc6473`）；最小完整元素组成 L1 距离为 2.9356064665780197 质量百分点，未发现 L1≤0.5 的匹配。**这不是全局去重结论**：未记录或不可用的亲缘关系及尚未提交的 C/D 实际候选仍须 A 统一复核。

## 文件与复建

- `build_candidates.py`：从两份设计输入及 A 封存源码、历史快照构建 B 候选；缺失或哈希不符会报错，遇到已存在输出目录会拒绝覆盖。
- `finalize_candidates.py`：生成自检汇总和 `candidate_manifest.json`，其中列出交接文件大小与 SHA-256。
- `A_review_request.md`：交给 A 的具体复核事项及待冻结项。

在协作仓库检出目录根部，使用具备 `numpy`、`scipy`、`xraylib` 的 Python 环境运行（本次验证：Python 3.13.14、numpy 2.4.6、scipy 1.17.1、xraylib 4.3.0）：

```powershell
python -B datasets/round3/member_B/build_candidates.py --out "$env:TEMP/round3-b-candidates-rebuild-new"
```

实际隔离复建命令、环境、退出码、六文件哈希与缺失历史快照时退出码 1 的记录见 `rebuild_verification.json`。四份配方相关文件（`B_samples.json`、`family_registry.json`、`formula_registry.csv`、`coverage.json`）相对初版 PR 保持原 SHA-256；历史检查及输入身份因改用 A 的 3,800 条封存快照而更新。

正式 90 谱试片、1,500 基础谱和 T 留出谱尚未开始。A 需先确认全局候选闭包、用途/条件与噪声种子、profile、源码/依赖身份和真实命令；不得把本地候选自检写成训练谱验收或真实设备精度验证。

