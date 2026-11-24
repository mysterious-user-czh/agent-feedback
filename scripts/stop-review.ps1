[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$processFile = Join-Path $root 'review-server-process.json'
if (-not (Test-Path $processFile)) {
    Write-Output 'Agent Skills Feedback review server is not managed by this launcher.'
    exit 0
}
$saved = Get-Content $processFile -Raw | ConvertFrom-Json
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($saved.pid)" -ErrorAction SilentlyContinue
if ($process) {
    $commandLine = [string]$process.CommandLine
    if ($commandLine -notmatch 'agent_feedback\.review_server' -or $commandLine -notlike "*$root*") {
        throw 'Saved review PID belongs to another process; refusing to stop it.'
    }
    Stop-Process -Id $saved.pid -Force
}
Remove-Item $processFile -Force
Write-Output 'Agent Skills Feedback review server stopped.'
