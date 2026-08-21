@echo off
:: ==========================================
:: Quant Trading Signal Bot Local Simulation Script (Template)
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

python src/main.py

echo Execution completed. Check logs/ directory for details.
pause
