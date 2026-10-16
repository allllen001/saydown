"""螢幕下方中央的浮動狀態列：錄音時顯示音量條，處理時顯示進度。

錄音中如果有即時預覽，狀態列上方會多一個泡泡，顯示最近聽到的字。

畫面用 Pillow 畫（抗鋸齒、柔和陰影），再用 UpdateLayeredWindow 以逐像素透明貼到螢幕。
風格和設定視窗一樣是白色毛玻璃：Windows 的壓克力模糊只能套整個矩形，圓角外也會糊掉，
所以改成自己做——把視窗設成「截圖時看不到」，就能持續擷取正下方的畫面，模糊後填進圓角形狀再蓋一層白。
視窗設為「不搶焦點、滑鼠可穿透」，所以不會影響文字貼到原本的游標位置。
Tk 只負責事件迴圈，必須在自己的執行緒裡運作，其他執行緒只能透過 show()/hide() 等方法丟指令進來。
"""

import ctypes
import math
import queue
import threading
import time
import traceback
import tkinter as tk
from ctypes import wintypes

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageGrab

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
ULW_ALPHA = 2
AC_SRC_ALPHA = 1

# 顏色和 glass.py（設定、歷史紀錄視窗）一致
TINT = (246, 247, 251, 208)  # 蓋在模糊背景上的白
EDGE_LIGHT = (255, 255, 255, 230)  # 玻璃內緣的亮線
EDGE_DARK = (29, 36, 51, 34)  # 玻璃外緣的細線，在淺色背景上也看得出邊界
FG = (29, 36, 51)  # glass.INK
SUB = (107, 115, 133)  # glass.MUTED
ROSE = (232, 54, 88)
ACCENT = (79, 91, 213)  # glass.ACCENT
GREEN = (35, 154, 114)  # 和 Saydown 圖示的綠一致，表示「學到了」
WDA_EXCLUDEFROMCAPTURE = 0x11
BLUR_REFRESH = 0.2  # 背後畫面多久重新擷取一次（秒）

BARS = 14
FONTS = r"C:\Windows\Fonts"
FADE = 0.14  # 出現／消失的淡入淡出秒數


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


# 64 位元下 HDC／HBITMAP 是指標，不宣告型別會被截斷
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
    wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
    ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD,
]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE, wintypes.DWORD,
]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]


def font(name, px):
    try:
        return ImageFont.truetype(f"{FONTS}\\{name}", px)
    except OSError:
        return ImageFont.truetype(f"{FONTS}\\msjh.ttc", px)


def with_alpha(img, factor):
    """整張圖的不透明度乘上 factor（0~1）。"""
    if factor >= 1:
        return img
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda a: int(a * factor)))
    return out


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


