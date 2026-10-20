# 提示词 1｜成员 B：富铁配方、P3/P4 条件和 B 配方谱试产

你是负责三人方案中**成员 B**的 XRF 基本参数法与数据工程 Agent。请实际完成本提示词的文件交付，并把所有新增内容放在 `C:\Users\Lenovo\Desktop\兴智杯AI开发大赛\datasets\B-part`。不要改写 A 的目录、两份 PDF 或任何已密封批次。“成员 B”与《X射线模拟训练集数据产生要求 v1.0》所称的“B 阶段”含义不同。

## 0. 核对依据和执行环境

完整阅读工作区根目录的《三人训练集产生方案_v1.0.pdf》《X射线模拟训练集数据产生要求_v1.0.pdf》，以及 `datasets\A-part-20261018` 内的 `README.md`、`A_samples.json`、`A_formula_registry.csv`、`A_design_ranges.json`、`A_coverage.json`、`A_acceptance_summary.json`、`build_A.py`、`P1.json`、`P2.json`。PDF 是需求依据；A 的 `reference_production_plan.md` 仅作检索辅助。先列出当前已有与缺失的文件，不能把方案描述当作已完成事实。

**现成谱生成程序就在工作区**：`fp-spectrum-generator-competition-v0.2.1\fp_competition\app.py`，同目录有 `minerals.py`、`core.py`、`dataset.py`、`default_profile.json`、`requirements-lock.txt`、README、测试和 GUI 启动脚本。此程序为交付软件 0.2.1、物理模型 0.2.0；从该目录运行 CLI 的 `design-mineral`、`convert-components`、`support`、`batch`、`audit`、`replay`、`pack`。配方设计优先调用现有 `design-mineral`/`components_to_elements`，稀疏与干扰对照用 B 的可复现预处理脚本构造；**不要重写 XRF 物理求解器，也不要用 GUI 逐条手工导出批次**。生成器本身只读，所有生成文件和隔离环境写入 `B-part` 的新路径。

已核对本地生成器 35 个文件与 A 的 `P1_pack.zip` 中封存生成器逐文件 SHA256 一致；执行时仍要重新记录本地 `app.py`、`core.py`、`minerals.py`、`dataset.py`、`requirements-lock.txt` 及 A 封存版本的摘要。如果本地文件被改动，先停下并查明来源，不能混用版本。生产采用本地 CLI；交叉复核采用每批自动封存的源码快照。按本地 `requirements-lock.txt` 在 `B-part/work/` 建隔离环境并记录 Python、依赖、系统和数值线程设置；`启动生成器.cmd` 只为交互界面提供入口，它会回退到本机 `py -3`，不作为可复现批量生产命令。若环境阻塞，先完成可独立完成的范围设计，留下准确错误和未完成项。当前已有 A 的 2,500 条配方及 P1/P2 各 200 条试产谱，但尚无正式 P3/P4 配置、C 的 1,000 条配方或 5,000 条主表。

## 1. 设计并交付 B 的 1,500 条富铁氧化物配方

按互斥情景交付 `routine` 900 条、`sparse_boundary` 300 条、`interference` 300 条。先提交 `B_design_ranges.json` 与 `B_design_basis.md`，明确数值范围、采样分布、Fe2O3T 主平衡组分、富铁判据、其他氧化物与痕量上限、精确零机制、质量闭合方法、来源和适用边界。数值判据须在采样前写明并逐样核查；不能直接把 A 的 SiO2 平衡配置改名为富铁矿。公开资料只能支持明确的事实，模拟范围若由团队人为设定要明确标注为实验设计，不能声称代表全部铁矿石或真实总体。

