r"""打包 Saydown：PyInstaller 產生 dist/Saydown，再用 Inno Setup 做成安裝檔。

在專案根目錄執行：.venv\Scripts\python.exe packaging\build.py
預設兩個版本都打包：
  GPU 版 dist/Saydown-Setup-<版本>.exe：含 NVIDIA 函式庫（約 2 GB），有 NVIDIA 顯示卡的電腦用
  CPU 版 dist/Saydown-Setup-<版本>-CPU.exe：不含 NVIDIA 函式庫，沒有顯示卡的電腦用
加 --gpu 或 --cpu 只打包其中一個。
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from version import __author__, __version__  # noqa: E402

ISCC = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Inno Setup 6" / "ISCC.exe"
if not ISCC.exists():
    ISCC = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")

# 版本：(PyInstaller 輸出資料夾, 暫存資料夾, 安裝檔檔名後綴)
FLAVORS = {
    "gpu": ("dist", "build/pyi", ""),
    "cpu": ("dist/cpu", "build/pyi-cpu", "-CPU"),
}


def build(flavor):
    distpath, workpath, suffix = FLAVORS[flavor]
    env = {**os.environ, "SAYDOWN_CPU": "1" if flavor == "cpu" else "0"}
    subprocess.run([sys.executable, "-m", "PyInstaller", "packaging/saydown.spec", "--noconfirm",
                    "--distpath", distpath, "--workpath", workpath], cwd=ROOT, env=env, check=True)
    app_dir = str(Path(distpath).relative_to("dist") / "Saydown")
    subprocess.run([str(ISCC), f"/DAppVersion={__version__}", f"/DAppAuthor={__author__}",
                    f"/DFlavor={suffix}", f"/DAppDir={app_dir}", "packaging/saydown.iss"], cwd=ROOT, check=True)
    print(f"完成：dist/Saydown-Setup-{__version__}{suffix}.exe")


if __name__ == "__main__":
    picked = [f for f in FLAVORS if f"--{f}" in sys.argv[1:]] or list(FLAVORS)
    for flavor in picked:
        build(flavor)
