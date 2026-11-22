[CmdletBinding()]
param(
    [string]$HermesHome = $(if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA 'hermes' }),
    [string]$HermesBin = '',
    [string]$InstallRoot = 'D:\KimiData\agent-feedback',
    [string]$Python = 'python',
    [switch]$NoAutoCollector
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$pluginRoot = $PSScriptRoot
$payload = Join-Path $pluginRoot 'payload'

function Find-Hermes {
    if ($HermesBin) { return (Resolve-Path $HermesBin).Path }
    $command = Get-Command hermes -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $installs = Join-Path $env:LOCALAPPDATA 'hermes\installs'
    if (Test-Path $installs) {
        $candidate = Get-ChildItem $installs -Filter hermes.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -like '*\venv\Scripts\hermes.exe' } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($candidate) { return $candidate.FullName }
    }
    throw 'Hermes CLI not found. Pass -HermesBin <absolute path to hermes.exe>.'
}

$HermesHome = [IO.Path]::GetFullPath($HermesHome)
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$HermesBin = Find-Hermes
$venvPython = Join-Path $InstallRoot 'venv\Scripts\python.exe'
$skillTarget = Join-Path $HermesHome 'skills\agent-feedback'
$config = Join-Path $HermesHome 'config.yaml'
$registered = $false
$skillCopied = $false
$collectorStarted = $false

if (Test-Path $skillTarget) { throw "Skill already exists: $skillTarget. Refusing to overwrite it." }
New-Item -ItemType Directory -Force $HermesHome, $InstallRoot | Out-Null
$env:HERMES_HOME = $HermesHome

$existing = (& $HermesBin mcp list 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) { throw "hermes mcp list failed: $existing" }
if ($existing -match '(?im)(^|\s)agent-feedback(\s|$)') {
    throw 'MCP server agent-feedback already exists. Refusing to overwrite it.'
}

& $Python -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ required'"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required.' }
if (-not (Test-Path $venvPython)) {
    & $Python -m venv (Join-Path $InstallRoot 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the dedicated Python environment.' }
}
$wheel = Get-ChildItem (Join-Path $payload 'agent_feedback_local-*.whl') | Select-Object -First 1
if (-not $wheel) { throw 'Bundled wheel is missing.' }
& $venvPython -m pip install ("{0}[mcp]" -f $wheel.FullName)
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
& $venvPython -c "import agent_feedback; assert agent_feedback.__version__ == '0.11.2'"
if ($LASTEXITCODE -ne 0) { throw 'Installed package version verification failed.' }

$contracts = Join-Path $InstallRoot 'contracts.json'
Copy-Item (Join-Path $payload 'contracts.json') $contracts -Force
foreach ($name in @('run-collector.ps1','start-auto-collector.ps1','stop-auto-collector.ps1','status-auto-collector.ps1')) {
    Copy-Item (Join-Path $pluginRoot $name) (Join-Path $InstallRoot $name) -Force
}
$db = Join-Path $InstallRoot 'data\feedback.db'
New-Item -ItemType Directory -Force (Split-Path $db) | Out-Null

try {
    New-Item -ItemType Directory -Force (Split-Path $skillTarget) | Out-Null
    Copy-Item (Join-Path $payload 'skill\agent-feedback') $skillTarget -Recurse
    $skillCopied = $true
    $backup = ''
    if (Test-Path $config) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $backup = "$config.agent-feedback-backup-$stamp"
        Copy-Item $config $backup
    }
    $addArgs = @(
        'mcp', 'add', 'agent-feedback', '--command', $venvPython,
        '--env', "AGENT_FEEDBACK_DB=$db", "AGENT_FEEDBACK_CONTRACTS=$contracts",
        '--args', '-m', 'agent_feedback.mcp_server'
    )
    'Y' | & $HermesBin @addArgs
    if ($LASTEXITCODE -ne 0) { throw 'hermes mcp add failed.' }
    $registered = $true
    & $HermesBin mcp test agent-feedback
    if ($LASTEXITCODE -ne 0) { throw 'hermes mcp test failed.' }
    if (-not $NoAutoCollector) {
        & (Join-Path $InstallRoot 'start-auto-collector.ps1') -InstallRoot $InstallRoot -HermesHome $HermesHome
        if ($LASTEXITCODE -ne 0) { throw 'Automatic collector startup failed.' }
        $collectorStarted = $true
    }
    $manifest = @{
        version = '0.11.2'; hermes_home = $HermesHome; hermes_bin = $HermesBin
        install_root = $InstallRoot; database = $db; contracts = $contracts
        skill = $skillTarget; config_backup = $backup; auto_collector = (-not $NoAutoCollector)
        installed_at = (Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json -Depth 3
    Set-Content (Join-Path $InstallRoot 'install.json') $manifest -Encoding UTF8
    Write-Host ''
    Write-Host 'agent-feedback 0.11.2 installed and MCP connection verified.' -ForegroundColor Green
    Write-Host "Hermes Home: $HermesHome"
    Write-Host "Data: $db"
    Write-Host "Automatic collector: $(-not $NoAutoCollector)"
    Write-Host 'Restart the Hermes chat session to load the new Skill and tools.'
} catch {
    if ($collectorStarted) { & (Join-Path $InstallRoot 'stop-auto-collector.ps1') -InstallRoot $InstallRoot 2>$null | Out-Null }
    if ($registered) { & $HermesBin mcp remove agent-feedback 2>$null | Out-Null }
    if ($skillCopied) { Remove-Item $skillTarget -Recurse -Force -ErrorAction SilentlyContinue }
    throw
}