生成 `B_samples.json`，顶层使用本地 `app.py batch` 接受的 `samples` 数组；每条包含唯一、稳定的 `Bxxxxx` ID、`composition_percent`（实际输入模型的**元素质量百分数，含 O 与全部基体元素**）和完整 `provenance`。后者至少保存原始化合物质量百分数、痕量 ppm、元素换算、闭合、设计依据、`matrix=iron_rich_oxide`、`owner=B`、`scenario`、`parent_family` 与对照参数。按本地 `minerals.py` 的 `components_to_elements` 转换并保留输出；`Fe2O3T` 的 O 分配仅是模型化学计量假设，不等于实测铁价态。`10000 ppm = 1%`。如某元素已由化合物提供，不能再次作为痕量添加；注意该函数连零量化合物所含元素也视为“已由化合物表示”。以 `strict` 闭合；若不能闭合，应修正设计或逐样明确记录非 strict 决策，不可静默归一化。

在 300 条稀疏/边界配方中，对适用的非必需目标安排精确零、低量、中量和高量；初始低量统计口径为 `0 < 元素质量百分数 <= 0.1`，它不是检出限。每个适用元素争取至少 50 个零和 50 个低量的独立配方，达不到就逐元素记录缺口与原因。Fe/O 是必需基体，不要求为零。统计 32 个候选目标，但 O 是基体账目而非直接荧光目标。不要把“配方中精确零”解释为实物样品未检出。

300 条干扰配方建议采用 60 个母家族×5 个完整对照，其中 As/Pb 与 S/Pb 各 30 个家族；对照覆盖双零、仅前者、仅 Pb、共同低量和不同含量比。若采用不同结构，仍须满足 300 条、完整家族、候选重叠场景和对照可比较性。同一母配方的所有近邻、微扰、增强和对照必须共享 `parent_family`。用 CaSO4 引入 S 时，记录 Ca/O 同时变化，不能宣称是严格单变量 S 对照；具体谱线要以试产 `full_results` 核对。不得另加未经验证的经验强度修正。

提供可重跑的 `build_B.py`、固定随机种子、`B_formula_registry.csv`、`B_coverage.json` 与 `B_cross_A_overlap.json`。registry 至少有 ID、家族、基体、情景、组成 SHA256 和待全局划分状态。为方便与 A 比较，组成哈希按 A 的 `build_A.py` 中非零元素字典、`json.dumps(..., sort_keys=True)`、SHA256 规则计算，同时另外用统一元素顺序及 12 位小数进行数值去重/跨 A 对比，列明两种判据；近邻检测阈值与方法也要写明。组成去重以实际 `used_percent` 为准，不能按名字、家族或未经换算的氧化物去重。若不足 1,500 独立组成，按固定规则补足并重算全部统计。验证非负、有限、组成和为 100%（文档规定 `strict` 容差为 1e-6 个百分点）、配方与 provenance 换算一致、900/300/300 配额、家族完整和跨 A 重叠。B 不直接修改 A 配方；重叠清单交 A 合并主表时处理。

## 2. 提出并预检 P3/P4 候选条件

交付完整字段的 `P3_candidate.json`、`P4_candidate.json`，从 A 的 P1/P2 和**本地生成器**的 `default_profile.json` 比对后构建。P3 为 20 kV，并改变刻度与噪声；P4 为 49 kV、100 μm Al 滤片、较长空气路径和较大噪声。两者维持 Ag 靶、Si 探测器、2,048 通道。缺失的数值字段不能靠“默认值大概如此”跳过；保存逐字段差异、单位、选值理由、中心/边界能窗、配置 SHA256 与 `calibration_status=assumed_unverified`。它们是**候选配置**，在 A 冻结前不得作为正式 P3/P4 使用，也不代表真实仪器标定。

从现成生成器目录以**所建隔离环境的 Python**运行 `-B app.py support --profile <P3_candidate.json绝对路径> --out <B-part内新报告路径>`，对 P4 同样执行，并在下述实际试产 `full_results` 中复核 32 个候选元素的激发、K/L/M 可用线、线中心与能窗、探测效率、空气路径和窗外损失。把两份原始 support 输出及逐元素结论写入 `B_profile_support_P3.json`、`B_profile_support_P4.json` 和 `B_profile_review.md`。重点查看 P3 低电压下重元素 K 系、P4 低能线衰减和 Na/Mg 的条件敏感性。线存在不证明可分辨、检出或达到 5% 误差；Ba K 系超窗时还需检查 L/M 信息，不能简单判为完全不可推断。

