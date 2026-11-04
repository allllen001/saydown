"""打包成 exe 時的入口：同一支 Saydown.exe 依參數扮演守護程式、主程式、歷史紀錄或設定視窗。"""

import os
import subprocess
import sys


def started_by_store_app():
    """上層程式是不是 Store App（裝在 WindowsApps，例如 Claude 桌面版）。

    從這類 App 裡啟動的程式，寫進 %APPDATA% 的東西會被偷偷轉到那個 App 的私人資料夾，
    設定、詞庫、歷史就會分成兩份，彼此看不到。
    """
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap in (None, wintypes.HANDLE(-1).value):
        return False
    parents = {}
    entry = Entry(dwSize=ctypes.sizeof(Entry))
    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        parents[entry.th32ProcessID] = entry.th32ParentProcessID
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)

    k32.OpenProcess.restype = wintypes.HANDLE
    pid = parents.get(os.getpid())
    for _ in range(10):  # 往上找幾層就夠了
        if not pid:
            break
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            got = k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
            k32.CloseHandle(handle)
            if got and "\\windowsapps\\" in buf.value.lower():
                return True
        pid = parents.get(pid)
    return False


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else "--guard"
    if role == "--guard" and getattr(sys, "frozen", False):
        try:
            escape = started_by_store_app()
        except Exception:
            escape = False
        if escape:  # 交給檔案總管重開，資料才會寫進真正的 %APPDATA% 底下
            subprocess.Popen(["explorer.exe", sys.executable])
            return
    if role != "--main" and sys.stdout is None:  # 沒有主控台
        sys.stdout = sys.stderr = open(os.devnull, "w")
    if role == "--main":
        import voice_input
        voice_input.main()
    elif role == "--history":
        import history
        history.run_window()
    elif role == "--settings":
        import settings
        settings.run_window()
    else:
        import saydown_guard
        saydown_guard.main()


if __name__ == "__main__":
    main()
