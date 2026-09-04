"""템플릿 이미지 캡처 도구.

사용법:
  1. 오버워치에서 캡처할 화면(리플레이 메뉴/재생 중/종료 화면)을 띄운다
  2. python capture_template.py replay_playing
  3. 5초 안에 게임 화면으로 전환 → 전체 화면이 templates/_full_<이름>.png 로 저장됨
  4. 저장된 이미지를 그림판 등으로 열어, 해당 화면에서만 나타나는
     '고유하고 변하지 않는 영역'(예: 재생 컨트롤 바의 아이콘)을 잘라내
     templates/<이름>.png 로 저장한다

팁: 템플릿은 작을수록 빠르고, 고유할수록 오탐이 적다. 100~300px 정도의
    UI 요소가 적당하다. 플레이어 이름/시간 등 매번 바뀌는 부분은 제외.
"""
import os
import sys
import time
import mss
import mss.tools

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

name = sys.argv[1] if len(sys.argv) > 1 else "template"
os.makedirs("templates", exist_ok=True)
print(f"5초 후 화면 캡처: {name} — 게임 화면으로 전환하세요")
time.sleep(5)

with mss.mss() as sct:
    mon = sct.monitors[1]
    img = sct.grab(mon)
    out = f"templates/_full_{name}.png"
    mss.tools.to_png(img.rgb, img.size, output=out)
print(f"저장됨: {out} — 고유 영역을 잘라 templates/{name}.png 로 저장하세요")
