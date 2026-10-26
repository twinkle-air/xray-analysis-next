# OOM 中止记录（保留，不覆盖，不计交付）

- 结果：123 批通过（12,300 谱），74+ 批 `MemoryError` 失败；`selfcheck_summary.json` 为 `failed_partial_retained`。
- 原因：本机 15.7 GB 内存，4 worker 在重放阶段峰值叠加时触发内存耗尽（与 r3 同因）。
- 处置：只把通过 resume 校验（summary 哈希 + 归档 SHA + QC 清单哈希）的 123 批迁入 `round4-B-production-r6`；
  失败批次与展开数据保留在本目录。下一轮改用 `--workers 3`。
- 未删除失败谱、未放宽窗口预算、未修改冻结输入。
