"""리플레이 메뉴 조작 모듈: pydirectinput으로 게임 내 클릭/키 입력.

주의: 오버워치는 DirectInput 기반이라 pyautogui 클릭이 무시될 수 있어
pydirectinput을 사용한다. 게임은 '창모드(테두리 없음)' 권장.

v0.2: 리플레이 코드로 찾은 행을 클릭 → '보기'로 재생 진입, 선수 시점(F키) 입력,
종료 후 ESC로 목록(로비) 복귀를 담당한다.
v0.4: 목록이 길어 코드가 화면 밖에 있을 때 마우스 휠로 스크롤 탐색을 지원한다.
      pyautogui/pydirectinput 휠이 게임에 전달되지 않는 경우가 있어, ctypes SendInput
      기반 휠 입력(sendinput)을 추가하고 auto의 1순위로 둔다.
"""
import ctypes
import time
from ctypes import wintypes

import pydirectinput

pydirectinput.PAUSE = 0.15

# ---- ctypes SendInput 마우스 휠 (Windows) ----
_INPUT_MOUSE = 0
_MOUSEEVENTF_WHEEL = 0x0800
_WHEEL_DELTA = 120

# dwExtraInfo는 포인터 크기 정수(ULONG_PTR)여야 한다.
if ctypes.sizeof(ctypes.c_void_p) == 8:
    _ULONG_PTR = ctypes.c_uint64
else:
    _ULONG_PTR = ctypes.c_uint32


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", _ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD),
                ("u", _INPUTUNION)]


def _sendinput_wheel_once(delta: int):
    """SendInput으로 휠 이벤트 1개를 전송. delta>0 위로, <0 아래로."""
    mi = _MOUSEINPUT(0, 0, delta & 0xFFFFFFFF, _MOUSEEVENTF_WHEEL, 0, 0)
    inp = _INPUT(_INPUT_MOUSE, _INPUTUNION(mi=mi))
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def sendinput_scroll(clicks: int):
    """SendInput으로 휠을 clicks 틱 굴린다(부호 규약은 다른 백엔드와 동일: >0 위, <0 아래).
    실제 마우스처럼 틱당 WHEEL_DELTA(±120) 이벤트를 나눠 보낸다."""
    clicks = int(clicks)
    if clicks == 0:
        return
    step = _WHEEL_DELTA if clicks > 0 else -_WHEEL_DELTA  # 아래(-)는 delta = -120*틱수
    for _ in range(abs(clicks)):
        _sendinput_wheel_once(step)
        time.sleep(0.02)


def _click(x: int, y: int):
    x, y = int(x), int(y)
    pydirectinput.moveTo(x, y)
    time.sleep(0.2)
    pydirectinput.click()


