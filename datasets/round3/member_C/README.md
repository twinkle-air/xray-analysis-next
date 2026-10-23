# 第三轮成员C：候选已构建，待全局冻结

状态：250个候选配方与105个设计族已构建并自检通过；**未生成任何第三轮能谱**，实际训练谱为0。构造逻辑沿用A发布的参考实现（`../member_A/build_candidates.py`），配方取值来自A发布的 `../shared/preparation_v1/design_allocation.json` 中 `owner=C` 的105族，并与本地独立重推导逐条比对一致。不改profile、种子、标签、物理核心或用途；不复用第二轮seed冒充新数据；不删旧轮材料。

| 类型 | 配方 | 完整底板族 | 硅酸盐/富铁 |
| --- | ---: | ---: | --- |
| 关键元素梯度 | 90 | 15，每族6水平 | 54/36 |
| 匹配干扰对照 | 50 | 10，每族5控制 | 30/20 |
| 负例/加标配对 | 60 | 30，每族2控制 | 36/24 |
| 常规独立背景 | 50 | 50 | 30/20 |
| 合计 | 250 | 105 | 150/100 |

基础谱目标仍为250×3条件×2噪声=1,500；追加T谱数量=6×A最终分配的C留出配方数，留出名单未下发，因此此处不预设总数。

- [本人任务清单](../planning/C_任务清单.md) · [唯一方案](../planning/第三轮数据构建方案.md)
- [250候选（完整组成、原始底板、换算与补偿账目）](candidates/C_samples.json) · [105族登记](candidates/family_registry.json)
- [每族原始底板单表](candidates/original_backgrounds.json) · [CSV主表](candidates/formula_registry.csv) · [共享模板登记册](candidates/candidate_registry.csv)
- [候选检查、历史近邻与C-A交叉筛查](candidates/candidate_checks.json) · [32标签覆盖](candidates/coverage.json) · [输入身份](candidates/input_identity.json)
- [确定性重建与失败路径核查](reports/verification.json) · [实际命令与环境](reports/commands_and_environment.json) · [生产前待办](reports/production_readiness.json)
- [公共条件/配置身份（prepared 未冻结）](frozen_inputs/prepared_not_frozen.json) · [C输入快照哈希](inputs/source_manifest.json) · [交付清单](delivery_manifest.json) · [自检汇总](selfcheck_summary.json)

## 已实际运行的命令

在仓库根目录、使用 `inputs/generator/fp_competition/requirements-lock.txt` 对应依赖的Python环境（本次为CPython 3.12.14 + numpy 2.4.6 + scipy 1.17.1 + xraylib 4.3.0，与 `../shared/preparation_v1/source_identity.json` 记录逐项一致）：

```text
python -X utf8 -B datasets/round3/member_C/build_candidates.py --out datasets/round3/member_C/candidates   # 退出码0，2 s
python -X utf8 -B datasets/round3/member_C/verify_candidates.py                                               # 退出码0，4 s
```

两条命令只创建配方与账目，不生成谱。重新构建必须指定不存在的新目录，不覆盖原候选。

## 自检结果

250个候选组成互不重复，族内共用同一独立抽取的原始底板；闭合100质量百分点且保留O基体，32目标之外无未跟踪元素。换算/补偿账目可按记录的原始底板与受控ppm逐条独立重建（rtol 1e-10）。1,498个精确零标签逐条核验：无正量化合物或痕量来源仍携带该元素。梯度使用连续抽样区间且水平单调，落在登记的区间内；干扰族5控制、配对族负例/加标严格按方案。

历史比对使用与A同一份已发布快照（3,800条：第二轮全部1,000配方加已知第一轮候选/试片/研究登记），最小完整组成L1为 **4.3701** 质量百分点，**无≤0.5匹配**；C与A已发布250候选两两比较最小L1为 **5.1417**，**无≤0.5对**；C内部不同设计族之间无≤0.5连接。未记录的历史亲缘与B/D交叉关系仍无法排除，全局闭包是A的步骤。核验脚本另外以6个篡改用例（缺变体、重复ID/组成、零标签被未记录来源污染、补偿账目改动、原始底板改动、把同族变体拆出去）确认这些缺陷都会被拒绝。

`candidates/candidate_checks.json` 与 `reports/verification.json` 保存以上证据；`frozen_inputs/prepared_not_frozen.json` 只登记A准备的9个开发/3个留出配置、窗口预算与源码依赖身份（P1/P2/P3三处哈希与第二轮A基线逐项相同，`exact_source_bytes_preserved` 为真），**不构成任何批准或冻结**。

## 仍缺项（不由C单方面补齐）

1. B/D候选尚未发布，全局候选去重、历史族连通闭包与用途划分待A冻结。
2. 每族条件分配（1锚点+2开发条件）、长曝光梯度覆盖、计数噪声子种子清单与全局碰撞检查待A发放。
3. 从已确认训练族取1梯度+1干扰+1配对+2常规族做15配方×6=90谱试片（计入1,500，使用新目录），并实测时间与体积。
4. 基础1,500谱批量生成、每密封批次以封存生成器做完整audit、完整物理replay与pack（不传 `--limit`，错误/缺项/环境差异如实保留，窗外不事后放宽、不删难谱）。
5. A下发新留出清单后补T挑战谱，只做文件与物理QC；T不进入训练、校正、响应字典与选参。
6. 第二轮遗留的公共输入清单成员会签仍未完成；若后续统一条件与此不同，需另起版本。

以上任一项未冻结前，本目录不是可执行的出谱输入，也不能当作已验收训练数据。候选检查属于合成侧核对，不证明真实设备上的95%/5%准确度。大文件交付沿用第二轮无损办法：仅以ZIP上传并核对SHA/CRC与integrity，`transport_parts` 不作谱加载；本轮尚无密封批次，故未上传任何谱数据。
