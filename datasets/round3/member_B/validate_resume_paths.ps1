# Reproduce the three resume paths the review asked for.
#
# The drivers are COPIED into a temporary harness directory before running: run_B_parallel.py
# writes its log, per-batch terminal logs and chunk JSON next to itself, so running the copy
# keeps the production delivery untouched. Evidence lands in reports/resume_validation/.
$ErrorActionPreference = 'Continue'
$d = $PSScriptRoot
$out = Join-Path $d 'reports\resume_validation'
$synthetic = Join-Path $out 'synthetic'
New-Item -ItemType Directory -Force -Path $out | Out-Null
New-Item -ItemType Directory -Force -Path $synthetic | Out-Null

$utf8 = New-Object System.Text.UTF8Encoding($false)
function Write-Utf8([string]$path, [string]$text) {
  [System.IO.File]::WriteAllText($path, $text, $utf8)
}

$workRepo = Join-Path (Split-Path $d -Parent) 'B-part-20261024_work\repo'
$workOut = Join-Path $workRepo 'work\round3\member_B_production_v1'

$harness = Join-Path $env:TEMP ('b-resume-harness-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force -Path $harness | Out-Null
foreach ($name in @('run_B_parallel.py', 'run_B_production.ps1', 'verify_batch_qc.py')) {
  Copy-Item (Join-Path $d $name) (Join-Path $harness $name) -Force
}
$parallel = Join-Path $harness 'run_B_parallel.py'
$ps1 = Join-Path $harness 'run_B_production.ps1'

# The delivery must not change while the controls run; capture its fingerprint first.
$logPath = Join-Path $d 'production_parallel.log'
$logBefore = (Get-Item $logPath).Length
$terminalBefore = @(Get-ChildItem (Join-Path $d 'logs') -Filter '*.terminal.log').Count
$chunksBefore = @(Get-ChildItem $d -Filter 'production_chunk_*.json').Count

$results = @()

function New-TestRoot([string]$name) {
  $root = Join-Path $harness ('root-' + $name)
  New-Item -ItemType Directory -Force -Path (Join-Path $root 'datasets/round3/shared/freeze_v1') | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $root 'datasets/round3/shared/releases') | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $root 'datasets/round3/shared/production_tools') | Out-Null
  Copy-Item (Join-Path $workRepo 'datasets/round3/shared/freeze_v1/batch_plan.json') `
            (Join-Path $root 'datasets/round3/shared/freeze_v1/batch_plan.json') -Force
  return $root
}

# Case A: a completed tree (every sealed batch has passed QC) -> verify-only succeeds.
$env:B_REPO_ROOT = $workRepo
$env:B_OUTPUT_ROOT = $workOut
$logA = & python -X utf8 -B $parallel --verify-only 2>&1
$codeA = $LASTEXITCODE
Write-Utf8 (Join-Path $out 'caseA_parallel_verify.log') ((($logA | Out-String).TrimEnd()) + "`ncaseA_parallel_exit=$codeA`n")
$results += [pscustomobject]@{ case = 'A_complete_parallel_verify'; exit = $codeA; expected = 0 }

$psA = & powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -Member B -Repository $workRepo -OutputRoot $workOut -VerifyOnly 2>&1
$codeA2 = $LASTEXITCODE
Write-Utf8 (Join-Path $out 'caseA_ps1_verify.log') ((($psA | Out-String).TrimEnd()) + "`ncaseA_ps1_exit=$codeA2`n")
$results += [pscustomobject]@{ case = 'A_complete_ps1_verify'; exit = $codeA2; expected = 0 }

# Case B: a pending batch whose runner fails -> both drivers must exit non-zero.
$rootB = New-TestRoot 'fail'
$stub = @'
import sys
print('stub runner: simulated batch failure', flush=True)
sys.exit(23)
'@
Write-Utf8 (Join-Path $rootB 'datasets/round3/shared/production_tools/run_batch.py') $stub
Copy-Item (Join-Path $rootB 'datasets/round3/shared/production_tools/run_batch.py') (Join-Path $synthetic 'stub_run_batch_failure.py') -Force
$env:B_REPO_ROOT = $rootB
$env:B_OUTPUT_ROOT = (Join-Path $rootB 'work')
$logB = & python -X utf8 -B $parallel --workers 1 --limit 1 2>&1
$codeB = $LASTEXITCODE
Write-Utf8 (Join-Path $out 'caseB_parallel_failure.log') ((($logB | Out-String).TrimEnd()) + "`ncaseB_parallel_exit=$codeB`n")
$results += [pscustomobject]@{ case = 'B_failure_parallel'; exit = $codeB; expected = 1 }

$psB = & powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -Member B -Repository $rootB -OutputRoot (Join-Path $rootB 'work') 2>&1
$codeB2 = $LASTEXITCODE
Write-Utf8 (Join-Path $out 'caseB_ps1_failure.log') ((($psB | Out-String).TrimEnd()) + "`ncaseB_ps1_exit=$codeB2`n")
$results += [pscustomobject]@{ case = 'B_failure_ps1'; exit = $codeB2; expected = 1 }

# Case C: a sealed directory exists but its QC is missing -> stop, never report completion.
$rootC = New-TestRoot 'incomplete'
$firstBatch = (Get-Content -Raw (Join-Path $rootC 'datasets/round3/shared/freeze_v1/batch_plan.json') | ConvertFrom-Json).batches |
  Where-Object { $_.member -eq 'B' } | Select-Object -First 1
$sealedC = Join-Path $rootC ('work/sealed/' + $firstBatch.batch_id)
New-Item -ItemType Directory -Force -Path $sealedC | Out-Null
Write-Utf8 (Join-Path $sealedC 'manifest.json') '{"spectrum_count": 0}'
Copy-Item $sealedC (Join-Path $synthetic ('sealed_' + $firstBatch.batch_id)) -Recurse -Force -ErrorAction SilentlyContinue
$env:B_REPO_ROOT = $rootC
$env:B_OUTPUT_ROOT = (Join-Path $rootC 'work')
$logC = & python -X utf8 -B $parallel --verify-only 2>&1
$codeC = $LASTEXITCODE
Write-Utf8 (Join-Path $out 'caseC_parallel_incomplete.log') ((($logC | Out-String).TrimEnd()) + "`ncaseC_parallel_exit=$codeC`n")
$results += [pscustomobject]@{ case = 'C_incomplete_sealed_parallel'; exit = $codeC; expected = 3 }

$psC = & powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -Member B -Repository $rootC -OutputRoot (Join-Path $rootC 'work') -VerifyOnly 2>&1
$codeC2 = $LASTEXITCODE
Write-Utf8 (Join-Path $out 'caseC_ps1_incomplete.log') ((($psC | Out-String).TrimEnd()) + "`ncaseC_ps1_exit=$codeC2`n")
$results += [pscustomobject]@{ case = 'C_incomplete_sealed_ps1'; exit = $codeC2; expected = 3 }

# The controls must not touch the delivered production evidence.
$logAfter = (Get-Item $logPath).Length
$terminalAfter = @(Get-ChildItem (Join-Path $d 'logs') -Filter '*.terminal.log').Count
$chunksAfter = @(Get-ChildItem $d -Filter 'production_chunk_*.json').Count
$clean = ($logBefore -eq $logAfter) -and ($terminalBefore -eq $terminalAfter) -and ($chunksBefore -eq $chunksAfter)

$pass = (@($results | Where-Object { $_.exit -ne $_.expected }).Count -eq 0) -and $clean
$summary = [ordered]@{
  generated_at = (Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')
  all_expected = $pass
  delivery_untouched = $clean
  isolation = 'drivers copied to a temporary harness directory; synthetic roots live under that harness'
  real_tree = $workOut
  synthetic_root_failure = $rootB
  synthetic_root_incomplete = $rootC
  note = 'Cases B and C use a stub runner and a fabricated sealed directory to exercise driver control flow; they are not produced spectra.'
  cases = $results
}
Write-Utf8 (Join-Path $out 'resume_validation_summary.json') (($summary | ConvertTo-Json -Depth 6))

$results | Format-Table -AutoSize | Out-String | Write-Host
"all_expected=$pass delivery_untouched=$clean"
exit ([int](-not $pass))
