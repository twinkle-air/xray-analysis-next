# A 部分数据集（成员 A）

本目录对应《三人训练集产生方案 v1.0》的成员 A，不是《数据产生要求》的阶段 A。

## 配方设计

- `A_samples.json`：2,500 条独立采用组成，常规 1,500、稀疏/边界 500、干扰对照 500。
- `A_formula_registry.csv`：稳定配方 ID、parent_family、情景、组成 SHA256；等待 C 合并全局主表并按家族划分。
- `A_design_ranges.json`：常规配方范围，来自本项目 `fp_competition/mineral_design_ranges.json`；它是人为模拟设计，不是实际地质样品分布。
- `build_A.py`：固定种子的配方构建记录，调用现有软件的化合物换算和配方设计功能，不修改生成器核心。
- `A_coverage.json`：32 个目标的零/低/较高含量覆盖和缺口。低含量统计口径为 0 < 元素质量百分数 ≤ 0.1%，并非检出限。

常规配方沿用已有氧化物均匀抽样、正痕量对数均匀抽样及 25% 痕量缺失概率。稀疏/边界配方另设零、低含量及 0.02/0.05/0.1/0.25/0.5/0.75/1 的组分缩放，以 SiO2 补足；其中纯 SiO2-Al2O3 和 SiO2-Fe2O3 对照不受常规 Al2O3 下限约束。每条配方保存实际组分与换算 provenance。Si 和 O 是本批必需基体，不要求为零。组分采样范围和缩放是方法研究假设，不是牌号或矿物总体的科学认证。

干扰配方共 100 个母配方，每个 5 个对照：两者均零、仅前者、仅 Pb、共同低量、前者增至 10 倍。50 组 As/Pb（As、Pb 各以 100 ppm 为基准）；50 组 S/Pb（CaSO4 0.1% 与 Pb 100 ppm 为基准）。S 以 CaSO4 加入，同时改变 Ca/O，不能当作严格单变量 S 对照。不同对照通过 SiO2 重新补足；同一母配方的 5 个成员共享 parent_family。谱线重叠和响应支持以实际 full_results 为准，不能由候选干扰名称直接断言可分辨或可定量。

## P1/P2 试产

`A_pilot_samples.json` 选择 100 条：常规 20、稀疏/边界 20、干扰 12 个完整家族共 60。`pilot_P1` 和 `pilot_P2` 各 200 谱，固定 profile、replicates=2、无 jitter，分别使用 2026101801/02 批次种子，split seed=20261018。两次重复只改变计数噪声。试产沿用原生 blind_inputs、truth、full_results、源码/环境快照及完整性清单。

**本批全部标为 workflow_pilot_only，禁止按生成器内部 split 直接作为正式训练/验证/测试集。** 原生 split 仅隔离完全相同组成，无法保证干扰家族隔离；不得修改密封 truth/manifest 来迁就全局划分。独立的 `pilot_index.csv` 记录 parent_family 和用途，正式全库划分由 C 在 5,000 主表冻结后另行执行。

生产后，审计、全量物理 replay 报告存放在密封数据集外。两批完整重算原始状态为 `passed_with_environment_differences`：生成时未设置线程限制，复算设置 OPENBLAS_NUM_THREADS=1、OMP_NUM_THREADS=1；Python/依赖及其他记录环境一致，全部计数一致，最大数组差异为 0。环境对照保存在 `P1_replay_environment.json` / `P2_replay_environment.json`，不篡改原始报告为“环境相同”。辅助检查脚本最初只接受 passed，因此在完整报告写出后拒绝继续打包；核明仅线程设置差异后复用已经写出的完整报告，执行后续打包。`*_check_timings.json` 对复用报告的耗时记为 null，不虚构此前计算时间。单人自检不构成三人分工规定的交叉复核；最终状态保留 pending_independent_validation。

## 下载与复核

GitHub 目录中的 `P1_pack.zip`、`P2_pack.zip` 各含完整密封批次（200 谱），对应 `.zip.sha256` 是外部哈希；本地目录另外保留已经解压的 `pilot_P1`、`pilot_P2`，不在 Git 中重复存储。审计/重算 JSON、运行日志和汇总作为验收证据随包外文件提交。

本目录 `.gitattributes` 禁止 Git 自动转换换行，保证 JSON、CSV、脚本和哈希清单下载后的字节与本地交付一致。

分别解压 ZIP 到新的 `pilot_P1`、`pilot_P2` 文件夹。按包内 `reproducibility/requirements-lock.txt` 建环境后，使用相应包内 `reproducibility/generator/fp_competition/app.py` 执行 `audit --dataset <解压目录> --out <包外新报告路径>` 和 `replay --dataset <解压目录> --out <包外新报告路径>`；全量复算不传 limit。源码快照含物理核心和完整依赖记录，无需使用 Agent。`replay_thread_preflight.json` 记录本次复算进程使用的线程限制；这是进程级运行设置，不改写物理配置。

配方重建脚本 `build_A.py` 应在原生成器项目的 `datasets/A-part-20261018` 或 `outputs/member-A-20261018` 路径运行（两级父目录包含 `fp_competition`）。若仅下载了协作仓库，请先把任一 ZIP 的 `reproducibility/generator/fp_competition` 复制到本地项目根目录作为生成器源码，再运行脚本。重建应使用新目录，保留原有证据文件。

## 未完成的正式工作

P1/P2 各 10,000、合计 20,000 正式谱尚待 B/C 的 2,500 配方与 A 配方合并为同一 5,000 主表，完成去重、亲缘分组及全局索引验证后生产。本目录不能被计为已经完成 20,000 正式谱，也不能把试产重复计入正式预算。

工程一致性、闭合、可复算不证明真实设备准确度或实测含量相对误差 ≤5%。P1/P2 为未标定的假定条件；不包含水分、颗粒、非均匀性等未实现物理机制。
