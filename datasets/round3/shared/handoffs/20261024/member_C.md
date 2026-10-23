# 第三轮 C：全量生产与一次性交付（当前指令）

2026-10-24 owner 明确指示“不用试产，直接全部推送，我再统一审查吧”。以 owner_release_v3 为准，替代此前分阶段试片交接。同步最新 main 后直接完成 1,500 基础谱 + 186 T挑战谱 = **1686 条谱**，自检完成后提交一份完整 PR，由 owner 统一审查。无需先交90谱等待放行。

在仓库根目录、已安装冻结依赖的 Python 环境执行：

```powershell
powershell -NoProfile -File datasets/round3/shared/production_tools/run_member_full.ps1 -Member C -Python python
```

可加 `-PlanOnly` 预览全部批次与命令；这不生成数据，也不代表自检通过。实际输出默认在 `work/round3/member_C_production_v1/`。逐批确切参数见 `member_C_full_commands.json`。

freeze_v1 的配方、整族用途、profile、噪声种子、物理核心与数量不变。冻结计划中 phase=pilot 的90谱只是基础1,500中的既有批次，本次一并生产，不额外加90谱、不做中途审查。不自由 jitter 或改种子。程序每批执行生成、窗口预算、完整 audit/replay、封装和 ZIP SHA/CRC；T批次显式使用 --heldout-qc。失败保留产物和日志并停止，修复原因后续交，不跳过检查或删除难谱。

若已实际完成部分冻结批次，不重复计数或覆盖原产物；核对其完整QC与身份后保留，按命令清单只运行缺失批次。已存在目录会拒绝覆盖。

交付：全部原生无损ZIP及.sha256、全量audit/replay/window_budget报告与终端日志、commands/environment/退出码、覆盖1686条唯一记录的外置索引、完整清单/自检汇总与实际耗时/体积。通过本人分支PR提交，不直接写main、不上传展开谱目录。统一复核数量/版本、文件及哈希、自检证据、全局family/split。生产放行不是数据审查通过。

T只用于留出物理QC，禁止训练/字典/校正/选参。training_inclusion_approved仍为false。
