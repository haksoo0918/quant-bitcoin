#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# 퀀트 봇 Termux 원클릭 무인 자동 실행 설정 스크립트
# - 안드로이드 기기(집 Wi-Fi 연결)에서 데스크톱 없이 매일 09:05 KST 자동 실행
# ==============================================================================

set -e

echo "=== [1/5] 기본 패키지 업데이트 및 필수 도구 설치 ==="
pkg update -y
pkg install -y python git cronie termux-api

echo "=== [2/5] 화면 꺼짐 방지(Wakelock) 활성화 ==="
termux-wake-lock

echo "=== [3/5] 파이썬 패키지 설치 ==="
pip install --upgrade pip
pip install requests pyjwt pyupbit pandas numpy python-dotenv

echo "=== [4/5] 봇 실행 크론탭(스케줄러) 등록 (매일 09:05 KST) ==="
# Termux 기기 시간 기준 매일 09:05 자동 실행
PROJECT_DIR="$(pwd)"
CRON_JOB="5 9 * * * cd $PROJECT_DIR && python src/main.py --live >> bot_cron.log 2>&1"

# 기존 crontab 백업 후 등록
(crontab -l 2>/dev/null | grep -v "quant-bitcoin"; echo "$CRON_JOB") | crontab -

echo "=== [5/5] 크론 데몬 시작 ==="
crond

echo "=============================================================================="
echo "✅ 모든 설정이 완료되었습니다!"
echo "• 매일 아침 09:05에 봇이 자동으로 실행됩니다."
echo "• 기기가 집 Wi-Fi에 연결되어 있으면 등록된 고정 IP로 안전하게 거래됩니다."
echo "=============================================================================="
