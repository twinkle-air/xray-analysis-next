# 第三轮A：候选已构建，待全局冻结

已完成250种候选组成、105个设计族；90梯度、50干扰、60负例/加标、50常规，硅酸盐/富铁150/100。候选不是已经生成的能谱，实际训练谱数量为0。目标仍为1,500基础谱，追加T谱数量等待全局分配。

- [任务依据](../planning/A_任务清单.md) · [唯一方案](../planning/第三轮数据构建方案.md)
- [250候选及完整组成/换算/补偿账目](candidates_v1/A_samples.json)
- [105族登记](candidates_v1/family_registry.json) · [CSV主表](candidates_v1/formula_registry.csv)
- [候选检查与历史近邻](candidates_v1/candidate_checks.json) · [32标签覆盖](candidates_v1/coverage.json)
- [编译、确定性重建与失败路径核查](reports/verification.json) · [生产前待办](reports/production_readiness.json)
- [公共条件/设计准备](../shared/preparation_v1/README.md) · [源输入哈希](inputs/source_manifest.json)

在仓库根目录、安装inputs/generator/fp_competition/requirements-lock.txt对应依赖的Python环境中运行：

```text
python -B datasets/round3/member_A/verify_candidates.py
```

重新构建候选必须指定一个不存在的新目录，不覆盖原候选：

```text
python -B datasets/round3/member_A/build_candidates.py --out datasets/round3/member_A/candidates_rebuild
```

构建脚本只创建配方和账目，不生成谱。inputs保存已有历史组成的检查快照、设计范围、原锚点及未改物理核心的生成器源码；不依赖本机outputs路径复现候选。source_manifest为候选输入快照，不能视作生产冻结。

可用历史检查覆盖第二轮全部1,000配方及已知第一轮候选/试片/研究登记，共3,800条记录（不宣称互相独立）。最小完整组成L1约3.6702质量百分点，无≤0.5匹配；A不同设计族之间无≤0.5连接。同族变体仍须整体分配。未记录的历史亲缘和B/C/D交叉关系尚未排除。

公共9开发/3留出配置完成24次固定探针数值检查，不是90谱试片。T不可进入模型训练、校正、响应字典和选参，模型侧适配尚未完成。未跑模型挑选新候选。

下一步先收齐B/C/D候选，做全局闭包与用途、每族条件/长曝光、子种子和正式源码/命令冻结，再做A的15配方×6=90谱试片，最后批量生产及封存源全量audit/replay。当前不能把本目录当成已验收训练数据；合成检查不证明真实95%/5%准确度。
