schtasks /Delete /TN "InvestmentFundDailyReport" /F 2>$null
Write-Host "已删除任务 InvestmentFundDailyReport（若存在）"
