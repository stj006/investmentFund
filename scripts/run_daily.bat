@echo off
setlocal EnableExtensions

cd /d "%~dp0.."
set "ROOT=%CD%"
set "LOG_DIR=%ROOT%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f %%i in ('wmic os get localdatetime ^| findstr /r "[0-9]"') do set "DT=%%i"
set "TODAY=%DT:~0,8%"
set "LOG_FILE=%LOG_DIR%\daily_%TODAY%.log"

echo [%date% %time%] start daily_report >> "%LOG_FILE%"

if exist "%ROOT%\.venv\Scripts\activate.bat" (
    call "%ROOT%\.venv\Scripts\activate.bat"
)

set PYTHONIOENCODING=utf-8
python "%ROOT%\scripts\daily_report.py" >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [%date% %time%] failed exit=%EXIT_CODE% >> "%LOG_FILE%"
    python "%ROOT%\scripts\notify_failure.py" >> "%LOG_FILE%" 2>&1
    endlocal & exit /b %EXIT_CODE%
)

echo [%date% %time%] done >> "%LOG_FILE%"
endlocal & exit /b 0
