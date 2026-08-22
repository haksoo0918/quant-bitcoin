@echo off
:: ========================================================
:: Quant Trading Bot Execution Script Wrapper
:: Settings and API keys are managed in .env file.
:: Command-line arguments (%*) are passed directly to Python.
::
:: Examples:
::   run_bot.bat --signal-only
::   run_bot.bat --dry-run
::   run_bot.bat --live
::   run_bot.bat --live --no-alt
:: ========================================================

cd /d "%~dp0"

python src/main.py %*

echo.
echo Execution finished.
pause

