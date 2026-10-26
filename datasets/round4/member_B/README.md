# 第四轮成员B交付入口

状态（2026-10-26）：**候选与完整生产均已交付**。20,000 条谱全部通过批级窗口预算、全量 audit、全量物理 replay 与 ZIP CRC，0 失败。等待 A 的汇总复核；`eligible_for_training=false`。

## 交付内容

| 目录 | 内容 |
|---|---|
| `candidates/` | 1,000 个候选组成 / 320 个合并前设计族、补偿账目、xraylib 线表证据、历史与跨成员 L1 筛查（已合并，PR #49） |
| `production_v1/` | 200 个原生批次 ZIP 与 SHA-256、外部实际索引、盲包（四段）、QC 汇总包、失败/中止与迁移证据、archive/delivery 清单、selfcheck 与资源预检 |
| `sealed_QC_only/` | 2,000 条封存记录索引与纪律说明（谱本体在 `production_v1/archives/`） |

## 本轮结论

- 记录数：**20,000 / 20,000**（训练 16,000 / 验证 2,000 / 封存 2,000）
- 批次：200 / 200 全部 `passed_all_records`，失败 0
- 原生归档：200 个 ZIP，合计约 4.79 GB，单体 22.7–25.1 MB
- 盲包：`B_round4_blind_inputs.zip` 160 MB，拆为四段（恢复方法见 `production_v1/blind/RESTORE.md`）
- 封存：`eligible_for_training=false`，只做生成/QC，未进入训练、校正、字典或选参

## 复核

```powershell
python datasets/round4/shared/production_tools/verify_release_gates.py --help
python datasets/round4/member_B/verify_candidates.py   # 候选侧
```

生产侧每批的 `summary.json`、`audit.json`、`replay.json`、`window_budget.json`、
`commands.json`、`actual_record_index.csv` 均已收进 `production_v1/reports/B_all_batch_QC.zip`，
逐文件 SHA-256 见 `production_v1/delivery_manifest.json`。

## 运行环境与重跑记录

运行环境：Python 3.13.14，`numpy 2.4.6 / scipy 1.17.1 / xraylib 4.3.0 / matplotlib 3.11.2 / openpyxl 3.1.5`
（与 `freeze_v1/scope.json` 的依赖版本一致）。

本机共出现 6 个失败/中止修订，全部保留未删，逐批记录与原始文档见 `production_v1/reports/failed_attempts/`：

| 修订 | 实测结果 | 完成 / 失败批次 |
|---|---|---|
| r1 | 缺 `matplotlib 3.11.2`，全批失败 | 0 / 200 |
| r2 | `--workers 2` 约 16.5 s/记录、预计约 23 小时，主动中止 | 0 / 0（未写 selfcheck） |
| r3 | `--workers 8` 在 15.7 GB 内存下 `MemoryError` | 37 / 128 |
| r4 | 当时权威修订，完成 63 批后暂停（未写 REASON） | 63 / 0 |
| r5 | `--workers 4`，`MemoryError` | 123 / 74 |
| r6 | `--workers 3`，验证段 `0010..0020` 仍 `MemoryError` | 189 / 11 |
| r7 | `--workers 2`，本次交付 | 200 / 0 |

迁移按 runner 自身的 resume 校验（summary 哈希 + 归档 SHA-256 + QC 清单哈希 + ZIP CRC）逐批进行；
`failed_attempts/migration.json` 记录每个最终批次的来源修订、原包与最终包 SHA-256、QC 哈希一致性；
`failure_records.zip` 收录全部 413 个逐批 `failure.json`，`failure_index.csv` 为其索引。
失败批次与展开数据保留在本机原修订目录（`failed_attempts/retention.json` 记录位置与体积），
未删除失败谱、未放宽窗口预算、未改冻结输入；未记录的字段在证据 JSON 中为 `null`，没有事后补写日志。

生成器/配置版本、冻结清单 SHA-256（`25deee31…`）与 release（`production_release_v1.json`）都在
`production_v1/selfcheck_summary.json` 与 `archive_index.json` 中可查。
