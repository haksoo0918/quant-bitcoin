@echo off
:: ==========================================
:: Quant Trading Bot Local Execution Script (Template)
:: ==========================================

:: 1. API Keys and Environment Variables
:: (Copy this file to run_bot.bat and fill in your keys)
set UPBIT_ACCESS_KEY=YOUR_UPBIT_ACCESS_KEY
set UPBIT_SECRET_KEY=YOUR_UPBIT_SECRET_KEY
set BITHUMB_ACCESS_KEY=YOUR_BITHUMB_ACCESS_KEY
set BITHUMB_SECRET_KEY=YOUR_BITHUMB_SECRET_KEY
set DISCORD_WEBHOOK_URL=YOUR_DISCORD_WEBHOOK_URL

:: 2. Execute Program
cd /d "%~dp0"

python main.py >> trading_log.txt 2>&1

echo Execution completed. Check trading_log.txt for details.
pause
