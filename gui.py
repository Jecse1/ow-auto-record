"""오버워치 리플레이 자동 녹화 - 데스크톱 GUI (v0.3).

콘솔 없이 세션 등록 → 녹화 시작 → 진행 상황 확인까지 하나의 창에서 처리한다.
표준 라이브러리(Tkinter)만 사용하며, 녹화 로직은 main.run_sessions()를 그대로 재사용한다.

실행:
  python gui.py            # 실제 녹화 (OBS/게임 필요)
  python gui.py --demo     # 녹화 파이프라인을 흉내 내는 데모 모드 (하드웨어 불필요)
  python gui.py --selftest # 자동 자가 검증(모델/라운드트립/데모/중단) 후 종료
"""
import sys
import argparse
import queue
import threading
import tempfile
import os

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import tkinter as tk
from tkinter import ttk, messagebox

import sessions as sess_mod
import main as pipeline


# ---- 선수 토큰 <-> 표시 라벨 ----
BLUE = [f"blue{i}" for i in range(1, 6)]
RED = [f"red{i}" for i in range(1, 6)]


def player_label(token: str) -> str:
    team = "블루" if token.startswith("blue") else "레드"
    return f"{team} {token[-1]}"


# ==========================================================================
#  데모 파이프라인 (mock) — main.run_sessions와 동일한 진행 이벤트를 흉내 낸다.
#  실제 OCR/화면감지/OBS 없이 GUI를 검증하기 위한 용도.
# ==========================================================================
def run_demo(sessions, ctx):
    result = {"ok": 0, "fail": 0, "failures": [], "aborted": False,
              "obs_error": None, "invalid": None, "total": 0}
    errs = sess_mod.validate_all(sessions)
    if errs:
        result["invalid"] = errs
        ctx.emit("error", message="세션 검증 실패:\n" + "\n".join(errs))
        return result

    total = sum(len(s["players"]) for s in sessions)
    result["total"] = total
    ctx.emit("start", total=total)
    ctx.log("=" * 52)
    ctx.log(" [데모] 오버워치 리플레이 자동 녹화 (실제 녹화 없음)")
    ctx.log("=" * 52)
    ctx.log(f"[세션] {len(sessions)}개 세션, 총 {total}개 시점 (데모)")

    for r in range(5, 0, -1):
        if ctx.stopped():
            break
        ctx.emit("countdown", remaining=r)
        ctx.sleep(0.4)

    done = 0
    if not ctx.stopped():
        ctx.emit("locating")
        ctx.log("[OCR] (데모) 목록에서 코드 검색 중...")
        ctx.sleep(0.5)

        steps = ["행 선택·재생 진입", "재생 진입 대기", "시점 전환", "녹화 중", "녹화 정지", "로비 복귀"]
        for si, session in enumerate(sessions):
            if ctx.stopped():
                break
            code = session["code"]
            ctx.log(f"\n===== (데모) 세션 {si + 1}/{len(sessions)}: {code} =====")
            for pi, player in enumerate(session["players"]):
                if ctx.stopped():
                    break
                fkey = sess_mod.fkey_for(player)
                ctx.emit("item_start", index=done + 1, total=total,
                         si=si, pi=pi, code=code, player=player, fkey=fkey)
                aborted_item = False
                for st in steps:
                    if ctx.stopped():
                        aborted_item = True
                        break
                    text = f"{st} {fkey.upper()}" if st == "시점 전환" else st
                    ctx.emit("step", si=si, pi=pi, text=text)
                    ctx.log(f"[데모] {code}/{player}: {text}")
                    if st == "녹화 중":
                        for e in range(3):
                            if ctx.stopped():
                                aborted_item = True
                                break
                            ctx.emit("recording", si=si, pi=pi, elapsed=e + 1)
                            ctx.sleep(0.4)
                    else:
                        ctx.sleep(0.3)
                if aborted_item or ctx.stopped():
                    ctx.emit("item_done", si=si, pi=pi, success=False, reason="중단됨")
                    break
                # 데모에서는 red5 시점을 실패로 시뮬레이션(실패 표시 확인용)
                success = player != "red5"
                reason = "완료" if success else "재생 화면 감지 실패(데모)"
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
                ctx.sleep(0.3)

    result["aborted"] = ctx.stopped()
    tail = " (중단됨)" if result["aborted"] else ""
    ctx.log("\n" + "=" * 52)
    ctx.log(f" [데모] 완료: 총 {total}개 중 {result['ok']}개 성공{tail}")
    ctx.log("=" * 52)
    ctx.emit("finished", ok=result["ok"], fail=result["fail"],
             failures=result["failures"], aborted=result["aborted"], total=total)
    return result