class Overlay:
    def __init__(self, level_getter):
        self.level_getter = level_getter  # 回傳 0~1 的目前音量
        self.limit = 540  # 錄音上限（秒），最後 60 秒改成倒數
        self.cmds = queue.Queue()
        self.state = "hidden"
        self.label = ""
        self.since = 0.0
        self.hide_at = None
        self.levels = [0.0] * BARS
        self.preview_text = ""
        self.preview_since = 0.0
        self.closing = None  # 淡出中：(開始時間, 最後一格畫面)
        self.cache = {}
        self.backdrop = None
        self.grabbed_at = 0.0
        self.live_backdrop = False  # 視窗能從截圖中排除時，才能邊顯示邊擷取背後畫面
        self.grabbing = False
        threading.Thread(target=self._run, daemon=True).start()

    # ---------- 給其他執行緒呼叫 ----------

    def recording(self, label):
        self.cmds.put(("recording", label, None))

    def relabel(self, label):
        """錄音中途只換文字，不重設計時與音量條。"""
        self.cmds.put(("relabel", label, None))

    def preview(self, text):
        """錄音中即時辨識到的字，顯示在狀態列上方；錄音結束自動清掉。"""
        self.cmds.put(("preview", text, None))

    def processing(self, label):
        self.cmds.put(("processing", label, None))

    def flash(self, label, seconds=1.5):
        """短暫顯示訊息後自動消失，例如錄音太短、沒聽到聲音。"""
        self.cmds.put(("flash", label, seconds))

    def learned(self, words, seconds=6):
        """自動學詞成功：綠色勾勾＋學到的詞，比一般 flash 醒目、停留較久。"""
        self.cmds.put(("learned", words, seconds))

    def hide(self):
        self.cmds.put(("hidden", "", None))

    # ---------- Tk 執行緒 ----------

    def _run(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.root = root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)

        s = root.winfo_fpixels("1i") / 96  # DPI 縮放倍率
        self.s = s
        self.m = int(18 * s)  # 四周留給陰影的空間
        self.pw, self.ph = int(380 * s), int(46 * s)  # 狀態列（膠囊）
        self.bmax, self.bh = int(620 * s), int(42 * s)  # 預覽泡泡的最大寬度與高度
        self.gap = int(10 * s)
        self.W = self.bmax + 2 * self.m
        self.H = self.bh + self.gap + self.ph + 2 * self.m
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        # 狀態列底部和改版前一樣在螢幕底往上 90 單位
        self.x = (sw - self.W) // 2
        self.y = sh - int(90 * s) - (self.H - self.m)
        root.geometry(f"{self.W}x{self.H}+{self.x}+{self.y}")

        self.f_label = font("msjhbd.ttc", int(14 * s))
        self.f_timer = font("seguisb.ttf", int(13 * s))
        self.f_text = font("msjh.ttc", int(15 * s))

        root.update_idletasks()
        self.hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            self.hwnd,
            GWL_EXSTYLE,
            style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST,
        )
        user32.ShowWindow(self.hwnd, SW_HIDE)
        # Windows 10 2004 以後可讓視窗不出現在截圖裡；做不到就只在顯示前擷取一次背景
        self.live_backdrop = bool(user32.SetWindowDisplayAffinity(self.hwnd, WDA_EXCLUDEFROMCAPTURE))
        self._init_surface()
        self._tick()
        root.mainloop()

    def _init_surface(self):
        """建立一塊和視窗一樣大的 32 位元點陣圖，之後每格畫面都寫進這裡再貼到螢幕。"""
        self.screen_dc = user32.GetDC(None)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)
        bmi = BITMAPINFOHEADER(
            ctypes.sizeof(BITMAPINFOHEADER), self.W, -self.H, 1, 32, 0, 0, 0, 0, 0, 0
        )
        self.bits = ctypes.c_void_p()
        bmp = gdi32.CreateDIBSection(self.mem_dc, ctypes.byref(bmi), 0, ctypes.byref(self.bits), None, 0)
        gdi32.SelectObject(self.mem_dc, bmp)

    def _present(self, img, opacity=1.0):
        a = np.asarray(img, dtype=np.uint16)
        alpha = a[..., 3:4]
        bgra = np.empty((self.H, self.W, 4), np.uint8)
        bgra[..., :3] = (a[..., 2::-1] * alpha // 255).astype(np.uint8)  # RGB→BGR 並預乘 alpha
        bgra[..., 3] = a[..., 3]
        ctypes.memmove(self.bits, bgra.ctypes.data, bgra.nbytes)
        blend = BLENDFUNCTION(0, 0, max(0, min(255, int(255 * opacity))), AC_SRC_ALPHA)
        for _ in range(2):
            if user32.UpdateLayeredWindow(
                self.hwnd, self.screen_dc,
                ctypes.byref(wintypes.POINT(self.x, self.y)), ctypes.byref(wintypes.SIZE(self.W, self.H)),
                self.mem_dc, ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA,
            ):
                return
            # Tk 進入事件迴圈後會對視窗呼叫 SetLayeredWindowAttributes，之後 UpdateLayeredWindow
            # 一律回錯誤 87；拿掉分層樣式再加回去就能重設，改回逐像素透明
            style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style & ~WS_EX_LAYERED)
            user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)

    def _tick(self):
        try:
            while True:
                state, label, seconds = self.cmds.get_nowait()
                self._set(state, label, seconds)
        except queue.Empty:
            pass
        if self.hide_at and time.time() >= self.hide_at:
            self._set("hidden", "", None)
        try:
            if self.closing:
                t = (time.time() - self.closing[0]) / FADE
                if t >= 1:
                    self.closing = None
                    user32.ShowWindow(self.hwnd, SW_HIDE)
                else:
                    self._present(self.closing[1], 1 - ease(t))
            elif self.state != "hidden":
                if self.live_backdrop and not self.grabbing and time.time() - self.grabbed_at > BLUR_REFRESH:
                    # 擷取＋模糊約 30 ms，放背景做，動畫才不會頓
                    self.grabbing = True
                    threading.Thread(target=self._grab_backdrop, daemon=True).start()
                self.last_frame = self._draw()
                self._present(self.last_frame, ease((time.time() - self.shown_at) / FADE))
        except Exception:  # 畫面出錯不能讓 Tk 迴圈停掉，下一格再試；同樣的錯只印一次
            err = traceback.format_exc()
            if err != getattr(self, "last_error", None):
                self.last_error = err
                print(err, flush=True)
        self.root.after(16 if self.closing else 33, self._tick)

    def _set(self, state, label, seconds):
        if state == "relabel":
            self.label = label
            return
        if state == "preview":
            if self.state == "recording":  # 錄音結束後才到的舊預覽不顯示
                if not self.preview_text:
                    self.preview_since = time.time()
                self.preview_text = label
            return
        self.preview_text = ""
        was_hidden = self.state == "hidden"
        self.state, self.label = state, label
        self.since = time.time()
        self.hide_at = time.time() + seconds if seconds else None
        if state == "recording":
            self.levels = [0.0] * BARS
        if state == "hidden":
            if not was_hidden and getattr(self, "last_frame", None) is not None:
                self.closing = (time.time(), self.last_frame)
        elif was_hidden or self.closing:
            self.closing = None
            self.shown_at = time.time()
            self._grab_backdrop()  # 視窗還沒顯示，擷取到的一定是乾淨的背景
            self.last_frame = self._draw()
            self._present(self.last_frame, 0)
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)

    # ---------- 繪圖 ----------

    def _grab_backdrop(self):
        """擷取視窗正下方的畫面並模糊，當作毛玻璃透出來的背景。"""
        try:
            img = ImageGrab.grab(bbox=(self.x, self.y, self.x + self.W, self.y + self.H))
            small = img.resize((max(1, self.W // 6), max(1, self.H // 6)), Image.BILINEAR)
            small = ImageEnhance.Color(small.filter(ImageFilter.GaussianBlur(2.5))).enhance(1.1)
            self.backdrop = small.resize((self.W, self.H), Image.BICUBIC).convert("RGBA")
        except OSError:  # 鎖定畫面、UAC 時擷取不到，沿用上一張
            pass
        finally:
            self.grabbed_at = time.time()
            self.grabbing = False

    def _glass(self, w, h, radius):
        """同尺寸的陰影、形狀遮罩、白色玻璃面只畫一次。"""
        key = ("glass", w, h, radius)
        if key not in self.cache:
            m, ss = self.m, 3  # 3 倍超取樣做抗鋸齒
            shadow = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).rounded_rectangle(
                (m, m + int(5 * self.s), m + w, m + h + int(5 * self.s)), radius, fill=(20, 24, 40, 70)
            )
            shadow = shadow.filter(ImageFilter.GaussianBlur(10 * self.s))
            big_mask = Image.new("L", (w * ss, h * ss), 0)
            ImageDraw.Draw(big_mask).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius * ss, fill=255)
            mask = big_mask.resize((w, h), Image.LANCZOS)
            big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
            d = ImageDraw.Draw(big)
            d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius * ss, fill=TINT, outline=EDGE_DARK, width=ss)
            d.rounded_rectangle((ss, ss, w * ss - 1 - ss, h * ss - 1 - ss), radius * ss - ss,
                                outline=EDGE_LIGHT, width=ss)
            self.cache[key] = (shadow, mask, big.resize((w, h), Image.LANCZOS))
        return self.cache[key]

    def _put_glass(self, frame, x, y, w, h, radius, opacity=1.0):
        """在 (x, y)（陰影外框的左上角）畫一塊白色毛玻璃。"""
        shadow, mask, face = self._glass(w, h, radius)
        frame.alpha_composite(with_alpha(shadow, opacity), (x, y))
        gx, gy = x + self.m, y + self.m
        if self.backdrop is not None:
            blur = self.backdrop.crop((gx, gy, gx + w, gy + h))
            blur.putalpha(mask if opacity >= 1 else mask.point(lambda a: int(a * opacity)))
            frame.alpha_composite(blur, (gx, gy))
        frame.alpha_composite(with_alpha(face, opacity), (gx, gy))

    def _dot(self, r, color, alpha=255):
        key = ("dot", r, color)
        if key not in self.cache:
            ss = 4
            big = Image.new("RGBA", (2 * r * ss, 2 * r * ss), (0, 0, 0, 0))
            ImageDraw.Draw(big).ellipse((0, 0, 2 * r * ss - 1, 2 * r * ss - 1), fill=color + (255,))
            self.cache[key] = big.resize((2 * r, 2 * r), Image.LANCZOS)
        return with_alpha(self.cache[key], alpha / 255)

    def _halo(self, r, color):
        key = ("halo", r, color)
        if key not in self.cache:
            size = 4 * r
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            ImageDraw.Draw(img).ellipse((r, r, 3 * r, 3 * r), fill=color + (200,))
            self.cache[key] = img.filter(ImageFilter.GaussianBlur(r * 0.6))
        return self.cache[key]

    def _bubble(self, text):
        """預覽泡泡的文字層：太長時只留結尾，左邊漸隱，像即時字幕。回傳（泡泡寬度, 文字層）。"""
        key = ("bubble", text)
        if key in self.cache:
            return self.cache[key]
        for k in [k for k in self.cache if k[0] == "bubble"]:
            del self.cache[k]  # 預覽一直在變，只留最新一句
        s, f = self.s, self.f_text
        pad = int(20 * s)
        room = self.bmax - 2 * pad
        tw = int(f.getlength(text))
        w = min(self.bmax, max(self.bh * 2, tw + 2 * pad))
        img = Image.new("RGBA", (w, self.bh), (0, 0, 0, 0))
        inner = min(tw, room)
        layer = Image.new("RGBA", (inner, self.bh), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(
            (inner - tw, self.bh // 2), text, font=f, fill=FG + (255,), anchor="lm"
        )
        if tw > room:  # 左邊 48 單位漸隱
            fade = int(48 * s)
            ramp = np.ones(inner, np.float32)
            ramp[:fade] = np.linspace(0, 1, fade) ** 1.5
            a = np.asarray(layer.getchannel("A"), np.float32) * ramp
            layer.putalpha(Image.fromarray(a.astype(np.uint8)))
        img.alpha_composite(layer, (pad, 0))
        self.cache[key] = (w, img)
        return self.cache[key]

    def _draw(self):
        s, m = self.s, self.m
        now = time.time()
        frame = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))

        text = " ".join(self.preview_text.split())
        if self.state == "recording" and text:
            bw_, layer = self._bubble(text)
            t = ease((now - self.preview_since) / 0.2)
            rise = int((1 - t) * 6 * s)  # 出現時從下方微微浮上來
            bx = (self.W - bw_) // 2 - m
            self._put_glass(frame, bx, rise, bw_, self.bh, int(14 * s), t)
            frame.alpha_composite(with_alpha(layer, t), (bx + m, rise + m))

        pw, ph = self.pw, self.ph
        px, py = (self.W - pw) // 2 - m, self.H - ph - 2 * m
        self._put_glass(frame, px, py, pw, ph, ph // 2)
        x0, y0 = px + m, py + m  # 狀態列內容的左上角
        cy = y0 + ph // 2
        d = ImageDraw.Draw(frame)
        elapsed = now - self.since

        if self.state == "recording":
            # 柔和呼吸的紅點
            r = int(5 * s)
            cx = x0 + int(24 * s)
            pulse = (math.sin(elapsed * math.pi * 1.6) + 1) / 2
            halo = with_alpha(self._halo(r, ROSE), 0.25 + 0.45 * pulse)
            frame.alpha_composite(halo, (cx - 2 * r, cy - 2 * r))
            frame.alpha_composite(self._dot(r, ROSE), (cx - r, cy - r))
            d.text((cx + int(16 * s), cy), self.label, font=self.f_label, fill=FG + (255,), anchor="lm")

            # 音量條：圓頭、會慢慢回落，越大聲越亮
            level = min(1.0, self.level_getter() * 12)
            self.levels = self.levels[1:] + [max(level, self.levels[-1] * 0.72)]
            bw, gap, ss = int(3 * s), int(3 * s), 3
            bars_w = BARS * (bw + gap) - gap
            maxh = ph - int(22 * s)
            strip = Image.new("RGBA", (bars_w * ss, maxh * ss), (0, 0, 0, 0))
            sd = ImageDraw.Draw(strip)
            for i, lv in enumerate(self.levels):
                bh = max(bw, int(lv * maxh)) * ss
                bx = i * (bw + gap) * ss
                top = (maxh * ss - bh) // 2
                sd.rounded_rectangle(
                    (bx, top, bx + bw * ss - 1, top + bh - 1), bw * ss // 2,
                    fill=ROSE + (int(140 + 115 * lv),),
                )
            right = x0 + pw - int(22 * s)
            frame.alpha_composite(strip.resize((bars_w, maxh), Image.LANCZOS), (right - bars_w, cy - maxh // 2))

            remaining = self.limit - elapsed
            if remaining <= 60:  # 和 Typeless 一樣，快到上限時倒數
                label, color = f"剩 0:{max(0, int(remaining)):02d}", ROSE
                f = self.f_label
            else:
                mm, sec = divmod(int(elapsed), 60)
                label, color, f = f"{mm}:{sec:02d}", SUB, self.f_timer
            d.text((right - bars_w - int(12 * s), cy), label, font=f, fill=color + (255,), anchor="rm")
        elif self.state == "processing":
            # 三個點依序亮起、微微跳動
            r = int(3.5 * s)
            for i in range(3):
                phase = (math.sin(elapsed * 7 - i * 0.9) + 1) / 2
                cx = x0 + int(18 * s) + i * int(10 * s)
                lift = int(phase * 3 * s)
                frame.alpha_composite(
                    self._dot(r, ACCENT, int(90 + 165 * phase)), (cx - r, cy - r - lift)
                )
            d.text((x0 + int(52 * s), cy), self.label, font=self.f_label, fill=FG + (255,), anchor="lm")
        elif self.state == "learned":
            # 綠色圓底白勾，出現時微微彈一下
            pop = 1 + 0.25 * max(0.0, 1 - elapsed / 0.25) * math.sin(min(elapsed, 0.25) / 0.25 * math.pi)
            r = int(9 * s * pop)
            cx = x0 + int(26 * s)
            frame.alpha_composite(self._dot(r, GREEN), (cx - r, cy - r))
            w = max(2, int(2 * s))
            d.line([(cx - r * 0.45, cy + r * 0.02), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.48, cy - r * 0.34)],
                   fill=(255, 255, 255, 255), width=w, joint="curve")
            tx = cx + int(18 * s)
            d.text((tx, cy), "已加入詞庫", font=self.f_label, fill=GREEN + (255,), anchor="lm")
            words = self.label
            wx = tx + int(d.textlength("已加入詞庫", font=self.f_label)) + int(12 * s)
            room = x0 + pw - int(20 * s) - wx
            while words and d.textlength(words, font=self.f_label) > room:  # 太多詞就截斷
                words = words[:-2] + "…" if len(words) > 2 else ""
            d.text((wx, cy), words, font=self.f_label, fill=FG + (255,), anchor="lm")
        else:  # flash
            d.text((x0 + pw // 2, cy), self.label, font=self.f_label, fill=ACCENT + (255,), anchor="mm")
        return frame
