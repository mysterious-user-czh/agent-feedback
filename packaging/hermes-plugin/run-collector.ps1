param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$HermesHome
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $InstallRoot 'venv\Scripts\python.exe'
$db = Join-Path $InstallRoot 'data\feedback.db'
$contracts = Join-Path $InstallRoot 'contracts.json'
$state = Join-Path $HermesHome 'state.db'
& $python -m agent_feedback.cli --db $db --contracts $contracts watch-hermes $state --interval 60
