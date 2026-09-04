"""휠 스크롤 진단 도구 (게임에서 실행).

리플레이 목록 화면을 띄운 상태에서 실행하면, 5초 후 목록 중앙(list_area)으로
마우스를 옮기고 각 휠 입력 방식(sendinput / pydirectinput / pyautogui)으로
'휠 다운 N틱'을 3회씩 시도한다. 매 시도 전후로 목록 영역(ocr.roi)의 평균 픽셀
차이를 출력하므로, 어떤 방식이 실제로 목록을 스크롤하는지 눈으로/수치로 확인할 수 있다.

사용법:
  python test_scroll.py            # 3가지 방식 모두 순서대로 시도
  python test_scroll.py sendinput  # 특정 방식만 시도

동작하는 방식을 찾으면 config.yaml의 scroll.scroll_method에 그 값을 넣으세요.
탐색 알고리즘·녹화 파이프라인은 건드리지 않는 독립 도구입니다.
"""
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import cv2
import numpy as np
import yaml

from screen_detector import ScreenDetector
from replay_controller import ReplayController

ALL_METHODS = ["sendinput", "pydirectinput", "pyautogui"]


def roi_gray(detector, roi):
    """현재 화면을 캡처해 목록 영역(roi)만 회색조로 잘라 반환."""
    frame = detector.grab_color()
    crop = frame[roi["y0"]:roi["y1"], roi["x0"]:roi["x1"]]
    return cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)


def pixel_diff(a, b):
    if a.shape != b.shape:
        return 999.0
    return float(np.mean(cv2.absdiff(a, b)))


def main():
    methods = [m for m in sys.argv[1:] if m in ALL_METHODS] or ALL_METHODS

    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    sc = cfg.get("scroll", {}) or {}
    roi = cfg["ocr"]["roi"]
    ticks = int(sc.get("scroll_ticks_per_step", 3))
    wait = float(sc.get("scroll_wait", 0.5))
    thr = float(sc.get("end_diff_threshold", 2.0))
    la = sc.get("list_area", {"x": 1130, "y": 650})

    detector = ScreenDetector(cfg)
    controller = ReplayController(cfg)

    print("=" * 56)
    print(" 휠 스크롤 진단 도구")
    print("=" * 56)
    print(f"목록 중앙(list_area): ({la['x']}, {la['y']})   틱/스텝: {ticks}   대기: {wait}s")
    print(f"픽셀차 임계값(변화 판정): {thr}  (이 값보다 크면 '스크롤됨'으로 봄)")
    print(f"시도할 방식: {', '.join(methods)}")
    print("\n리플레이 목록 화면을 띄우고 창을 활성화하세요. 5초 후 시작합니다...")
    for r in range(5, 0, -1):
        print(f"  {r}...")
        time.sleep(1.0)

    summary = {}
    for method in methods:
        controller.scroll_method = method
        print(f"\n----- 방식: {method} -----")
        changed_any = False
        for i in range(1, 4):
            before = roi_gray(detector, roi)
            try:
                used = controller.scroll_list(-ticks)  # 아래로 스크롤
            except Exception as e:
                print(f"  [{i}/3] {method} 사용 불가/실패: {e}")
                break
            time.sleep(wait)
            after = roi_gray(detector, roi)
            diff = pixel_diff(before, after)
            moved = diff > thr
            changed_any = changed_any or moved
            mark = "변화 있음 ✅" if moved else "변화 없음 ✗"
            print(f"  [{i}/3] 휠 다운 {ticks}틱(실제 {used}) → 픽셀차 {diff:.2f}  {mark}")
        summary[method] = changed_any

    print("\n" + "=" * 56)
    print(" 결과 요약")
    print("=" * 56)
    working = [m for m, ok in summary.items() if ok]
    for m in methods:
        if m in summary:
            print(f"  {m:14s}: {'동작함 ✅' if summary[m] else '동작 안 함 ✗'}")
    if working:
        print(f"\n→ 동작하는 방식: {', '.join(working)}")
        print(f"   config.yaml의 scroll.scroll_method 를 '{working[0]}'로 고정하는 것을 권장합니다.")
    else:
        print("\n→ 어떤 방식도 목록을 움직이지 못했습니다.")
        print("   창모드(테두리 없음) 여부, 관리자 권한 실행, list_area 좌표(목록 위인지)를 확인하세요.")


if __name__ == "__main__":
    main()
