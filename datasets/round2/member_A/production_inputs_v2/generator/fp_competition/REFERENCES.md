# 来源、取舍与实现对应

检索日期：2026-10-14。主题包括 XRF 吸收增强、有限厚度、跨设备校准、SDD 能量响应、谱库噪声和数据标签。只使用公开检索词；没有上传私人谱或源程序。没有联系作者或取得未公开实验数据。来源是物理依据，不是本程序正确性证明。

| 编号 | 资料及访问范围 | 采用方式 | 边界 |
|---|---|---|---|
| R01 | NIST XCOM，Interpolation and Combination；官方说明 https://www.physics.nist.gov/PhysRefData/Xcom/Text/chap3.html （检索文本可读，直接页曾失败） | 吸收边不能跨边平滑，混合物按质量分数求和；采用 xraylib 直接查询并在边处分段积分 | 不把 xraylib 全部值称为 NIST 原始数据 |
| R02 | xraylib 官方 API，https://github.com/tschoonj/xraylib/wiki/The-xraylib-API-list-of-all-functions （官方全文可读） | 使用 cm²/g、cm²/g/sr、keV、弧度；采用 CS_FluorLine_Kissel_Cascade 和 DCS_Rayl/DCS_Compt | 原子内级联截面不等同于不同元素间二次荧光，后者另算 |
| R03 | Amptek AN-SDD-003, Silicon Drift Detectors，https://www.amptek.com/-/media/ametekamptek/documents/resources/amptek-silicon-drift-detectors.pdf （7 页官方 PDF 可读） | Fano 与电子学噪声平方相加；同型号的响应受工作状态影响 | 厂商典型性能不能补作本批设备的实测参数 |
| R04 | Rettenmeier, Design of optimum filters for signal processing with silicon drift detectors, 2021, DOI https://doi.org/10.1002/xrs.3227 （公开检索片段） | Fano=0.115、成对能量3.65eV 作为有出处的 Si 模型先验 | 不是从当前设备拟合得出；需后续独立校准 |
| R05 | de Boer, Calculation of X-ray fluorescence intensities from bulk and multilayer samples, 1990, 19:145–154, DOI https://doi.org/10.1002/xrs.1300190312 （出版商摘要；作者上传正文片段可检索） | 为 E1 形式的荧光传输积分提供依据；本版自行实现单层平板一代再激发数值积分 | 没有逐式复现全文所有多层公式，也没有验证完整高阶效应 |
| R06 | Rousseau, Some considerations on how to solve the Sherman equation in practice, 2004, DOI https://doi.org/10.1016/j.sab.2004.06.002 （摘要及引言片段） | 注意二次荧光角度因子，避免把一次/二次项量纲混用 | 不用摘要替代完整数值基准 |
| R07 | Wählisch et al., Validation of secondary fluorescence excitation in quantitative X-ray fluorescence analysis of thin alloy films, 2020, https://arxiv.org/abs/2003.08930 ；期刊 DOI https://doi.org/10.1039/D0JA00171F （作者预印本摘要） | 二次荧光需要独立验证和不确定度评价，不能省略后仍宣称高精度 | 对象为合金薄膜，不能直接移用其数值到不锈钢块样 |
| R08 | XMI-MSIM 官方 User guide，https://github.com/tschoonj/xmimsim/wiki/User-guide （全文可读） | 显式 gain/zero、活时间、响应、逃逸与计数噪声；将计数噪声放在探测器响应之后 | 本版没有调用或安装 XMI-MSIM，未做其交叉对照 |
| R09 | Rousseau, Corrections for matrix effects in X-ray fluorescence analysis—A tutorial, 2006, DOI https://doi.org/10.1016/j.sab.2006.06.014 （公开摘要/引言） | 理论模型与实验校准结合，记录影响系数的适用范围 | 本次九个有基准样品且跨设备未配对，未拟合经验校正系数 |
| R10 | Kowalska & Jakowiuk, INCT-8-B-01, 2001，https://www.ichtj.waw.pl/ichtj/publ/b_report/b2001_08.htm （作者机构摘要） | DS/PDS 可作为未来配对校准的比较方法 | 当前不同成分的两组数据不满足直接配对输入；没有实现虚假迁移 |
| R11 | Panchuk et al., Feasibility study on multivariate calibration transfer in X-ray fluorescence spectrometry, 2026, DOI https://doi.org/10.1016/j.sab.2025.107373 （出版商摘要；大学记录可读） | 矿石跨设备模型迁移具有研究依据 | 本版未复现实验，文中误差不能等同于本项目达标率 |
| R12 | NIST SRD128, X-ray transition energies, https://www.nist.gov/pml/x-ray-transition-energies-database （官方介绍） | 解释谱线能量参考与独立标定的区别 | 本次未用候选谱线自动授予能量标定可信状态 |
| R13 | NIST, Energy dispersive x-ray spectrometry, Special Publication 604, https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nbsspecialpublication604.pdf （公开章节检索文本） | 参考峰形和能量位置不一致会影响拟合，因此保留刻度假设、优先评价稳健特征 | 不引用其案例误差作为本项目性能 |
| R14 | USGS BHVO-2, June 2022，https://www.usgs.gov/media/files/bhvo-2-geochemical-reference-material-information-sheet （原PDF下载并阅读表1/2/说明；落地页声明Public Domain） | 转录10种主量氧化物及18种选定痕量、不确定度，保存原件哈希，显式转换/归一化 | 文献汇总估计，非USGS计量溯源认证；重建组成不等于实物完整组成；没有实测XRF谱 |
| R15 | USGS BCR-2, June 2022，https://www.usgs.gov/media/files/bcr-2-geochemical-reference-material-information-sheet-0 （访问同R14） | 与BHVO-2组成对照，构建第二个公开基体重建样例 | 同R14；缺失元素不能在实物上判零 |
| R16 | Jochum et al., Reference Values Following ISO Guidelines for Frequently Requested Rock Reference Materials, 2016, DOI https://doi.org/10.1111/j.1751-908X.2015.00392.x （出版商公开正文可读） | 参考组成、不确定度以及RM/CRM的身份边界；本版数字来自USGS信息表 | 不把文献推荐值与模型归一化标签混用；未再发行论文全文 |
| R17 | xraylib官方跃迁宏，https://github.com/tschoonj/xraylib/blob/master/include/xraylib-lines.h ，官方API见R02 （官方页面及本机4.3.0常量可读） | 选择独立K/L/M跃迁，不叠加合并宏；CompoundParser化合物质量分数；NIST干空气混合物CS_Total_CP | 仅使用本机数据库存在且>=1keV的跃迁，不称所有谱线都完整；整壳与逐线核查不是独立物理求解器验证 |
| R18 | Amptek C-Series Low Energy X-Ray Windows，https://www.amptek.com/products/x-ray-detectors/fastsdd-x-ray-detectors-for-xrf/c-series-low-energy-x-ray-windows （官方全文/表格可读） | 轻元素对窗口/空气路径敏感，加入入射/出射空气衰减及支持边界 | 未实现C窗口材料/结构；厂商窗口不代表用户设备，也不能由下载资料授予校准状态 |

