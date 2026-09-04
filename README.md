# 오버워치 리플레이 자동 녹화 프로그램 (v0.2)

패치로 리플레이 호환이 끊기기 전에, 원하는 리플레이들을 **선수 시점별로** 사람 개입 없이
순차 녹화하는 도구입니다.

## 0. 다른 PC에서 시작하기 (처음이라면 여기부터)

압축 파일(`ow-auto-record.zip`)을 받은 분은 아래 **4단계**만 하면 됩니다.

1. **압축 해제**: `ow-auto-record.zip`을 원하는 위치에 풀면 `ow-auto-record` 폴더가 생깁니다.
2. **`setup.bat` 실행** (더블클릭): Python이 없으면 자동으로 설치하고, 가상환경(venv)과
   필요한 라이브러리까지 한 번에 설치합니다. *(중간에 창이 닫히지 마세요.)*
3. **OBS 준비**: OBS Studio(28 이상)를 실행 → **도구 > WebSocket 서버 설정**에서 서버를 켜고,
   **`config.example.yaml`을 `config.yaml`로 복사**한 뒤, 설정한 **비밀번호를
   `config.yaml`의 `obs.password`** 에 입력해 저장합니다. *(`config.yaml`은 비밀번호가 들어
   있어 저장소에 포함되지 않습니다. 항상 `config.example.yaml`을 복사해서 사용하세요.)*
4. **`run_gui.bat` 실행** (더블클릭): 창에서 리플레이 코드/선수를 등록하고 녹화를 시작합니다.

### 환경 요구 사항

- **Windows 10 / 11**
- 오버워치: **1920×1080, 테두리 없는 창모드, 디스플레이 배율 100%**
- 게임 **언어 한국어** (화면 인식 템플릿이 한국어 UI 기준)
- 관전(시점) 단축키는 **기본값 사용** — 1팀 `F1~F5`, 2팀 `F7~F11`
- **OBS Studio 28 이상** (WebSocket v5 내장), 게임 캡처 소스 + 녹화 출력 설정 완료

### 알아두기

- **최초 `setup.bat`은 인터넷이 필요**하며, easyocr/torch 등 용량이 큰 라이브러리를
  내려받느라 **10분 이상 걸릴 수 있습니다.** 창이 멈춘 것처럼 보여도 기다려 주세요.
- 이미 설치했다면 `setup.bat`은 의존성만 업데이트하고 넘어갑니다.
- **Tesseract는 선택 설치**입니다. 없어도 easyocr만으로 동작하며, 설치되어 있으면
  숫자 인식(코드 OCR) 정확도가 좋아집니다. (설치 방법은 아래 4-1 참고)

## 1. v0.2에서 새로 생긴 것

- **데스크톱 GUI**(v0.3): 콘솔 없이 창 하나로 세션 등록 → 녹화 시작 → 진행 확인 (`gui.py`)
- **목록 스크롤 탐색**(v0.4): 코드가 목록 화면 밖에 있으면 마우스 휠로 스크롤하며 찾음
  (맨 위로 리셋 → 아래로 한 스텝씩 스크롤하며 OCR, 스크롤 끝에 도달하면 종료)
- **세션 기반 녹화**: "어떤 코드의 리플레이를, 어떤 선수 시점으로 녹화할지"를 `sessions.yaml`로 관리
- **리플레이 코드 자동 인식(OCR)**: 목록 화면의 주황색 배지(6자리 코드)를 읽어 해당 행을 찾아 클릭
  (고정 좌표에 의존하지 않음)
- **선수 시점 자동 전환**: 재생 진입 후 F1~F5(1팀)/F7~F11(2팀)로 관전 시점 고정 후 녹화
- **녹화 파일명 태깅**: `<코드>_<선수>_<날짜시간>.mkv` 형식으로 자동 리네임

## 2. 개요

- 화면 인식(OpenCV 템플릿 매칭)으로 리플레이 재생/종료를 감지
- 리플레이 코드 OCR(easyocr + 선택적 Tesseract)로 목록에서 대상 리플레이를 찾음
- OBS Studio를 obs-websocket으로 제어하여 녹화 시작/정지 및 파일명 태깅
- pydirectinput으로 목록 선택 → 재생 → 시점 전환 → 나가기까지 전체 자동화

