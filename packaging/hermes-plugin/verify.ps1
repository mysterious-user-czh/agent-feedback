[CmdletBinding()]
param(
    [string]$InstallRoot = 'D:\KimiData\agent-feedback',
    [ValidateRange(5, 86400)][int]$MaxStatusAgeSeconds = 180
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$manifestPath = Join-Path $InstallRoot 'install.json'
if (-not (Test-Path $manifestPath)) { throw "Installation manifest not found: $manifestPath" }
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$python = Join-Path $InstallRoot 'venv\Scripts\python.exe'
& $python -c "import agent_feedback; print('Package:', agent_feedback.__version__)"
if ($LASTEXITCODE -ne 0) { throw 'Package verification failed.' }
if (-not (Test-Path $manifest.contracts)) { throw 'Contracts file is missing.' }
if (-not (Test-Path (Join-Path $manifest.skill 'SKILL.md'))) { throw 'Skill is missing.' }
$env:HERMES_HOME = $manifest.hermes_home
& $manifest.hermes_bin mcp test agent-feedback
if ($LASTEXITCODE -ne 0) { throw 'MCP verification failed.' }
if ($manifest.auto_collector) {
    $collector = & (Join-Path $InstallRoot 'status-auto-collector.ps1') -InstallRoot $InstallRoot | ConvertFrom-Json
    if (-not $collector.process_running) { throw 'Automatic collector process is not running.' }
    if ($collector.last_run_age_seconds -lt 0 -or $collector.last_run_age_seconds -gt $MaxStatusAgeSeconds) {
        throw "Automatic collector status is stale or has an invalid timestamp: $($collector.last_run_age_seconds)s."
    }
    $collectionInProgress = $collector.phase -eq 'collecting' -and -not $collector.success
    if (-not $collectionInProgress -and (-not $collector.success -or -not $collector.coverage_complete)) {
        throw 'Automatic collector has not passed complete source-to-store coverage.'
    }
    if ($collectionInProgress) {
        Write-Host "Collector heartbeat is fresh; a coverage cycle is currently running."
    } else {
        Write-Host ("Collector: {0} sessions, {1} messages, {2} selections, {3} failures + {4} cancellations; coverage complete." -f
            $collector.covered_sessions, $collector.covered_messages, $collector.covered_skill_selections,
            $collector.covered_tool_failures, $collector.covered_tool_cancellations)
    }
}
Write-Host 'Verification passed: package, contracts, Skill, MCP and configured collector.' -ForegroundColor Green
