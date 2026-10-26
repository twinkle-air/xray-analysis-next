# 失败、中止与续跑迁移证据（B，第四轮）

本目录是第四轮 B 生产过程中所有失败/中止修订的原始证据摘录。数据来自仍保留在本机的
`repo4/outputs/round4-B-production*` 目录；没有事后补写运行日志，未记录的字段在 JSON 中为 `null`。

## 修订序列（实测）

| 修订 | 结果 | 完成批次 / 谱 | 失败记录 | 记录文档 |
|---|---|---:|---:|---|
| `round4-B-production` | failed_partial_retained | 0 / 0 | 200 | RETRY_REASON.md |
| `round4-B-production-r2-aborted-partial` | 未生成 selfcheck（中止或运行中） | 0 / 0 | 0 | REASON.md |
| `round4-B-production-r3` | failed_partial_retained | 37 / 3,700 | 128 | REASON.md |
| `round4-B-production-r4` | 未生成 selfcheck（中止或运行中） | 63 / 6,300 | 0 | — |
| `round4-B-production-r5` | failed_partial_retained | 123 / 12,300 | 74 | REASON.md |
| `round4-B-production-r6` | failed_partial_retained | 189 / 18,900 | 11 | REASON.md |
| `round4-B-production-r7` | passed_member_full_QC_pending_coordinator_acceptance | 200 / 20,000 | 0 | — |

- r1：环境缺 `matplotlib 3.11.2`（及 `openpyxl 3.1.5`），200 批全部失败、0 条谱；补齐依赖后另起修订。
- r2：保留原因文档记录 4 worker， 实测约 16.5 s/记录、预计约 23 小时，主动中止，未写 selfcheck。
- r3：`--workers 8` 在 15.7 GB 内存下 `MemoryError`；37 批通过、128 批失败。
- r4：当时的权威修订，完成 63 批后暂停；未写 REASON 文档，本目录不臆造。
- r5：`--workers 4`，123 批通过、74 批失败。
- r6：`--workers 3`，189 批通过、11 批失败（验证段 `0010..0020`）。
- r7：`--workers 2`，200 / 200 通过，即本次交付。

## 文件

| 文件 | 内容 |
|---|---|
| `reason_docs/` | 各修订原始的 `REASON.md` / `RETRY_REASON.md` 副本（逐字节复制） |
| `selfcheck/` | r1、r3、r5、r6 当时的 `selfcheck_summary.json` 副本（含完整 failures 列表） |
| `failure_records.zip` | 全部 **413** 个逐批 `failure.json`，按 `修订/批次/` 归档 |
| `failure_index.csv` | 上述失败记录的索引（修订、批次、错误文本、字段） |
| `attempts.json` | 每个修订的工作进程数、完成量、失败数、起止时间、体积，以及未记录字段的 `null` |
| `migration.json` | 200 个最终批次的来源修订、迁移路径、原包与最终包 SHA-256、QC 哈希一致性、失败过的修订 |
| `retention.json` | 失败/部分数据在本机的保留位置、文件数与体积（不随仓库交付） |
| `carry_completed.py` | 迁移续跑所用脚本的副本，说明准入规则 |

## 迁移对应关系

逐批迁移记录见 `migration.json`。摘要：200 个最终批次中，
200 个的原包与最终包 SHA-256 完全一致，
200 个的 QC 文件哈希与最终包一致，
0 个无法在早期修订中找到来源（`null`，如实标注）。

迁移准入使用 runner 自身的 resume 校验（批次 summary 哈希、归档 SHA-256、QC 清单哈希、ZIP CRC）；
只有通过校验的批次才被复制到新修订，失败批次与其展开数据保留在原修订目录，不删除、不改窗口预算、不改冻结输入。

## 汇总口径复核

worker 数按原始原因文档中本次修订的描述摘录，后续重启参数单独理解，不用于覆盖本次 worker 数。完整 CLI 和进程退出码未被保留，在 attempts.json 中明确为 null。

413 表示归档内实际保留的 failure.json 数量。selfcheck 原件的失败项另计：r1=200、r3=181、r5=77、r6=11、r7=0。r3 原件记录 19 批完成，目录盘点有 37 个通过 summary；r5 原件有77条失败项，目录盘点有74份 failure.json。这些来源并非已证实为同一观测，差异原因未记录；原始 selfcheck、原因文档和 failure.json 均未改写。最终交付计数以 r7 的 20,000 条记录及200批完整 QC 为准。
