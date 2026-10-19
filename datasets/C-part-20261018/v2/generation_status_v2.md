# v2 批次生成状态（只读快照）

- 数据集目录：`P5_dataset_v2`｜阶段：**sealed_complete_batch**｜谱数 2000/2000（100.0%）
- 三者一致性：blind 2000 / full 2000 / truth 2000 → True；manifest.records 2000，独立族 1000
- 主表：`master_samples_v2.json` SHA-256 `78ca94780021c179…`
- 批次身份：{"schema": "competition-fp-dataset/0.2", "software_version": "0.2.1", "physical_model_version": "0.2.0", "batch_version": "C-recipes-v2", "supersedes": "C-part-20261018 (C-recipes-v1, PR #2 review_failed)", "seed": 2026110205, "split_seed": 20261102, "replicates": 2, "status": "complete", "acceptance_status": "pending_independent_validation", "source_samples_semantic_sha256": "07b1215d8288a556dc583801594c84b3b04dfc606d89ff0cc60e90de40474262", "physics_core_sha256": "e820ecdb5ed5fbceb870f382c8c7c411ba85c65673bc19258fb935f562ed83b0"}
- 磁盘占用：1.30 GiB｜剩余 0 谱，预计 0.0–0.0 分钟
- 质检产物：{"audit.json": false, "replay.json": false, "integrity.json": true, "reproducibility/environment.json": true}
- 是否已推送 GitHub：否（以分支提交为准）

## 说明

- 合成数据；未做真实设备校准，不能据此得出 95%/5% 一类准确率结论。
- 批次未完成前 manifest.records 只是阶段性清单，不可作为最终交付依据。
- 本批若最终不用于交付，也仅作为候选试产，不得进入训练/调参入口。
