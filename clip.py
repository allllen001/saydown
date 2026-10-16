"""剪貼簿：完整備份與還原（含圖片等格式），以及不進 Win+V 歷史的文字寫入。"""

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.GetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.SetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.EnumClipboardFormats.argtypes = (wintypes.UINT,)
user32.EnumClipboardFormats.restype = wintypes.UINT
user32.RegisterClipboardFormatW.argtypes = (wintypes.LPCWSTR,)
user32.RegisterClipboardFormatW.restype = wintypes.UINT
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalSize.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
# 這些格式的資料不是記憶體區塊（或由系統自動從別的格式轉出），不能逐位元組複製
NON_HGLOBAL = {2, 3, 9, 14, 0x0080, 0x0081, 0x0082, 0x0083, 0x008E}
# 系統會從 CF_UNICODETEXT／CF_DIB 自動合成的格式，還原時跳過，避免重複
SYNTHESIZED = {1, 7, 17}  # CF_TEXT、CF_OEMTEXT、CF_DIBV5

EXCLUDE_HISTORY = user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")
NO_HISTORY = user32.RegisterClipboardFormatW("CanIncludeInClipboardHistory")
NO_CLOUD = user32.RegisterClipboardFormatW("CanUploadToCloudClipboard")


def _open(retries=20):
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)  # 其他程式正在用剪貼簿
    return False


def sequence():
    return user32.GetClipboardSequenceNumber()


def _alloc(data):
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
    if not handle:
        raise MemoryError("剪貼簿記憶體配置失敗")
    ptr = kernel32.GlobalLock(handle)
    if not ptr:  # 寫入空指標會讓整個程序當掉，try/except 也擋不住
        kernel32.GlobalFree(handle)
        raise MemoryError("剪貼簿記憶體鎖定失敗")
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    return handle


def snapshot():
    """把剪貼簿目前所有能複製的格式存起來。打不開時回傳 None。"""
    if not _open():
        return None
    items = []
    try:
        fmt = 0
        while True:
            fmt = user32.EnumClipboardFormats(fmt)
            if not fmt:
                break
            if fmt in NON_HGLOBAL or fmt in SYNTHESIZED:
                continue
            handle = user32.GetClipboardData(fmt)
            if not handle:
                continue
            size = kernel32.GlobalSize(handle)
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                continue
            try:
                items.append((fmt, ctypes.string_at(ptr, size)))
            finally:
                kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    return items


def restore(items):
    if items is None or not _open():
        return
    try:
        user32.EmptyClipboard()
        for fmt, data in items:
            try:
                handle = _alloc(data)
            except MemoryError:
                continue  # 這個格式放不回去就跳過，其餘照常還原
            if not user32.SetClipboardData(fmt, handle):
                kernel32.GlobalFree(handle)
        # 還原的內容是使用者原本就有的，不要再進 Win+V 歷史一次
        _mark_private()
    finally:
        user32.CloseClipboard()


def _mark_private():
    zero = (0).to_bytes(4, "little")
    for fmt, data in ((EXCLUDE_HISTORY, b""), (NO_HISTORY, zero), (NO_CLOUD, zero)):
        handle = _alloc(data)
        if not user32.SetClipboardData(fmt, handle):
            kernel32.GlobalFree(handle)


def set_text(text):
    """寫入文字，並標記成不進 Win+V 歷史、不上傳雲端剪貼簿。"""
    if not _open():
        raise OSError("剪貼簿被其他程式占用")
    try:
        user32.EmptyClipboard()
        handle = _alloc((text + "\0").encode("utf-16-le"))
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise OSError("無法寫入剪貼簿")
        _mark_private()
    finally:
        user32.CloseClipboard()


def get_text():
    if not _open():
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
