[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$InstallRoot)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$pidFile = Join-Path $InstallRoot 'collector-process.json'
$running = $false
if (Test-Path $pidFile) {
    $info = Get-Content $pidFile -Raw | ConvertFrom-Json
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($info.pid)" -ErrorAction SilentlyContinue
    if ($process) {
        $commandLine = [string]$process.CommandLine
        $running = $commandLine.Contains('run-collector.ps1') -and $commandLine.Contains($InstallRoot)
    }
}
$statusPath = Join-Path $InstallRoot 'data\collector-status.json'
if (-not (Test-Path $statusPath)) { throw 'No collector status is available.' }
$status = Get-Content $statusPath -Raw | ConvertFrom-Json
$properties = $status.PSObject.Properties.Name
$hasCoverage = $properties -contains 'coverage'
$hasImport = $properties -contains 'import'
$hasPhase = $properties -contains 'phase'
$hasError = $properties -contains 'error'
$lastRunUtc = [datetimeoffset]::Parse([string]$status.last_run_utc).UtcDateTime
[pscustomobject]@{
    process_running = $running
    last_run_utc = $status.last_run_utc
    last_run_age_seconds = [math]::Round(((Get-Date).ToUniversalTime() - $lastRunUtc).TotalSeconds, 3)
    phase = $(if ($hasPhase) { $status.phase } else { $(if ($status.success) { 'complete' } else { 'error' }) })
    success = [bool]$status.success
    error = $(if ($hasError) { [string]$status.error } else { $null })
    coverage = $(if ($hasCoverage) { $status.coverage } else { $null })
    covered_sessions = $(if ($hasCoverage) { "$($status.coverage.covered_sessions)/$($status.coverage.source_sessions)" } else { $null })
    covered_messages = $(if ($hasCoverage) { "$($status.coverage.covered_messages)/$($status.coverage.source_messages)" } else { $null })
    covered_skill_selections = $(if ($hasCoverage) { "$($status.coverage.covered_skill_selections)/$($status.coverage.source_skill_selections)" } else { $null })
    covered_tool_failures = $(if ($hasCoverage) { "$($status.coverage.covered_tool_failures)/$($status.coverage.source_tool_failures)" } else { $null })
    covered_tool_cancellations = $(if ($hasCoverage) { "$($status.coverage.covered_tool_cancellations)/$($status.coverage.source_tool_cancellations)" } else { $null })
    covered_tool_error_or_cancel_events = $(if ($hasCoverage) { "$($status.coverage.covered_tool_error_or_cancel_events)/$($status.coverage.source_tool_error_or_cancel_events)" } else { $null })
    coverage_complete = $(if ($hasCoverage) { [bool]$status.coverage.coverage_complete } else { $false })
    excluded_subagents = $(if ($hasCoverage) { $status.coverage.excluded_subagents } else { $null })
    parse_failures = $(if ($hasImport) { $status.import.parse_failures } else { $null })
} | ConvertTo-Json -Depth 5
