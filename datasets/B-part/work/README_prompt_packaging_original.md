# 成员 B：交给执行 Agent 的任务提示词

1. 先发送 `01_B_design_and_pilot_prompt.md`：直接使用工作区 `fp-spectrum-generator-competition-v0.2.1/fp_competition/app.py`，完成 1,500 条 B 配方、P3/P4 候选条件，并先生成/验收 400 条 B 配方试产谱；同时核查三人方案 M1 状态。
2. 待 A/C 冻结 5,000 条主表、P3/P4 最终配置、亲缘划分与索引规则，再发送 `02_B_formal_production_prompt.md`：先过门禁与 M3，随后正式生成 P3/P4 共 20,000 条谱，交 A 交叉复核；之后按冻结条件复核 C 的 P5。
3. `03_prompt_review.md` 记录覆盖性、本地生成器与 A 封存版本的逐文件核验，以及当前阻塞条件。

当前目录只有提示词和审查记录，不代表 B 数据或试产谱已生成。
