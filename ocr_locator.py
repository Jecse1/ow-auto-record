"""리플레이 코드 배지 검출 + OCR 모듈.

리플레이 목록 화면에서 주황색 배지(6자리 코드)를 찾아 코드와 클릭 좌표를 얻는다.

인식 파이프라인:
  1) 배지 열 ROI에서 easyocr 텍스트 검출기로 각 배지의 '타이트한' 위치 박스를 얻는다
     (HSV 색상 필터는 보조/폴백으로 사용).
  2) 각 박스를 CLAHE로 대비를 높여 easyocr(1순위)로 읽고,
     Tesseract(2순위, 있으면)로 숫자 혼동(5→S, 0→O 등)을 보정한다.
  3) 대상 코드를 찾을 때는 혼동 문자(1↔I, 5↔S 등)를 감안한 거리로 매칭한다.

easyocr는 필수, Tesseract는 선택(정확도 보강). 둘 다 대문자+숫자 화이트리스트를 적용.
"""

import os
import re
from collections import Counter, defaultdict

import cv2
import numpy as np

ALLOW = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CODE_RE = re.compile(r"^[A-Z0-9]{6}$")

# easyocr가 흔히 '숫자'를 '비슷한 글자'로 잘못 읽는 쌍. Tesseract가 숫자로 읽으면 보정한다.
LETTER_TO_DIGIT = {"S": "5", "O": "0", "I": "1", "Z": "2", "B": "8", "G": "6", "T": "7"}
# 대상 코드 매칭 시 서로 같은 것으로 취급할 혼동 문자 그룹 → 대표 문자로 정규화
CONFUSION_CANON = {
    "I": "1", "1": "1", "L": "1",
    "O": "0", "0": "0", "Q": "0",
    "S": "5", "5": "5",
    "Z": "2", "2": "2",
    "B": "8", "8": "8",
    "G": "6", "6": "6",
    "T": "7", "7": "7",
}


def canon(code: str) -> str:
    """혼동 문자를 대표 문자로 바꾼 정규형(대상 코드 매칭용)."""
    return "".join(CONFUSION_CANON.get(c, c) for c in code.upper())


