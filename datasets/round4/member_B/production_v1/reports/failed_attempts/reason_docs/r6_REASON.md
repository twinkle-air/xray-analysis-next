# 部分批次 OOM 中止记录（保留，不覆盖）

- 结果：189/200 批通过（18,900 谱），11 批 `MemoryError`（均为 `validation_development_0010..0020`）。
- 原因：本机 15.7 GB 内存，验证段批次在 replay 阶段峰值更高，3 worker 下仍触顶。
- 处置：189 批按 resume 校验迁入 `round4-B-production-r7`；11 批在新修订用 `--workers 2` 重跑。
- 未删除失败谱、未放宽窗口预算、未修改冻结输入。
