"""OCR 테스트 도구 (게임 없이 검증용).

리플레이 목록 스크린샷 이미지 경로를 인자로 받아, 인식된 코드와 각 배지의 좌표를 출력한다.

사용법:
  python test_ocr.py tests/lobby.jpg
  python test_ocr.py tests/lobby.jpg R19FV7 CWR5WC TYZY7S G68XMC   # 기대 코드 지정 시 채점

config.yaml의 ocr 설정을 그대로 사용한다.
"""

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import cv2
import yaml

from ocr_locator import CodeLocator


def main():
    if len(sys.argv) < 2:
        print("사용법: python test_ocr.py <이미지경로> [기대코드1 기대코드2 ...]")
        sys.exit(1)

    image_path = sys.argv[1]
    expected = [c.strip().upper() for c in sys.argv[2:]]

    image = cv2.imread(image_path)
    if image is None:
        print(f"[오류] 이미지를 읽을 수 없습니다: {image_path}")
        sys.exit(1)

    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    row_click_x = cfg["replay_list"].get("row_click_x", 600)
    locator = CodeLocator(cfg)
    print(f"\n이미지: {image_path}  (크기 {image.shape[1]}x{image.shape[0]})")
    results = locator.detect_and_read(image)

    print(f"\n인식된 코드(원문) {len(results)}개:")
    for code, cx, cy in results:
        print(f"  {code}   배지중심=({cx}, {cy})")

    if expected:
        # 채점은 실제 실행과 동일한 경로(find_row: 혼동 문자 canon + 편집거리)로 한다.
        # OCR 원문에 I↔1, Z↔2, S↔5, O↔0 같은 혼동이 있어도 실제로는 이 매칭으로
        # 올바른 행을 찾으므로, 이 기준이 실동작을 그대로 반영한다.
        ok, miss = [], []
        for code in expected:
            hit = locator.find_row(image, code, row_click_x)
            if hit is not None:
                ok.append(code)
                print(f"  [매칭] {code} → 행 y={hit[1]}")
            else:
                miss.append(code)
        print(f"\n채점: {len(ok)}/{len(expected)} 인식(실행과 동일한 매칭 기준)")
        if miss:
            print(f"  누락: {', '.join(miss)}")
            sys.exit(2)
        print("  모두 인식되었습니다. ✅")


if __name__ == "__main__":
    main()
