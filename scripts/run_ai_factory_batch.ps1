Param(
  [Parameter(Mandatory = $false)]
  [string]$RepoRoot = "C:\Users\alonz\repos\studies\networks\network_sim",

  # One or more YAML configs to run (relative to RepoRoot or absolute).
  [Parameter(Mandatory = $false)]
  [string[]]$Configs = @(
    "ai_factory_simulation\scenarios\ai_factory_su_dp_light_scenario_ecmp.yaml",
    "ai_factory_simulation\scenarios\ai_factory_su_dp_light_scenario_adaptive.yaml",
    "ai_factory_simulation\scenarios\ai_factory_su_dp_heavy_scenario_ecmp.yaml",
    "ai_factory_simulation\scenarios\ai_factory_su_dp_heavy_scenario_adaptive.yaml"
  ),

  # If set, continue running the remaining configs even if one fails.
  [Parameter(Mandatory = $false)]
  [switch]$ContinueOnError,

  # Safety: heavy configs can take a very long time. By default we refuse to run
  # configs whose filename includes 'heavy'. Use this flag to explicitly allow them.
  [Parameter(Mandatory = $false)]
  [switch]$AllowHeavy
)

$ErrorActionPreference = "Stop"

Set-Location $RepoRoot

Write-Host "RepoRoot: $RepoRoot"
Write-Host "Configs:"
$Configs | ForEach-Object { Write-Host "  - $_" }
Write-Host "ContinueOnError: $ContinueOnError"
Write-Host "AllowHeavy: $AllowHeavy"
Write-Host ""

$failures = @()

foreach ($cfg in $Configs) {
  # Resolve relative paths from RepoRoot
  $cfgPath = $cfg
  if (-not [System.IO.Path]::IsPathRooted($cfgPath)) {
    $cfgPath = Join-Path -Path $RepoRoot -ChildPath $cfgPath
  }

  if (-not (Test-Path -LiteralPath $cfgPath)) {
    throw "Config not found: $cfg (resolved to $cfgPath)"
  }

  $cfgName = [System.IO.Path]::GetFileName($cfgPath)
  if ((-not $AllowHeavy) -and ($cfgName -match '(?i)heavy')) {
    throw "Refusing to run heavy config '$cfgName'. Pass -AllowHeavy to override."
  }

  $start = Get-Date
  Write-Host "========================================"
  Write-Host "Running: $cfgPath"

  # Use python from PATH. (If you use a venv, activate it before running this script.)
  python .\ai_factory_network_simulation.py $cfgPath
  $exitCode = $LASTEXITCODE

  $elapsed = (Get-Date) - $start
  Write-Host "Finished: $cfgName (exit=$exitCode, elapsed=$elapsed)"

  if ($exitCode -ne 0) {
    $failures += $cfgName
    if (-not $ContinueOnError) {
      Write-Host "Aborting batch due to failure."
      exit $exitCode
    }
  }
}

Write-Host "========================================"
if ($failures.Count -gt 0) {
  Write-Host "Batch completed with failures:"
  $failures | ForEach-Object { Write-Host "  - $_" }
  exit 1
}

Write-Host "Batch completed successfully."
exit 0

