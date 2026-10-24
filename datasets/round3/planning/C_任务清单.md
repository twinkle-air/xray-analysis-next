# 第三轮成员C任务清单

更新日期：2026-10-24。当前执行依据为已合并 PR #31 的 [owner_release_v3](../shared/releases/owner_release_v3.json)。公共输入与全局分配已冻结，**现在直接完成本人全量生产、自检和上传，提交完整 PR 后由 owner 统一审查**。不再先交90谱试片等待放行。生产已授权不代表你的数据已验收通过。

## 本次交付数量

| 类型 | 配方 | 完整底板族 | 硅酸盐/富铁配方 |
| --- | ---: | ---: | --- |
| 关键元素梯度 | 90 | 15，每族6水平 | 54/36 |
| 匹配干扰对照 | 50 | 10，每族5控制 | 30/20 |
| 负例/加标配对 | 60 | 30，每族2控制 | 36/24 |
| 常规独立背景 | 50 | 50 | 30/20 |
| 合计 | 250 | 105（合并前设计数） | 150/100 |

| 项目 | 数量 |
| --- | ---: |
| 基础谱 | 1,500 |
| 冻结分配的内部留出配方 | 31 |
| 追加T挑战谱（每留出配方6谱） | 186 |
| 最终总谱数 | **1686** |
| 原生密封批次 | 48 |

原计划phase=pilot的90谱属于基础1,500条，本次一并生成，不另加90条，也不设置中途审查。配方/族用途/profile/种子全部按 [freeze_v1](../shared/freeze_v1/README.md)；不能自选家族、交换用途、换种子凑数或自由jitter。

## 现在依次执行

1. 同步仓库最新main，在封存生成器所需依赖齐备的Python环境运行下面命令。若环境使用独立解释器路径，将 `-Python python` 替换为实际路径。
2. 一次执行本人全部冻结批次，完成生成、窗口预算、完整audit、完整物理replay和pack；不传--limit、不修改物理核心、不向已有sealed目录追加。任何失败保留产物和日志并停止，不降低预算或删难谱。
3. 核对本人1686条记录、250配方及105设计族完整变体，确认文件/完整结果哈希、全局ID和种子、整族用途与profile一致。T批次仅留出物理QC，脚本会显式带--heldout-qc。
4. 将原生无损ZIP、.sha256和完整自检证据整理到 `datasets/round3/member_C/`，在本人分支一次提交完整PR，base为main。PR标题建议 `data: round3 C complete 1686 spectra and full self-check`。由owner统一审查后决定是否合并；不要直接写main。

```powershell
powershell -NoProfile -File datasets/round3/shared/production_tools/run_member_full.ps1 -Member C -Python python
```

可加 `-PlanOnly` 预览批次，不生成数据。默认实际输出为 `work/round3/member_C_production_v1/`，该工作目录不是最终上传目录。逐批参数和续做缺失批次见 [完整命令清单](../shared/handoffs/20261024/member_C_full_commands.json)；[交接单](../shared/handoffs/20261024/member_C.md)提供补充说明。若已有实际完成的冻结批次，验证身份和完整QC后保留，按清单仅运行缺失批次，不重复计数、不覆盖原件。

## PR必须包含的材料

- README：实际数量、目录、执行命令、依赖/环境、耗时和体积、完成/失败/缺项情况；不将pending写成passed。
- 原生密封ZIP及其.sha256；保留blind_inputs、truth、full_results、inputs/configs、manifest/integrity、源码与依赖快照，不上传展开谱目录。
- 全量audit/replay/window_budget JSON、终端日志、真实命令和退出码；记录ZIP SHA/CRC核验。报告可无损打包，但不可只提交自述“检查通过”。
- 覆盖1686条谱的外置记录索引，带批次限定的唯一ID、配方/族/用途、profile、seed/repeat、blind/full/archive哈希；native generator_split不能直接当研究划分。
- delivery_manifest.json：交付文件大小和SHA-256；selfcheck_summary.json：实际检查范围和结果。保留已冻结候选、换算/补偿账目及输入身份，不重写候选数据。

owner统一核对数量/版本、文件及哈希完整性、实际全量自检证据、全局family/split。正常情况下不再替成员重复全量物理replay。

## 不要遗漏

- 32目标完整保留，O等基体参与模拟，ppm到百分数转换有账目；零/低含量和结构不可观察都不能从原定准确率分母中删除。
- blind仅原始计数和必要格式；不含元素、浓度档、真实刻度/profile、母族或种子。外部盲ID不暴露条件，native身份由隔离索引映射。
- 保留truth/full_results、六分量、谱线/窗外账目、manifest/integrity和源码/依赖快照；完整结果也必须有哈希。
- 已排除或失败的旧轮材料不能递归混入，transport_parts不是谱。ZIP/分块恢复后核对完整SHA、CRC和integrity。
- 不把自检通过写成真实设备准确度通过；前版模型仍只适用于合成研究，实测不能改synthetic标记冒充合成输入。

T不能用于训练、校正拟合、响应字典或选参；training_inclusion_approved仍为false。全量生产放行、数据PR审查通过、训练入库是不同状态。本清单替代此前同文件中的“方案未冻结/先试片等待复核”安排，历史版本保留在Git历史。