# ==========================================================================
#  GUI
# ==========================================================================
class RecorderApp(tk.Tk):
    def __init__(self, demo=False, sessions_path="sessions.yaml"):
        super().__init__()
        self.demo = demo
        self.sessions_path = sessions_path
        self.title("오버워치 리플레이 자동 녹화" + ("  [데모]" if demo else ""))
        self.geometry("820x760")
        self.minsize(720, 640)

        self.sessions = []           # [{"code":.., "players":[..]}]
        self.q = queue.Queue()       # 워커 스레드 → GUI 이벤트 큐
        self.worker = None
        self.stop_event = None
        self.cfg = None
        self._running = False
        self._finished_result = None  # 마지막 실행 결과(요약)

        self._build_ui()
        self._load_existing()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_queue)

    # ---------------- UI 구성 ----------------
    def _build_ui(self):
        pad = dict(padx=6, pady=4)

        # 1) 세션 입력
        inp = ttk.LabelFrame(self, text="세션 입력")
        inp.pack(fill="x", **pad)

        row1 = ttk.Frame(inp)
        row1.pack(fill="x", padx=6, pady=4)
        ttk.Label(row1, text="리플레이 코드:").pack(side="left")
        self.code_var = tk.StringVar()
        self.code_var.trace_add("write", self._force_upper)
        self.code_entry = ttk.Entry(row1, textvariable=self.code_var, width=12)
        self.code_entry.pack(side="left", padx=6)
        ttk.Label(row1, text="(대문자+숫자 6자리)").pack(side="left")

        chk = ttk.Frame(inp)
        chk.pack(fill="x", padx=6, pady=2)
        self.player_vars = {}
        self.player_checks = {}
        ttk.Label(chk, text="블루팀:").grid(row=0, column=0, sticky="w")
        for i, tok in enumerate(BLUE):
            v = tk.BooleanVar()
            self.player_vars[tok] = v
            cb = ttk.Checkbutton(chk, text=str(i + 1), variable=v)
            cb.grid(row=0, column=i + 1, padx=2)
            self.player_checks[tok] = cb
        ttk.Label(chk, text="레드팀:").grid(row=1, column=0, sticky="w")
        for i, tok in enumerate(RED):
            v = tk.BooleanVar()
            self.player_vars[tok] = v
            cb = ttk.Checkbutton(chk, text=str(i + 1), variable=v)
            cb.grid(row=1, column=i + 1, padx=2)
            self.player_checks[tok] = cb

        self.add_btn = ttk.Button(inp, text="세션 추가", command=self._add_session)
        self.add_btn.pack(anchor="e", padx=6, pady=4)

        # 2) 세션 목록
        listf = ttk.LabelFrame(self, text="세션 목록  (선수 1명당 리플레이 1회 재생·녹화)")
        listf.pack(fill="both", expand=True, **pad)

        tf = ttk.Frame(listf)
        tf.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.tree = ttk.Treeview(tf, columns=("detail", "status"), show="tree headings", height=9)
        self.tree.heading("#0", text="세션 / 선수")
        self.tree.heading("detail", text="시점 / 횟수")
        self.tree.heading("status", text="상태")
        self.tree.column("#0", width=220)
        self.tree.column("detail", width=160, anchor="center")
        self.tree.column("status", width=200, anchor="w")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        btns = ttk.Frame(listf)
        btns.pack(side="left", fill="y", padx=6, pady=6)
        self.del_btn = ttk.Button(btns, text="삭제", command=self._delete_selected)
        self.up_btn = ttk.Button(btns, text="위로", command=lambda: self._move(-1))
        self.down_btn = ttk.Button(btns, text="아래로", command=lambda: self._move(1))
        self.save_btn = ttk.Button(btns, text="저장", command=self._save)
        for b in (self.del_btn, self.up_btn, self.down_btn, self.save_btn):
            b.pack(fill="x", pady=3)

        # 3) 진행 상황
        prog = ttk.LabelFrame(self, text="진행 상황")
        prog.pack(fill="both", expand=True, **pad)

        ctrl = ttk.Frame(prog)
        ctrl.pack(fill="x", padx=6, pady=4)
        self.start_btn = ttk.Button(ctrl, text="녹화 시작", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(ctrl, text="중단", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.countdown_var = tk.StringVar(value="")
        ttk.Label(ctrl, textvariable=self.countdown_var, foreground="#c0392b").pack(side="left", padx=12)

        pbar = ttk.Frame(prog)
        pbar.pack(fill="x", padx=6, pady=2)
        self.progress = ttk.Progressbar(pbar, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True)
        self.progress_var = tk.StringVar(value="0 / 0")
        ttk.Label(pbar, textvariable=self.progress_var, width=12, anchor="e").pack(side="left", padx=6)

        self.current_var = tk.StringVar(value="대기 중")
        ttk.Label(prog, textvariable=self.current_var, anchor="w").pack(fill="x", padx=6)

        logf = ttk.Frame(prog)
        logf.pack(fill="both", expand=True, padx=6, pady=4)
        self.log_text = tk.Text(logf, height=10, wrap="word", state="disabled")
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=lsb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        lsb.pack(side="left", fill="y")

        self.summary_var = tk.StringVar(value="")
        ttk.Label(prog, textvariable=self.summary_var, foreground="#27632a", anchor="w").pack(fill="x", padx=6, pady=2)

    # ---------------- 세션 편집 로직 ----------------
    def _force_upper(self, *_):
        s = self.code_var.get().upper()
        if s != self.code_var.get():
            self.code_var.set(s)

    def _set_inputs(self, code, players):
        """(테스트/프로그램용) 코드·선수 입력 상태를 설정."""
        self.code_var.set(code.upper())
        for tok, v in self.player_vars.items():
            v.set(tok in players)

    def _selected_players(self):
        return [tok for tok in BLUE + RED if self.player_vars[tok].get()]

    def _add_session(self) -> bool:
        code = self.code_var.get().strip().upper()
        players = self._selected_players()
        if not sess_mod.validate_code(code):
            messagebox.showerror("입력 오류", "리플레이 코드는 대문자+숫자 6자리여야 합니다.")
            return False
        if not players:
            messagebox.showerror("입력 오류", "선수를 최소 1명 선택하세요.")
            return False
        self.sessions.append({"code": code, "players": players})
        self._refresh_tree()
        # 입력 초기화
        self.code_var.set("")
        for v in self.player_vars.values():
            v.set(False)
        return True

    def _selected_session_index(self):
        sel = self.tree.selection()
        if not sel:
            return None
        iid = sel[0]
        # 부모/자식 모두 세션 인덱스로 환원
        top = iid.split("P")[0]  # "S{si}"
        if top.startswith("S"):
            try:
                return int(top[1:])
            except ValueError:
                return None
        return None

    def _select_session(self, index):
        self.tree.selection_set(f"S{index}")

    def _delete_selected(self):
        i = self._selected_session_index()
        if i is None:
            messagebox.showinfo("삭제", "삭제할 세션을 목록에서 선택하세요.")
            return
        del self.sessions[i]
        self._refresh_tree()

    def _move(self, delta):
        i = self._selected_session_index()
        if i is None:
            return
        j = i + delta
        if j < 0 or j >= len(self.sessions):
            return
        self.sessions[i], self.sessions[j] = self.sessions[j], self.sessions[i]
        self._refresh_tree()
        self._select_session(j)

    def _refresh_tree(self, statuses=None):
        """세션 목록으로 Treeview를 다시 그린다. statuses: {(si,pi or None): text}."""
        statuses = statuses or {}
        self.tree.delete(*self.tree.get_children())
        for si, s in enumerate(self.sessions):
            n = len(s["players"])
            pstat = statuses.get((si, None), "대기")
            self.tree.insert("", "end", iid=f"S{si}", text=f"{si + 1}. {s['code']}",
                             values=(f"{n}명 → {n}회", pstat), open=True)
            for pi, player in enumerate(s["players"]):
                cstat = statuses.get((si, pi), "대기")
                self.tree.insert(f"S{si}", "end", iid=f"S{si}P{pi}",
                                 text=f"    {player_label(player)}",
                                 values=(sess_mod.fkey_for(player).upper(), cstat))

    def _set_status(self, si, pi, text):
        iid = f"S{si}P{pi}" if pi is not None else f"S{si}"
        if self.tree.exists(iid):
            self.tree.set(iid, "status", text)

    def _save(self):
        errs = sess_mod.validate_all(self.sessions) if self.sessions else ["세션이 없습니다."]
        if errs:
            messagebox.showerror("저장 오류", "\n".join(errs))
            return False
        sess_mod.save_sessions(self.sessions, self.sessions_path)
        self._log(f"[저장] {len(self.sessions)}개 세션을 {self.sessions_path}에 저장했습니다.")
        return True

    def _load_existing(self):
        loaded = sess_mod.load_sessions(self.sessions_path)
        if loaded:
            self.sessions = loaded
            self._refresh_tree()
            self._log(f"[불러오기] {self.sessions_path}에서 {len(loaded)}개 세션을 불러왔습니다.")

    # ---------------- 실행 제어 ----------------
    def _set_inputs_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for w in (self.code_entry, self.add_btn, self.del_btn, self.up_btn,
                  self.down_btn, self.save_btn, self.start_btn):
            w.configure(state=state)
        for cb in self.player_checks.values():
            cb.configure(state=state)
        self.stop_btn.configure(state="normal" if not enabled else "disabled")

    def _start(self):
        if self._running:
            return
        if not self.sessions:
            messagebox.showinfo("녹화 시작", "먼저 세션을 추가하세요.")
            return
        errs = sess_mod.validate_all(self.sessions)
        if errs:
            messagebox.showerror("세션 오류", "\n".join(errs))
            return
        # 시작 시 자동 저장
        if not self.demo:
            sess_mod.save_sessions(self.sessions, self.sessions_path)
        # 실제 모드면 config 로드
        if not self.demo and self.cfg is None:
            try:
                self.cfg = pipeline.load_config()
            except Exception as e:
                messagebox.showerror("설정 오류", f"config.yaml을 읽지 못했습니다:\n{e}")
                return

        self._running = True
        self._finished_result = None
        self._clear_log()
        self.summary_var.set("")
        self.progress.configure(value=0, maximum=max(1, sum(len(s['players']) for s in self.sessions)))
        self.progress_var.set(f"0 / {sum(len(s['players']) for s in self.sessions)}")
        self._refresh_tree()  # 상태 초기화
        self._set_inputs_enabled(False)

        self.stop_event = threading.Event()
        ctx = pipeline.RunContext(
            log=lambda m: self.q.put({"type": "log", "msg": m}),
            progress=lambda ev: self.q.put(ev),
            stop_event=self.stop_event,
        )
        target = run_demo if self.demo else pipeline.run_sessions
        args = (self.sessions, ctx) if self.demo else (self.sessions, self.cfg, ctx)

        def worker():
            try:
                res = target(*args)
                self.q.put({"type": "_result", "result": res})
            except Exception as e:
                self.q.put({"type": "log", "msg": f"[오류] 실행 스레드 예외: {e}"})
                self.q.put({"type": "obs_error", "message": str(e)})
            finally:
                self.q.put({"type": "_worker_done"})

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def _stop(self):
        if self.stop_event and not self.stop_event.is_set():
            self.stop_event.set()
            self.current_var.set("중단 요청됨 — 녹화 정지 중...")
            self._log("[중단] 사용자가 중단을 요청했습니다.")
            self.stop_btn.configure(state="disabled")

    def _on_close(self):
        if self._running:
            if not messagebox.askokcancel("종료", "녹화가 진행 중입니다. 정지하고 종료할까요?"):
                return
            if self.stop_event:
                self.stop_event.set()
            # 워커가 안전 정지(safe_stop)할 시간을 잠깐 준 뒤 종료
            self.after(1500, self.destroy)
            return
        self.destroy()

    # ---------------- 큐 소비(메인 스레드에서 위젯 갱신) ----------------
    def _drain_queue(self):
        try:
            while True:
                ev = self.q.get_nowait()
                self._handle_event(ev)
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _handle_event(self, ev):
        t = ev.get("type")
        if t == "log":
            self._log(ev["msg"])
        elif t == "start":
            n = ev["total"]
            self.progress.configure(maximum=max(1, n), value=0)
            self.progress_var.set(f"0 / {n}")
        elif t == "countdown":
            self.countdown_var.set(f"{ev['remaining']}초 후 시작 — 게임 창을 활성화하세요")
        elif t == "locating":
            self.countdown_var.set("")
            self.current_var.set(ev.get("text") or "목록에서 코드 찾는 중...")
        elif t == "item_start":
            self.countdown_var.set("")
            self.current_var.set(f"[{ev['index']}/{ev['total']}] {ev['code']} / "
                                 f"{player_label(ev['player'])}({ev['fkey'].upper()})")
            self._set_status(ev["si"], None, "진행 중")
            self._set_status(ev["si"], ev["pi"], "진행 중")
        elif t == "step":
            self._set_status(ev["si"], ev["pi"], ev["text"])
            base = self.current_var.get().split("  —  ")[0]
            self.current_var.set(f"{base}  —  {ev['text']}")
        elif t == "recording":
            self._set_status(ev["si"], ev["pi"], f"녹화 중 ({ev['elapsed']}초)")
            base = self.current_var.get().split("  —  ")[0]
            self.current_var.set(f"{base}  —  녹화 중 ({ev['elapsed']}초)")
        elif t == "item_done":
            ok = ev["success"]
            self._set_status(ev["si"], ev["pi"], "완료" if ok else f"실패: {ev['reason']}")
            self._update_session_status(ev["si"])
        elif t == "overall":
            self.progress.configure(value=ev["done"])
            self.progress_var.set(f"{ev['done']} / {ev['total']}")
        elif t == "obs_error":
            messagebox.showerror(
                "OBS 연결 실패",
                "OBS에 연결하지 못했습니다.\n\n"
                "- OBS가 실행 중인지\n- 도구 > WebSocket 서버 설정에서 서버가 켜져 있는지\n"
                "- config.yaml의 obs.port / obs.password가 맞는지\n확인하세요.\n\n"
                f"세부: {ev.get('message','')}")
        elif t == "error":
            messagebox.showerror("오류", ev.get("message", "알 수 없는 오류"))
        elif t == "finished":
            self._on_finished(ev)
        elif t == "_result":
            self._finished_result = ev["result"]
        elif t == "_worker_done":
            self._running = False
            self._set_inputs_enabled(True)
            self.current_var.set("대기 중")
            self.countdown_var.set("")

    def _update_session_status(self, si):
        """자식 상태를 모아 세션(부모) 상태를 갱신."""
        s = self.sessions[si]
        states = [self.tree.set(f"S{si}P{pi}", "status") for pi in range(len(s["players"]))
                  if self.tree.exists(f"S{si}P{pi}")]
        if all(x == "완료" for x in states):
            self._set_status(si, None, "완료")
        elif any(x.startswith("실패") for x in states) and all(
                x == "완료" or x.startswith("실패") for x in states):
            self._set_status(si, None, "일부 실패")
        else:
            self._set_status(si, None, "진행 중")

    def _on_finished(self, ev):
        fails = ev.get("failures", [])
        tail = " (중단됨)" if ev.get("aborted") else ""
        self.summary_var.set(f"완료 {ev['ok']} / 실패 {ev['fail']}{tail}")
        if fails:
            self._log("실패 항목:")
            for code, player, reason in fails:
                self._log(f"   - {code} / {player_label(player)}: {reason}")

    # ---------------- 로그 ----------------
    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")


# ==========================================================================
#  자가 검증 (--selftest): 게임/OBS 없이 GUI 자체를 검증
# ==========================================================================
def selftest():
    tmp = os.path.join(tempfile.mkdtemp(), "sessions.yaml")
    app = RecorderApp(demo=True, sessions_path=tmp)
    app.withdraw()
    failures = []

    def check(cond, label):
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label}")
            failures.append(label)

    # --- Part A: 세션 편집/검증/라운드트립 (동기) ---
    print("[selftest] Part A: 세션 모델")
    orig_err = messagebox.showerror
    messagebox.showerror = lambda *a, **k: None  # 검증 실패 팝업 억제
    try:
        app._set_inputs("R19FV7", ["blue1", "red1"])
        check(app._add_session(), "유효 세션 추가(R19FV7)")
        app._set_inputs("TYZY7S", ["red5"])
        check(app._add_session(), "유효 세션 추가(TYZY7S)")
        app._set_inputs("bad", ["blue1"])
        check(not app._add_session(), "잘못된 코드 거부(bad)")
        app._set_inputs("ABC123", [])
        check(not app._add_session(), "선수 미선택 거부")
        check(len(app.sessions) == 2, "세션 개수 2")

        # 순서 변경
        app._select_session(0)
        app._move(1)
        check(app.sessions[0]["code"] == "TYZY7S", "위/아래로 순서 변경")
        # 삭제
        app._select_session(0)
        app._delete_selected()
        check(len(app.sessions) == 1 and app.sessions[0]["code"] == "R19FV7", "선택 세션 삭제")
        # 라운드트립: 다시 추가 후 저장→로드
        app._set_inputs("TYZY7S", ["red3", "red5"])
        app._add_session()
        check(app._save(), "sessions.yaml 저장")
        reloaded = sess_mod.load_sessions(tmp)
        check(reloaded == app.sessions, "저장→로드 라운드트립 일치")
    finally:
        messagebox.showerror = orig_err

    # --- Part B: 데모 실행 + 진행/상태/중단 (이벤트 루프) ---
    print("[selftest] Part B: 데모 실행/진행/중단")
    state = {"finished": False}
    _orig_finished = app._on_finished

    def wrap_finished(ev):
        _orig_finished(ev)
        state["finished"] = True
        state["ev"] = ev
    app._on_finished = wrap_finished

    app._start()
    check(app._running, "녹화(데모) 시작됨")
    check(str(app.start_btn["state"]) == "disabled", "실행 중 입력 비활성화")

    app.after(1400, app._stop)  # 진행 도중 중단 요청

    def watchdog(elapsed=0):
        if state["finished"] and not app._running:
            app.quit()
        elif elapsed > 12000:
            failures.append("데모가 12초 내 종료되지 않음")
            app.quit()
        else:
            app.after(200, lambda: watchdog(elapsed + 200))
    app.after(200, watchdog)
    app.mainloop()

    check(state["finished"], "finished 이벤트 수신")
    check(not app._running, "종료 후 실행 상태 해제")
    check(str(app.start_btn["state"]) == "normal", "종료 후 입력 재활성화")
    ev = state.get("ev", {})
    check(ev.get("aborted") is True, "중단 반영(aborted=True)")
    check(app._finished_result is not None, "결과 요약 수신")

    try:
        app.destroy()
    except Exception:
        pass

    print()
    if failures:
        print(f"[selftest] 실패 {len(failures)}건: {failures}")
        return 1
    print("[selftest] 전체 통과 ✅")
    return 0


def parse_args(argv):
    p = argparse.ArgumentParser(description="OW 리플레이 자동 녹화 GUI")
    p.add_argument("--demo", action="store_true", help="녹화 파이프라인을 흉내 내는 데모 모드")
    p.add_argument("--selftest", action="store_true", help="자동 자가 검증 후 종료")
    return p.parse_args(argv)


def main():
    args = parse_args(sys.argv[1:])
    if args.selftest:
        sys.exit(selftest())
    app = RecorderApp(demo=args.demo)
    app.mainloop()


if __name__ == "__main__":
    main()
