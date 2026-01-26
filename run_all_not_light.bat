@echo off
setlocal enableextensions enabledelayedexpansion

REM Always run from this script's directory (repo root)
cd /d "%~dp0"

set "PYTHON=python"
set "ENTRY=ai_factory_network_simulation.py"
set "STOP_ON_ERROR=0"

REM Set LIST_ONLY=1 to only print the list and exit.
if "%LIST_ONLY%"=="1" (
  set "STOP_ON_ERROR=0"
)

if not exist "batch_logs" mkdir "batch_logs" >nul 2>&1

REM === Edit this list (comment/uncomment freely) ===
REM Put one scenario per line in SCENARIO_LIST. Comment lines with REM.
set "SCENARIO_LIST="
call :add "ai_factory_simulation\scenarios\scenario_configuraions\no_link_failures\ai_factory_su_mixed_scenario_ecmp.yaml"
call :add "ai_factory_simulation\scenarios\scenario_configuraions\no_link_failures\ai_factory_su_mixed_scenario_adaptive.yaml"
call :add "ai_factory_simulation\scenarios\scenario_configuraions\no_link_failures\ai_factory_su_dp_heavy_scenario_ecmp.yaml"
call :add "ai_factory_simulation\scenarios\scenario_configuraions\no_link_failures\ai_factory_su_dp_heavy_scenario_adaptive.yaml"

call :add "ai_factory_simulation\scenarios\scenario_configuraions\link_failures\ai_factory_su_mixed_scenario_ecmp.yaml"
call :add "ai_factory_simulation\scenarios\scenario_configuraions\link_failures\ai_factory_su_mixed_scenario_adaptive.yaml"
call :add "ai_factory_simulation\scenarios\scenario_configuraions\link_failures\ai_factory_su_dp_heavy_scenario_ecmp.yaml"
call :add "ai_factory_simulation\scenarios\scenario_configuraions\link_failures\ai_factory_su_dp_heavy_scenario_adaptive.yaml"

call :add "ai_factory_simulation\scenarios\scenario_configuraions\testing\ai_factory_su_dp_light_scenario_ecmp.yaml"
call :add "ai_factory_simulation\scenarios\scenario_configuraions\testing\ai_factory_su_dp_light_scenario_adaptive.yaml"

REM Note: mixed testing yamls here are "*_light.yaml" and intentionally excluded.
REM ================================================

if "%SCENARIO_LIST%"=="" (
  echo No scenarios defined. Edit run_all_not_light.bat and add scenario YAMLs.
  exit /b 2
)

echo.
echo Running scenarios (edit list in this file to comment/uncomment):
echo.
echo %SCENARIO_LIST%
echo.

REM PowerShell runner: parses SCENARIO_LIST (newline-separated) and runs each scenario in isolation.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Set-StrictMode -Version Latest;" ^
  "$listOnly = [int]'%LIST_ONLY%';" ^
  "$py = '%PYTHON%';" ^
  "$entry = '%ENTRY%';" ^
  "$stopOnError = [int]'%STOP_ON_ERROR%';" ^
  "$raw = @'%SCENARIO_LIST%'@;" ^
  "$scenarios = $raw -split ""`r?`n"" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' };" ^
  "if($listOnly -eq 1){ $scenarios | ForEach-Object { Write-Host $_ }; exit 0 }" ^
  "$logDir = Join-Path (Get-Location) 'batch_logs';" ^
  "$summary = New-Object System.Collections.Generic.List[object];" ^
  "foreach($s in $scenarios){" ^
  "  $ts = Get-Date -Format 'yyyyMMdd_HHmmss';" ^
  "  $safe = ($s -replace '[\\/:*?\"<>| ]','_');" ^
  "  $logPath = Join-Path $logDir ('run_' + $safe + '_' + $ts + '.log');" ^
  "  Write-Host '';" ^
  "  Write-Host ('=== RUN: ' + $s + ' ===');" ^
  "  Write-Host ('Log: ' + $logPath);" ^
  "  $sw = [System.Diagnostics.Stopwatch]::StartNew();" ^
  "  $p = Start-Process -FilePath $py -ArgumentList @($entry, $s) -NoNewWindow -PassThru -Wait -RedirectStandardOutput $logPath -RedirectStandardError $logPath;" ^
  "  $sw.Stop();" ^
  "  $ok = ($p.ExitCode -eq 0);" ^
  "  $summary.Add([pscustomobject]@{ scenario=$s; exitCode=$p.ExitCode; ok=$ok; seconds=[math]::Round($sw.Elapsed.TotalSeconds,3); log=$logPath });" ^
  "  if(-not $ok){" ^
  "    Write-Host ('FAILED exitCode=' + $p.ExitCode) -ForegroundColor Red;" ^
  "    if($stopOnError -eq 1){ throw ('Stopping on error for scenario: ' + $s); }" ^
  "  } else {" ^
  "    Write-Host ('OK (' + [math]::Round($sw.Elapsed.TotalSeconds,1) + 's)') -ForegroundColor Green;" ^
  "  }" ^
  "}" ^
  "$summaryPath = Join-Path $logDir ('summary_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.txt');" ^
  "$summary | Format-Table -AutoSize | Out-String | Set-Content -Path $summaryPath -Encoding UTF8;" ^
  "Write-Host '';" ^
  "Write-Host ('Wrote summary: ' + $summaryPath);" ^
  "Write-Host '';" ^
  "if(($summary | Where-Object { -not $_.ok }).Count -gt 0){ exit 1 } else { exit 0 }"

if errorlevel 1 (
  echo.
  echo Some scenarios failed. See batch_logs\summary_*.txt and per-run logs.
  exit /b 1
)

echo.
echo All scenarios completed successfully.
exit /b 0

:add
REM Adds a scenario line to SCENARIO_LIST (newline separated)
if defined SCENARIO_LIST (
  set "SCENARIO_LIST=%SCENARIO_LIST%^
%~1"
) else (
  set "SCENARIO_LIST=%~1"
)
exit /b 0
