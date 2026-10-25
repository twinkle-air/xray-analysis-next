# A 部分候选配方 v1

状态：A 本地候选校核已完成；尚未完成 B/C/D 汇总、全局亲缘闭环、用途/阶段分配或生产冻结。此目录中的内容是组成候选，不是能谱数据。

## 本次候选规模

- 2,000 个唯一组成，640 个合并前设计族。
- 元素梯度：80 族 × 10 个配方 = 800。
- 零/加标：80 族 × 5 个配方 = 400。
- 基体组成干扰对照：80 族 × 5 个配方 = 400。
- 常规覆盖：400 族 × 1 个配方 = 400。
- 每类按硅酸盐/氧化物与富铁氧化物两种现有范围各半配置。
- 梯度、零/加标、对照以 Na/Mg/Al/Si/Fe 为目标；每个配方仍保留完整 32 个目标元素标签和 O 基体闭合。

每个配方记录完整 used composition、原始氧化物/痕量背景、换算结果、受控元素值、移除/加入的载体和质量补偿比例。候选范围复用第三轮 A 已使用的范围文件，哈希见 `source_manifest.json`；这只是第四轮范围讨论的起点，尚未获第四轮全局批准。Fe 梯度限定在硅酸盐/氧化物基体，Si 梯度限定在富铁氧化物基体，以避免把被控制元素同时当作强制平衡相。

“基体组成干扰对照”指保持同一母配方背景，配对改变目标与另一种主量元素组成。它是用于后续模拟的组成控制，不声称已由谱线分析证实存在具体峰重叠。

## 历史近邻边界

候选与第三轮 A 输入表中的第一/二轮已知历史组成，以及仓库中第三轮 A/B/C/D 候选组成比较 L1 距离。`nearest_history.csv` 与 `original_background_nearest_history.csv` 保存逐条近邻；≤0.5 个百分点的连接仍须在全局闭环处理。候选范围只覆盖已登记来源，不能证明不存在未记录的历史亲缘。

所有候选的 requested role 仍为 `unassigned_pending_global_freeze`。脚本生成的候选设计 RNG 值仅用于可复现地构造配方，不是测谱噪声子种子、条件实例或批量生成种子。

## 复核与重建

在协作仓库根目录执行：

```powershell
python datasets/round4/member_A/build_candidates.py
python datasets/round4/member_A/verify_candidates.py
```

`build_candidates.py` 默认拒绝覆盖已有输出。当前工作副本缺少 round3 B/C/D 候选文件时，可用已核实的 round3 快照目录运行：

```powershell
python datasets/round4/member_A/build_candidates.py --round3-root <round3快照中的datasets/round3目录>
python datasets/round4/member_A/verify_candidates.py --round3-root <同一目录>
```

全局冻结之后，候选范围、近邻亲缘、四人合并后的用途和阶段都可能调整。此包不提供生成谱的命令，也不授予生产放行或训练纳入资格。
