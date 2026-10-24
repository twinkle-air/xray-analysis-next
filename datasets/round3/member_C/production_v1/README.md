# 第三轮成员 C 全量交付

2026-10-24。**1,686 条合成谱**（基础 1,500 + 内部留出 T 挑战 186），48 个原生密封批次，250 配方 / 105 设计族，全部按 `shared/freeze_v1` 与 `owner_release_v3` 生成并逐批通过窗口预算、完整 audit、完整物理 replay（不传 `--limit`）、pack、ZIP CRC 与 SHA-256。当前状态：**待 owner 统一审查**；`training_inclusion_approved=false`，T 仅用于留出物理 QC。

## 数量

| 项目 | 数量 |
| --- | ---: |
| 基础谱 | 1,500 |
| T 挑战谱（31 个留出配方 × 3 T profile × 2 重复） | 186 |
| 总谱数 | 1,686 |
| 原生密封批次 | 48 |
| 配方 / 设计族 | 250 / 105 |
| 族用途（训练/验证/内部留出） | 72 / 16 / 17 |
| 硅酸盐 / 富铁配方 | 150 / 100 |
| 类别（梯度/干扰/配对/常规） | 90 / 50 / 60 / 50 |
| 归档体积（48 ZIP） | 398,833,953 B |
| QC 归档 | 488,106 B |

## 目录

- `archives/R3_C_*.zip` 与同名 `.sha256`：48 个原生密封批次，含 `blind_inputs`、`truth.jsonl`、`full_results`、六分量、谱线/窗外账目、`configs`、`inputs`、`reproducibility`（生成器/依赖/环境快照）、`manifest.json`、`integrity.json`。不交付展开谱目录。
- `C_round3_blind_inputs.zip`（+ `.sha256`）：1,686 个仅含 `axis/x/counts/synthetic` 的不透明文件，文件名用 `opaque_blind_id`，不含元素、浓度、profile、母族或种子。
- `actual_record_index.csv`：1,686 行外置记录索引，`global_record_id = batch_id/native_id`；含配方/族/用途/profile/repeat/noise_seed、blind/full 哈希、归档路径与哈希；`eligible_for_training=false`。
- `archive_index.json`：每批 SHA-256、字节数、谱数、audit/replay 成员路径。
- `reports/C_all_batch_QC.zip`：48 批的 `audit.json`、`replay.json`、`window_budget.json`、`commands.json`、`summary.json`、`external_record_index.csv`、stdout/stderr 日志、`parallel_run.json`。
- `reports/commands_and_environment.json`：48 批真实 argv、退出码、每批耗时、依赖/环境、冻结身份。
- `verification.json` / `selfcheck_summary.json` / `delivery_manifest.json`。

## 执行

官方入口（单批顺序驱动）：

```powershell
powershell -NoProfile -File datasets/round3/shared/production_tools/run_member_full.ps1 -Member C -Python <venv>/Scripts/python.exe
```

实际执行使用同一份冻结命令清单 `shared/handoffs/20261024/member_C_full_commands.json` 的 48 条 argv，仅替换解释器路径与输出根目录，并以 10 个并发批次运行（驱动脚本随交付保存为 `reports/run_parallel.py`）。每批仍独立执行生成 → 窗口预算 → audit → replay → pack；未修改物理核心、未传 `--limit`、未放宽预算、未删除难谱。

环境：Python 3.12.14（项目本地 venv），numpy 2.4.6、scipy 1.17.1、xraylib 4.3.0、matplotlib 3.11.2、openpyxl 3.1.5，与 `requirements-lock.txt` 一致。

耗时：48 批动作累计 6.69 小时（生成 0.00 h、replay 3.11 h、audit 4.7 min、pack 6.3 min）；10 并发墙钟约 44 分钟（15:12–15:56，本机 16 逻辑核）。

## 核验结果

- 48/48 批 `audit=passed`、`replay=all_records_passed`（`complete_physics_recalculation=true`）、窗口预算全行通过、`zip_crc_checked=true`。
- 48 个 ZIP 的 SHA-256 与 `.sha256`、`summary.json`、`archive_index.json` 一致；5,484 个 ZIP 成员按 `integrity.json` 逐文件重算 SHA-256 通过。
- 1,686 行与 `record_plan.csv` 逐字段一致；`global_record_id`、`opaque_blind_id`、`noise_seed`、`(recipe, profile, repeat)` 均 1,686 个唯一值。
- 1,500 基础 + 186 T；250 配方、105 族、族用途 72/16/17；每族变体数 × 3 profile × 2 重复逐族核对；T profile 只出现在 `challenge` 批次；物理核心哈希与冻结身份一致。

## 失败与保留

两次启动失败发生在任何完整批次之前：第 1 次解释器缺 matplotlib（已按锁定依赖补齐），第 2 次为切换并发而主动停止。两者产物保留在 `work/round3/member_C_production_v1_failed_attempt*`，未计入交付、未进入索引；交付内无失败谱。

## 限制

合成数据，未做真实设备准确度或外部独立盲测；T 不得用于训练、校正、响应字典或选参；owner 审查通过前不是已验收训练数据。候选阶段材料（`candidates/`、`frozen_inputs/`、`reports/verification.json` 的候选版）保留未改。
