"""오버워치 리플레이 자동 녹화 - 메인 루프 (v0.3).

세션(코드 + 선수들) 목록을 받아 선수 시점별로 리플레이를 재생·녹화한다.

이 모듈은 두 가지 방식으로 쓸 수 있다.
  1) 콘솔 실행:  python main.py   (run.bat) — 기존과 동일하게 동작
  2) 함수 재사용: run_sessions(sessions, cfg, ctx) — GUI(gui.py) 등에서 호출.
     ctx(RunContext)로 로그/진행상황 콜백과 중단(stop) 신호를 전달한다.

녹화 파이프라인 로직(OCR·감지·OBS 제어)은 v0.2와 동일하며, 로그/진행 보고와
중단 처리를 위해 호출 구조만 정리했다.

실행 전 체크리스트:
  - OBS 실행 + WebSocket 서버 켜짐 + 게임 캡처 소스/녹화 출력 설정 완료
  - 오버워치: 경력 > 리플레이 목록 화면을 열어둔 상태 (창모드 권장)
  - templates/ 템플릿, config.yaml 좌표 보정, sessions.yaml 준비
"""
import sys
import time
import threading
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import yaml

import sessions as sess_mod
from screen_detector import ScreenDetector
from obs_client import ObsRecorder
from replay_controller import ReplayController
from ocr_locator import CodeLocator


