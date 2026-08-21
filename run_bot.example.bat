@echo off
:: ==========================================
:: Quant Trading Bot Local Execution Script (Template)
:: ==========================================

:: 1. Execution Mode Configuration
:: - Mode A (Signal Briefing Only, No API Keys needed): set SIGNAL_ONLY=true
:: - Mode B (Dry-Run Simulation with Fake Balances): set SIGNAL_ONLY=false & set DRY_RUN=true
:: - Mode C (Live Auto-Trading with Real Orders): set SIGNAL_ONLY=false & set DRY_RUN=false
set SIGNAL_ONLY=false
set DRY_RUN=false

:: 2. Exchange API Keys & Discord Webhook
:: (Copy this file to run_bot.bat and fill in your keys if running Live Trading)
set UPBIT_ACCESS_KEY=YOUR_UPBIT_ACCESS_KEY
set UPBIT_SECRET_KEY=YOUR_UPBIT_SECRET_KEY
set BITHUMB_ACCESS_KEY=YOUR_BITHUMB_ACCESS_KEY
set BITHUMB_SECRET_KEY=YOUR_BITHUMB_SECRET_KEY
set DISCORD_WEBHOOK_URL=YOUR_DISCORD_WEBHOOK_URL

:: 3. Execute Program
cd /d "%~dp0"

python src/main.py

echo Execution completed. Check logs/ directory for details.
pause
