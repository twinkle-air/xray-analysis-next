# OOM 中止记录（保留，不覆盖，不计交付）

- 结果：37 批通过（3,700 谱）、128+ 批 `MemoryError` 失败；`selfcheck_summary.json` 为 `failed_partial_retained`。
- 原因：本机物理内存 15.7 GB，`--workers 8` 的峰值工作集超出可用内存。
- 处置：失败批次与展开数据全部保留在本目录；通过的 37 批已按 runner 的 resume 规则（summary 哈希 + 归档 SHA + QC 清单哈希 + ZIP CRC）迁移到 `outputs/round4-B-production-r4`，只补齐剩余批次。
- 未删除失败谱、未放宽窗口预算、未修改冻结输入。
