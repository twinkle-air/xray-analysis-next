[CmdletBinding()]
param(
 [ValidateSet('B','C','D')][string]$Member = 'B',
 [string]$Python = 'python',
 [string]$Repository = '',
 [string]$OutputRoot = '',
 [switch]$PlanOnly,
 [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'

function Write-Log([string]$message) {
  $stamp = Get-Date -Format 'HH:mm:ss'
  Write-Host ('[' + $stamp + '] ' + $message)
}

# Walk up from the start directory until the collaboration repository root is found, so this
# script works both from datasets/round3/member_<X>/ and from a checkout root.
function Find-RepoRoot([string]$start) {
  $dir = (Resolve-Path -LiteralPath $start).Path
  while ($true) {
    if (Test-Path (Join-Path $dir 'datasets/round3/shared/freeze_v1/batch_plan.json')) { return $dir }
    $parent = Split-Path $dir -Parent
    if ([string]::IsNullOrEmpty($parent) -or $parent -eq $dir) {
      throw ('cannot locate the collaboration repository root from ' + $start)
    }
    $dir = $parent
  }
}

$startDir = $PSScriptRoot
if (-not [string]::IsNullOrEmpty($Repository)) { $startDir = $Repository }
$repoRoot = Find-RepoRoot $startDir
$freeze = Join-Path $repoRoot 'datasets/round3/shared/freeze_v1'
$release = Join-Path $repoRoot 'datasets/round3/shared/releases/owner_release_v3.json'
$runner = Join-Path $repoRoot 'datasets/round3/shared/production_tools/run_batch.py'
$verifyScript = Join-Path $PSScriptRoot 'verify_batch_qc.py'
if (-not (Test-Path $verifyScript)) { throw ('missing QC verifier next to this script: ' + $verifyScript) }
if ([string]::IsNullOrEmpty($OutputRoot)) {
  $OutputRoot = Join-Path $repoRoot ('work/round3/member_' + $Member + '_production_v1')
}

$planPath = Join-Path $freeze 'batch_plan.json'
$plan = Get-Content -Raw -LiteralPath $planPath -Encoding utf8 | ConvertFrom-Json
$batches = @($plan.batches | Where-Object { $_.member -eq $Member })
$expected = @{ B = 1746; C = 1686; D = 1716 }
$count = ($batches | Measure-Object -Property spectra -Sum).Sum
$baseCount = ($batches | Where-Object { $_.phase -ne 'challenge' } | Measure-Object -Property spectra -Sum).Sum
if ($count -ne $expected[$Member] -or $baseCount -ne 1500) { throw 'Frozen complete-member quota mismatch' }

# Ask the shared verifier whether an existing sealed directory really finished.
function Get-BatchState([string]$batchId) {
  $sealed = Join-Path $OutputRoot ('sealed/' + $batchId)
  $qc = Join-Path $OutputRoot ('qc/' + $batchId)
  # Redirect every stream to a file: under $ErrorActionPreference = 'Stop' a harmless warning on
  # stderr becomes a terminating NativeCommandError and would abort the classification loop.
  $stateFile = Join-Path ([System.IO.Path]::GetTempPath()) ('batch-state-' + [guid]::NewGuid().ToString('N') + '.json')
  & $Python -X utf8 -B $verifyScript --batch $batchId --plan $planPath --freeze $freeze --sealed $sealed --qc $qc *> $stateFile
  $code = $LASTEXITCODE
  $line = ''
  try { $line = (Get-Content -LiteralPath $stateFile -ErrorAction Stop | Select-Object -Last 1) } catch { }
  Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
  $state = 'unknown'
  $problems = @('verifier produced no parsable state')
  try {
    $parsed = $line | ConvertFrom-Json
    $state = $parsed.state
    if ($null -ne $parsed.problems) { $problems = @($parsed.problems) }
  } catch {
    $problems = @('verifier output: ' + $line)
  }
  return [pscustomobject]@{ Code = $code; State = $state; Problems = $problems }
}

$pending = @()
$complete = 0
$broken = 0
foreach ($batch in $batches) {
  $state = Get-BatchState $batch.batch_id
  if ($state.Code -eq 3 -or $state.State -eq 'incomplete') {
    $broken++
    Write-Log ('INCOMPLETE ' + $batch.batch_id + ': ' + (($state.Problems | Select-Object -First 3) -join '; '))
    continue
  }
  if ($state.State -eq 'complete') { $complete++; continue }
  $pending += $batch
}

Write-Log ('plan: total=' + $batches.Count + ' complete=' + $complete + ' pending=' + $pending.Count + ' incomplete=' + $broken)

if ($broken -gt 0) {
  Write-Log 'stop: a sealed batch directory exists without complete QC evidence'
  exit 3
}

if ($VerifyOnly) {
  if ($pending.Count -gt 0) {
    Write-Log ('verify-only: ' + $pending.Count + ' batch(es) still pending')
    exit 5
  }
  Write-Log ('verify-only: all ' + $batches.Count + ' batches carry complete QC evidence')
  exit 0
}

if ($PlanOnly) {
  foreach ($batch in $pending) {
    [pscustomobject]@{ batch_id = $batch.batch_id; spectra = $batch.spectra; phase = $batch.phase; executable = $Python } |
      ConvertTo-Json -Compress -Depth 4
  }
  exit 0
}

$run = 0
$failed = 0
foreach ($batch in $pending) {
  $sealed = Join-Path $OutputRoot ('sealed/' + $batch.batch_id)
  $qc = Join-Path $OutputRoot ('qc/' + $batch.batch_id)
  $arguments = @('-X','utf8','-B',$runner,'--repository',$repoRoot,'--freeze',$freeze,'--release',$release,
                 '--batch',$batch.batch_id,'--out',$sealed,'--qc-out',$qc)
  if ($batch.phase -eq 'challenge') { $arguments += '--heldout-qc' }
  & $Python @arguments
  $code = $LASTEXITCODE
  if ($code -ne 0) {
    $failed++
    Write-Log ('FAILED ' + $batch.batch_id + ' code=' + $code + '; keeping its sealed output and logs')
    break
  }
  $state = Get-BatchState $batch.batch_id
  if ($state.State -ne 'complete') {
    $failed++
    Write-Log ('FAILED ' + $batch.batch_id + ' produced incomplete QC: ' + (($state.Problems | Select-Object -First 3) -join '; '))
    break
  }
  $run++
  Write-Log ('ok ' + $batch.batch_id + ' spectra=' + $batch.spectra)
}

if ($failed -gt 0) {
  # A failed batch must reach the caller: a plain success return after `break` reads as a
  # completed run to any CI or coordinator step that only checks the exit code.
  throw ('Member ' + $Member + ': ' + $failed + ' batch failure(s); sealed output and logs were kept')
}

Write-Log ('Member ' + $Member + ': complete ' + $count + ' spectra across ' + $batches.Count + ' batches (' + $run + ' newly run). Submit native ZIPs, hashes, full QC evidence and the record index via PR for owner review.')
exit 0
