"""OBS 제어 모듈: obs-websocket(v5, OBS 28+) 경유 녹화 시작/정지 및 파일명 태깅."""
import os
import time

import obsws_python as obs


class ObsRecorder:
    def __init__(self, config: dict):
        c = config["obs"]
        self.client = obs.ReqClient(host=c["host"], port=c["port"], password=c["password"], timeout=5)
        self.tag_filename = c.get("filename_tag", True)
        self.rename_retries = c.get("rename_retries", 20)
        self.rename_retry_delay = c.get("rename_retry_delay", 0.5)

    def is_recording(self) -> bool:
        return self.client.get_record_status().output_active

    def start(self):
        if not self.is_recording():
            self.client.start_record()
            print("[OBS] 녹화 시작")

    def stop(self) -> str | None:
        """녹화 정지 후 저장된 파일 경로 반환."""
        if self.is_recording():
            resp = self.client.stop_record()
            path = getattr(resp, "output_path", None)
            print(f"[OBS] 녹화 정지 → {path}")
            return path
        return None

    def stop_and_tag(self, code: str, player: str, when_str: str) -> str | None:
        """녹화 정지 후 파일명을 '<코드>_<선수>_<날짜시간>'으로 변경한다.
        태깅이 꺼져 있거나 실패하면 원본 경로를 반환한다."""
        path = self.stop()
        if not path or not self.tag_filename:
            return path
        return self._rename_with_retry(path, f"{code}_{player}_{when_str}")

    def _rename_with_retry(self, path: str, new_stem: str) -> str:
        """OBS가 파일 쓰기를 끝내(잠금 해제) 이름을 바꿀 수 있을 때까지 재시도."""
        folder = os.path.dirname(path)
        ext = os.path.splitext(path)[1]
        # 파일명에 쓸 수 없는 문자 정리
        safe = "".join(ch for ch in new_stem if ch.isalnum() or ch in "_-")
        target = os.path.join(folder, safe + ext)

        if os.path.abspath(target) == os.path.abspath(path):
            return path
        # 이름 충돌 방지
        n = 1
        while os.path.exists(target):
            target = os.path.join(folder, f"{safe}_{n}{ext}")
            n += 1

        for attempt in range(self.rename_retries):
            try:
                os.rename(path, target)
                print(f"[OBS] 파일명 변경 → {target}")
                return target
            except (PermissionError, OSError):
                # 아직 OBS가 파일을 쓰는 중일 수 있음 → 잠시 대기 후 재시도
                time.sleep(self.rename_retry_delay)
        print(f"[경고] 파일명 변경 실패(잠금 해제 대기 초과): {path} — 원본 유지")
        return path
