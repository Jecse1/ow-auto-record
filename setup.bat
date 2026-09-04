@echo off
setlocal enabledelayedexpansion
REM 오버워치 리플레이 자동 녹화 - 설치 스크립트 (Python 자동 설치 포함)
REM 다른 PC에서 압축을 푼 뒤 이 파일을 더블클릭하면 됩니다.

cd /d "%~dp0"

echo ============================================================
echo   오버워치 리플레이 자동 녹화 - 설치 setup
echo ============================================================
echo.

set "PYEXE="

REM ---------------------------------------------------------
echo [1/4] Python 확인 중...
REM PATH의 python이 3.10 이상인지 확인
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if !errorlevel! equ 0 (
    set "PYEXE=python"
    echo   - PATH에서 Python 3.10 이상을 찾았습니다. 그대로 사용합니다.
    goto make_venv
)
echo   - PATH에 Python 3.10 이상이 없습니다. 자동 설치를 시도합니다.
echo.

REM ---------------------------------------------------------
echo [1/4] Python 설치 winget...
where winget >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo   [안내] 이 PC에는 winget 앱 설치 관리자 이 없습니다.
    echo   아래 페이지에서 Python 3.11을 직접 내려받아 설치하세요:
    echo       https://www.python.org/downloads/windows/
    echo   [중요] 설치 첫 화면에서 'Add python.exe to PATH' 를 반드시 체크하세요.
    echo   설치가 끝나면 이 setup.bat 을 다시 실행하면 됩니다.
    echo.
    pause
    exit /b 1
)
echo   - winget으로 Python 3.11 설치 중... 인터넷 필요, 수 분 소요
winget install -e --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements

REM PATH 갱신이 즉시 안 될 수 있으므로 설치 경로를 직접 확인
set "CAND=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if exist "!CAND!" (
    set "PYEXE=!CAND!"
    echo   - 설치된 Python 사용: !CAND!
    goto make_venv
)
REM 혹시 PATH가 갱신됐으면 python 재확인
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if !errorlevel! equ 0 (
    set "PYEXE=python"
    echo   - 설치된 Python PATH 을 사용합니다.
    goto make_venv
)
echo.
echo   [오류] Python 설치를 확인하지 못했습니다.
echo   새 명령 프롬프트를 열고 setup.bat 을 다시 실행해 보세요.
pause
exit /b 1

REM ---------------------------------------------------------
:make_venv
echo.
echo [2/4] 가상환경 venv 준비...
if exist "venv\Scripts\python.exe" (
    echo   - 기존 venv를 발견했습니다. 의존성만 업데이트합니다.
) else (
    echo   - venv 생성 중...
    "!PYEXE!" -m venv venv
    if !errorlevel! neq 0 (
        echo   [오류] venv 생성에 실패했습니다.
        pause
        exit /b 1
    )
    echo   - venv 생성 완료.
)

REM ---------------------------------------------------------
echo.
echo [3/4] 의존성 설치 중...
echo   easyocr/torch 등 용량이 커 최초에는 10분 이상 걸릴 수 있습니다. 인터넷 필요
"venv\Scripts\python.exe" -m pip install --upgrade pip
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo.
    echo   [오류] 의존성 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행하세요.
    pause
    exit /b 1
)

REM ---------------------------------------------------------
echo.
echo [4/4] 설치 완료!
echo.
echo   이제 run_gui.bat 을 실행하세요.
echo   실행 전에 OBS의 WebSocket 서버를 켜고, config.yaml 의
echo   obs.password 에 본인 비밀번호를 입력하는 것을 잊지 마세요.
echo   Tesseract는 선택 사항입니다. 없어도 동작하며, 있으면 OCR 정확도가 좋아집니다.
echo.
pause