## 3. 요구 사항

- Windows, 오버워치 **창모드(테두리 없음), 1920x1080 권장**
- OBS Studio 28 이상 (WebSocket v5 내장)
- Python 3.10 이상

## 4. 설치

가상환경(venv) 사용을 권장합니다.

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

> easyocr는 처음 실행할 때 인식 모델(약 64MB)을 자동으로 내려받습니다(최초 1회, 인터넷 필요).

### 4-0. GUI로 사용하기 (권장)

콘솔 대신 창 하나로 세션 등록·녹화·진행 확인을 모두 할 수 있습니다.

```
run_gui.bat            더블클릭  (콘솔 창 없이 GUI 실행)
```
또는 수동으로:
```
venv\Scripts\activate
python gui.py           # 실제 녹화 (OBS/게임 필요)
python gui.py --demo    # 녹화 없이 동작만 미리 보는 데모 모드
```

GUI 사용 흐름:
1. **세션 입력** — 리플레이 코드(자동 대문자) 입력 → 블루/레드 1~5 체크박스로 선수 선택 → **[세션 추가]**.
   목록에 "코드 / 선수(=녹화 횟수) / 상태"가 표시됩니다. 선택 후 **[삭제] / [위로] / [아래로]**로 편집.
2. **[저장]** 으로 `sessions.yaml`에 기록(다음 실행 시 자동 로드). **[녹화 시작]** 시에도 자동 저장됩니다.
3. **[녹화 시작]** → 5초 카운트다운("게임 창을 활성화하세요") 후 자동 진행.
   전체 진행 바 / 현재 작업(코드·선수·단계) / 세션별 상태 / 하단 로그가 실시간 갱신됩니다.
4. **[중단]** 또는 창 닫기(X) 시 녹화 중이면 OBS를 안전하게 정지한 뒤 종료합니다.
   OBS 연결 실패 시 원인·조치를 팝업으로 안내합니다.

> 콘솔 방식(`run.bat` / `python main.py`)도 그대로 사용할 수 있습니다.

### 4-1. (선택) Tesseract 설치 — 숫자 인식 정확도 보강

리플레이 코드에는 `1/I`, `5/S`, `0/O`처럼 헷갈리는 글자가 있습니다.
easyocr만으로도 대부분 맞지만, **Tesseract를 함께 쓰면 숫자 오인식을 보정**해 정확도가 올라갑니다.

1. 설치(둘 중 하나):
   - `winget install UB-Mannheim.TesseractOCR`
   - 또는 https://github.com/UB-Mannheim/tesseract/wiki 에서 설치 파일 다운로드
2. 설치 경로를 `config.yaml`의 `ocr.tesseract.cmd`에 지정
   (기본값: `C:/Program Files/Tesseract-OCR/tesseract.exe`)
3. 쓰지 않으려면 `ocr.tesseract.enabled: false`로 두면 easyocr만 사용합니다.

## 5. OBS 설정

1. 도구 > WebSocket 서버 설정 > "WebSocket 서버 활성화" 체크
2. 포트(기본 4455)와 비밀번호를 `config.yaml`의 `obs` 항목에 기입
3. 장면에 오버워치 게임 캡처 소스를 추가하고 녹화 출력(경로/포맷) 설정
   - 파일명 태깅(`obs.filename_tag: true`)은 녹화가 끝난 뒤 파일을 리네임하는 방식입니다.

## 6. 최초 1회 보정

### 6-1. 템플릿 이미지 (2장)

이 저장소에는 예시 스크린샷에서 잘라낸 템플릿이 이미 들어 있습니다
(`templates/replay_menu.png`, `replay_ended.png`).
**해상도/UI가 다르거나 패치로 화면이 바뀌면** 아래로 다시 캡처하세요.

| 템플릿 | 캡처 시점 | 잘라낼 영역 예시 |
|---|---|---|
| `replay_menu.png` | 리플레이 목록(로비) | 왼쪽 '리플레이' 탭 등 이 화면 고유 UI |
| `replay_ended.png` | "리플레이 종료" 화면 | 주황색 "리플레이 종료" 문구 |

> v0.3부터 재생 진입은 감지하지 않습니다. '보기'를 클릭하면 리플레이가 항상
> 자동 재생되므로, `recording.load_wait`(초)만큼 고정 대기한 뒤 F키 시점 전환을
> 수행합니다. 기존 `replay_playing.png`는 미사용이며 파일만 남아 있습니다.

