[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][ValidateSet('B','C','D')][string]$Member,
 [string]$Python = 'python',
 [string]$OutputRoot = '',
 [switch]$PlanOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../../..')).Path
$freeze = Join-Path $repoRoot 'datasets/round3/shared/freeze_v1'
$release = Join-Path $repoRoot 'datasets/round3/shared/releases/owner_release_v3.json'
$runner = Join-Path $PSScriptRoot 'run_batch.py'
if (-not $OutputRoot) { $OutputRoot = Join-Path $repoRoot ('work/round3/member_' + $Member + '_production_v1') }
$plan = Get-Content -Raw -LiteralPath (Join-Path $freeze 'batch_plan.json') -Encoding utf8 | ConvertFrom-Json
$batches = @($plan.batches | Where-Object { $_.member -eq $Member })
$expected = @{ B = 1746; C = 1686; D = 1716 }
$count = ($batches | Measure-Object -Property spectra -Sum).Sum
$baseCount = ($batches | Where-Object { $_.phase -ne 'challenge' } | Measure-Object -Property spectra -Sum).Sum
if ($count -ne $expected[$Member] -or $baseCount -ne 1500) { throw 'Frozen complete-member quota mismatch' }
foreach ($batch in $batches) {
 $sealed = Join-Path $OutputRoot ('sealed/' + $batch.batch_id)
 $qc = Join-Path $OutputRoot ('qc/' + $batch.batch_id)
 $arguments = @('-X','utf8','-B',$runner,'--repository',$repoRoot,'--freeze',$freeze,'--release',$release,'--batch',$batch.batch_id,'--out',$sealed,'--qc-out',$qc)
 if ($batch.phase -eq 'challenge') { $arguments += '--heldout-qc' }
 if ($PlanOnly) {
  [pscustomobject]@{batch_id=$batch.batch_id; spectra=$batch.spectra; phase=$batch.phase; executable=$Python; arguments=$arguments} | ConvertTo-Json -Compress -Depth 5
  continue
 }
 & $Python @arguments
 if ($LASTEXITCODE -ne 0) { throw ('Batch failed; preserve outputs and stop: ' + $batch.batch_id) }
}
if (-not $PlanOnly) { Write-Output ('Member ' + $Member + ': complete ' + $count + ' spectra. Submit native ZIPs, hashes, full QC evidence and record index via PR for owner review. Training inclusion remains unapproved.') }
