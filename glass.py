"""設定、歷史紀錄、詞庫視窗共用的白色玻璃風格。

做法：視窗底色用一個特定的淺灰（KEY），設成色鍵挖空，再對視窗開壓克力模糊，
挖空的地方就會透出模糊後的桌面，看起來像白色毛玻璃。內容放在白色圓角卡片上，字才清楚。
KEY 刻意選得和玻璃顏色接近，字的抗鋸齒邊緣混到 KEY 也不會有黑邊。
壓克力開不起來（舊版 Windows）時就不挖空，維持淺灰底色，一樣能用。
"""

import ctypes
import tkinter as tk
import paths
from tkinter import font as tkfont
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

KEY = "#eceef3"  # 玻璃（挖空）的顏色，任何元件都不要剛好用到這個顏色
CARD = "#ffffff"
FIELD = "#f6f7fb"  # 卡片裡的輸入框、文字框底色
LINE = "#e3e6ee"
INK = "#1d2433"
MUTED = "#6b7385"
ACCENT = "#4f5bd5"  # 靛藍，按鈕、開關、選取
ACCENT_HOVER = "#4350c4"
ACCENT_SOFT = "#e9ebfb"
DANGER = "#c2410c"
FONT_NAME = "Microsoft JhengHei UI"
FONT = (FONT_NAME, 10)
FONT_BOLD = (FONT_NAME, 10, "bold")
SECTION = (FONT_NAME, 9, "bold")
TITLE = (FONT_NAME, 17, "bold")
GLASS_TINT = 0xA6F6F3F2  # 壓克力的染色，格式是 AABBGGRR：約 65% 的偏冷白


class _Accent(ctypes.Structure):
    _fields_ = [("state", ctypes.c_int), ("flags", ctypes.c_int), ("color", ctypes.c_uint), ("anim", ctypes.c_int)]


class _CompositionData(ctypes.Structure):
    _fields_ = [("attr", ctypes.c_int), ("data", ctypes.c_void_p), ("size", ctypes.c_size_t)]


