# PyInstaller 設定：python -m PyInstaller packaging/saydown.spec（在專案根目錄執行）
import os
import sys
import sysconfig
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from version import __author__, __version__  # noqa: E402

site_packages = Path(sysconfig.get_paths()["purelib"])  # 執行打包的 Python 環境，不一定在專案資料夾裡
# CPU 版（build.py --cpu 設定 SAYDOWN_CPU=1）不帶 NVIDIA 函式庫，安裝檔少約 2 GB
CPU_ONLY = os.environ.get("SAYDOWN_CPU") == "1"
# cuBLAS / cuDNN 不是用 import 載入的，PyInstaller 抓不到，手動帶進 nvidia/*/bin
cuda = [] if CPU_ONLY else [(str(dll), f"nvidia/{dll.parent.parent.name}/bin")
                            for dll in (site_packages / "nvidia").glob("*/bin/*.dll")]
if not CPU_ONLY and not cuda:
    raise SystemExit(f"找不到 NVIDIA 函式庫（{site_packages / 'nvidia'}），GPU 版不能打包")
marker = ROOT / "build" / "cpu-only"  # 程式看到這個檔就一律用 CPU（paths.CPU_ONLY）

ver = tuple(int(x) for x in __version__.split(".")) + (0,)
version_file = ROOT / "build" / "version_info.txt"
version_file.parent.mkdir(exist_ok=True)
marker.write_text("", encoding="utf-8")
version_file.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={ver}, prodvers={ver}),
  kids=[StringFileInfo([StringTable('040404B0', [
    StringStruct('CompanyName', '{__author__}'),
    StringStruct('FileDescription', 'Saydown 本機語音輸入'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('LegalCopyright', '© 2026 {__author__}'),
    StringStruct('ProductName', 'Saydown'),
    StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [0x0404, 1200])])])
""", encoding="utf-8")

a = Analysis(
    [str(ROOT / "saydown.py")],
    pathex=[str(ROOT)],
    binaries=cuda + collect_dynamic_libs("ctranslate2"),
    datas=[
        (str(ROOT / "saydown.ico"), "."),
        (str(ROOT / "config.example.json"), "."),
        *([(str(marker), ".")] if CPU_ONLY else []),
        *collect_data_files("faster_whisper"),
        *collect_data_files("opencc"),
    ],
    hiddenimports=[
        "voice_input", "history", "settings", "saydown_guard", "glass", "importer", "learn",
        "pystray._win32", "pypdf",
        *collect_submodules("comtypes", filter=lambda name: ".test" not in name),
    ],
    excludes=["matplotlib", "IPython", "pytest", "comtypes.test"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Saydown",
    icon=str(ROOT / "saydown.ico"),
    version=str(version_file),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Saydown", upx=False)
