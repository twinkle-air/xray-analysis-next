# FP 能谱生成器：比赛研究版 0.2.1

这是独立的 Python 程序，针对用户提供的早期 FP 生成器重新整理数值核心、配置、中文界面和谱库生成。没有修改原始微信目录中的程序，也不依赖本项目的智能体或 Skill。

用途是建立物理约束的合成数据、研究未知能量刻度/响应的分析方法、开展流程测试。当前没有完成真实设备校准，也没有证明“95% 盲测含量结果相对误差 ≤5%”。

## 0.2.1 审查整改：可复现的标准数据包

本版交付软件为0.2.1，物理求解模块仍为0.2.0；core.py、minerals.py、robustness.py字节保持工作区修订前状态，哈希见physics_baseline.json。这不是对缺失的队友修改版源码作来源认证。原300条数据与原审查报告不覆盖、不改写。

批量导出默认保存blind_inputs、truth以及每条完整full_results，自动封存输入样本、原始CLI输入文件、采用配置、生成配方、源码快照和实际环境依赖。每条manifest分别写blind_input_sha256/full_results_sha256；兼容字段sha256仍指盲输入。integrity.json覆盖其他全部封存文件，自身排除。生成status=complete只表示生成完成，acceptance_status仍为pending_independent_validation。

在本目录运行（使用全新输出路径）：

```powershell
python -B app.py design-mineral --ranges mineral_design_ranges.json --count 100 --out mineral_100.json --seed 20261017
python -B app.py batch --samples mineral_100.json --profile default_profile.json --jitter mineral_jitter_example.json --design-ranges mineral_design_ranges.json --replicates 3 --seed 20261017 --split-seed 20261017 --targets Na Mg Al Si P S Cl K Ca Ti V Cr Mn Fe Co Ni Cu Zn As Se Rb Sr Y Zr Nb Mo Cd Sn Sb Ba W Pb --out dataset-v2
python -B app.py audit --dataset dataset-v2 --out dataset-v2-qc.json
python -B app.py replay --dataset dataset-v2 --out dataset-v2-replay.json
python -B app.py pack --dataset dataset-v2 --out dataset-v2.zip
```

独立复核时应安装数据包reproducibility/requirements-lock.txt中的依赖，并调用其reproducibility/generator/fp_competition/app.py快照，而不是假定工作区代码相同。使用-B避免在封存源码目录写pycache；QC/重算报告写在数据包外。audit遍历全包哈希、结构、标签、组成、完整分量、窗口账目、批次抽样、Poisson重放和成分族隔离；replay额外调用完整物理核心逐条重算。replay默认全量，--limit N为前N条抽查，报告会标为subset。哈希不提供来源真实性或科学准确度认证。

批次seed控制扰动和子种子派生。--split-seed单独控制划分；省略时沿用批次seed以兼容旧行为。每条谱使用不同记录子种子；只有配方/profile固定、仅改变单谱seed时，改变的才只是计数噪声。配方设计seed另在原设计文件保存。固定环境下要求计数逐道相同；浮点重算比较rtol=1e-12、atol=1e-8，并明确报告环境差异。文件字节相同不等价于物理数值复现。

每条full/truth保存energy_window，区分首末通道中心和左右半通道边界；manifest和自动README根据整批真实profile统计范围。outside_window_counts来自荧光及散射响应deposit的窗外积分，包括中心完全在窗外的信号及峰尾，不只记录峰尾。账目：detected_signal_before_window_counts = 入窗非本底期望信号 + 窗外损失（容差内）。它是效率及出射空气衰减之后的账目，不能称源端光子守恒。损失比例的分母和算法随manifest明确记录。

Ba的K线中心落在窗外不代表不能使用L/M系；生成器记录其窗口位置统计，不自动给出可定量/不可定量结论。需要独立评估响应、重叠和信噪比。本版pack先执行QC并拒绝失败数据，写ZIP及独立.zip.sha256；全物理重算是单独验收项，pack不会代替执行。

