[CmdletBinding()]
param(
    [string]$InstallRoot = 'D:\KimiData\agent-feedback',
    [switch]$Purge
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$manifestPath = Join-Path $InstallRoot 'install.json'
if (-not (Test-Path $manifestPath)) { throw "Installation manifest not found: $manifestPath" }
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$stopCollector = Join-Path $InstallRoot 'stop-auto-collector.ps1'
if (Test-Path $stopCollector) { & $stopCollector -InstallRoot $InstallRoot }
$env:HERMES_HOME = $manifest.hermes_home
& $manifest.hermes_bin mcp remove agent-feedback
if ($LASTEXITCODE -ne 0) { throw 'Failed to remove the MCP registration. No Skill or data was deleted.' }
if ((Split-Path $manifest.skill -Leaf) -ne 'agent-feedback') { throw 'Unexpected Skill path; refusing deletion.' }
if (Test-Path $manifest.skill) { Remove-Item $manifest.skill -Recurse -Force }
if ($Purge) {
    Remove-Item $InstallRoot -Recurse -Force
    Write-Host 'Collector, registration, Skill, runtime and feedback data removed.'
} else {
    Write-Host 'Collector, registration and Skill removed. Runtime, feedback data and config backups were preserved.'
}