## 3. 必做：先生成 B 配方的 P3/P4 试产谱

在 1,500 条配方与候选条件完成后，确定性选择 100 条 B 配方：40 条常规、20 条稀疏/边界、As/Pb 和 S/Pb 各 4 个完整的 5 条家族（共 40 条）。保存选择脚本、ID 与家族清单为 `B_pilot_samples.json` 和 `B_pilot_family_exposure.csv`。若干扰家族不全是 5 条，保持 100 条与完整家族，记录等效分配。将这些**已查看标签和谱的家族**交 C 标记为开发暴露，只能进入后续训练/验证家族或从正式基准剔除，不得被分到盲测配方家族。此专项试产与三人方案 M1 的“A 给 100 配方，B 生成 3 次谱”不是同一任务。

使用同一份 B 试产样品文件，从现成生成器目录的 `app.py batch` 分别以 P3/P4 候选 profile、`--replicates 2`、`--closure strict`、`--legacy-al reject`、完整 32 元素 `--targets`、`--design-ranges <B_design_ranges.json>`、**不传 `--jitter`** 生成 `pilot_P3`/`pilot_P4`，每批 200 条、合计 400 条。`--samples`、`--profile`、`--out` 传 `B-part` 中相应文件/新目录的绝对路径。试产批次种子与正式 `2026101803/04` 不同，明确记录；`--split-seed 20261018` 可以与正式一致，但内部 split 只识别精确相同组成，**不识别 `parent_family`**。两批标注 `workflow_pilot_only`，不得用于正式训练、调参或最终测试，也不得计入 20,000 条。确认同配方重复谱的实际组成、profile、期望谱相同，仅计数采样不同；另核查线系、能窗、支持、六分量和窗外损失。

每批先从现成生成器的 `app.py audit` 在密封目录外写 QC 报告，再用批次内 `reproducibility/generator/fp_competition/app.py` **独立执行不加 `--limit` 的全量 `replay`**，随后用现成或封存程序 `pack`；保存 JSON 报告、完整日志、环境差异、ZIP 外部 SHA256，并核对 ZIP CRC。`pack` 会做 QC，却不会替代全物理 `replay`。`app.py` 要求 `--out` 为不存在的新路径；失败的 `failed_partial` 批次和原报告应保留，修复后使用新的版本目录。若 P3/P4 冻结值不同于候选试产值，在正式生产前用冻结配置重做必要的试产验收。没有实际跑完不能写通过；单人自检不算 A 对 B 的交叉复核。

## 4. M1 与交付状态

另核查三人方案的 M1：A 提供 100 配方、B 生成 3 次谱、C 主审、A 复核，共**新 300 条**。A 现有 P1/P2 各 200 条试产，以及上述 B 专项 400 条，都不能自动顶替 M1。若 A/C 已正式关闭 M1，记录可核查证据；若尚未关闭，准备可用的 A 100 配方、环境和生产方案，取得 A 冻结的 M1 条件后执行并交 C/A 复核；条件未提供时记录 `M1_pending_profile`，不得自行猜成 P3/P4。M1 的输出与 B 专项试产分开命名、分开计数，且不计入正式预算。

最少交付：`B_design_ranges.json`、`B_design_basis.md`、`build_B.py`、`B_samples.json`、`B_formula_registry.csv`、`B_coverage.json`、`B_cross_A_overlap.json`、`P3_candidate.json`、`P4_candidate.json`、`B_profile_support_P3.json`、`B_profile_support_P4.json`、`B_profile_review.md`、`B_pilot_samples.json`、`B_pilot_family_exposure.csv`、P3/P4 试产密封目录或完整 ZIP、各自外部 SHA256/audit/replay/日志、`B_environment.json`、`B_preflight.json` 和 `README.md`。`README.md` 给出实际数量、覆盖与缺口、全部验证命令/退出码、哈希、原始与采用组成区别、条件假设、试产状态、M1 状态、交给 A/C 的文件及仍待冻结的依赖。仅将实际完成的事项记为 `passed`；受阻事项记 `pending` 或 `blocked` 并附证据。完成后给用户简短汇报和文件链接。
