@echo off
chcp 65001 > nul
setlocal

echo =======================================================
echo 🗑️ 퀀트 매매 봇 Windows 작업 스케줄러 등록 해제기
echo =======================================================
echo.

set "TASK_NAME=QuantCryptoLiveTrader"

echo 등록 해제할 작업 이름: %TASK_NAME%
echo.

schtasks /delete /tn "%TASK_NAME%" /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo =======================================================
    echo [성공] 작업 스케줄러에서 성공적으로 제거되었습니다.
    echo =======================================================
) else (
    echo.
    echo [안내] 등록된 작업이 없거나 이미 삭제되었습니다.
)

echo.
pause
