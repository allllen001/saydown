"""滑鼠側鍵／中鍵當快捷鍵：低階滑鼠 hook，綁定的按鍵會被吃掉，不會觸發瀏覽器上一頁。"""

import ctypes
import logging
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C
WATCHED = {WM_MBUTTONDOWN, WM_MBUTTONUP, WM_XBUTTONDOWN, WM_XBUTTONUP}


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class MouseEvent:
    """仿 keyboard.KeyboardEvent，讓滑鼠鍵可以走同一套快捷鍵邏輯。"""

    def __init__(self, name, event_type):
        self.name = name
        self.event_type = event_type


def button_name(msg, mouse_data):
    if msg in (WM_MBUTTONDOWN, WM_MBUTTONUP):
        return "mouse middle"
    return "mouse x1" if (mouse_data >> 16) == 1 else "mouse x2"


def start(names, callback):
    """names：要攔截的按鍵（例如 {"mouse x2"}）；callback(event) 回傳 False 代表吃掉。"""

    def proc(code, wparam, lparam):
        if code == 0 and wparam in WATCHED:
            info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            name = button_name(wparam, info.mouseData)
            if name in names:
                down = wparam in (WM_MBUTTONDOWN, WM_XBUTTONDOWN)
                try:
                    if callback(MouseEvent(name, "down" if down else "up")) is False:
                        return 1
                except Exception:
                    pass
        return user32.CallNextHookEx(None, code, wparam, lparam)

    handle = MouseHook()

    def loop():
        handle.thread_id = kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        # 先建立訊息佇列，否則剛啟動就呼叫 stop() 時 WM_QUIT 會送不到
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # PM_NOREMOVE
        hook_proc = HOOKPROC(proc)  # 保留參照，避免被回收
        hook = user32.SetWindowsHookExW(14, hook_proc, None, 0)  # WH_MOUSE_LL
        handle.ready.set()
        if not hook:
            logging.getLogger("voice_input").error("滑鼠快捷鍵註冊失敗")
            return
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(hook)

    threading.Thread(target=loop, daemon=True, name="mousehook").start()
    handle.ready.wait(2)
    return handle


class MouseHook:
    def __init__(self):
        self.thread_id = 0
        self.ready = threading.Event()

    def stop(self):
        """結束 hook 執行緒的訊息迴圈，順便解除 hook（換快捷鍵時用）。"""
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)  # WM_QUIT
