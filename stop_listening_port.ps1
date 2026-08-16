[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [Parameter(Position = 0)]
    [ValidateNotNullOrEmpty()]
    [ValidateScript({
        foreach ($value in $_) {
            if ($value -lt 1 -or $value -gt 65535) {
                throw "端口必须在 1 到 65535 之间。"
            }
        }
        $true
    })]
    [int[]]$Port = @(5188)
)

$ErrorActionPreference = "Stop"
$requestedPorts = @($Port | Sort-Object -Unique)

function Get-TcpListeners {
    $netstat = Join-Path $env:SystemRoot "System32\netstat.exe"
    foreach ($line in & $netstat -ano -p TCP) {
        if ($line -match '^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$') {
            [pscustomobject]@{
                LocalPort = [int]$Matches[1]
                OwningProcess = [int]$Matches[2]
            }
        }
    }
}

$listeners = @(Get-TcpListeners | Where-Object { $_.LocalPort -in $requestedPorts })

foreach ($requestedPort in $requestedPorts) {
    if (-not ($listeners | Where-Object { $_.LocalPort -eq $requestedPort })) {
        Write-Output "端口 $requestedPort 当前没有监听进程。"
    }
}

$owners = @($listeners | Group-Object OwningProcess | Sort-Object Name)
foreach ($owner in $owners) {
    $processId = [int]$owner.Name
    $ownedPorts = @($owner.Group.LocalPort | Sort-Object -Unique)

    if ($processId -le 0 -or $processId -eq $PID) {
        Write-Warning "跳过进程 $processId；它不能由此脚本安全停止。"
        continue
    }

    $currentListeners = @(
        Get-TcpListeners |
            Where-Object { $_.OwningProcess -eq $processId -and $_.LocalPort -in $ownedPorts }
    )
    if (-not $currentListeners) {
        Write-Warning "进程 $processId 已不再监听目标端口，已跳过。"
        continue
    }

    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    $processName = if ($process) { $process.ProcessName } else { "未知进程" }
    $target = "PID $processId ($processName)，端口 $($ownedPorts -join ', ')"

    if ($PSCmdlet.ShouldProcess($target, "停止监听进程")) {
        Stop-Process -Id $processId -Force -ErrorAction Stop
        Write-Output "已停止 $target。"
    }
}
