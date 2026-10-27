# Round-4 member C production_v1

冻结生成器 v1 全量 20,000 谱（200 批 × 100），freeze manifest `25deee3198281d033641ca45817a40727461269df11d653df5ca842b908fa519`，无试片，全部记录 `eligible_for_training=false`，等待协调人验收。

- `actual_record_index.csv`：20,000 条记录的实际路径/SHA 账目。
- `transfer_chunks/C_round4_blind_inputs.zip.part*` + `chunk_manifest.json`：全部盲谱 ZIP 的无损分块（48 MiB/块），按序拼接后核对整档 SHA-256 与 ZIP CRC；分块本身不是能谱。
- `transfer_chunks/C_all_batch_QC.zip`：200 批 audit/replay/window_budget/commands/summary/index 的 QC 包。
- `native_archive_inventory.json` / `native_archive_pointers.json` / `native_archive_receipt.json`：200 个原生 truth/full 档案（六分量、窗外账目、full_results、配置/环境/源码快照，共 4.48 GiB）的交接账目。原包不放 git 历史（会拖垮共享克隆带宽），改走 Release 资产：https://github.com/twinkle-air/xray-analysis-next/releases/tag/round4-C-production-v1-native，逐档 SHA-256 与 ZIP CRC 全量复核记录在 inventory，GitHub 回报的 asset digest 与之一致；20 个 sealed_test 原包合并为单个 AES256 容器上传，明文逐档 SHA-256 仍在 inventory 里，协调人解密后可逐档核对，其他成员看不到密封真值明文。
- `selfcheck/summary.json`、`delivery_manifest.json`：本人全量自检与交付账目。

密封测试记录在仓库内只交盲谱 JSON 与 QC 证据（见 `../sealed_QC_only/`）；其原生真值包以 AES256 容器随 Release 交接，凭据与解密核对方法见 `native_archive_receipt.json`。

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

## 原生档案接收与核对

```powershell
# 1) 逐个下载 Release 资产（仓库为私有：用带 token 的 API 地址 + Accept: application/octet-stream）
$env:GH_TOKEN = <协调人自己的只读 token>
$inv = Get-Content ../native_archive_inventory.json -Raw | ConvertFrom-Json
$rec = Get-Content ../native_archive_receipt.json -Raw | ConvertFrom-Json
foreach ($e in $inv.entries) {
  if ($e.role -eq "sealed_test") { continue }
  $a = $rec.assets | Where-Object { $_.asset -eq $e.archive }
  $h = @{ Authorization = ("Bearer " + $env:GH_TOKEN); Accept = "application/octet-stream" }
  Invoke-WebRequest $a.api_url -OutFile $e.archive -Headers $h
  if ((Get-FileHash $e.archive -Algorithm SHA256).Hash.ToLower() -ne $e.sha256) { "MISMATCH " + $e.archive }
}
# 2) 密封 20 档：解密 AES256 容器后按 receipt.sealed_test_custody.archives_inside 逐档核对
gpg --decrypt --pinentry-mode loopback R4_C_sealed_test_native_archives.zip.aes256.gpg > R4_C_sealed_test_native_archives.zip
```

GitHub 对每个资产回报的 digest 已记在 native_archive_receipt.json，与 inventory 的 SHA-256 全部一致（181/181），因此除“上传成功”外还有服务端存储字节的独立佐证；本人已实测通过 api_url 取回一个 validation 资产并核对 SHA-256 相同。
