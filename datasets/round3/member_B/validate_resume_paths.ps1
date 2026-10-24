# Reproduce the resume paths and the verifier's negative cases.
#
# The drivers are COPIED into a temporary harness directory before running: run_B_parallel.py
# writes its log, per-batch terminal logs and chunk JSON next to itself, so running the copy
# keeps the production delivery untouched. Negative cases mutate a COPY of one real batch's QC
# inside the harness, never the delivered files. Evidence lands in reports/resume_validation/.
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
function Read-Json([string]$path) { Get-Content -Raw -LiteralPath $path | ConvertFrom-Json }

$workRepo = Join-Path (Split-Path $d -Parent) 'B-part-20261024_work\repo'
$workOut = Join-Path $workRepo 'work\round3\member_B_production_v1'
$workFreeze = Join-Path $workRepo 'datasets/round3/shared/freeze_v1'

$harness = Join-Path $env:TEMP ('b-resume-harness-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force -Path $harness | Out-Null
foreach ($name in @('run_B_parallel.py', 'run_B_production.ps1', 'verify_batch_qc.py')) {
  Copy-Item (Join-Path $d $name) (Join-Path $harness $name) -Force
}
$parallel = Join-Path $harness 'run_B_parallel.py'
$ps1 = Join-Path $harness 'run_B_production.ps1'
$verify = Join-Path $harness 'verify_batch_qc.py'

# The delivery must not change while the controls run; capture its fingerprint first.
$logPath = Join-Path $d 'production_parallel.log'
$logBefore = (Get-Item $logPath).Length
$terminalBefore = @(Get-ChildItem (Join-Path $d 'logs') -Filter '*.terminal.log').Count
$chunksBefore = @(Get-ChildItem $d -Filter 'production_chunk_*.json').Count

$results = @()

function New-TestRoot([string]$name) {
  $root = Join-Path $harness ('root-' + $name)
  $shared = Join-Path $root 'datasets/round3/shared'
  New-Item -ItemType Directory -Force -Path (Join-Path $shared 'releases') | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $shared 'production_tools') | Out-Null
  Copy-Item $workFreeze (Join-Path $shared 'freeze_v1') -Recurse -Force
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
$firstBatch = (Read-Json (Join-Path $rootC 'datasets/round3/shared/freeze_v1/batch_plan.json')).batches |
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

# --- Negative cases: real passed QC copied aside, then one identity/evidence field mutated ---
$negRoot = New-TestRoot 'negative'
$negFreeze = Join-Path $negRoot 'datasets/round3/shared/freeze_v1'
$planPath = Join-Path $negFreeze 'batch_plan.json'
$plan = Read-Json $planPath
$targetBatch = $plan.batches | Where-Object { $_.batch_id -eq 'R3_B_base_D1_001' } | Select-Object -First 1
$negSealed = Join-Path $negRoot 'work/sealed/R3_B_base_D1_001'
$negQc = Join-Path $negRoot 'work/qc/R3_B_base_D1_001'
New-Item -ItemType Directory -Force -Path (Join-Path $negRoot 'work/sealed') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $negRoot 'work/qc') | Out-Null
Copy-Item (Join-Path $workOut 'sealed/R3_B_base_D1_001') $negSealed -Recurse -Force
Copy-Item (Join-Path $workOut 'qc/R3_B_base_D1_001') $negQc -Recurse -Force

$pristine = Join-Path $negRoot 'pristine'
New-Item -ItemType Directory -Force -Path $pristine | Out-Null
foreach ($name in @('summary.json', 'window_budget.json', 'commands.json', 'external_record_index.csv')) {
  Copy-Item (Join-Path $negQc $name) (Join-Path $pristine $name) -Force
}

function Restore-NegativeFiles {
  foreach ($name in @('summary.json', 'window_budget.json', 'commands.json', 'external_record_index.csv')) {
    Copy-Item (Join-Path $pristine $name) (Join-Path $negQc $name) -Force
  }
}

function Invoke-Verifier {
  $raw = & python -X utf8 -B $verify --batch 'R3_B_base_D1_001' --plan $planPath --freeze $negFreeze --sealed $negSealed --qc $negQc 2>&1
  $code = $LASTEXITCODE
  $last = ($raw | Select-Object -Last 1)
  return [pscustomobject]@{ exit = $code; line = $last }
}