```
python capture_template.py replay_ended
```
→ 전체 화면이 저장되면, 고유하고 변하지 않는 영역(100~300px)을 잘라 `templates/<이름>.png`로 저장.
플레이어 이름·시간처럼 매번 바뀌는 부분은 포함하지 마세요.

### 6-2. 클릭 좌표 보정

```
python calibrate.py
```
마우스를 올려 좌표를 확인하고 `config.yaml`에 기입합니다.

- `replay_list.view_button`: 항목 선택 후 누르는 **'보기'** 버튼 좌표
- `replay_list.row_click_x`: 목록 행을 선택할 때 클릭할 x좌표
  (배지/공유 아이콘을 피해 목록 본문. 세로 위치 y는 OCR로 자동 결정)

## 7. 녹화할 세션 등록 (`sessions.yaml`)

한 **세션** = 리플레이 코드 1개 + 녹화할 선수 시점 목록. 각 선수마다 리플레이를 처음부터 다시 재생합니다.

```yaml
sessions:
  - code: R19FV7
    players:
      - blue1      # 1팀 1번 → F1
      - red1       # 2팀 1번 → F7
  - code: TYZY7S
    players:
      - red3       # 2팀 3번 → F9
```

- 선수 표기: `blue1`~`blue5`(1팀, F1~F5), `red1`~`red5`(2팀, F7~F11)
- `sessions.yaml`이 **없으면** 실행 시 콘솔에서 코드/선수를 입력받아 자동으로 만들어 저장합니다.
- 실행 시작 시 코드 형식·선수 표기의 유효성을 먼저 검사합니다.

## 8. OCR 점검 (게임 없이 테스트)

리플레이 목록 스크린샷으로 코드 인식이 잘 되는지 미리 확인할 수 있습니다.

```
python test_ocr.py tests/lobby.jpg
python test_ocr.py tests/lobby.jpg R19FV7 CWR5WC TYZY7S G68XMC   # 기대 코드 지정 시 채점
```
인식된 코드와 각 배지의 좌표가 출력됩니다.

## 9. 실행

1. OBS 실행 (녹화는 프로그램이 제어하므로 시작하지 않음)
2. 오버워치에서 경력 > 리플레이 목록 화면을 열어둠
3. 아래 중 하나로 실행 → 5초 안에 게임 창 활성화
   - **간편 실행**: `run.bat` 더블클릭
   - **수동 실행**: `venv\Scripts\activate` 후 `python main.py`
4. 이후 자동 진행. 중단은 Ctrl+C (녹화 정지 처리됨)

> OBS 미실행/WebSocket 미활성 시 원인과 조치를 안내하고 종료합니다.
> 실행 중 오류·중단이 발생해도 녹화는 반드시 정지됩니다.

## 10. 동작 흐름

```
sessions.yaml 검증
→ [세션마다] 목록을 맨 위로 리셋 → 아래로 스크롤하며 코드 OCR로 행 위치 파악
             (스크롤 끝까지 못 찾으면 "목록 전체에서 코드 XXXXXX를 찾지 못했습니다" 후 건너뜀)
   [선수마다]
     코드 행 클릭 → '보기' → load_wait 고정 대기 → 선수 시점(F키) 1회 입력 → 녹화 시작
     → "리플레이 종료" 감지(또는 최대 시간 초과) → 녹화 정지 → 파일명 태깅
     → ESC로 목록 복귀 → 다음 선수/세션
```

종료 판정은 2중: ① `replay_ended` 템플릿(1순위) ② `max_duration` 초과(안전장치).

## 11. 문제 해결

- **코드 인식이 안 됨/틀림**:
  `python test_ocr.py tests/lobby.jpg`로 점검. Tesseract를 설치하면 숫자 인식이 좋아집니다(4-1).
  해상도가 1920x1080이 아니면 `config.yaml`의 `ocr.roi`(배지 열 영역, 목록 세로 전체)를 화면에 맞게 조정하세요.
  (`python test_ocr.py tests/lobby_scroll.jpg`로 스크롤 상태의 배지 인식도 함께 점검)
