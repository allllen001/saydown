r"""程式資源與使用者資料的位置。

直接用原始碼執行時，一切都在程式資料夾（和以前一樣）；
打包成 exe 後程式裝在唯讀的 Program Files，設定、詞庫、歷史、記錄檔改放 %APPDATA%\Saydown。
"""

import os
import shutil
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
SRC = Path(__file__).resolve().parent
RES = Path(getattr(sys, "_MEIPASS", SRC))  # 唯讀資源：圖示、預設設定、CUDA DLL
DATA = Path(os.environ["APPDATA"]) / "Saydown" if FROZEN else SRC
CONFIG_PATH = DATA / "config.json"
DEFAULT_CONFIG = RES / "config.example.json"
ICO_PATH = RES / "saydown.ico"


def ensure_data():
    """第一次執行時建立資料夾，並用預設設定產生 config.json。"""
    DATA.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        shutil.copyfile(DEFAULT_CONFIG, CONFIG_PATH)


def command(role):
    """啟動 Saydown 某個部分（main／guard／history／settings）的命令列。"""
    if FROZEN:
        return [sys.executable, f"--{role}"]
    script = {"main": "voice_input.py", "guard": "saydown_guard.py"}.get(role, f"{role}.py")
    pythonw = SRC / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable).with_name("pythonw.exe")
    return [str(pythonw), str(SRC / script)]
