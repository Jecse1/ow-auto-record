@echo off
REM 오버워치 리플레이 자동 녹화 - GUI 실행 스크립트
REM venv의 pythonw로 실행해 콘솔 창 없이 GUI만 띄웁니다.

cd /d "%~dp0"

if not exist "venv\Scripts\pythonw.exe" (
    echo [오류] venv를 찾을 수 없습니다.
    echo   먼저 아래로 가상환경을 만들고 의존성을 설치하세요:
    echo     python -m venv venv
    echo     venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

REM 콘솔 없이 GUI 실행 (문제 발생 시 아래 줄을 python.exe로 바꾸면 오류 로그가 보입니다)
start "" "venv\Scripts\pythonw.exe" gui.py %*
