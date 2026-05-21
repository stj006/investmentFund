# 注册 Windows 计划任务：每天 20:35 运行基金日报
# 用法:
#   powershell -ExecutionPolicy Bypass -File scripts\register_scheduled_task.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BatPath = Join-Path $ProjectRoot "scripts\run_daily.bat"
$TaskName = "InvestmentFundDailyReport"

if (-not (Test-Path $BatPath)) {
    Write-Error "找不到 $BatPath"
}

# 使用 schtasks，兼容 Win10/11 各版本 PowerShell
$createArgs = @(
    "/Create",
    "/TN", $TaskName,
    "/TR", "`"$BatPath`"",
    "/SC", "DAILY",
    "/ST", "20:35",
    "/F"
)
$proc = Start-Process -FilePath "schtasks.exe" -ArgumentList $createArgs -Wait -PassThru -NoNewWindow

if ($proc.ExitCode -ne 0) {
    Write-Error "schtasks 注册失败，退出码 $($proc.ExitCode)"
}

Write-Host "已注册计划任务: $TaskName"
Write-Host "  执行: $BatPath"
Write-Host "  时间: 每天 20:35"
Write-Host ""
Write-Host "立即测试:"
Write-Host "  schtasks /Run /TN `"$TaskName`""
Write-Host ""
Write-Host "删除任务:"
Write-Host "  schtasks /Delete /TN `"$TaskName`" /F"