class ReplayController:
    def __init__(self, config: dict):
        self.cfg = config["replay_list"]
        sc = config.get("scroll", {}) or {}
        self.scroll_method = sc.get("scroll_method", "auto")
        self.list_area = sc.get("list_area", {"x": 1130, "y": 650})

    def click_row(self, x: int, y: int):
        """리플레이 목록에서 (x, y) 위치의 행을 클릭해 선택한다."""
        print(f"[조작] 행 클릭 ({int(x)}, {int(y)})")
        _click(x, y)

    def click_view(self):
        """'보기(재생)' 버튼을 클릭해 재생에 진입한다."""
        btn = self.cfg["view_button"]
        print(f"[조작] '보기' 클릭 ({btn['x']}, {btn['y']})")
        _click(btn["x"], btn["y"])

    def select_and_play(self, x: int, y: int):
        """행 선택 후 재생 진입."""
        self.click_row(x, y)
        time.sleep(0.5)
        self.click_view()

    def _tap_key(self, fkey: str, quiet: bool = False):
        """keyDown → 짧은 유지 → keyUp 방식으로 F키를 명시적으로 입력한다.

        리플레이 로딩 직후에는 짧은 press()가 씹히는 경우가 있어
        keyDown/keyUp을 분리하고 사이에 유지 시간을 둔다.

        quiet=True면 로그를 남기지 않는다(녹화 루프의 반복 입력용 — 매번
        찍으면 시끄럽다).
        """
        if not quiet:
            ts = time.strftime("%H:%M:%S")
            print(f"[조작] 선수 시점 전환: {fkey.upper()} (입력 {ts})")
        pydirectinput.keyDown(fkey)
        time.sleep(0.05)
        pydirectinput.keyUp(fkey)

    def set_pov(self, fkey: str):
        """관전 시점을 특정 선수로 고정한다 (F1~F5 / F7~F11). F키를 1회 입력한다.

        준비 시간이 있는 리플레이는 이 1회 입력 시점에 선수가 아직 영웅을 안
        골라 시점이 안 잡힐 수 있다. 이후 시점 유지는 녹화 루프(wait_for_end)에서
        같은 F키를 주기적으로 반복 입력해 처리한다.
        """
        self._tap_key(fkey)

    def _try_scroll(self, method: str, clicks: int):
        """단일 방식으로 휠 입력. 사용 불가/실패 시 예외를 던진다."""
        if method == "sendinput":
            sendinput_scroll(clicks)
        elif method == "pydirectinput":
            if not hasattr(pydirectinput, "scroll"):
                raise RuntimeError("pydirectinput.scroll 미지원(설치 버전)")
            pydirectinput.scroll(clicks)
        elif method == "pyautogui":
            import pyautogui
            pyautogui.scroll(clicks)
        else:
            raise ValueError(f"알 수 없는 scroll_method: {method}")

    def _do_scroll(self, clicks: int):
        """설정된 방식으로 마우스 휠을 굴린다. clicks>0 위로, <0 아래로.
        실제로 사용된 방식 문자열을 반환한다.

        auto 순서: sendinput → pydirectinput → pyautogui (앞선 방식이 예외 없이
        전송되면 그것을 사용). 게임이 특정 방식을 '무시'하는 경우는 예외가 아니라
        화면 무변화로 나타나므로, 탐색 알고리즘 쪽에서 경고로 안내한다.
        """
        order = {
            "auto": ["sendinput", "pydirectinput", "pyautogui"],
            "sendinput": ["sendinput"],
            "pydirectinput": ["pydirectinput"],
            "pyautogui": ["pyautogui"],
        }.get(self.scroll_method, ["sendinput", "pydirectinput", "pyautogui"])

        last_err = None
        for m in order:
            try:
                self._try_scroll(m, clicks)
                return m
            except Exception as e:
                last_err = e
                if self.scroll_method != "auto":
                    raise
                print(f"[스크롤] {m} 실패({e}) → 다음 방식 시도")
        if last_err:
            raise last_err

    def scroll_list(self, ticks: int):
        """목록 중앙(list_area)에 마우스를 두고 휠을 ticks만큼 굴린다.
        ticks>0이면 위로(맨 위 리셋), <0이면 아래로 스크롤. 사용된 방식을 반환."""
        la = self.list_area
        pydirectinput.moveTo(int(la["x"]), int(la["y"]))
        time.sleep(0.05)
        return self._do_scroll(int(ticks))

    def back_to_lobby(self):
        """리플레이(종료 화면 포함)에서 ESC로 목록(로비)로 복귀한다."""
        print("[조작] ESC — 목록으로 복귀")
        pydirectinput.press("esc")
        time.sleep(1.0)

    # ---- 폴백: 고정 좌표 방식 (use_ocr: false) ----
    def fallback_row(self, index: int):
        """OCR 미사용 시, 설정된 고정 좌표의 index번째 행을 반환 (x, y)."""
        rows = self.cfg.get("fallback_rows", [])
        if index < 0 or index >= len(rows):
            return None
        r = rows[index]
        return (r["x"], r["y"])
