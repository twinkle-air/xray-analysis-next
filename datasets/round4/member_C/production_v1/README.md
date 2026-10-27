# Round-4 member C production_v1

冻结生成器 v1 全量 20,000 谱（200 批 × 100），freeze manifest `25deee3198281d033641ca45817a40727461269df11d653df5ca842b908fa519`，无试片，全部记录 `eligible_for_training=false`，等待协调人验收。

- `actual_record_index.csv`：20,000 条记录的实际路径/SHA 账目。
- `transfer_chunks/C_round4_blind_inputs.zip.part*` + `chunk_manifest.json`：全部盲谱 ZIP 的无损分块（48 MiB/块），按序拼接后核对整档 SHA-256 与 ZIP CRC；分块本身不是能谱。
- `transfer_chunks/C_all_batch_QC.zip`：200 批 audit/replay/window_budget/commands/summary/index 的 QC 包。
- `native_archive_pointers.json`：200 个原生档案（含 truth/full 结果，共 4.48 GiB）的本地路径、大小与 SHA-256。原生档案不进 git：本仓库共享克隆带宽下 4.8 GiB 会使他人无法拉取，档案保持在本人输出目录可重建，需要时另行受控传输。
- `selfcheck/summary.json`、`delivery_manifest.json`：本人全量自检与交付账目。

密封测试记录只交盲谱 JSON 与 QC 证据（见 `../sealed_QC_only/`），不交原生档案。

## 分块恢复（PowerShell）

```powershell
cd datasets/round4/member_C/production_v1/transfer_chunks
$parts = (Get-ChildItem 'C_round4_blind_inputs.zip.part*').Name | Sort-Object
$out = 'C_round4_blind_inputs.zip'
Remove-Item $out -ErrorAction SilentlyContinue
$fs = [IO.File]::Create($out)
foreach ($p in $parts) { $fs.Write([IO.File]::ReadAllBytes($p), 0, (Get-Item $p).Length) }
$fs.Close()
(Get-FileHash $out -Algorithm SHA256).Hash.ToLower()   # 必须等于 chunk_manifest.json 的 sha256
```