# Positive control on the untouched copy.
$positive = Invoke-Verifier
Write-Utf8 (Join-Path $out 'negative_00_control_complete.log') ($positive.line + "`ncontrol_exit=" + $positive.exit + "`n")
$results += [pscustomobject]@{ case = 'N0_control_complete'; exit = $positive.exit; expected = 0 }

$cases = @(
  @{ id = 'N1_summary_batch_id'; mutate = { param($qc, $p)
      $j = Read-Json (Join-Path $qc 'summary.json'); $j.batch_id = 'R3_B_base_P1_001'
      Write-Utf8 (Join-Path $qc 'summary.json') ($j | ConvertTo-Json -Depth 10) } },
  @{ id = 'N2_summary_freeze_sha'; mutate = { param($qc, $p)
      $j = Read-Json (Join-Path $qc 'summary.json'); $j.freeze_manifest_sha256 = ('0' * 64)
      Write-Utf8 (Join-Path $qc 'summary.json') ($j | ConvertTo-Json -Depth 10) } },
  @{ id = 'N3_index_batch_id'; mutate = { param($qc, $p)
      $rows = Import-Csv (Join-Path $qc 'external_record_index.csv')
      foreach ($r in $rows) { $r.batch_id = 'R3_B_base_P1_001' }
      $rows | Export-Csv (Join-Path $qc 'external_record_index.csv') -NoTypeInformation -Encoding UTF8 } },
  @{ id = 'N4_window_row_fails'; mutate = { param($qc, $p)
      $j = Read-Json (Join-Path $qc 'window_budget.json')
      $j.rows[0].passed = $false; $j.rows[0].lost_fraction = 0.99; $j.rows[0].budget = 0.5
      Write-Utf8 (Join-Path $qc 'window_budget.json') ($j | ConvertTo-Json -Depth 10) } },
  @{ id = 'N5_missing_replay_action'; mutate = { param($qc, $p)
      $j = Read-Json (Join-Path $qc 'commands.json')
      $kept = @($j | Where-Object { $_.action -ne 'replay' })
      Write-Utf8 (Join-Path $qc 'commands.json') ((ConvertTo-Json -InputObject $kept -Depth 10)) } },
  @{ id = 'N6_index_recipe_mismatch'; mutate = { param($qc, $p)
      $rows = Import-Csv (Join-Path $qc 'external_record_index.csv')
      $rows[0].recipe_id = 'R3_B_not_a_frozen_recipe_V99'
      $rows | Export-Csv (Join-Path $qc 'external_record_index.csv') -NoTypeInformation -Encoding UTF8 } },
  @{ id = 'N7_command_uses_limit'; mutate = { param($qc, $p)
      $j = Read-Json (Join-Path $qc 'commands.json')
      foreach ($entry in $j) { if ($entry.action -eq 'audit') { $entry.command = @($entry.command) + @('--limit','1') } }
      Write-Utf8 (Join-Path $qc 'commands.json') ($j | ConvertTo-Json -Depth 10) } }
)

foreach ($case in $cases) {
  Restore-NegativeFiles
  & $case.mutate $negQc $null
  $result = Invoke-Verifier
  Write-Utf8 (Join-Path $out ('negative_' + $case.id + '.log')) ($result.line + "`nexit=" + $result.exit + "`n")
  $results += [pscustomobject]@{ case = $case.id; exit = $result.exit; expected = 3 }
}
Restore-NegativeFiles

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
  isolation = 'drivers copied to a temporary harness directory; negative cases mutate a copied batch, never the delivery'
  real_tree = $workOut
  synthetic_root_failure = $rootB
  synthetic_root_incomplete = $rootC
  synthetic_negative_root = $negRoot
  note = 'Cases B/C/N* use a stub runner, a fabricated sealed directory or a mutated copy of real QC; they exercise control flow and the verifier, and are not produced spectra.'
  cases = $results
}
Write-Utf8 (Join-Path $out 'resume_validation_summary.json') (($summary | ConvertTo-Json -Depth 6))

$results | Format-Table -AutoSize | Out-String | Write-Host
"all_expected=$pass delivery_untouched=$clean"
exit ([int](-not $pass))
