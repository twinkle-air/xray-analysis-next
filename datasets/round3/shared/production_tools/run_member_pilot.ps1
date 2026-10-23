[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][ValidateSet('B','C','D')][string]$Member,
 [string]$Python = 'python',
 [string]$OutputRoot = ''
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../../..')).Path
$freeze = Join-Path $repoRoot 'datasets/round3/shared/freeze_v1'
$release = Join-Path $repoRoot 'datasets/round3/shared/releases/owner_release_v2.json'
$runner = Join-Path $PSScriptRoot 'run_batch.py'
if (-not $OutputRoot) { $OutputRoot = Join-Path $repoRoot ('work/round3/member_' + $Member + '_pilot_v1') }
$plan = Get-Content -Raw -LiteralPath (Join-Path $freeze 'batch_plan.json') -Encoding utf8 | ConvertFrom-Json
$batches = @($plan.batches | Where-Object { $_.member -eq $Member -and $_.phase -eq 'pilot' })
$count = ($batches | Measure-Object -Property spectra -Sum).Sum
if ($count -ne 90) { throw 'Frozen member pilot must contain exactly 90 spectra' }
foreach ($batch in $batches) {
 $sealed = Join-Path $OutputRoot ('sealed/' + $batch.batch_id)
 $qc = Join-Path $OutputRoot ('qc/' + $batch.batch_id)
 $arguments = @('-X','utf8','-B',$runner,'--repository',$repoRoot,'--freeze',$freeze,'--release',$release,'--batch',$batch.batch_id,'--out',$sealed,'--qc-out',$qc)
 & $Python @arguments
 if ($LASTEXITCODE -ne 0) { throw ('Pilot failed; preserve all outputs and stop: ' + $batch.batch_id) }
}
Write-Output ('Member ' + $Member + ': 90-spectrum pilot complete. Submit all sealed ZIPs, SHA-256, audit/replay/window reports and actual environment to A. Bulk remains blocked.')