def dpi_aware():
    """要在建立 Tk 之前呼叫，字和圖示才不會糊。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def scale(widget):
    return widget.winfo_fpixels("1i") / 96


def apply(win):
    """把 Tk／Toplevel 視窗變成白色毛玻璃。"""
    win.configure(bg=KEY)
    try:
        win.iconbitmap(str(paths.ICO_PATH))
    except tk.TclError:
        pass
    win.update_idletasks()
    try:
        hwnd = int(win.wm_frame(), 16)
        accent = _Accent(4, 2, GLASS_TINT, 0)  # 4＝ACCENT_ENABLE_ACRYLICBLURBEHIND
        data = _CompositionData(19, ctypes.cast(ctypes.byref(accent), ctypes.c_void_p), ctypes.sizeof(accent))
        if ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data)):
            win.attributes("-transparentcolor", KEY)
    except Exception:
        pass  # 沒有壓克力就維持淺灰底色


def style(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", font=FONT, foreground=INK, background=CARD, bordercolor=LINE,
                lightcolor=LINE, darkcolor=LINE, focuscolor=ACCENT)

    s.configure("TButton", padding=(14, 6), width=-4, background=FIELD, foreground=INK, borderwidth=1, relief="flat")
    s.map("TButton", background=[("pressed", LINE), ("active", "#eef0f6")], bordercolor=[("focus", ACCENT)])
    s.configure("Accent.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT, font=FONT_BOLD)
    s.map("Accent.TButton", background=[("pressed", ACCENT_HOVER), ("active", ACCENT_HOVER)],
          bordercolor=[("active", ACCENT_HOVER)])
    s.configure("Glass.TButton", background=CARD)  # 放在玻璃上的按鈕用白底
    s.map("Glass.TButton", background=[("pressed", LINE), ("active", FIELD)])

    for name in ("TEntry", "TCombobox", "TSpinbox"):
        s.configure(name, fieldbackground=FIELD, background=FIELD, padding=(8, 5), arrowcolor=MUTED,
                    insertcolor=INK, borderwidth=1)
        s.map(name, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", FIELD), ("disabled", CARD)], foreground=[("disabled", MUTED)],
              background=[("readonly", FIELD), ("active", FIELD)], arrowcolor=[("active", ACCENT)])
        s.configure(name, lightcolor=FIELD, darkcolor=FIELD)  # 去掉立體感的亮暗邊
    s.configure("Glass.TEntry", fieldbackground=CARD)
    # 放進圓角外殼的下拉選單：自己不要再有邊框
    s.configure("Flat.TCombobox", bordercolor=FIELD, lightcolor=FIELD, darkcolor=FIELD, padding=(2, 3),
                fieldbackground=FIELD, background=FIELD)
    s.map("Flat.TCombobox", bordercolor=[("focus", FIELD)], lightcolor=[("focus", FIELD)],
          darkcolor=[("focus", FIELD)], fieldbackground=[("readonly", FIELD)], background=[("active", FIELD)],
          selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", INK)])
    root.option_add("*TCombobox*Listbox.font", FONT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_SOFT)
    root.option_add("*TCombobox*Listbox.selectForeground", INK)

    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # 拿掉外框
    s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=int(30 * scale(root)),
                borderwidth=0)
    s.map("Treeview", background=[("selected", ACCENT_SOFT)], foreground=[("selected", INK)])
    s.configure("Treeview.Heading", background=CARD, foreground=MUTED, font=SECTION, relief="flat",
                borderwidth=0, padding=(4, 6))
    s.map("Treeview.Heading", background=[("active", CARD)])

    # 細捲軸：沒有箭頭，只有圓潤的拇指
    s.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {
        "children": [("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})], "sticky": "ns"})])
    s.configure("Vertical.TScrollbar", troughcolor=CARD, background="#d6dae3", bordercolor=CARD,
                lightcolor="#d6dae3", darkcolor="#d6dae3", arrowsize=int(8 * scale(root)), gripcount=0)
    s.map("Vertical.TScrollbar", background=[("active", "#b9bfcc")])
    return s


def _rounded(w, h, radius, fill, outline, back, ss=3):
    """抗鋸齒圓角矩形，邊緣混到 back 色（通常是 KEY）。"""
    img = Image.new("RGB", (w * ss, h * ss), back)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius * ss, fill=outline)
    d.rounded_rectangle((ss, ss, w * ss - 1 - ss, h * ss - 1 - ss), radius * ss - ss, fill=fill)
    return img.resize((w, h), Image.LANCZOS)


class Card(tk.Canvas):
    """圓角卡片。內容放在 card.body。

    expand=False：卡片高度跟著內容；expand=True：內容填滿卡片（給 pack/paned 決定大小）。
    fill／outline 可改成輸入框的樣子（見 Field）。
    """

    def __init__(self, parent, expand=False, pad=14, radius=12, bg=KEY, fill=CARD, outline=LINE, padx=None):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0)
        s = scale(self)
        self.pad, self.radius, self.back, self.expand = int(pad * s), int(radius * s), bg, expand
        self.padx = int((pad if padx is None else padx) * s)
        self.fill, self.outline = fill, outline
        self.body = tk.Frame(self, bg=fill)
        self.item = self.create_window(self.padx, self.pad, window=self.body, anchor="nw")
        self.photo = None
        self.size = None
        self.bind("<Configure>", self._layout)
        if not expand:
            self.body.bind("<Configure>", self._fit)

    def _fit(self, _=None):
        self.configure(height=self.body.winfo_reqheight() + 2 * self.pad)
        if isinstance(self, Field):  # 輸入框寬度跟著內容；卡片則由 pack 的 fill 決定
            self.configure(width=self.body.winfo_reqwidth() + 2 * self.padx)

    def _layout(self, e=None):
        w, h = (e.width, e.height) if e else (self.winfo_width(), self.winfo_height())
        if w < 4 or h < 4 or (w, h, self.outline) == self.size:
            return
        self.size = (w, h, self.outline)
        self.itemconfigure(self.item, width=w - 2 * self.padx)
        if self.expand:
            self.itemconfigure(self.item, height=h - 2 * self.pad)
        self.photo = ImageTk.PhotoImage(_rounded(w, h, self.radius, self.fill, self.outline, self.back))
        self.delete("bg")
        self.create_image(0, 0, image=self.photo, anchor="nw", tags="bg")
        self.tag_lower("bg")

    def set_outline(self, color):
        self.outline = color
        self._layout()


class Field(Card):
    """圓角輸入框外殼：把 Entry、Text、Combobox 放進 field.body，取得焦點時外框變靛藍。"""

    def __init__(self, parent, expand=False, bg=CARD, fill=FIELD, pad=6, padx=10, radius=9):
        super().__init__(parent, expand=expand, pad=pad, padx=padx, radius=radius, bg=bg, fill=fill, outline=LINE)

    def watch(self, widget):
        widget.bind("<FocusIn>", lambda e: self.set_outline(ACCENT), add="+")
        widget.bind("<FocusOut>", lambda e: self.set_outline(LINE), add="+")
        return widget


def entry(parent, variable, width=20, bg=CARD, fill=FIELD):
    """圓角單行輸入框，回傳 (外殼, Entry)；外殼負責 pack。"""
    field = Field(parent, bg=bg, fill=fill, pad=5)
    e = tk.Entry(field.body, textvariable=variable, width=width, font=(FONT_NAME, 11), relief="flat", bd=0,
                 bg=fill, fg=INK, insertbackground=INK, selectbackground=ACCENT_SOFT, selectforeground=INK,
                 highlightthickness=0)
    e.pack(fill="x", ipady=1)
    field.watch(e)
    return field, e


def combo(parent, variable, values, width=18, state="readonly", bg=CARD):
    """圓角下拉選單，回傳 (外殼, Combobox)；外殼負責 pack。"""
    field = Field(parent, bg=bg, pad=3, padx=6)
    box = ttk.Combobox(field.body, textvariable=variable, values=values, state=state, width=width, font=FONT,
                       style="Flat.TCombobox")
    box.pack(fill="x")
    field.watch(box)
    return field, box


class Button(tk.Canvas):
    """圓角按鈕。kind：normal（淺灰）、accent（靛藍實心）、danger（淺灰底紅字）。"""

    def __init__(self, parent, text, command=None, kind="normal", bg=CARD, padx=16):
        s = scale(parent)
        self.font = tkfont.Font(family=FONT_NAME, size=10, weight="bold" if kind == "accent" else "normal")
        self.w = self.font.measure(text) + int(padx * 2 * s)
        self.h = int(32 * s)
        super().__init__(parent, width=self.w, height=self.h, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        on_glass = bg == KEY
        fills = {
            "accent": (ACCENT, ACCENT_HOVER, "#3a46b0"),
            "normal": (CARD, "#f6f7fb", "#eceef4") if on_glass else ("#eef0f6", "#e4e7f0", "#d9dde8"),
            "danger": (CARD, "#fbe9e2", "#f6d8cc") if on_glass else ("#eef0f6", "#fbe9e2", "#f6d8cc"),
        }[kind]
        ink = {"accent": "white", "normal": INK, "danger": DANGER}[kind]
        r = int(8 * s)
        self.images = [ImageTk.PhotoImage(_rounded(self.w, self.h, r, f, f, bg)) for f in fills]
        self.item = self.create_image(0, 0, anchor="nw", image=self.images[0])
        self.label = self.create_text(self.w // 2, self.h // 2, text=text, fill=ink, font=self.font)
        self.command = command
        self.bind("<Enter>", lambda e: self._show(1))
        self.bind("<Leave>", lambda e: self._show(0))
        self.bind("<ButtonPress-1>", lambda e: self._show(2))
        self.bind("<ButtonRelease-1>", self._release)

    def set_text(self, text):
        """換字（寬度不變，新字要和原本差不多長）。"""
        self.itemconfigure(self.label, text=text)

    def _show(self, i):
        self.itemconfigure(self.item, image=self.images[i])

    def _release(self, e):
        inside = 0 <= e.x < self.w and 0 <= e.y < self.h
        self._show(1 if inside else 0)
        if inside and self.command:
            self.command()


class Scrollbar(tk.Canvas):
    """細捲軸：圓頭拇指、沒有箭頭，內容不用捲動時自動隱藏。用法和 ttk.Scrollbar 一樣。"""

    def __init__(self, parent, command, bg=CARD):
        s = scale(parent)
        self.bw = int(10 * s)
        super().__init__(parent, width=self.bw, bg=bg, highlightthickness=0, bd=0)
        self.command, self.back = command, bg
        self.lo, self.hi = 0.0, 1.0
        self.photo, self.drag, self.hover = None, None, False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))

    def set(self, lo, hi):
        self.lo, self.hi = float(lo), float(hi)
        self._draw()

    def _hover(self, on):
        self.hover = on
        self._draw()

    def _draw(self):
        self.delete("all")
        h = self.winfo_height()
        if h < 4 or (self.lo <= 0 and self.hi >= 1):
            return
        w = self.bw - 4
        y0 = int(self.lo * h)
        y1 = max(int(self.hi * h), y0 + w * 3)
        color = "#b9bfcc" if self.hover or self.drag else "#d6dae3"
        self.photo = ImageTk.PhotoImage(_rounded(w, y1 - y0, w // 2, color, color, self.back))
        self.create_image(2, y0, anchor="nw", image=self.photo)

    def _press(self, e):
        h = self.winfo_height()
        if self.lo * h <= e.y <= self.hi * h:
            self.drag = (e.y, self.lo)
        else:  # 點空白處：直接跳到那裡
            self.command("moveto", e.y / h - (self.hi - self.lo) / 2)

    def _move(self, e):
        if self.drag:
            y, lo = self.drag
            self.command("moveto", lo + (e.y - y) / self.winfo_height())


class Toggle(tk.Canvas):
    """開關（取代勾選框）。用法和 ttk.Checkbutton 一樣：variable、command。"""

    def __init__(self, parent, variable, command=None, bg=CARD):
        s = scale(parent)
        self.w, self.h = int(38 * s), int(22 * s)
        super().__init__(parent, width=self.w, height=self.h, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.var, self.command, self.back = variable, command, bg
        self.images = {on: ImageTk.PhotoImage(self._draw(on)) for on in (False, True)}
        self.item = self.create_image(0, 0, anchor="nw")
        self.bind("<Button-1>", self._click)
        self.var.trace_add("write", lambda *_: self._refresh())
        self._refresh()

    def _draw(self, on):
        ss, w, h = 4, self.w, self.h
        img = Image.new("RGB", (w * ss, h * ss), self.back)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), h * ss // 2, fill=ACCENT if on else "#cfd4de")
        r = h * ss // 2 - 3 * ss
        cx = w * ss - h * ss // 2 if on else h * ss // 2
        d.ellipse((cx - r, h * ss // 2 - r, cx + r, h * ss // 2 + r), fill="white")
        return img.resize((w, h), Image.LANCZOS)

    def _refresh(self):
        self.itemconfigure(self.item, image=self.images[bool(self.var.get())])

    def _click(self, _):
        self.var.set(not self.var.get())
        if self.command:
            self.command()


def section(parent, text, bg=KEY):
    return tk.Label(parent, text=text, bg=bg, fg=MUTED, font=SECTION, anchor="w")


def text_box(parent, height=4, bg=CARD):
    """圓角多行文字框，回傳 (外殼, Text)；外殼負責 pack。"""
    field = Field(parent, expand=True, bg=bg, pad=8, padx=10)
    field.configure(height=int(height * 22 * scale(parent)))  # 畫布預設很高，會把下方按鈕擠掉
    t = tk.Text(field.body, height=height, wrap="word", font=(FONT_NAME, 11), bg=FIELD, fg=INK, relief="flat",
                bd=0, padx=2, pady=2, highlightthickness=0, selectbackground=ACCENT_SOFT, selectforeground=INK,
                insertbackground=INK)
    t.pack(fill="both", expand=True)
    field.watch(t)
    return field, t