class CodeLocator:
    def __init__(self, config: dict):
        oc = config["ocr"]
        self.roi = oc["roi"]
        self.badge_hsv = oc["badge_hsv"]
        self.detect_scale = oc.get("detect_scale", 2.0)
        self.clahe = cv2.createCLAHE(clipLimit=oc.get("clahe_clip", 2.0), tileGridSize=(8, 8))
        self.easyocr_heights = oc.get("easyocr_heights", [64, 96])
        self.match_max_distance = oc.get("match_max_distance", 1)
        # 스크롤 경계에서 상하로 잘린 배지(높이가 정상보다 작음) 제외 기준 비율
        self.min_badge_height_ratio = oc.get("min_badge_height_ratio", 0.6)
        # 스크롤 탐색 설정 (config["scroll"]). 없으면 기본값.
        self.scroll = config.get("scroll", {}) or {}

        tcfg = oc.get("tesseract", {}) or {}
        self.tess_enabled = tcfg.get("enabled", True)
        self.tess_configs = tcfg.get("configs", [[128, 2.0], [64, 4.0]])
        self._tess = None
        self._tess_wl = "-c tessedit_char_whitelist=" + ALLOW
        if self.tess_enabled:
            self._init_tesseract(tcfg.get("cmd", ""))

        self._reader = None  # easyocr는 초기화가 느려 지연 로딩

    # ---- 엔진 초기화 ----
    def _init_tesseract(self, cmd):
        try:
            import pytesseract
            # 배포 PC에 Tesseract가 없을 수 있다(선택 사항). 지정된 경로에 실행 파일이
            # 없으면 조용히 easyocr만 사용한다(PATH 탐색/오류 없이 폴백).
            if cmd and not os.path.exists(cmd):
                self._tess = None
                print("[OCR] Tesseract 미설치(선택 사항). easyocr만 사용합니다.")
                return
            if cmd:
                pytesseract.pytesseract.tesseract_cmd = cmd
            # 동작 확인
            pytesseract.get_tesseract_version()
            self._tess = pytesseract
            print("[OCR] Tesseract 사용 가능 (숫자 인식 보정 활성화)")
        except Exception as e:
            self._tess = None
            print(f"[OCR] Tesseract 비활성화({e}). easyocr만 사용합니다.")

    @property
    def reader(self):
        if self._reader is None:
            import easyocr
            print("[OCR] easyocr 초기화 중... (최초 실행 시 모델 로딩으로 수십 초 걸릴 수 있음)")
            self._reader = easyocr.Reader(["en"], gpu=False)
        return self._reader

    # ---- 전처리 ----
    def _prep(self, gray, height, clip=None):
        h, w = gray.shape
        g = cv2.resize(gray, (max(1, int(w * height / h)), height), interpolation=cv2.INTER_CUBIC)
        cl = self.clahe if clip is None else cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
        g = cl.apply(g)
        return cv2.copyMakeBorder(g, 18, 18, 24, 24, cv2.BORDER_REPLICATE)

    @staticmethod
    def _posvote(strings):
        strings = [s for s in strings if CODE_RE.match(s)]
        if not strings:
            return None
        cols = defaultdict(Counter)
        for s in strings:
            for i, c in enumerate(s):
                cols[i][c] += 1
        return "".join(cols[i].most_common(1)[0][0] for i in range(6))

    def _easyocr_read(self, gray):
        outs = []
        for h in self.easyocr_heights:
            res = self.reader.readtext(self._prep(gray, h), allowlist=ALLOW,
                                       contrast_ths=0.05, adjust_contrast=0.7)
            outs.append("".join(x[1] for x in res).replace(" ", "").upper())
        return self._posvote(outs)

    def _tess_read(self, gray):
        if self._tess is None:
            return None
        outs = []
        for h, clip in self.tess_configs:
            img = self._prep(gray, h, clip)
            raw = self._tess.image_to_string(img, config=f"--oem 3 --psm 7 {self._tess_wl}")
            outs.append(raw.strip().replace(" ", "").replace("\n", "").upper())
        return self._posvote(outs)

    def _recognize(self, crop_bgr):
        """배지 crop(BGR) → 6자리 코드 문자열 또는 None."""
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        e = self._easyocr_read(gray)
        t = self._tess_read(gray)
        if e is None:
            return t
        # 숫자 보정: easyocr가 혼동 글자로 읽고 Tesseract가 짝 숫자로 읽으면 숫자로 교체
        if t and len(t) == len(e) == 6:
            e = "".join(
                LETTER_TO_DIGIT[e[i]] if (e[i] in LETTER_TO_DIGIT and t[i] == LETTER_TO_DIGIT[e[i]]) else e[i]
                for i in range(6)
            )
        return e

    # ---- 배지 위치 검출 ----
    def _detect_boxes(self, image_bgr):
        """ROI에서 배지(코드 텍스트) 박스들을 (x0,y0,x1,y1)로 반환."""
        r = self.roi
        roi = image_bgr[r["y0"]:r["y1"], r["x0"]:r["x1"]]
        f = self.detect_scale
        up = cv2.resize(roi, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
        boxes = []
        for bbox, text, conf in self.reader.readtext(up, allowlist=ALLOW):
            if len(text.replace(" ", "")) < 4:
                continue
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            boxes.append((
                int(min(xs) / f) + r["x0"], int(min(ys) / f) + r["y0"],
                int(max(xs) / f) + r["x0"], int(max(ys) / f) + r["y0"],
            ))
        if not boxes:
            boxes = self._detect_boxes_hsv(image_bgr)
        boxes.sort(key=lambda b: b[1])
        return boxes

    def _detect_boxes_hsv(self, image_bgr):
        """폴백: HSV 주황색 필터로 배지 영역 박스를 찾는다."""
        r = self.roi
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        lower = np.array(self.badge_hsv["lower"])
        upper = np.array(self.badge_hsv["upper"])
        mask = cv2.inRange(hsv, lower, upper)
        col = np.zeros_like(mask)
        col[r["y0"]:r["y1"], r["x0"]:r["x1"]] = 255
        mask = cv2.bitwise_and(mask, col)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                                cv2.getStructuringElement(cv2.MORPH_RECT, (40, 5)))
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if w >= 60 and 14 <= h <= 46:
                boxes.append((x, y, x + w, y + h))
        return boxes

    @staticmethod
    def _drop_clipped(boxes, ratio):
        """상하로 잘린 배지(높이가 화면 내 중앙값 대비 ratio 미만)를 제거한다.
        스크롤 경계에서 부분적으로 보이는 행을 인식 대상에서 빼기 위한 것."""
        if len(boxes) < 2:
            return boxes
        heights = sorted(b[3] - b[1] for b in boxes)
        med = heights[len(heights) // 2]
        if med <= 0:
            return boxes
        return [b for b in boxes if (b[3] - b[1]) >= ratio * med]

    # ---- 공개 API ----
    def detect_and_read(self, image_bgr, drop_clipped=False):
        """리플레이 목록 이미지에서 (code, cx, cy) 리스트를 반환.
        cx, cy는 배지 중심 좌표(디버깅/표시용).
        drop_clipped=True면 상하로 잘린 배지를 인식 대상에서 제외한다(스크롤 탐색용)."""
        boxes = self._detect_boxes(image_bgr)
        if drop_clipped:
            boxes = self._drop_clipped(boxes, self.min_badge_height_ratio)
        results = []
        for x0, y0, x1, y1 in boxes:
            pad = 4
            crop = image_bgr[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
            if crop.size == 0:
                continue
            code = self._recognize(crop)
            if code and CODE_RE.match(code):
                results.append((code, (x0 + x1) // 2, (y0 + y1) // 2))
        return results

    def find_row(self, image_bgr, target_code, row_click_x, drop_clipped=False):
        """대상 코드가 있는 행의 클릭 좌표 (row_click_x, badge_y)를 반환. 없으면 None.
        혼동 문자를 감안해 매칭한다."""
        target_c = canon(target_code)
        best = None
        best_dist = 99
        for code, cx, cy in self.detect_and_read(image_bgr, drop_clipped=drop_clipped):
            d = _distance(canon(code), target_c)
            if d < best_dist:
                best_dist, best = d, (code, cx, cy)
        if best is None or best_dist > self.match_max_distance:
            return None
        return (row_click_x, best[2])

    # ---- 스크롤 탐색 ----
    def _roi_gray(self, image_bgr):
        r = self.roi
        crop = image_bgr[r["y0"]:r["y1"], r["x0"]:r["x1"]]
        return cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    def list_changed(self, frame_a, frame_b, threshold):
        """두 프레임의 목록 영역(roi) 평균 픽셀 차이가 threshold를 넘으면 True(변화 있음).
        스크롤이 더 이상 되지 않으면(끝 도달) 차이가 거의 0이 되어 False를 반환한다."""
        ga, gb = self._roi_gray(frame_a), self._roi_gray(frame_b)
        if ga.shape != gb.shape:
            return True
        return float(np.mean(cv2.absdiff(ga, gb))) > threshold

    def find_row_scrolling(self, target_code, row_click_x, grab_fn, scroll_fn,
                           wait_fn=None, log=None, stopped_fn=None):
        """목록을 위→아래로 스크롤하며 대상 코드 행을 탐색한다.

        grab_fn()      : 현재 화면(BGR)을 반환하는 콜백
        scroll_fn(n)   : 휠 n틱 스크롤(n>0 위로, n<0 아래로) 콜백
        wait_fn()      : 스크롤 후 대기 콜백(중단 가능하면 True 반환 시 중단)
        log(msg)       : 진행 로그 콜백
        stopped_fn()   : 중단 여부 콜백

        찾으면 (row_click_x, badge_y), 못 찾으면 None, 중단되면 "__stopped__" 반환.
        """
        sc = self.scroll
        reset_ticks = int(sc.get("scroll_reset_ticks", 10))
        step_ticks = int(sc.get("scroll_ticks_per_step", 3))
        max_steps = int(sc.get("scroll_max_steps", 30))
        thr = float(sc.get("end_diff_threshold", 2.0))
        log = log or (lambda m: None)
        stopped = stopped_fn or (lambda: False)

        def _wait():
            if wait_fn:
                return bool(wait_fn())
            return False

        # 1) 맨 위로 리셋
        if reset_ticks > 0:
            scroll_fn(reset_ticks)
            if _wait() or stopped():
                return "__stopped__"

        frame = grab_fn()
        no_change = 0  # 연속 무변화 횟수
        for step in range(1, max_steps + 1):
            if stopped():
                return "__stopped__"
            log(f"스크롤 탐색 중 ({step}/{max_steps})...")
            hit = self.find_row(frame, target_code, row_click_x, drop_clipped=True)
            if hit is not None:
                return hit
            if step == max_steps:
                break
            # 2) 아래로 한 스텝 스크롤 후 재확인
            scroll_fn(-step_ticks)
            if _wait() or stopped():
                return "__stopped__"
            nxt = grab_fn()
            if self.list_changed(frame, nxt, thr):
                no_change = 0
                frame = nxt
                continue
            # 무변화: 첫 스텝이면 휠 미전달 의심, 이후면 스크롤 끝일 수 있음.
            no_change += 1
            if step == 1:
                log("[경고] 휠 입력이 게임에 전달되지 않는 것 같습니다. "
                    "scroll_method를 바꿔보세요(test_scroll.py로 확인).")
            # 끝 판정은 연속 2회 무변화일 때만 확정(1회 무변화는 한 번 더 시도).
            if no_change >= 2:
                break
        return None


def _distance(a: str, b: str) -> int:
    """길이가 같으면 해밍거리, 다르면 레벤슈타인 거리."""
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y)
    # 간단한 레벤슈타인
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            cur = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (a[i - 1] != b[j - 1]))
            prev = cur
    return dp[n]
