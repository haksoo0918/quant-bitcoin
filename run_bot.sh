#!/usr/bin/env bash
# ========================================================
# Quant Crypto Trading Bot - Linux / Server Execution Wrapper
# Settings and API keys are managed in .env file.
# Command-line arguments ("$@") are passed directly to Python.
# ========================================================

# Navigate to project root directory
cd "$(dirname "$0")" || exit 1

# Activate Python virtual environment if exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Ensure logs directory exists
mkdir -p logs

TODAY=$(date +"%Y%m%d")
LOG_FILE="logs/bot_${TODAY}.log"

echo "========================================================" | tee -a "$LOG_FILE"
echo "  [$(date +'%Y-%m-%d %H:%M:%S')] Starting Quant Trading Bot" | tee -a "$LOG_FILE"
echo "========================================================" | tee -a "$LOG_FILE"

# Execute Python bot
if [ $# -eq 0 ]; then
    python3 src/main.py --live 2>&1 | tee -a "$LOG_FILE"
else
    python3 src/main.py "$@" 2>&1 | tee -a "$LOG_FILE"
fi

EXIT_CODE=${PIPESTATUS[0]}
echo "  [$(date +'%Y-%m-%d %H:%M:%S')] Finished (Exit Code: $EXIT_CODE)" | tee -a "$LOG_FILE"
echo "========================================================" | tee -a "$LOG_FILE"

exit $EXIT_CODE
