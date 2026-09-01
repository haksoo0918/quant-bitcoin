@echo off
chcp 65001 >nul
title 퀀트 코인 전략 로컬 대시보드

echo =======================================================
echo   퀀트 코인 전략 로컬 대시보드 웹 서버를 시작합니다.
echo   접속 주소: http://localhost:8000
echo   종료하려면 이 창을 닫으세요.
echo =======================================================

start "" http://localhost:8000
python -m http.server 8000 --directory docs
