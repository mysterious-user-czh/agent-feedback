[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$HermesHome
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$HermesHome = [IO.Path]::GetFullPath($HermesHome)
$pidFile = Join-Path $InstallRoot 'collector-process.json'
if (Test-Path $pidFile) {
    $old = Get-Content $pidFile -Raw | ConvertFrom-Json
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$($old.pid)" -ErrorAction SilentlyContinue
    if ($existing) {
        $commandLine = [string]$existing.CommandLine
        if (-not $commandLine.Contains('run-collector.ps1') -or -not $commandLine.Contains($InstallRoot)) {
            throw 'Saved collector PID belongs to another process; refusing to reuse it.'
        }
        Write-Output "Collector already running: $($old.pid)"
        exit 0
    }
    Remove-Item $pidFile -Force
}
$state = Join-Path $HermesHome 'state.db'
if (-not (Test-Path $state)) { throw "Hermes state.db not found: $state" }
$runner = Join-Path $InstallRoot 'run-collector.ps1'
$stdout = Join-Path $InstallRoot 'collector-output.log'
$stderr = Join-Path $InstallRoot 'collector-error.log'
$started = (Get-Date).ToUniversalTime()
$statusPath = Join-Path $InstallRoot 'data\collector-status.json'
$statusDirectory = Split-Path $statusPath
New-Item -ItemType Directory -Force $statusDirectory | Out-Null
if (Test-Path $statusPath) {
    $statusArchive = Join-Path $statusDirectory ("collector-status-pre-start-{0}.json" -f $started.ToString('yyyyMMddTHHmmssfffffffZ'))
    Move-Item $statusPath $statusArchive -Force
}
$arguments = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
    '-File', "`"$runner`"", '-InstallRoot', "`"$InstallRoot`"", '-HermesHome', "`"$HermesHome`""
)
$process = Start-Process powershell.exe -ArgumentList $arguments -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr
@{ pid = $process.Id; started_utc = $started.ToString('o'); hermes_home = $HermesHome } |
    ConvertTo-Json | Set-Content $pidFile -Encoding UTF8
$ready = $false
for ($i = 0; $i -lt 180; $i++) {
    Start-Sleep -Seconds 1
    if ($process.HasExited) { break }
    if (Test-Path $statusPath) {
        try {
            $status = Get-Content $statusPath -Raw | ConvertFrom-Json
            $lastRunUtc = [datetimeoffset]::Parse([string]$status.last_run_utc).UtcDateTime
            if ($status.success -and $lastRunUtc -ge $started.AddSeconds(-2)) {
                $ready = $true
                break
            }
        } catch { }
    }
}
if (-not $ready) {
    function Stop-FailedCollectorDescendants {
        param([Parameter(Mandatory=$true)][int]$ParentId)
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$ParentId" -ErrorAction SilentlyContinue |
            ForEach-Object {
                Stop-FailedCollectorDescendants -ParentId $_.ProcessId
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            }
    }
    Stop-FailedCollectorDescendants -ParentId $process.Id
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    throw 'Collector did not produce a successful fresh coverage report. See collector-error.log.'
}
Write-Output "Automatic collector running: $($process.Id); first coverage check passed."
