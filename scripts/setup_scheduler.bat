@echo off
setlocal

echo =======================================================
echo Quant Crypto Trading Bot - Windows Task Scheduler Setup
echo =======================================================
echo.
echo Target Schedule: Daily at 09:05:00 AM (KST)
echo Executable: run_bot.bat --live
echo.

set "TASK_NAME=QuantCryptoLiveTrader"
for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
set "BAT_PATH=%PROJECT_ROOT%\run_bot.bat"

if not exist "%BAT_PATH%" (
    echo [ERROR] run_bot.bat file not found in project root.
    echo Please copy run_bot.example.bat to run_bot.bat first.
    pause
    exit /b 1
)

echo Registering task: %TASK_NAME%
echo Path: %BAT_PATH%
echo.

schtasks /create /f /tn "%TASK_NAME%" /sc daily /st 09:05 /tr "%BAT_PATH% --live"

if %ERRORLEVEL% equ 0 (
    echo.
    echo =======================================================
    echo [SUCCESS] Task registered successfully in Task Scheduler!
    echo It will execute automatically every day at 09:05 AM KST.
    echo =======================================================
) else (
    echo.
    echo [ERROR] Failed to register task.
    echo Please run this batch file as Administrator (Right click -> Run as administrator).
)

echo.
pause
