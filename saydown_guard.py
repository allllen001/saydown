"""Saydown 守護程式：負責啟動主程式（voice_input.py，打包後是 Saydown.exe --main），它消失或卡住就自動重開。

- 使用者從系統匣按「結束」時主程式以結束碼 0 離開，守護程式跟著結束，不會再開。
- 其他離開方式（當機、被結束工作）都會重開；10 分鐘內重開超過 5 次就停手並跳出提示，避免無限循環。
- 主程式每幾秒更新 heartbeat 檔；啟動 3 分鐘後若超過 90 秒沒更新，視為卡住，結束後重開。
開機自動啟動與「啟動Saydown.bat」都是啟動這支，不是直接啟動主程式。
"""

import ctypes
import logging
import os
import subprocess
import sys
import time

import paths

paths.ensure_data()
BASE = paths.DATA
HEARTBEAT = BASE / "heartbeat"

CHECK_SECONDS = 5
STARTUP_GRACE = int(os.environ.get("SAYDOWN_GUARD_GRACE", 180))  # 啟動後多久才檢查心跳（載入 Whisper、Ollama 暖機要時間）
STALE_SECONDS = int(os.environ.get("SAYDOWN_GUARD_STALE", 90))
MAIN_CMD = paths.command("main")
if os.environ.get("SAYDOWN_GUARD_MAIN"):  # 測試時換成假的主程式
    MAIN_CMD = [MAIN_CMD[0], os.environ["SAYDOWN_GUARD_MAIN"]]
MAX_RESTARTS, WINDOW = 5, 600

logging.basicConfig(
    filename=BASE / "voice_input.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("guard")


def single_instance():
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\SaydownGuard")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)


def kill_tree(proc):
    # venv 的 pythonw.exe 是轉呼叫真正 Python 的小程式，要連子程序一起結束
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)


def heartbeat_age():
    try:
        return time.time() - HEARTBEAT.stat().st_mtime
    except OSError:
        return float("inf")


def main():
    single_instance()
    restarts = []
    while True:
        try:
            HEARTBEAT.unlink()
        except OSError:
            pass
        started = time.time()
        proc = subprocess.Popen(MAIN_CMD, cwd=BASE)
        log.info("守護：啟動 Saydown（pid %d）", proc.pid)
        code = None
        while code is None:
            time.sleep(CHECK_SECONDS)
            code = proc.poll()
            if code is None and time.time() - started > STARTUP_GRACE and heartbeat_age() > STALE_SECONDS:
                log.warning("守護：Saydown 超過 %d 秒沒有回應，結束後重開", STALE_SECONDS)
                kill_tree(proc)
                proc.wait(timeout=30)
                code = "hang"
        if code == 0:
            log.info("守護：Saydown 正常結束，守護一起結束")
            return
        log.warning("守護：Saydown 意外結束（結束碼 %s，執行了 %.0f 秒）", code, time.time() - started)
        now = time.time()
        restarts = [t for t in restarts if now - t < WINDOW] + [now]
        if len(restarts) > MAX_RESTARTS:
            log.error("守護：%d 分鐘內重開超過 %d 次，停止自動重開", WINDOW // 60, MAX_RESTARTS)
            ctypes.windll.user32.MessageBoxW(
                None, "Saydown 一直意外結束，已停止自動重開。\n原因記在 voice_input.log 與 crash.log。",
                "Saydown", 0x30,
            )
            return
        time.sleep(3)


if __name__ == "__main__":
    if sys.stdout is None:  # pythonw
        sys.stdout = sys.stderr = open(os.devnull, "w")
    main()
