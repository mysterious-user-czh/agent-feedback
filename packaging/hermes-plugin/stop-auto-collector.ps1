[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$InstallRoot)
$ErrorActionPreference = 'Stop'
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$pidFile = Join-Path $InstallRoot 'collector-process.json'
if (-not (Test-Path $pidFile)) { Write-Output 'Collector is not registered.'; exit 0 }
$info = Get-Content $pidFile -Raw | ConvertFrom-Json
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($info.pid)" -ErrorAction SilentlyContinue
if ($process) {
    $commandLine = [string]$process.CommandLine
    if (-not $commandLine.Contains('run-collector.ps1') -or -not $commandLine.Contains($InstallRoot)) {
        throw 'PID identity mismatch; refusing to stop an unrelated process.'
    }
    $script:descendantIds = @()
    function Stop-Descendants {
        param([Parameter(Mandatory=$true)][int]$ParentId)
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ParentId" -ErrorAction SilentlyContinue)
        foreach ($child in $children) {
            Stop-Descendants -ParentId $child.ProcessId
            Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
            $script:descendantIds += [int]$child.ProcessId
        }
    }
    Stop-Descendants -ParentId $info.pid
    Stop-Process -Id $info.pid -Force
    Start-Sleep -Milliseconds 500
    $allIds = @($script:descendantIds) + @([int]$info.pid)
    $remaining = @($allIds | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    if ($remaining.Count) { throw "Collector process tree did not stop cleanly: $remaining" }
}
Remove-Item $pidFile -Force
Write-Output 'Collector and all descendant processes stopped.'
