# 第四轮成员B交付入口

状态（2026-10-26）：**候选与完整生产均已交付**。20,000 条谱全部通过批级窗口预算、全量 audit、全量物理 replay 与 ZIP CRC，0 失败。等待 A 的汇总复核；`eligible_for_training=false`。

## 交付内容

| 目录 | 内容 |
|---|---|
| `candidates/` | 1,000 个候选组成 / 320 个合并前设计族、补偿账目、xraylib 线表证据、历史与跨成员 L1 筛查（已合并，PR #49） |
| `production_v1/` | 200 个原生批次 ZIP 与 SHA-256、外部实际索引、盲包（两段）、QC 汇总包、archive/delivery 清单、selfcheck 与资源预检 |
| `sealed_QC_only/` | 2,000 条封存记录索引与纪律说明（谱本体在 `production_v1/archives/`） |

## 本轮结论

- 记录数：**20,000 / 20,000**（训练 16,000 / 验证 2,000 / 封存 2,000）
- 批次：200 / 200 全部 `passed_all_records`，失败 0
- 原生归档：200 个 ZIP，合计约 4.79 GB，单体 22.7–25.1 MB
- 盲包：`B_round4_blind_inputs.zip` 160 MB，拆为两段（恢复方法见 `production_v1/blind/RESTORE.md`）
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

本机曾出现四个失败/中止修订，全部保留未删：缺 `matplotlib` 导致的全批失败、4 worker 过慢主动中止、
8/4/3 worker 在 15.7 GB 内存下的 `MemoryError` 分批失败。已通过批次按 runner 的 resume 规则迁移续跑，
失败批次与展开数据保留在原修订目录并附 `REASON.md`；未删除失败谱、未放宽窗口预算、未改冻结输入。

生成器/配置版本、冻结清单 SHA-256（`25deee31…`）与 release（`production_release_v1.json`）都在
`production_v1/selfcheck_summary.json` 与 `archive_index.json` 中可查。
