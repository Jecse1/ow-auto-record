"""세션(녹화 작업) 정의 모듈.

한 '세션'은 하나의 리플레이 코드와, 그 리플레이에서 녹화할 선수 시점 목록이다.
sessions.yaml 예시:

    sessions:
      - code: R19FV7
        players: [blue1, red1]      # 블루 1번(F1), 레드 1번(F7)
      - code: TYZY7S
        players: [red3]             # 레드 3번(F9)

선수 표기 → 관전 단축키 매핑:
  blue1~blue5 = F1~F5   (1팀)
  red1~red5   = F7~F11  (2팀)
"""

import os
import re

import yaml

CODE_RE = re.compile(r"^[A-Z0-9]{6}$")

# 선수 표기 → F키 (pydirectinput이 쓰는 소문자 키 이름)
PLAYER_TO_FKEY = {
    "blue1": "f1", "blue2": "f2", "blue3": "f3", "blue4": "f4", "blue5": "f5",
    "red1": "f7", "red2": "f8", "red3": "f9", "red4": "f10", "red5": "f11",
}
VALID_PLAYERS = list(PLAYER_TO_FKEY.keys())


def fkey_for(player: str) -> str:
    """선수 표기에 해당하는 F키 이름을 반환. 잘못된 표기면 KeyError."""
    return PLAYER_TO_FKEY[player.strip().lower()]


def validate_code(code: str) -> bool:
    return bool(CODE_RE.match(code.strip().upper()))


def validate_session(sess: dict) -> list:
    """세션 하나를 검사하고 오류 메시지 리스트를 반환(비어 있으면 정상)."""
    errors = []
    code = str(sess.get("code", "")).strip().upper()
    if not validate_code(code):
        errors.append(f"코드 형식 오류: '{sess.get('code')}' (대문자+숫자 6자리여야 함)")
    players = sess.get("players") or []
    if not players:
        errors.append(f"[{code}] 선수 목록이 비어 있습니다.")
    for p in players:
        if str(p).strip().lower() not in PLAYER_TO_FKEY:
            errors.append(f"[{code}] 알 수 없는 선수 표기: '{p}' (가능: {', '.join(VALID_PLAYERS)})")
    return errors


def normalize_sessions(raw: dict) -> list:
    """yaml에서 읽은 구조를 정규화한 세션 리스트로 변환."""
    sessions = []
    for sess in raw.get("sessions", []) or []:
        sessions.append({
            "code": str(sess["code"]).strip().upper(),
            "players": [str(p).strip().lower() for p in (sess.get("players") or [])],
        })
    return sessions


def validate_all(sessions: list) -> list:
    """전체 세션 검증. 오류 메시지 리스트 반환."""
    errors = []
    if not sessions:
        errors.append("세션이 하나도 없습니다.")
    for sess in sessions:
        errors.extend(validate_session(sess))
    return errors


def load_sessions(path: str = "sessions.yaml"):
    """sessions.yaml을 읽어 정규화된 세션 리스트를 반환. 파일이 없으면 None."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return normalize_sessions(raw)


def save_sessions(sessions: list, path: str = "sessions.yaml"):
    """세션 리스트를 sessions.yaml로 저장."""
    data = {"sessions": [{"code": s["code"], "players": s["players"]} for s in sessions]}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def create_interactive(path: str = "sessions.yaml") -> list:
    """콘솔에서 세션을 입력받아 sessions.yaml로 저장하고 리스트를 반환."""
    print("\n=== 세션 대화형 입력 ===")
    print("리플레이 코드와 녹화할 선수를 입력합니다. 코드 입력을 비워 두면 종료됩니다.")
    print(f"선수 표기: {', '.join(VALID_PLAYERS)}  (blue=1팀 F1~F5, red=2팀 F7~F11)\n")

    sessions = []
    while True:
        code = input("리플레이 코드 (엔터=입력 종료): ").strip().upper()
        if not code:
            break
        if not validate_code(code):
            print("  ! 코드는 대문자+숫자 6자리여야 합니다. 다시 입력하세요.")
            continue
        raw_players = input("  선수들 (쉼표로 구분, 예: blue1, red3): ").strip()
        players = [p.strip().lower() for p in raw_players.split(",") if p.strip()]
        bad = [p for p in players if p not in PLAYER_TO_FKEY]
        if not players:
            print("  ! 선수를 최소 1명 입력하세요.")
            continue
        if bad:
            print(f"  ! 알 수 없는 표기: {', '.join(bad)}. 다시 입력하세요.")
            continue
        sessions.append({"code": code, "players": players})
        print(f"  + 추가됨: {code} -> {', '.join(players)}\n")

    if sessions:
        save_sessions(sessions, path)
        print(f"\n{len(sessions)}개 세션을 {path}에 저장했습니다.")
    return sessions
