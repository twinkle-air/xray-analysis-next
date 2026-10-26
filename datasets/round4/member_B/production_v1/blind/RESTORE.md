# 盲包恢复（B，第四轮 20,000 条）

`B_round4_blind_inputs.zip` 共 160,384,941 字节，因 GitHub 单文件 100 MB 限制拆为 4 段：

```
B_round4_blind_inputs.zip.part01
B_round4_blind_inputs.zip.part02
B_round4_blind_inputs.zip.part03
B_round4_blind_inputs.zip.part04
```

恢复（PowerShell）：

```powershell
$parts = Get-ChildItem B_round4_blind_inputs.zip.part* | Sort-Object Name
$out = [System.IO.File]::Create((Join-Path $PWD 'B_round4_blind_inputs.zip'))
foreach ($p in $parts) { $in = [System.IO.File]::OpenRead($p.FullName); $in.CopyTo($out); $in.Close() }
$out.Close()
Get-FileHash B_round4_blind_inputs.zip -Algorithm SHA256
```

恢复后必须与 `B_round4_blind_inputs.zip.sha256`（`58bef87ea58561983b686d6644e4be65f431bd4270f349c103872ade69bec3ac`）一致，再进行 ZIP CRC 校验（`Expand-Archive` 或 Python `zipfile.testzip()`）。
各段各自的 SHA-256 见 `PARTS.sha256`；合并顺序按文件名 part01…part04，不能调换。

盲包内每个文件名都是 opaque 盲 ID，只含原始通道计数与必要格式字段；真值、条件、种子、家族与用途都不在其中，这些元数据只在 `../actual_record_index.csv` 与批次 QC 里。
