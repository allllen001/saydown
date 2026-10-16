"""打包 Saydown：PyInstaller 產生 dist/Saydown，再用 Inno Setup 做成安裝檔。

在專案根目錄執行：.venv\Scripts\python.exe packaging\build.py
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

subprocess.run([sys.executable, "-m", "PyInstaller", "packaging/saydown.spec", "--noconfirm",
                "--distpath", "dist", "--workpath", "build/pyi"], cwd=ROOT, check=True)
subprocess.run([str(ISCC), f"/DAppVersion={__version__}", f"/DAppAuthor={__author__}",
                "packaging/saydown.iss"], cwd=ROOT, check=True)
print(f"完成：dist/Saydown-Setup-{__version__}.exe")
