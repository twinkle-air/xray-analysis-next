# 第二轮成员 A 数据交付 v2

2026-10-21。生成器 0.2.1 / 物理模型 0.2.0。按 GitHub 协作仓库 main 提交 `351eff645aeb7ad98a35b93371ad5cc9262a75a1` 的第二轮简化方案和 A 清单构建。你本人是 A 和项目主负责人；本次完成 A 的数据生产与自检，尚未替其他成员作全局确认。

## 实际完成

| 内容 | 实际结果 |
| --- | --- |
| 独立配方 | 250：硅酸盐/氧化物 150，富铁氧化物 100 |
| 配方情景 | 硅酸盐 90/30/30，富铁 60/20/20，分别为常规/稀疏边界/干扰 |
| 母族 | 210，含 10 个完整五成员干扰家族 |
| 条件及重复 | P1/P2/P3 各 500；固定 profile、每配方两次独立计数噪声、无 jitter |
| 正式谱数 | 1,500，30 个封存分片，每片 25 配方 × 2 |
| 结构审计 | 30/30 passed，errors 均为空 |
| 物理重算 | 1,500/1,500，30 份完整 replay，未使用 limit |
| 重算一致性 | 计数一致；报告最大数组差异 0；所有报告 same_environment=true |
| 配方/条件对应 | 全部 750 对重复的期望谱逐道完全相同；1,500 个子种子和全局 ID 唯一 |
| 完整性 | 1,500 条 blind/full 双哈希、30 个 ZIP 外部 SHA256 及原始输入摘要核对通过 |

这些结果是 A 自检，不是另一人独立复核、外部认证或真实样品定量准确度证明。

## 当前使用边界

**可交协调人合库复核，尚不可当作已冻结训练/验证/测试集。** B/C/D 候选未齐，跨成员精确组成去重、亲缘连通分组、首轮曝光处理和全局权威划分仍为 pending。实际索引所有记录 `eligible_for_training=false`、`benchmark_split=pending_global_family_split`；各片 generator_split 只是原生局部划分，不可直接拼接训练。

配方重新独立抽样，和可取得的首轮 A 2,500 配方及 B 100 试产配方比较无 12 位小数精度的组成键重复；该检查不覆盖全部历史 C/D 组成，也不证明不存在已知近邻。最近 L1 距离保留在候选检查中，仅作描述，不私设未经验证的家族阈值。

本轮采用内部按家族留出评估，不宣称独立保管人盲测。所有 profile 为 assumed_unverified；不据此证明实测浓度误差 5% 或真实设备响应。O 保留在基体组成中，不作为直接可测目标。

## 正式文件入口

- `repository_requirements/`：所依据提交的原始仓库说明快照；其中旧的“尚未生成”描述属于该提交历史，不是本次结果。
- `selfcheck_summary.json`：实际通过项、未完成项、数量、体积和中止批次说明。
- `production_v2/`：30 个 `P*_S*_dataset.zip` 及各自 `.zip.sha256`；包外 audit/replay、命令、退出码、耗时、日志及状态。每个 ZIP 含 blind_inputs、truth、full_results、原始输入、profile、manifest、integrity 和封存源码/环境。
- `package_manifest.json`：30 个正式压缩包与审计/重算报告的哈希、数量和耗时。
- `actual_record_index.jsonl`（程序读取）及 `.csv`（人工筛查）：真实 1,500 条谱的配方、母族、条件、重复、种子、原生族/划分及双哈希映射。JSONL 保留布尔字段类型；CSV 的 False 不能用 Python bool(string) 判断。
- `production_inputs_v2/`：本次 A 固定的三条件、250 主配方、10 个完整母族分片、各片种子、范围、源码及其 `freeze_manifest.json`。
- `candidates_v1/`：250 候选、范围/转换/覆盖/去重检查及配方登记。
- `final_artifact_checks.json`、`execution_code_checks.json`、`execution_timing.json`：最终一致性、脚本编译及正常/失败路径、实际运行时长。
- `delivery_hashes.json`：正式交付文件摘要。封存谱内还有原生 integrity 及 manifest 的 blind/full 双哈希。

