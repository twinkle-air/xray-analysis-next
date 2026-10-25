# 第四轮完整配额生产工具

正式放行（2026-10-25）：项目负责人已明确授权ABCD完整生产，追加协作者审查已由负责人豁免。A 40,000谱，B/C/D各20,000谱，不做试片。当前准入以[production_release_v1.json](../releases/production_release_v1.json)为准；封存输入内的待审查文字是形成时的历史状态。


当前 release 已由项目负责人明确授权，`production_approved=true`，可以在本人无产谱预检通过后执行完整配额。没有 400 谱试片，也不需要等待逐阶段生成。

## 预检

在协作仓库根目录，以满足冻结中 NumPy/SciPy/xraylib 版本的 Python 运行。把 `--member A` 改为本人编号即可；以下命令不正演、不生成能谱：

```powershell
python -B datasets/round4/shared/production_tools/run_member.py --repository . --freeze datasets/round4/shared/freeze_v1 --release datasets/round4/shared/releases/production_release_v1.json --member A --dry-run --preflight-report outputs/round4-A-preflight.json
```

`--dry-run` 核对全部冻结文件和源码哈希、依赖版本、本人配额、每条种子/条件、整族用途及封存隔离。报告写在冻结目录之外。失败时先处理真实错误，不能把模板状态改成通过。

## 全量生产

PR #51 已合并；负责人已明确授权正式放行并豁免追加审查。冻结与工具哈希核对通过后，直接执行：

```powershell
python -B datasets/round4/shared/production_tools/run_member.py --repository . --freeze datasets/round4/shared/freeze_v1 --release datasets/round4/shared/releases/production_release_v1.json --member A --out outputs/round4-A-production --workers 4 --minimum-free-gib 10 --include-sealed-qc
```

A 一次处理 40,000 谱；B/C/D 将编号和输出路径改为本人，各处理 20,000 谱。`--include-sealed-qc` 只允许生成和物理 QC，不调用模型或读取封存结果来调参。所有产物初始 `eligible_for_training=false`。

执行器保留冻结的逐条 profile；同条件的两个噪声重复用不同种子。每个原生批次生成后依次检查窗口预算、完整 audit、完整物理 replay 和 ZIP CRC，再记录 actual_record_index。最后汇总 opaque 文件名盲包、原生档案、QC ZIP、交付清单和 SHA-256。展开的 sealed_batches 是本机复现工作副本，不计作新增谱或重复交付。

相同输出路径可续跑：仅跳过冻结哈希、档案 SHA/CRC 和完整成功摘要匹配的批次。遇到部分/失败批次会保留原谱与 failure.json 并拒绝覆盖，先记录处理原因，再使用明确的新修订路径重跑；不能静默移除失败记录。磁盘低于保留阈值时保留已完成批次并报错。

## 审查与复建

- `prepare_global.py`：候选接收、化合物与真零重建、完整历史池亲缘闭环、整族用途和学习曲线队列。`--out` 必须是新的目录。
- `prepare_conditions.py`：由既定敏感性幅度构造 50,000 个条件与 100,000 条记录；扩展生成器包装层并准备源码、窗口预算和静态检查。
- `verify_freeze.py`：独立核对全部条件与记录，验证旧输入抽样不变、显式条件重复一致和四个失败路径；不计算谱。
- `run_member.py`：完整配额执行和无产谱预检。实际审计/重放使用与封存源码一致的生成器，不只重放计数种子。

所有输入都以 `freeze_manifest.json` 绑定；生产工具通过 release 中的哈希绑定。改源码、候选、条件或名册后应建立新修订，不能在已批准冻结内就地替换。
