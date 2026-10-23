# 第三轮全局输入 v1：只放行 A 试片

四方1,000配方/420设计族全部收齐；候选和原始底板对3,800条已收录历史、跨族组成L1≤0.5检查无连接。全族用途固定为700训练/150验证/150内部留出，族数294/63/63。未记录历史亲缘不能排除，因此不是外部独立盲测。6,900条噪声种子全局唯一；对第二轮6,000条种子无碰撞，第一轮种子登记不完整，不宣称全历史查重。

`family_assignments.json` 固定每族三个基础profile；训练/验证为1锚点+2个不同D条件，内部留出为P1/P2/P3并额外T1/T2/T3。每个重点元素有4个训练梯度族含D5长曝光及较短曝光条件。`record_plan.csv` 固定计数子种子、重复、opaque盲ID和外置研究用途；原生generator_split不是研究划分。`batch_plan.json`把完整族组织成最多25配方的193个原生批次，四名成员的90谱试片均计入各自1,500基础谱。

`freeze_manifest.json`固定输入字节。`release.json`只批准A的90谱试片，批量出谱和训练入库均为false；B/C/D试片仍待后续负责人release。配置12份和物理核心逐字节继承准备区；T目录仅物理QC，模型、字典、校正和选参禁入。

前置检查为3,450个配方/profile静态组合与已封存24次探针数值检查；**不是3,450次完整正向验证**。可选全候选正向预检查未完成，不记通过。A实际90谱另逐条通过窗外预算、全量audit、全量物理replay、ZIP SHA/CRC，见member_A/pilot_v1。每个后续批次也必须检查预注册预算，不放宽、不删失败谱。物理核心和模型没有修改。

从仓库根目录复现A试片的一个批次（输出必须为新目录；相同冻结job只能作为重放核对，不可重复计入配额）：

```powershell
python -X utf8 -B datasets/round3/shared/production_tools/run_batch.py --repository . --freeze datasets/round3/shared/freeze_v1 --batch R3_A_pilot_D1_001 --out work/round3-replay/R3_A_pilot_D1_001 --qc-out work/round3-replay-qc/R3_A_pilot_D1_001
```

全部批次ID和固定种子见batch_plan，不改seed补数量。批量命令当前会明确拒绝；后续应版本化release后再运行。生产工具只在外围调用封存生成器，audit/replay/pack使用每个批次内的源码快照，不传--limit。原始sealed和full_results只以ZIP发布；独立盲输入使用opaque文件名另包，不把带类别/条件的native路径当作盲特征。
