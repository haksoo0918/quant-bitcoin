@echo off
setlocal

echo =======================================================
echo Quant Crypto Trading Bot - Windows Task Scheduler Removal
echo =======================================================
echo.

set "TASK_NAME=QuantCryptoLiveTrader"

echo Removing task: %TASK_NAME%
echo.

schtasks /delete /tn "%TASK_NAME%" /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo =======================================================
    echo [SUCCESS] Task removed successfully from Task Scheduler.
    echo =======================================================
) else (
    echo.
    echo [INFO] Task was not found or already deleted.
)

echo.
pause
