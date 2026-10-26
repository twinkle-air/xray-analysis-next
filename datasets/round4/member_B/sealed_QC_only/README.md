# 封存谱索引（B，第四轮）

本目录只放封存用途的**索引与说明**，不放能谱本体。2,000 条封存记录的 blind/full 路径、SHA-256 与所属原生归档在 `sealed_record_index.csv`；谱本体在 `../production_v1/archives/` 对应的批次 ZIP 内，其 SHA-256 见 `../production_v1/archive_index.json` 与每个 `.zip.sha256`。

封存纪律：`eligible_for_training=false`。仅允许文件与数值 QC；禁止训练、校正拟合、响应字典、选参或任何形式的模型尝试。报告中的封存结果只能称“未用于选择的内部评价”，因为同仓库内可见真值，不构成对全队的严格盲测隔离。
