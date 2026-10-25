# C 部分候选配方 v1

状态：C 本地候选校核已完成；尚未完成 A/B/D 汇总、全局亲缘闭环、最终用途/阶段分配或生产冻结。此目录中的内容是组成候选，不是能谱数据。

## 本次候选规模

- 1,000 个唯一组成，320 个合并前设计族。
- 元素梯度：40 族 × 10 个配方 = 400。
- 零/加标配对：40 族 × 5 个配方 = 200（1 个真零 + 4 个正水平）。
- 低含量干扰控制：40 族 × 5 个配方 = 200。
- 常规覆盖：200 族 × 1 个配方 = 200。
- 基体按硅酸盐/氧化物与富铁氧化物各半配置：500 / 500 个配方。
- 名义用途预算（仅候选阶段，A 全局冻结后才生效）：训练 800、验证 100、封存测试 100 个配方；对应 256/32/32 个完整族。

每个配方记录完整 used composition、原始氧化物/痕量背景、换算结果、受控元素值、移除/加入的载体和质量补偿比例。C 的目标是零含量—加标配对、低含量梯度和计数统计：梯度族同时覆盖痕量到主量范围，零/加标族覆盖检出阈值附近，真实标签是实际 used_percent。全部配方保留完整 32 个目标元素标签和 O 基体闭合。

## 干扰控制的线表证据

40 个低含量干扰族全部用 xraylib 实际线表核对：目标元素分析线与干扰元素线在 150 eV 候选能窗内，逐族记录线名、能量、相对强度和差值，见 `line_interference_evidence.csv`。能窗是候选筛选假设，不是已冻结的第四轮探测器响应或公共 profile；最终能窗和响应须由 A 的公共范围/条件冻结确认。

## 历史近邻边界

候选与第三轮 A 输入表中的第一/二轮已知历史组成（3,800 条）以及仓库中第三轮 A/B/C/D 候选组成（1,000 条）比较 L1 距离。`nearest_history.csv` 与 `original_background_nearest_history.csv` 保存逐条近邻。最小候选—历史 L1 为 3.7982 个百分点；≤0.5 连接 0 条；C 候选跨设计族 ≤0.5 近邻边 0 条。与已合并的 A 第四轮 2,000 个候选做逐对比较：最小 L1 2.9342 个百分点，≤0.5 对 0 个，精确重复 0 个；B/D 的第四轮候选和四人全局闭环仍待 A 合并。候选范围只覆盖已登记来源，不能证明不存在未记录的历史亲缘。

所有候选的 requested role 只是 `train_nominal`/`validation_nominal`/`sealed_test_nominal` 预算，`global_role_status` 仍为 `pending_global_freeze`；没有最终 train/test 分配、条件实例、生产噪声种子或训练资格。脚本生成的候选设计 RNG 值仅用于可复现地构造配方，不是测谱噪声子种子或批量生成种子。

## 下一步与生产口径

当前生产被前置条件阻塞：A 尚未发布第四轮公共范围、条件/profile、`freeze_v1` 和完整生产 release，仓库状态仍为 `usable_for_generation=false`、`production_started=false`。因此本目录不含运行器、条件实例、噪声种子或能谱，也不能复用第三轮命令出谱。

C 不安排 400 谱试片。待 A 的公共冻结和完整生产 release 通过后，按冻结 release 一次生成全部 20,000 条谱（1,000 配方 × 10 个真实条件 × 2 个独立计数噪声），随后做一次全量 audit/replay/QC，再打包交付。封存部分保持 `eligible_for_training=false`。

## 复核与重建

在协作仓库根目录执行：

```powershell
python datasets/round4/member_C/build_candidates.py
python datasets/round4/member_C/verify_candidates.py
```

`build_candidates.py` 默认拒绝覆盖已有输出。`verify_candidates.py` 独立检查数量、闭合、补偿重建、范围、名义用途计数、线表证据、历史距离和交付哈希，并写出 `independent_verification.json`。当前没有可执行的第四轮生产命令；本目录不含任何能谱。
