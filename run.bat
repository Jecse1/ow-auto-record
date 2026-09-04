@echo off
REM 오버워치 리플레이 자동 녹화 실행 스크립트
REM venv를 활성화한 뒤 main.py를 실행합니다.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [오류] venv를 찾을 수 없습니다.
    echo   먼저 아래 명령으로 가상환경을 만들고 의존성을 설치하세요:
    echo     python -m venv venv
    echo     venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

call "venv\Scripts\activate.bat"
python main.py

echo.
echo 프로그램이 종료되었습니다.
pause
