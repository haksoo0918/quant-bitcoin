@echo off
:: UTF-8 한글 깨짐 방지
chcp 65001 > nul

:: ==========================================
:: 퀀트 자동 매매 시스템 로컬 실행 배치 스크립트 (템플릿)
:: ==========================================

:: 1. API 키 및 환경 변수 설정 (이 파일을 run_bot.bat으로 복사 후 본인의 키로 변경해 주세요)
set UPBIT_ACCESS_KEY=YOUR_UPBIT_ACCESS_KEY
set UPBIT_SECRET_KEY=YOUR_UPBIT_SECRET_KEY
set BITHUMB_ACCESS_KEY=YOUR_BITHUMB_ACCESS_KEY
set BITHUMB_SECRET_KEY=YOUR_BITHUMB_SECRET_KEY
set DISCORD_WEBHOOK_URL=YOUR_DISCORD_WEBHOOK_URL

:: 실제 매매를 하려면 False, 모의 실행을 하려면 True로 설정
set DRY_RUN=False

:: 2. 프로그램 실행 및 로그 기록
:: 스크립트가 위치한 폴더로 경로 변경
cd /d "%~dp0"

:: 매매 결과 로그를 trading_log.txt 파일에 누적 기록합니다.
echo === 실행 일시: %date% %time% === >> trading_log.txt
python main.py >> trading_log.txt 2>&1

echo 매매 프로그램 실행 완료 (로그 확인: trading_log.txt)
