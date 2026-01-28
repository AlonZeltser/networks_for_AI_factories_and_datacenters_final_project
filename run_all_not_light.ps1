# Runs all NON "*_light.yaml" scenario YAMLs (testing + heavy/mixed) using an editable list.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\run_all_not_light.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\run_all_not_light.ps1 -ListOnly
#
# Notes:
# - Each scenario runs in its own Python process.
# - Per-run logs are written to .\batch_logs\
# - A summary file is written at the end.

[CmdletBinding()]
param(
    [switch]$ListOnly,
    [switch]$StopOnError
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$python = 'python'
$entry  = 'ai_factory_network_simulation.py'
$logDir = Join-Path $repoRoot 'batch_logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Write-Host "Repo root: $repoRoot"
Write-Host "Python:    $python"
Write-Host "Entrypoint: $entry"

if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    throw "Python executable not found on PATH. Try: py -3 ... or install Python and ensure 'python' is on PATH."
}
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $entry))) {
    throw "Entrypoint not found: $entry (expected at repo root)."
}

# === Edit this list (comment/uncomment freely) ===
$Scenarios = @(
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_adaptive_high.yaml',
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_adaptive_high_failures.yaml',
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_adaptive_low.yaml',
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_adaptive_mid.yaml',
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_ecmp_high.yaml',
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_ecmp_high_failures.yaml',
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_ecmp_low.yaml',
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_ecmp_mid.yaml',
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_flowlet_high.yaml',
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_flowlet_high_failures.yaml',
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_flowlet_low.yaml',
    #'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_dp_heavy_scenario_flowlet_mid.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_adaptive_high.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_adaptive_high_failures.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_adaptive_low.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_adaptive_mid.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_ecmp_high.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_ecmp_high_failures.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_ecmp_low.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_ecmp_mid.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_flowlet_high.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_flowlet_high_failures.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_flowlet_low.yaml',
    'ai_factory_simulation\scenarios\scenarios_configuration\ai_factory_su_mixed_scenario_flowlet_mid.yaml'

)
# ================================================

# Normalize + validate scenario paths
$Scenarios = $Scenarios | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }

$missing = @()
foreach ($s in $Scenarios) {
    $p = Join-Path $repoRoot $s
    if (-not (Test-Path -LiteralPath $p)) {
        $missing += $s
    }
}
if ($missing.Count -gt 0) {
    Write-Host "Missing scenario YAML files:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    throw "One or more scenario YAMLs are missing. Fix the list in run_all_not_light.ps1."
}

Write-Host ''
Write-Host 'Scenarios:'
$Scenarios | ForEach-Object { Write-Host "  $_" }
Write-Host ''

if ($ListOnly) {
    Write-Host 'ListOnly mode: exiting without running scenarios.'
    return
}

$summary = New-Object System.Collections.Generic.List[object]

foreach ($s in $Scenarios) {
    $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
    $safe = ($s -replace '[\\/:*?"<>| ]','_')
    $logPath = Join-Path $logDir ("run_${safe}_${ts}.log")

    Write-Host ''
    Write-Host "=== RUN: $s ==="
    Write-Host "Log: $logPath"

    $stderrPath = $logPath + '.stderr'
    if (Test-Path -LiteralPath $stderrPath) {
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath $python -ArgumentList @($entry, $s) -NoNewWindow -PassThru -Wait -RedirectStandardOutput $logPath -RedirectStandardError $stderrPath
    $sw.Stop()

    # Merge stderr into the main log (and clean up).
    if (Test-Path -LiteralPath $stderrPath) {
        Add-Content -LiteralPath $logPath -Value "`r`n--- STDERR ---`r`n" -Encoding UTF8
        Get-Content -LiteralPath $stderrPath -ErrorAction SilentlyContinue | Add-Content -LiteralPath $logPath -Encoding UTF8
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }

    $ok = ($p.ExitCode -eq 0)
    $summary.Add([pscustomobject]@{
        scenario  = $s
        exitCode  = $p.ExitCode
        ok        = $ok
        seconds   = [math]::Round($sw.Elapsed.TotalSeconds, 3)
        log       = $logPath
    }) | Out-Null

    if (-not $ok) {
        Write-Host "FAILED exitCode=$($p.ExitCode)" -ForegroundColor Red
        if ($StopOnError) {
            throw "Stopping on error for scenario: $s"
        }
    } else {
        Write-Host "OK ($([math]::Round($sw.Elapsed.TotalSeconds,1))s)" -ForegroundColor Green
    }
}

$summaryPath = Join-Path $logDir ("summary_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt")
$summary | Format-Table -AutoSize | Out-String | Set-Content -Path $summaryPath -Encoding UTF8

Write-Host ''
Write-Host "Wrote summary: $summaryPath"


exit 0
