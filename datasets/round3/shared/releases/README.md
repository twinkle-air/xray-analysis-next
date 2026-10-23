# Owner release v2（2026-10-24）

基于已合并PR #28与A的90谱全量QC，允许A继续1,410基础谱+252挑战谱；B/C/D只允许各自90谱试片。固定freeze_v1的配方、母族用途、profile和噪声种子完全不变，不改sealed输入。run_batch.py新增可选--release与按成员批量门禁；release固定runner摘要、freeze_manifest摘要和已通过的A试片证据摘要，9项门禁测试通过。

训练入库未批准；B/C/D的批量仍拒绝。每人试片通过后须另发布版本化release，不能把A通过当作全员生产通过。已有freeze_v1/release.json保留原试片授权，默认不传--release仍保持旧门禁。
