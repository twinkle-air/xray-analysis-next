# 失败修订记录（保留，不覆盖）

- 批次结果：200/200 失败，`PackageNotFoundError: No package metadata was found for matplotlib`
- 实际谱计数：0（`selfcheck_summary.json: actual_records=0`，`status=failed_partial_retained`）
- 原因：本地运行环境缺少冻结 `scope.json` 要求的 `matplotlib 3.11.2`（及 `openpyxl 3.1.5`）。
- 处理：补齐 `matplotlib==3.11.2`、`openpyxl==3.1.5`；`numpy 2.4.6 / scipy 1.17.1 / xraylib 4.3.0` 与冻结一致。
- 处置：本目录的 `sealed_batches/` 与 `reports/` 保留作失败证据，不计入任何交付数量；重跑使用新修订路径 `outputs/round4-B-production-r2`。
- 未删除任何失败谱或报告；未放宽窗口预算。
