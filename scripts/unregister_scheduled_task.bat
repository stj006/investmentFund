@echo off
schtasks /Delete /TN "InvestmentFundDailyReport" /F 2>nul
if %ERRORLEVEL%==0 (
    echo Deleted task InvestmentFundDailyReport
) else (
    echo Task InvestmentFundDailyReport not found or already removed
)
