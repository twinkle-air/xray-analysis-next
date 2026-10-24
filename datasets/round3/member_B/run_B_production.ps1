# Run all remaining frozen round-3 member-B batches, skipping batches already sealed.
# Paths derive from $PSScriptRoot so this file stays pure ASCII.
$ErrorActionPreference = 'Stop'

$delivery = $PSScriptRoot
$root     = Join-Path $delivery 'repo'
$freeze   = Join-Path $root 'datasets/round3/shared/freeze_v1'
$release  = Join-Path $root 'datasets/round3/shared/releases/owner_release_v3.json'
$runner   = Join-Path $root 'datasets/round3/shared/production_tools/run_batch.py'
$out      = Join-Path $root 'work/round3/member_B_production_v1'
$log      = Join-Path $delivery 'production_run.log'

New-Item -ItemType Directory -Path $out -Force | Out-Null

function Log($msg) {
  $line = ('[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'), $msg)
  Add-Content -LiteralPath $log -Value $line -Encoding utf8
  Write-Output $line
}

$plan = Get-Content -Raw -LiteralPath (Join-Path $freeze 'batch_plan.json') -Encoding utf8 | ConvertFrom-Json
$batches = @($plan.batches | Where-Object { $_.member -eq 'B' })

$total = ($batches | Measure-Object -Property spectra -Sum).Sum
Log ("start: batches={0} spectra={1}" -f $batches.Count, $total)

$swAll = [System.Diagnostics.Stopwatch]::StartNew()
$done = 0; $skipped = 0; $failed = 0

foreach ($batch in $batches) {
  $sealed = Join-Path $out ('sealed/' + $batch.batch_id)
  $qc     = Join-Path $out ('qc/' + $batch.batch_id)

  if (Test-Path $sealed) {
    $skipped++
    Log ("skip (exists): {0}" -f $batch.batch_id)
    continue
  }

  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $args = @('-X','utf8','-B',$runner,
            '--repository',$root,
            '--freeze',$freeze,
            '--release',$release,
            '--batch',$batch.batch_id,
            '--out',$sealed,
            '--qc-out',$qc)
  if ($batch.phase -eq 'challenge') { $args += '--heldout-qc' }

  $result = & python @args 2>&1
  $code = $LASTEXITCODE
  $sw.Stop()

  $last = ($result | Select-Object -Last 1)
  if ($code -ne 0) {
    $failed++
    Log ("FAILED {0} code={1} sec={2} :: {3}" -f $batch.batch_id, $code, [math]::Round($sw.Elapsed.TotalSeconds,1), $last)
    break
  }
  $done++
  Log ("ok {0} spectra={1} sec={2}" -f $batch.batch_id, $batch.spectra, [math]::Round($sw.Elapsed.TotalSeconds,1))
}

$swAll.Stop()
Log ("end: new={0} skipped={1} failed={2} elapsed_min={3}" -f $done, $skipped, $failed, [math]::Round($swAll.Elapsed.TotalMinutes,1))
