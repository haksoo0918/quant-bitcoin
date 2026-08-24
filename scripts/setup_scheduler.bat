@echo off
chcp 65001 > nul
setlocal

echo =======================================================
echo ⏰ 퀀트 매매 봇 Windows 작업 스케줄러 자동 등록기
echo =======================================================
echo.
echo 매일 오전 09:05 KST에 'run_bot.bat --live'를 자동 실행하도록
echo Windows 작업 스케줄러에 등록합니다.
echo.

set "TASK_NAME=QuantCryptoLiveTrader"
set "PROJECT_DIR=%~dp0.."
set "BAT_PATH=%PROJECT_DIR%\run_bot.bat"

if not exist "%BAT_PATH%" (
    echo [경고] run_bot.bat 파일이 존재하지 않습니다.
    echo run_bot.example.bat을 복사하여 run_bot.bat을 먼저 생성해 주세요.
    pause
    exit /b 1
)

echo 등록할 작업 이름: %TASK_NAME%
echo 실행 대상 파일: %BAT_PATH%
echo 실행 시각: 매일 오전 09:05:00
echo.

schtasks /create /tn "%TASK_NAME%" /tr "\"%BAT_PATH%\" --live" /sc daily /st 09:05 /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo =======================================================
    echo [성공] 작업 스케줄러에 성공적으로 등록되었습니다!
    echo PC가 켜져 있으면 매일 09:05에 자동으로 전략 주문이 실행됩니다.
    echo =======================================================
) else (
    echo.
    echo [오류] 스케줄러 등록에 실패했습니다.
    echo 관리자 권한으로 명령 프롬프트를 열고 다시 실행해 주세요.
)

echo.
pause