GUI“批量谱库”同样走完整封存出口。CLI能保存所给的原始样本/配置文件；GUI/API至少封存实际样本与配置，但未提供的原设计命令/原始文件不能补造，应在交付说明中标为未提供。多批合库仍须统一规划；仅在输入成分族全集一致且split_seed相同时，各批的现有划分才一致；相同seed不保证不同样本全集的划分一致。

## 启动

当前电脑：双击 `启动生成器.cmd`。它优先使用上级项目现有 `.venv`，找不到则调用本机 `py -3`。也可直接运行 `基于基本参数法的能谱生成模型_比赛研究版.py`。

新电脑安装：使用 Python 3.11 或更新版本，建立自己的虚拟环境，然后执行：

```powershell
python -m pip install -r requirements-lock.txt
python app.py gui
```

0.2.1在Windows、Python 3.12.14专用虚拟环境复核；0.2.0的Python 3.11验证记录保留为历史。没有在另一台电脑或其他操作系统上验证。

界面左侧可以编辑完整仪器 JSON 配置及样品质量百分数，选择原程序的九个成分预设或两份 USGS 公开组成的合成重建；右侧预览合成谱。支持单谱导出、批量生成，以及 `.pu` 实测谱形状叠加。叠加时各谱分别除以自己的最大值，只用于形状观察，不输出设备效率比或含量。公开重建预设名称带有 synthetic-reconstruction；来源及转化假设随 JSON/Excel 保存。

## 保留原成分值，并明确处理不完整标签

`legacy_presets.json` 从原程序 AST 读取而来，没有执行原程序。原始数值保留，缺失的 ZBGS001 不补造。

- `strict`：元素质量百分数必须合计 100%，否则拒绝。
- `normalize_explicit`：主动选择后才归一化，输出同时保存原值、采用值和归一化前总和。采用值才是这条模拟谱的含量标签，不能仍用原值给它评分。
- `reject`：默认拒绝有非零 Als/Alt 的配方，直到用户明确其处理方式。
- `sum_as_written`：明确选择按原程序数值把 Als 与 Alt 合并为 Al，只适合作为待核实的原值迁移方式。
- `alt_is_total`：明确假设 Alt 表示总 Al，不再相加 Als。是否符合实物样品需核实。

ZBG074 的原程序成分总和为 99.037%；ZBG072 为 99.9001%；ZBG212 为 99.9046%。本程序不会暗中按论文或公开目录修正任何数值。若自行提供完整组成，可以直接使用严格模式。预设成分来自用户指定基准，不称为有独立证书的认定值。

## 单谱生成

以下命令在此目录执行；从上级项目调用时，在路径前加 `fp_competition/`。

```powershell
python app.py generate --composition example_composition.json --profile default_profile.json --out my-spectrum --seed 20261014
```

输出目录必须不存在，防止覆盖源文件和既有结果。产物为 `result.json`、`spectrum.csv`、`spectrum.png`，安装 openpyxl 时同时产生 `spectrum.xlsx`。Excel 包含合成计数、期望计数、各分量、仪器假设、限制及原始/采用成分。

同一 seed 与配置可复现计数抽样；改变 seed 只改变计数噪声，不改变底层期望谱。`--no-poisson` 输出无抽样的期望计数。这里的 counts 是生成的合成计数，不能据此推断私人 `.pu` 的原始纵轴单位。

## 批量谱库

输入支持 JSON、CSV、XLSX，CSV/Excel 第一列为 `编号` 或 `id`，其他列是元素质量百分数，参见 `samples_template.csv`。不能输入不明单位或任意备注列冒充元素。

```powershell
python app.py batch --samples samples_template.csv --out my-library --replicates 10 --seed 20261014 --jitter jitter_example.json
```

如要明确以原代码数值迁移九个配方做方法测试：

```powershell
python app.py batch --samples legacy_presets.json --out legacy-method-library --replicates 10 --seed 20261014 --jitter jitter_example.json --closure normalize_explicit --legacy-al sum_as_written
```