- **스크롤이 안 됨/코드를 못 찾음**: `python test_scroll.py`로 어떤 휠 입력 방식이
  실제로 목록을 움직이는지 먼저 확인하세요(sendinput/pydirectinput/pyautogui를 순서대로
  시도하며 픽셀차를 출력). 동작하는 방식을 `config.yaml`의 `scroll.scroll_method`에 고정하면
  됩니다(기본 `auto`는 sendinput→pydirectinput→pyautogui 순). `scroll.list_area`(휠 입력 시
  마우스 위치)가 목록 위에 오는지, 스크롤이 너무 빨라 씹히면 `scroll.scroll_wait`를 늘리고,
  끝을 잘못 판정하면 `scroll.end_diff_threshold`를 조정하세요.
  첫 스크롤에서 화면이 안 변하면 로그에 "휠 입력이 게임에 전달되지 않는 것 같습니다" 경고가 뜹니다.
- **화면 감지가 안 됨**: `detection.match_threshold`를 0.75로 낮추거나 템플릿을 다시 캡처.
- **클릭이 무시됨**: 전체화면 → 창모드(테두리 없음)로 변경, 터미널을 **관리자 권한**으로 실행.
- **좌표가 안 맞음**: 해상도/창 위치가 바뀌면 `calibrate.py`로 다시 측정해 `config.yaml` 갱신.
- **패치 후 오작동**: UI가 바뀌면 **템플릿 3장만 다시 캡처**하면 됩니다(코드 수정 불필요).
  코드 배지 디자인이 바뀌면 `ocr.badge_hsv`/`ocr.roi`를 조정하세요.
- **OBS 연결 실패**: WebSocket 서버 활성화 여부, 포트/비밀번호 확인.
- **파일명이 안 바뀜**: 녹화 저장 폴더 쓰기 권한 확인. 잠금 해제 대기는
  `obs.rename_retries`/`rename_retry_delay`로 조정.

## 12. 파일 구성

```
ow-auto-record/
├─ config.yaml            # 모든 설정 (OBS/감지/OCR/좌표/녹화)
├─ sessions.yaml          # 녹화할 세션 목록 (코드 + 선수)
├─ screen_detector.py     # 화면 캡처 + 템플릿 매칭
├─ ocr_locator.py         # 배지 검출 + 코드 OCR (easyocr + Tesseract)
├─ obs_client.py          # OBS 녹화 시작/정지 + 파일명 태깅
├─ replay_controller.py   # 목록 선택·재생·시점(F키)·복귀
├─ sessions.py            # 세션 정의/검증/대화형 입력
├─ main.py                # 메인 루프 + run_sessions()(GUI 재사용용) + 콘솔 진입점
├─ gui.py                 # 데스크톱 GUI (Tkinter), 데모 모드(--demo)/자가검증(--selftest)
├─ test_ocr.py            # OCR 점검 도구 (게임 없이)
├─ test_scroll.py         # 휠 스크롤 진단 도구 (어떤 입력 방식이 먹는지 확인)
├─ capture_template.py    # 템플릿 캡처 보정 도구
├─ calibrate.py           # 좌표 보정 도구
├─ setup.bat              # (설치) Python 자동 설치 + venv + 의존성 (다른 PC 최초 1회)
├─ run.bat                # (콘솔) venv 활성화 후 main.py 실행
├─ run_gui.bat            # (GUI) venv의 pythonw로 gui.py 실행
├─ requirements.txt
├─ templates/             # 템플릿 이미지 2장 (replay_menu/replay_ended)
└─ tests/                 # 예시 스크린샷 (lobby/lobby_scroll/ingame/ended)
```

## 13. 한계와 주의

- 화면 인식 기반이므로 해상도/HUD 배율을 바꾸면 재보정이 필요합니다.
- 목록 스크롤 탐색은 v0.4부터 지원합니다(마우스 휠). 게임이 특정 휠 방식을 무시하면
  `scroll.scroll_method`를 바꿔 확인하세요.
- 리플레이 가져오기(import) 자동화는 이번 버전 범위 밖입니다. 목록에 코드가 보이지 않으면
  해당 세션을 건너뛰고 로그를 남깁니다.
- 녹화 중 다른 창을 띄우면 캡처·입력이 깨질 수 있으니 실행 중에는 PC 조작을 피하세요.