以上目录及索引是内部证据，不直接发送给盲输入分析器。只传 blind JSON 的五个原生字段；转交时使用索引中的 `blind_public_id` 隐藏原批次/条件文件名，不向分析器暴露 P1/P2/P3 路径、标签、条件、种子或索引行。opaque ID 只是避免显式命名泄漏，不作密码学保密保证。

## 解包、定位与复核

总交付包保留 `datasets/round2/member_A/` 的相对结构。30 个原生 ZIP 不在总包中重复存放解压文件。按需将 `production_v2/P1_S01_dataset.zip` 解压到 `production_v2/P1_S01_dataset/`，其他同理；解压后的正式索引路径即可对应文件。本机另外保留原生目录，避免反复解包。

按各包 `reproducibility/requirements-lock.txt` 准备环境。复核使用该片自己的 `reproducibility/generator/fp_competition/app.py` 执行 audit/replay，输出写包外新路径；全量 replay 不传 limit。命令记录保存本次真实绝对路径，其他机器须替换本地根路径，不能原样复制旧路径。

若单独重建候选，先将 `production_inputs_v2/generator/fp_competition` 复制到新项目根目录的 `fp_competition`，按输入账目运行 build_candidates.py；本次正式谱输入已经固定，不需要重建候选才能复核。

再生成需在新工作副本运行 `run_sharded_production.py --preflight` 和 `--run`，保持既定相对目录、冻结输入及依赖，并保证输出 `production_v2` 尚不存在；脚本拒绝覆盖原产物。代码语法检查、输入哈希变化拒绝、输出目录冲突拒绝、未完成时拒绝写成功汇总的路径已验证。物理核心及三个基线模块没有改动。

## 设计与公共配置

常规硅酸盐范围来自原矿物配置，富铁来自已记录的 B 设计范围；稀疏/边界允许精确零和显式扩大的平衡范围。全部都是人为模拟设计，不是实际矿石总体分布。provenance 保留 compounds_percent、trace_ppm 和换算账目，ppm 使用 10000 ppm = 1 mass percent。

As/Pb 和 S/Pb 各做五种完整对照；S 由 CaSO4 提供，会同时改变 Ca/O 与平衡组分，不能当作严格单变量 S 干预。32 目标的零/低/更高含量覆盖见 coverage，低含量分箱不是检出限。

P1/P2 沿用原 A 实际配置，P3 沿用原 B 低电压配置（20 kV、60 s、0.008 keV/channel、零点 0.3 keV）；没有混用旧规划中另一个同名 P3。完整参数与每片实际 seed 以 production_inputs_v2/A_run_config.json 及 freeze_manifest 为准。这只是 A 本次输入固定，不冒充 B/C/D 输入已确认。

## 中止与历史记录

初始三个大批次因串行效率而中止并改为完整母族分片；本地 `production_v1/` 保留 102 个未验收结果文件，状态 cancelled_partial_preserved_not_delivery。它们不计入正式 1,500，不进入正式总包，不用于训练；不是选择性删除困难谱或修改物理算法。

`production_inputs_v1/`、`run_production.py`、`planned_record_index.csv` 仅为本地中止/预排历史，均非当前入口。正式包排除它们及中止数据，避免将历史 seed/ID 和正式分片混用；早先候选 ZIP 保留原有历史身份。

## 实际体积与时间

正式原生目录合计 1,638,811,768 bytes，30 个压缩包合计 333,052,116 bytes。正式生成、全量审计/重算及分片打包的实测并行墙钟时间 1064.6 秒；不含候选准备、已中止 v1 和最终汇总打包。15 个并行工作进程的各命令耗时不能简单相加当作墙钟时间，也不能直接外推到队友机器。