后一命令明确采用两个尚需科学核实的标签处理决策；输出会逐条记录，不把结果冒充原样品的精确仿真。

`jitter_example.json` 是人为设定的研究范围，包括 gain、zero、噪声展宽、入射通量、质量厚度。它不是从两台设备反演出的参数分布。可以修改范围或省略 `--jitter`。界面默认关闭扰动，勾选后使用该文件中的范围。单次最多 10000 条，较大任务分批保存。

每批输出包括：

- `blind_inputs/`：只含通道、合成计数与合成标记，没有能量轴、元素含量、样品名称或仪器参数。
- `truth.jsonl`：合成标签、原配方、采用配方、seed、仪器参数、配方来源及限制。训练时关联对应行读取标签；评估推理时只能读取 blind_inputs，评分脚本单独读取 truth。
- `full_results/`：每条谱的完整期望谱、六类分量、谱线、窗口与损失、条件及来源；逐条独立哈希。
- `manifest.json`：文件摘要、生成状态、成分族、数据划分。
- `inputs/`、`configs/`、`reproducibility/`：实际输入、可取得的原文件、采用配置、recipe、源码快照及依赖环境。
- `integrity.json`、`README_dataset.md`：全部其他封存文件的校验清单，以及按本批实际数据生成的说明。QC/重算报告放在目录外。

同一采用成分的全部噪声重复/参数扰动归入同一个分组，约按 70/15/15 划分；有三个以上成分族时每组至少一个。此规则只用于合成方法研究，不能替代真实样品、设备和批次隔离，也不保证各元素的分布平衡。失败任务保留 `failed_partial` 状态和已生成清单，不假报整批成功。

## 设计更多成分

无需只围绕九个成分重复抽噪声。可先按明确范围设计新的混合物，再批量生成：

```powershell
python app.py design --ranges steel_design_ranges.json --count 1000 --out designed.json --seed 20261014
python app.py batch --samples designed.json --out designed-library --replicates 3 --jitter jitter_example.json --seed 20261014
```

该范围是方法研究用的成分空间，不能宣称每个随机组合都是实际存在或符合牌号标准的不锈钢。平衡元素 Fe 补足至 100%，不满足指定范围的组合重采样。元素允许 H–U；0.2.0 枚举 xraylib 可用的独立 K/L/M 跃迁，排除重复的合并线宏，但仍不产生低于 1 keV 的荧光线。

## 扩展到氧化物基体及32个候选目标（0.2.0）

默认候选目标为 `Na Mg Al Si P S Cl K Ca Ti V Cr Mn Fe Co Ni Cu Zn As Se Rb Sr Y Zr Nb Mo Cd Sn Sb Ba W Pb`。这是模拟/标签能力范围，不是32个元素的实测定量认证。先按样品体系选子集，分别评价各元素，不把纯元素有峰当作痕量检出证据。H/C/N/O可作为基体吸收和散射成分，本模型不将其作为直接荧光预测目标。

`public_data/` 保存实际下载的 BHVO-2 和 BCR-2 USGS 信息表PDF、网址/哈希/公开领域声明、转录的主量氧化物与18种选定痕量元素及不确定度。原表说明其组成是多实验室文献估计，未提供USGS计量溯源认证。两个预设是主量氧化物加选定痕量的**合成组成重建**，不完整原组成分别合计100.16674444%和99.9011607%，明确归一化后才生成谱。未选取的成分被排除于模型；这不代表它们在实际参考物中为零。不将原表95%置信水平不确定度当作随机样品分布。资料依据及访问范围见 REFERENCES.md。

地质基体设计使用质量百分数的化合物、mg/kg（ppm）的痕量，以及补足质量的SiO2。化合物按 xraylib 原子质量转换为元素质量分数，**10000 ppm = 1%**；保留转化前后数值。Fe2O3T表示总Fe按Fe2O3报出，不证明铁价态；本版采用Fe2O3化学计量分配O，明确标为假设。O是基体账目，不是本模型对O的直接测量值。