def load_config(path="config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class RunContext:
    """녹화 파이프라인과 호출자(콘솔/GUI) 사이의 로그·진행·중단 통로.

    log      : 한 줄 로그 콜백 (기본: print)
    progress : 구조화된 진행 이벤트 콜백  progress(dict)  (기본: 없음)
    stop_event : 중단 신호 (threading.Event). set()되면 파이프라인이 안전 종료.
    """

    def __init__(self, log=None, progress=None, stop_event=None):
        self._log = log or (lambda m: print(m))
        self._progress = progress
        self.stop_event = stop_event or threading.Event()

    def log(self, msg=""):
        try:
            self._log(str(msg))
        except Exception:
            pass

    def emit(self, etype, **kw):
        if self._progress:
            ev = {"type": etype}
            ev.update(kw)
            try:
                self._progress(ev)
            except Exception:
                pass

    def stopped(self) -> bool:
        return self.stop_event.is_set()

    def sleep(self, seconds) -> bool:
        """중단 가능한 sleep. 중단되면 즉시 True 반환."""
        end = time.time() + seconds
        while time.time() < end:
            if self.stopped():
                return True
            time.sleep(min(0.1, max(0.0, end - time.time())))
        return self.stopped()


def safe_stop(recorder, ctx=None):
    """어떤 상황에서도 녹화 정지를 시도하되, 실패해도 예외를 밖으로 던지지 않는다."""
    log = ctx.log if ctx else print
    try:
        recorder.stop()
    except Exception as e:
        log(f"[경고] 녹화 정지 시도 중 오류(무시하고 진행): {e}")


def wait_for(detector, name, timeout, interval, invert=False, ctx=None) -> bool:
    """템플릿이 나타날 때(invert=True면 사라질 때)까지 대기. 성공 시 True.
    ctx가 중단되면 False."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ctx and ctx.stopped():
            return False
        if detector.match(name) != invert:
            return True
        if ctx:
            if ctx.sleep(interval):
                return False
        else:
            time.sleep(interval)
    return False


def wait_for_end(detector, interval, max_duration, ctx=None, si=None, pi=None) -> str:
    """리플레이 종료를 판정하고 사유를 반환.
    1순위: replay_ended 템플릿, 안전장치: max_duration."""
    start = time.time()
    deadline = start + max_duration
    while time.time() < deadline:
        if ctx and ctx.stopped():
            return "중단됨"
        if detector.match("replay_ended"):
            return "종료 화면(replay_ended) 감지"
        if ctx:
            ctx.emit("recording", si=si, pi=pi, elapsed=int(time.time() - start))
            if ctx.sleep(interval):
                return "중단됨"
        else:
            time.sleep(interval)
    return f"최대 녹화 시간({max_duration:.0f}초) 초과 — 강제 정지"


def locate_code_scrolling(detector, locator, controller, ctx, code, row_click_x, cfg):
    """목록을 맨 위로 리셋한 뒤 아래로 스크롤하며 대상 코드 행을 탐색한다.
    찾으면 클릭 좌표 (row_click_x, badge_y), 못 찾거나 중단되면 None."""
    scroll_wait = cfg.get("scroll", {}).get("scroll_wait", 0.5)

    def grab_fn():
        return detector.grab_color()

    def scroll_fn(ticks):
        controller.scroll_list(ticks)

    def wait_fn():
        return ctx.sleep(scroll_wait)  # 중단되면 True

    def log_fn(msg):
        ctx.log(f"[스크롤] {msg}")
        ctx.emit("locating", text=msg)

    hit = locator.find_row_scrolling(
        code, row_click_x, grab_fn, scroll_fn,
        wait_fn=wait_fn, log=log_fn, stopped_fn=ctx.stopped)
    if hit == "__stopped__":
        return None
    return hit


def record_player(cfg, detector, recorder, controller, click_xy, code, player, ctx, si, pi):
    """한 선수 시점을 녹화한다. (성공여부, 사유)를 반환."""
    rc = cfg["recording"]
    interval = cfg["detection"]["poll_interval"]
    fkey = sess_mod.fkey_for(player)

    ctx.log(f"\n----- {code} / {player}({fkey.upper()}) 녹화 -----")
    ctx.emit("step", si=si, pi=pi, text="행 선택·재생 진입")
    controller.select_and_play(*click_xy)

    # '보기' 클릭 시 리플레이는 항상 자동 재생된다. 재생 여부를 감지하지 않고
    # load_wait 만큼 고정 대기해 로딩+진입을 기다린다. (중단 가능)
    load_wait = rc.get("load_wait", 3.0)
    ctx.emit("step", si=si, pi=pi, text=f"재생 로딩 대기 {load_wait:.0f}초")
    if ctx.sleep(load_wait):
        return False, "중단됨"

    # 선수 시점 고정 후 녹화 시작
    ctx.emit("step", si=si, pi=pi, text=f"시점 전환 {fkey.upper()}")
    controller.set_pov(fkey, retries=rc.get("pov_retry", 0),
                       retry_delay=rc.get("pov_retry_delay", 1.5))
    ctx.sleep(max(0.0, rc["start_delay"]))
    recorder.start()
    ctx.emit("step", si=si, pi=pi, text="녹화 중")

    # 종료 판정
    reason = wait_for_end(detector, interval, rc["max_duration"], ctx=ctx, si=si, pi=pi)
    ctx.log(f"[감지] {reason}")

    # 녹화 정지 + 파일명 태깅
    ctx.emit("step", si=si, pi=pi, text="녹화 정지")
    ctx.sleep(rc["stop_delay"])
    when = datetime.now().strftime("%Y%m%d_%H%M")
    try:
        recorder.stop_and_tag(code, player, when)
    except Exception as e:
        ctx.log(f"[오류] 녹화 정지/태깅 실패: {e}")
        safe_stop(recorder, ctx)

    # 로비 복귀
    ctx.emit("step", si=si, pi=pi, text="로비 복귀")
    controller.back_to_lobby()
    if not wait_for(detector, "replay_menu", rc["lobby_return_timeout"], interval, ctx=ctx):
        if not ctx.stopped():
            ctx.log("[경고] 로비(목록) 복귀를 확인하지 못했습니다. 계속 진행합니다.")

    if ctx.stopped():
        return True, "중단됨"
    return True, "완료"


def run_sessions(sessions, cfg=None, ctx=None) -> dict:
    """세션 목록을 받아 전체 녹화를 수행한다. 결과 요약 dict를 반환.
    반환: {ok, fail, failures:[(code,player,reason)], aborted, obs_error, invalid, total}"""
    if cfg is None:
        cfg = load_config()
    if ctx is None:
        ctx = RunContext()

    result = {"ok": 0, "fail": 0, "failures": [], "aborted": False,
              "obs_error": None, "invalid": None, "total": 0}

    # 세션 검증
    errs = sess_mod.validate_all(sessions)
    if errs:
        result["invalid"] = errs
        ctx.log("[오류] 세션 검증 실패:")
        for e in errs:
            ctx.log(f"   - {e}")
        ctx.emit("error", message="세션 검증 실패:\n" + "\n".join(errs))
        return result

    total = sum(len(s["players"]) for s in sessions)
    result["total"] = total
    ctx.log("=" * 52)
    ctx.log(" 오버워치 리플레이 자동 녹화 (v0.3)")
    ctx.log("=" * 52)
    ctx.log(f"[세션] {len(sessions)}개 세션, 총 {total}개 선수 시점 녹화 예정")
    ctx.emit("start", total=total)

    detector = ScreenDetector(cfg)
    controller = ReplayController(cfg)
    use_ocr = cfg["replay_list"].get("use_ocr", True)
    row_click_x = cfg["replay_list"].get("row_click_x", 600)
    locator = CodeLocator(cfg) if use_ocr else None

    # OBS 연결 (실패 시 안내 후 종료)
    try:
        recorder = ObsRecorder(cfg)
        ctx.log("[OBS] 연결 성공")
    except Exception as e:
        ctx.log(f"[오류] OBS에 연결하지 못했습니다: {e}")
        ctx.log("  - OBS 실행 여부, WebSocket 서버 활성화, config.yaml의 port/password를 확인하세요.")
        result["obs_error"] = str(e)
        ctx.emit("obs_error", message=str(e))
        return result

    # 5초 카운트다운
    ctx.log("\n[준비] 5초 안에 오버워치 리플레이 목록 화면을 띄우고 창을 활성화하세요...")
    for r in range(5, 0, -1):
        if ctx.stopped():
            break
        ctx.emit("countdown", remaining=r)
        ctx.sleep(1.0)

    done = 0
    try:
        if not ctx.stopped():
            if detector.match("replay_menu"):
                ctx.log("[확인] 리플레이 목록(로비) 화면 인식됨")
            else:
                ctx.log(f"[경고] 리플레이 목록 화면 미인식(점수 {detector.match_score('replay_menu'):.2f}). 계속 진행합니다.")

            for si, session in enumerate(sessions):
                if ctx.stopped():
                    break
                code = session["code"]
                ctx.log(f"\n===== 세션 {si + 1}/{len(sessions)}: {code} =====")

                for pi, player in enumerate(session["players"]):
                    if ctx.stopped():
                        break
                    ctx.emit("item_start", index=done + 1, total=total,
                             si=si, pi=pi, code=code, player=player, fkey=sess_mod.fkey_for(player))

                    # 코드 행 위치 결정 — 매 선수(녹화)마다 다시 스크롤 탐색한다.
                    # 한 선수 녹화 후 로비로 복귀하면 목록 스크롤이 초기 상태로 돌아가므로,
                    # 이전에 찾은 좌표를 재사용하지 않고 선수마다 새로 찾는다.
                    if use_ocr:
                        # 목록을 스크롤하며 코드 탐색 (화면 밖에 있어도 찾음)
                        ctx.emit("locating", text=f"{code} 코드 탐색 중...")
                        click_xy = locate_code_scrolling(
                            detector, locator, controller, ctx, code, row_click_x, cfg)
                        miss_reason = f"목록 전체에서 코드 {code}를 찾지 못했습니다"
                    else:
                        click_xy = controller.fallback_row(si)
                        miss_reason = f"폴백 좌표(fallback_rows[{si}]) 없음"

                    if click_xy is None:
                        if ctx.stopped():
                            break
                        ctx.log(f"[건너뜀] {code}/{player}: {miss_reason}")
                        result["fail"] += 1
                        result["failures"].append((code, player, miss_reason))
                        ctx.emit("item_done", si=si, pi=pi, success=False, reason=miss_reason)
                        done += 1
                        ctx.emit("overall", done=done, total=total)
                        continue

                    try:
                        success, reason = record_player(
                            cfg, detector, recorder, controller, click_xy, code, player, ctx, si, pi)
                    except Exception as e:
                        ctx.log(f"[오류] {code}/{player} 처리 중 예외: {e} — 녹화 정지 후 다음 진행")
                        safe_stop(recorder, ctx)
                        try:
                            controller.back_to_lobby()
                        except Exception:
                            pass
                        success, reason = False, f"예외: {e}"

                    if ctx.stopped() and reason == "중단됨":
                        ctx.emit("item_done", si=si, pi=pi, success=False, reason="중단됨")
                        break

                    if success:
                        result["ok"] += 1
                    else:
                        result["fail"] += 1
                        result["failures"].append((code, player, reason))
                    ctx.emit("item_done", si=si, pi=pi, success=success, reason=reason)
                    done += 1
                    ctx.emit("overall", done=done, total=total)

                    if ctx.stopped():
                        break
                    ctx.sleep(cfg["recording"]["between_replays"])
    except Exception as e:
        ctx.log(f"\n[오류] 예기치 못한 예외: {e}")
    finally:
        try:
            if recorder.is_recording():
                ctx.log("[정리] 녹화가 켜져 있어 정지합니다.")
                safe_stop(recorder, ctx)
        except Exception as e:
            ctx.log(f"[경고] 정리 중 오류: {e}")

    result["aborted"] = ctx.stopped()
    ctx.log("\n" + "=" * 52)
    tail = " (중단됨)" if result["aborted"] else ""
    ctx.log(f" 완료: 총 {total}개 시점 중 {result['ok']}개 녹화 성공{tail}")
    ctx.log("=" * 52)
    ctx.emit("finished", ok=result["ok"], fail=result["fail"],
             failures=result["failures"], aborted=result["aborted"], total=total)
    return result


def load_or_create_sessions():
    """sessions.yaml을 읽고 검증한다. 없으면 대화형으로 생성. 실패 시 None."""
    sessions = sess_mod.load_sessions()
    if sessions is None:
        print("[안내] sessions.yaml이 없습니다. 대화형으로 세션을 입력합니다.")
        sessions = sess_mod.create_interactive()
    errors = sess_mod.validate_all(sessions)
    if errors:
        print("[오류] 세션 검증 실패:")
        for e in errors:
            print(f"   - {e}")
        return None
    return sessions


def main():
    """콘솔 실행 진입점 (run.bat). 기존 방식 그대로 동작."""
    cfg = load_config()
    sessions = load_or_create_sessions()
    if not sessions:
        sys.exit(1)

    ctx = RunContext()  # log=print, 진행 콜백 없음 (콘솔)
    result = run_sessions(sessions, cfg, ctx)
    if result.get("obs_error") or result.get("invalid"):
        sys.exit(1)


if __name__ == "__main__":
    main()
