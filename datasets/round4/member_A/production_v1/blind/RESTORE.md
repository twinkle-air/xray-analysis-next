# A 盲包无损恢复

本目录的 part 文件是运输分片，不是额外谱。8 段按 transport_manifest.json 中的明确顺序恢复；不得将分片目录递归当作训练输入。

从 production_v1 目录运行：

```powershell
python -B blind/restore_blind.py
```

脚本逐段校验 SHA-256、合并后校验整体 SHA-256、ZIP CRC、40,000 个不透明文件名。恢复结果是 production_v1/A_round4_blind_inputs.zip，与原 delivery_manifest.json 和 archive_index.json 的逻辑路径一致。已存在且正确的结果只核验；已存在但不同的结果不会被覆盖。

原始 delivery_manifest.json 按重建后的逻辑文件记账；publication_manifest.json 列的是 Git 实际运输文件。分片重建不改变谱、噪声或计数，也不代表额外独立样本。