以下在 fp_competition 目录中运行，输出必须使用新路径：

```powershell
python app.py support --profile default_profile.json --out support.json
python app.py design-mineral --ranges mineral_design_ranges.json --count 1000 --out mineral-design.json --seed 20261014
python app.py batch --samples mineral-design.json --out mineral-library --replicates 3 --jitter mineral_jitter_example.json --targets Al Si P S Cl K Ca Ti V Cr Mn Fe Co Ni Cu Zn As Se Rb Sr Y Zr Nb Mo Cd Sn Sb Ba W Pb --seed 20261014
```

这里初始训练列表暂不含条件敏感的Na/Mg；条件得到验证后可以加入。`mineral_design_ranges.json` 的宽范围、痕量对数均匀分布、25%精确零概率及 `mineral_jitter_example.json` 均为明确的人为实验设计，不能声称来自真实土壤/矿石分布。它们覆盖硅酸盐/氧化物并掺入硫酸盐、氯化物用于S/Cl模型研究，不覆盖所有矿物、水分、粒度或物相。

`batch --targets ...` 写出固定列 `targets_percent`，包括精确零值，标签单位为元素质量百分数。零表示**在这条完整合成配方中**未加入该元素，非原始实物的未检出结论。可将非零换算为存在标签研究元素识别，但不可称为“谱中已检出”：弱线、重叠及吸收可能使其不可辨。不同化合物可贡献同一元素；若某元素已在化合物中，禁止再以痕量添加，避免重复计算。默认 targets 为整批输入元素并集，包含基体O/H；训练请显式选定可观测目标。

`support` 输出每元素激发可行性、各谱线能窗比例、探测器效率和外部空气透过率，并提示无激发线或严重衰减。这不是检出限或准确度计算；1%响应提示阈值仅是启发式标记，不含实际通量、基体与重叠影响。As Kα/Pb Lα、S Kα/Pb M等干扰现在可在生成谱中共同出现，但本生成程序没有提供经实测验证的解谱算法。

空气路径参数 `incident_air_path_cm` / `exit_air_path_cm` 默认为0以保持旧配置行为，不能据此宣称设备工作于真空。其衰减使用xraylib干燥空气混合物及 `air_density_g_cm3`；路径/密度均须据实验确定。Na/Mg尤其敏感；旧私有谱的气氛与真实响应仍未知。湿度和保护膜等额外吸收尚未建模。

如已有化合物表，可用 `convert-components --input components.json --out converted.json --closure strict` 转换再批量生成。输入包含 `id`、`compounds_percent` 及可选 `trace_ppm`；总质量必须100%，或显式选 `normalize_explicit`。更新源PDF仅在用户主动运行 `public_data/fetch_usgs.py` 时联网，正常模拟离线运行。

单次最多10000谱；合并多批库后应在全库按成分族重新统一划分，避免同成分跨批次进入不同集合。现有分组只隔离完全相同采用成分，不能隔离近邻配方或替代设备/基体留出。不要混用旧版本生成谱和新版谱而丢失版本标签。

## 数值模型

