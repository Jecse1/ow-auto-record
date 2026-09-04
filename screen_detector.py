"""화면 인식 모듈: mss로 화면 캡처 후 OpenCV 템플릿 매칭으로 상태 판정."""
import os

import cv2
import numpy as np
import mss


def score_template(screen_gray: np.ndarray, tpl_gray: np.ndarray) -> float:
    """회색조 화면에서 템플릿의 최고 매칭 점수(0~1)를 반환. 매칭 불가 시 -1.0."""
    if tpl_gray is None:
        return -1.0
    if screen_gray.shape[0] < tpl_gray.shape[0] or screen_gray.shape[1] < tpl_gray.shape[1]:
        return -1.0
    res = cv2.matchTemplate(screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(res)
    return float(max_val)


class ScreenDetector:
    def __init__(self, config: dict):
        self.threshold = config["detection"]["match_threshold"]
        self.monitor_idx = config["detection"]["monitor"]
        self.templates = {}
        for name, path in config["templates"].items():
            # 파일이 없으면 OpenCV의 지저분한 C++ 경고 대신 명확한 한국어 안내만 출력한다.
            if not os.path.exists(path):
                print(f"[경고] 템플릿 파일 없음: {path}")
                print(f"        '{name}' 감지가 비활성화됩니다. capture_template.py로 캡처해 저장하세요.")
                self.templates[name] = None
                continue
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                print(f"[경고] 템플릿 읽기 실패(형식 확인): {path} — '{name}' 감지 비활성화")
            self.templates[name] = img

    def grab_color(self) -> np.ndarray:
        """현재 화면을 BGR로 캡처해 반환 (OCR 등 색상 처리용)."""
        with mss.mss() as sct:
            mon = sct.monitors[self.monitor_idx]
            raw = np.array(sct.grab(mon))
        return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)

    def _grab(self) -> np.ndarray:
        with mss.mss() as sct:
            mon = sct.monitors[self.monitor_idx]
            raw = np.array(sct.grab(mon))
        return cv2.cvtColor(raw, cv2.COLOR_BGRA2GRAY)

    def match(self, name: str) -> bool:
        """지정한 템플릿이 현재 화면에 있으면 True."""
        return self.match_score(name) >= self.threshold

    def match_score(self, name: str) -> float:
        """디버깅용: 현재 화면에서의 매칭 점수(0~1) 반환. 템플릿 없으면 -1.0."""
        tpl = self.templates.get(name)
        if tpl is None:
            return -1.0
        return score_template(self._grab(), tpl)

    def score_in_image(self, name: str, image_bgr: np.ndarray) -> float:
        """주어진 BGR 이미지(파일 등)에서의 매칭 점수. 게임 없이 테스트/검증용."""
        tpl = self.templates.get(name)
        if tpl is None:
            return -1.0
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        return score_template(gray, tpl)
