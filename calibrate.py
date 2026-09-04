"""좌표 보정 도구: 마우스를 원하는 위치에 올리면 좌표를 실시간 출력.

사용법: python calibrate.py 실행 후 게임 화면에서 리플레이 목록 각 행,
재생 버튼, 나가기 버튼 위에 마우스를 올려 좌표를 확인하고
config.yaml의 replay_list 항목에 기입한다. Ctrl+C로 종료.
"""
import sys
import time
import pyautogui

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    while True:
        x, y = pyautogui.position()
        print(f"\r마우스 좌표: x={x:5d}, y={y:5d}   ", end="", flush=True)
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\n종료")