1. 管源采用归一化 Kramers 类连续谱、管窗/Al 滤片衰减及假定比例的靶材特征线。入射能量积分网格覆盖 1 keV 至管压；与探测器的输出能区独立。
2. 衰减、荧光产生截面、谱线能量、散射微分截面调用 xraylib；不再使用“光电衰减=总衰减×0.95”或带重复能量键的手填字典。吸收边作为积分区间边界。
3. 一次荧光使用均匀平板有限质量厚度的深度积分：`a = μ(E)/sin(入射角) + μ(E_line)/sin(出射角)`，厚度因子为 `(1-exp(-a*t))/a`。
4. 二次荧光使用一代再激发的质量深度数值积分。角度积分核为 `0.5*E1(μ_j*|z-z'|)`；对源层单元积分处理奇点，再计算次级线的出射吸收。该实现是作者编写的有限平板数值近似，不宣称完整复现某篇论文或已通过蒙特卡罗验证。
5. Rayleigh 与 Compton 使用 xraylib 的固定观察角微分截面及样品吸收，忽略多次散射与康普顿轮廓的详细束缚电子结构。
6. Si 响应使用 `FWHM² = 电子噪声FWHM² + 2.35482² * Fano因子 * 成对能量 * 光子能量`。所有能量单位在实现中明确换算。
7. 高斯按通道边界积分，宽度改变不增加总峰面积；越界部分单独记录。逃逸分量从主峰中扣出相同比例再移位，避免只叠加而凭空增加信号。默认逃逸比例是有效参数假设，不是晶体结构反演。
8. 将完整期望谱乘活时间得到期望计数，最后逐道抽取 Poisson 计数。模型参数扰动和统计计数噪声分开，移除固定 8%/15% 谱线随机扰动。

`incident_photons_s` 定义为经过源侧滤片、进入所设外部入射空气路径之前的有效总光子率，绝对值尚未校准。入射空气吸收不再次归一化；零空气路径时与旧版定义一致。改变滤片默认改变谱形；若实际总通量随滤片变化，需要同时提供相应入射通量。相对源谱中的靶线比例也仍是假设。

模型没有包含三级以上荧光、死时间、堆积、任意表面粗糙度、矿物粒度、湿度、多层样品或设备长期漂移。当前几何是局部点探测近似的均匀平板。有效固角、滤片和源谱的不确定性仍可能主导强度偏差。

## 降低对可疑峰宽和未知刻度的依赖（0.1.1）

保持物理模拟的Fano响应约束，不用未验证的窄峰反推硬件参数。匹配方法应同时考察刻度/噪声参数假设，并优先使用独立峰区域的面积特征；不能仅依据峰高或精确峰宽匹配。现有 `jitter_example.json` 用于产生不同假设，不代表已测定的仪器分布。

界面增加“保存峰形稳健性视图”。默认输出原视图以及额外6/10道FWHM的高斯展宽视图；只用于形状和敏感性分析，不修改原谱或物理参数，也不把相关的平滑通道当作独立Poisson计数。

可直接对已有通道JSON或2048道 `.pu` 执行：

```powershell
python app.py views --input your-spectrum.pu --out shape-views
```

每组保存输入SHA-256、未解释尾注、单位、展宽强度和窗外损失。原谱始终是定量依据，辅助视图不自动替换原谱。本版还提供 `robustness.integrate_channel_feature()`：按明确的通道区域和两侧线性本底直接积分，不强制单高斯峰形。侧区若有干扰或多元素重叠，不能用它自动解出各元素含量。

本批十份谱在约415道的强峰上，额外6道展宽后，固定ROI直接积分的最大相对变化约0.14%；额外10道约0.89%。但单高斯拟合面积在10道展宽后最大变化约5.76%；额外14道还使直接积分最大变化约5.11%。因此选择0/6/10为辅助视图，14仅作为压力研究案例，没有将任何展宽列为普遍适用的浓度校正。

上述百分数是处理敏感性，不是浓度误差或准确度。该结论只涉及已研究的强峰和指定ROI，不推广到弱峰与重叠线。两组峰宽差距在平滑后缩小是预期的数学结果，不能用它消除原始谱的物理一致性疑点。报告和逐谱结果在上级 `outputs/width-robustness-20261014/`。

## 检查与资料

在上级项目目录执行：

```powershell
python -B -m unittest discover -s fp_competition/tests -v
```

也可以在本目录执行 `python -B -m unittest discover -s tests -v`，测试文件自动定位源码。

见 `REFERENCES.md`、`VALIDATION.md`，以及本项目 `outputs/device-study-20261014/分析报告.md`。软件检查、数值收敛和界面运行均不等同于真实仪器科学验证。