0.2.0 本轮实际下载的是两份公开组成信息表，不是新取得的实测XRF谱。当前未发现并引入可同时核实谱计数、组成、仪器响应及授权的新增实测训练集。PyMca官方训练页直接访问超时；PubMed干扰案例仅检索摘要可见，未据其全文实施新算法。As/Pb和S/Pb干扰的具体能量以本机xraylib查值及生成检查为依据。

0.1.1 的通道展宽与ROI积分为本项目的数值策略，依据高斯卷积和信号积分性质，已经用现有谱做敏感性检查。它不是论文给出的通用校正公式，也不能解决未知刻度的可识别性。原测量疑点保持原样记录，展宽仅建立辅助视图。

用户提供论文与早期程序的计算路径存在不同：论文原级谱、本底/灵敏度经验标定等，不等于该早期代码中的 Kramers、手填衰减表和固定噪声实现。采用时以实际代码和明确方程为准，不把论文实验精度转嫁给本程序。

本版自编 E1 层积分的定义：用质量深度 z；一次源 q_j(z) 由多色入射的衰减与荧光产生截面积分得到。对于横向无限、均匀、各向同性线发射的单层样品，再激发通量核为 `0.5*E1(mu_j*abs(z-z'))`。对源单元的积分用原函数 `sign(t) * (abs(t)*E1(mu*abs(t)) + (1-exp(-mu*abs(t)))/mu)`，其 t=0 极限为0。次级线再乘目标元素产生截面并积分出射衰减。本版独立核查了单元积分与 SciPy 自适应积分的一致性，以及加密深度网格的收敛；没有实验证明所有样品上的模型偏差。
