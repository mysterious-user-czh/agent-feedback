[CmdletBinding()]
param(
    [string]$Database = '',
    [ValidateRange(1, 65535)][int]$Port = 7100,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$processFile = Join-Path $root 'review-server-process.json'
$url = "http://localhost:$Port/"

function Open-Review {
    if (-not $NoBrowser) { Start-Process $url }
    Write-Output "Agent Skills Feedback: $url"
}

function Get-ManagedProcess {
    if (-not (Test-Path $processFile)) { return $null }
    try { $saved = Get-Content $processFile -Raw | ConvertFrom-Json } catch {
        Remove-Item $processFile -Force
        return $null
    }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($saved.pid)" -ErrorAction SilentlyContinue
    if ($process -and [string]$process.CommandLine -match 'agent_feedback\.review_server' -and
        [string]$process.CommandLine -like "*$root*") {
        return $process
    }
    if ($process) { throw 'Saved review PID belongs to another process; refusing to reuse it.' }
    Remove-Item $processFile -Force
    return $null
}

$existing = Get-ManagedProcess
if ($existing) {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        if ($health.status -eq 'ok' -and -not $health.demo) { Open-Review; exit 0 }
    } catch { }
    throw 'The saved review process is not healthy. Run Stop Agent Skills Feedback.cmd, then retry.'
}
try {
    $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
    if ($health.status -eq 'ok') {
        throw "Port $Port already serves a review UI not managed by this launcher. Stop it or use -Port <other>."
    }
} catch [System.Net.WebException] { }

if (-not $Database) { $Database = $env:AGENT_FEEDBACK_DB }
$manifest = Join-Path $root 'install.json'
if (-not $Database -and (Test-Path $manifest)) {
    $Database = [string](Get-Content $manifest -Raw | ConvertFrom-Json).database
}
$defaultManifest = 'D:\KimiData\agent-feedback\install.json'
if (-not $Database -and (Test-Path $defaultManifest)) {
    $Database = [string](Get-Content $defaultManifest -Raw | ConvertFrom-Json).database
}
if (-not $Database) { $Database = Join-Path $HOME '.agent-feedback\feedback.db' }
$Database = [IO.Path]::GetFullPath($Database)
if (-not (Test-Path $Database)) {
    throw "Feedback database not found: $Database. Run a collection first or pass -Database <path>."
}

$python = $env:AGENT_FEEDBACK_PYTHON
if (-not $python) {
    foreach ($candidate in @('venv\Scripts\python.exe', '.venv\Scripts\python.exe')) {
        $path = Join-Path $root $candidate
        if (Test-Path $path) { $python = $path; break }
    }
}
if (-not $python) { $python = 'python' }
$contracts = $env:AGENT_FEEDBACK_CONTRACTS
if (-not $contracts) {
    $contracts = Join-Path $root 'contracts.json'
    if (-not (Test-Path $contracts)) { $contracts = Join-Path $root 'examples\contracts.json' }
}
$staticDir = Join-Path $root 'review-ui'
foreach ($required in @($contracts, $staticDir)) {
    if (-not (Test-Path $required)) { throw "Required review file not found: $required" }
}
$source = Join-Path $root 'src'
if (Test-Path $source) {
    $paths = @($source) + @($env:PYTHONPATH | Where-Object { $_ })
    $env:PYTHONPATH = [string]::Join([IO.Path]::PathSeparator, $paths)
}
$stdout = Join-Path $root 'review-server-output.log'
$stderr = Join-Path $root 'review-server-error.log'
$arguments = @(
    '-m', 'agent_feedback.review_server', '--db', "`"$Database`"",
    '--contracts', "`"$contracts`"", '--static-dir', "`"$staticDir`"",
    '--host', '127.0.0.1', '--port', $Port
)
$process = Start-Process $python -ArgumentList $arguments -WorkingDirectory $root `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    if ($process.HasExited) { break }
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
        if ($health.status -eq 'ok' -and -not $health.demo) { $ready = $true; break }
    } catch { }
}
if (-not $ready) {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    $detail = if (Test-Path $stderr) { Get-Content $stderr -Raw } else { '' }
    throw "Review server did not become healthy. $detail"
}
@{ pid = $process.Id; started_utc = (Get-Date).ToUniversalTime().ToString('o'); root = $root; port = $Port } |
    ConvertTo-Json | Set-Content $processFile -Encoding UTF8
Open-Review
