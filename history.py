"""Saydown的本機歷史紀錄：SQLite 存在資料夾（原始碼執行時是程式資料夾，安裝版是 %APPDATA% 的 Saydown 資料夾），不上傳。

直接執行這個檔案會開啟歷史紀錄視窗（由系統匣選單以獨立程序開啟）。
"""

import json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timedelta

import paths

paths.ensure_data()
BASE = paths.DATA
DB_PATH = BASE / "history.db"
CONFIG_PATH = paths.CONFIG_PATH

MODE_LABELS = {
    "cleanup": "修稿",
    "formal": "正式語氣",
    "english": "翻成英文",
    "ask": "Ask",
    "chat": "聊天語氣",
    "edit": "改寫",
}


LANGUAGE_NAMES = {"en": "英文", "ja": "日文", "ko": "韓文", "vi": "越南文", "id": "印尼文", "th": "泰文",
                  "es": "西班牙文", "fr": "法文", "de": "德文"}


def mode_label(mode):
    if mode.startswith("translate:"):
        return "翻成" + LANGUAGE_NAMES.get(mode.split(":", 1)[1], "外文")
    return MODE_LABELS.get(mode, mode)


def connect():
    db = sqlite3.connect(DB_PATH, timeout=5)
    db.execute(
        """CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY,
            created_at REAL NOT NULL,
            mode TEXT NOT NULL,
            app TEXT NOT NULL DEFAULT '',
            raw_text TEXT NOT NULL,
            selected_text TEXT NOT NULL DEFAULT '',
            result_text TEXT NOT NULL,
            audio_seconds REAL NOT NULL DEFAULT 0,
            asr_seconds REAL NOT NULL DEFAULT 0,
            llm_seconds REAL NOT NULL DEFAULT 0
        )"""
    )
    db.execute("CREATE INDEX IF NOT EXISTS history_created ON history(created_at)")
    # 每日統計另外存：歷史紀錄只留 30 天，統計要能一直累計
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'daily_stats'").fetchone()
    if not exists:
        db.execute(
            """CREATE TABLE daily_stats (
                day TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                words INTEGER NOT NULL DEFAULT 0,
                audio_seconds REAL NOT NULL DEFAULT 0
            )"""
        )
        db.execute(  # 第一次建立時，用還留著的歷史紀錄補上過去的資料
            "INSERT INTO daily_stats SELECT date(created_at, 'unixepoch', 'localtime'), COUNT(*),"
            " SUM(LENGTH(result_text)), SUM(audio_seconds) FROM history GROUP BY 1"
        )
        db.commit()
    return db


def add(mode, app, raw, selected, result, audio_s, asr_s, llm_s, keep_days=30):
    with connect() as db:
        db.execute(
            "INSERT INTO history (created_at, mode, app, raw_text, selected_text, result_text,"
            " audio_seconds, asr_seconds, llm_seconds) VALUES (?,?,?,?,?,?,?,?,?)",
            (time.time(), mode, app, raw, selected, result, audio_s, asr_s, llm_s),
        )
        db.execute(
            "INSERT INTO daily_stats VALUES (date('now', 'localtime'), 1, ?, ?) ON CONFLICT(day) DO UPDATE SET"
            " count = count + 1, words = words + excluded.words, audio_seconds = audio_seconds + excluded.audio_seconds",
            (len(result), audio_s),
        )
        if keep_days:
            db.execute("DELETE FROM history WHERE created_at < ?", (time.time() - keep_days * 86400,))
    db.close()


TYPING_PER_MINUTE = 40  # 估算省下時間用：一般人打中文每分鐘約 40 字


def period_stats(db):
    """今天、本週（週一起算）、本月、累計的次數、字數、錄音秒數與省下的分鐘數。"""
    today = datetime.now().date()
    starts = {
        "今天": today,
        "本週": today - timedelta(days=today.weekday()),
        "本月": today.replace(day=1),
        "累計": datetime(1970, 1, 1).date(),
    }
    out = {}
    for name, start in starts.items():
        count, words, audio = db.execute(
            "SELECT COALESCE(SUM(count),0), COALESCE(SUM(words),0), COALESCE(SUM(audio_seconds),0)"
            " FROM daily_stats WHERE day >= ?", (start.isoformat(),)
        ).fetchone()
        saved = max(0.0, words / TYPING_PER_MINUTE - audio / 60)
        out[name] = (count, words, audio, saved)
    return out


def daily_words(db, days=14):
    """最近幾天每天的字數（沒用的日子補 0），由舊到新。"""
    today = datetime.now().date()
    rows = dict(db.execute("SELECT day, words FROM daily_stats WHERE day >= ?",
                           ((today - timedelta(days=days - 1)).isoformat(),)).fetchall())
    return [(d, rows.get(d.isoformat(), 0)) for d in (today - timedelta(days=i) for i in range(days - 1, -1, -1))]


def fmt_minutes(minutes):
    minutes = int(round(minutes))
    if minutes < 60:
        return f"{minutes} 分鐘"
    return f"{minutes // 60} 小時 {minutes % 60} 分"


def open_stats(parent):
    import tkinter as tk

    import glass

    db = connect()
    win = tk.Toplevel(parent)
    win.title("Saydown・統計")
    sc = glass.scale(win)
    win.geometry(f"{int(560 * sc)}x{int(600 * sc)}+{parent.winfo_rootx() + int(80 * sc)}+{parent.winfo_rooty() + int(40 * sc)}")
    win.transient(parent)
    glass.apply(win)
    BG, PANEL, INK, MUTED = glass.KEY, glass.CARD, glass.INK, glass.MUTED

    tk.Label(win, text="統計", bg=BG, fg=INK, font=glass.TITLE, anchor="w").pack(fill="x", padx=22, pady=(16, 8))

    # 期間 × 指標的小表：一列一個期間
    table = glass.Card(win)
    table.pack(fill="x", padx=14)
    grid = table.body
    heads = ("", "口述次數", "字數", "錄音時間", "省下時間")
    for c, h in enumerate(heads):
        tk.Label(grid, text=h, bg=PANEL, fg=MUTED, font=glass.SECTION, anchor="e" if c else "w").grid(
            row=0, column=c, sticky="ew", padx=(0, 6), pady=(0, 6))
    for r, (name, (count, words, audio, saved)) in enumerate(period_stats(db).items(), start=1):
        values = (name, f"{count:,}", f"{words:,}", fmt_minutes(audio / 60), fmt_minutes(saved))
        for c, v in enumerate(values):
            tk.Label(grid, text=v, bg=PANEL, fg=INK, anchor="e" if c else "w",
                     font=glass.FONT_BOLD if c == 4 else glass.FONT).grid(row=r, column=c, sticky="ew", padx=(0, 6),
                                                                         pady=3)
    for c in range(len(heads)):
        grid.columnconfigure(c, weight=1)

    glass.section(win, "最近 14 天的字數").pack(fill="x", padx=24, pady=(14, 4))
    chart_card = glass.Card(win, expand=True)
    chart_card.pack(fill="both", expand=True, padx=14)
    canvas = tk.Canvas(chart_card.body, bg=PANEL, highlightthickness=0, bd=0)
    canvas.pack(fill="both", expand=True)
    tip = tk.Label(chart_card.body, bg=PANEL, fg=INK, font=glass.FONT, anchor="w")
    tip.pack(fill="x", pady=(6, 0))
    tk.Label(win, text=f"省下時間以打字每分鐘 {TYPING_PER_MINUTE} 字估算", bg=BG, fg=MUTED, font=glass.FONT,
             anchor="w").pack(fill="x", padx=24, pady=(6, 12))

    data = daily_words(db)
    bars = []

    def draw(_=None):
        from PIL import Image, ImageDraw, ImageTk

        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 50 or h < 50:
            return
        canvas.delete("all")
        bars.clear()
        bottom_pad, top_pad = int(22 * sc), int(18 * sc)
        plot_h = h - bottom_pad - top_pad
        peak = max([v for _, v in data] + [1])
        # 刻度：三格，每格取 1、2、5 乘 10 的次方，數字才好讀
        raw = peak / 3
        mag = 10 ** max(0, len(str(int(raw))) - 1)
        step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)
        top = step * 3
        for i in range(1, 4):
            y = top_pad + plot_h - plot_h * i / 3
            canvas.create_line(0, y, w, y, fill="#eef0f5")
            canvas.create_text(0, y - 2, text=f"{step * i:,}", anchor="sw", fill=MUTED,
                               font=(glass.FONT_NAME, 8))
        canvas.create_line(0, top_pad + plot_h, w, top_pad + plot_h, fill=glass.LINE)
        slot = w / len(data)
        bw = max(4, int(slot * 0.56))
        ss = 3
        img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = int(4 * sc) * ss  # 長條頂端 4px 圓角、底部貼齊基線
        today = datetime.now().date()
        for i, (day, v) in enumerate(data):
            x0 = int(i * slot + (slot - bw) / 2)
            bh = int(plot_h * v / top) if v else 0
            y0 = top_pad + plot_h - bh
            bars.append((x0, x0 + bw, day, v))
            if bh:
                box = (x0 * ss, y0 * ss, (x0 + bw) * ss, (top_pad + plot_h) * ss)
                d.rounded_rectangle(box, min(r, bh * ss // 2), fill=glass.ACCENT)
                d.rectangle((box[0], max(box[1], box[3] - r), box[2], box[3]), fill=glass.ACCENT)
            if (len(data) - 1 - i) % 2 == 0:  # 日期標籤從今天往回隔一天一個
                label = "今天" if day == today else f"{day.month}/{day.day}"
                canvas.create_text(x0 + bw / 2, h - 4, text=label, anchor="s", fill=MUTED, font=(glass.FONT_NAME, 8))
        canvas.photo = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))
        canvas.tag_raise(canvas.create_image(0, 0, image=canvas.photo, anchor="nw"))  # 長條蓋在格線上，標籤不受影響

    def hover(e):
        for x0, x1, day, v in bars:
            if x0 - 4 <= e.x <= x1 + 4:  # 感應範圍比長條寬一點
                tip.config(text=f"{day.month}/{day.day}　{v:,} 字")
                return
        tip.config(text="")

    canvas.bind("<Configure>", draw)
    canvas.bind("<Motion>", hover)
    canvas.bind("<Leave>", lambda e: tip.config(text=""))
    win.bind("<Escape>", lambda e: win.destroy())


def load_dictionary():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f).get("dictionary", [])


def save_dictionary(words):
    """只改 config.json 的 dictionary，其他設定原樣保留；Saydown下次處理時會自動讀到。"""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["dictionary"] = words
    tmp = CONFIG_PATH.with_name(f"config.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    for attempt in range(10):  # Saydown正在讀設定檔時 Windows 會拒絕取代，稍後重試
        try:
            os.replace(tmp, CONFIG_PATH)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05)


def add_word(word):
    word = word.strip()
    if not word:
        return False
    words = load_dictionary()
    if word in words:
        return False
    save_dictionary(words + [word])
    return True


# ---------- 視窗 ----------


def open_import(parent, on_added):
    """選一份 Word／PDF／文字檔，挑出候選詞讓使用者勾選後加入詞庫。分析在背景執行緒跑。"""
    import queue
    import tkinter as tk
    from tkinter import filedialog, ttk

    import glass
    import importer

    path = filedialog.askopenfilename(
        parent=parent, title="選擇文件",
        filetypes=[("Word、PDF、文字檔", "*.docx *.pdf *.txt *.md"), ("所有檔案", "*.*")],
    )
    if not path:
        return
    win = tk.Toplevel(parent)
    win.title("Saydown・匯入詞庫")
    sc = glass.scale(win)
    win.geometry(f"{int(460 * sc)}x{int(620 * sc)}+{parent.winfo_rootx() + int(30 * sc)}+{parent.winfo_rooty()}")
    win.transient(parent)
    glass.apply(win)
    BG, PANEL = glass.KEY, glass.CARD

    head = tk.Frame(win, bg=BG)
    head.pack(fill="x", padx=22, pady=(16, 2))
    tk.Label(head, text="匯入詞庫", bg=BG, fg=glass.INK, font=glass.TITLE).pack(side="left")
    tk.Label(win, text=os.path.basename(path), bg=BG, fg=glass.MUTED, font=glass.FONT, anchor="w").pack(
        fill="x", padx=24, pady=(0, 8))
    card = glass.Card(win, expand=True)
    card.pack(fill="both", expand=True, padx=14)
    body = card.body
    tk.Frame(win, bg=BG, height=int(14 * sc)).pack(fill="x")

    status = tk.Label(body, bg=PANEL, fg=glass.MUTED, font=glass.FONT, anchor="w")
    status.pack(fill="x", pady=(0, 8))
    bottom = tk.Frame(body, bg=PANEL)
    bottom.pack(fill="x", side="bottom", pady=(10, 0))
    tree = ttk.Treeview(body, columns=("pick", "term", "count"), show="headings", selectmode="none")
    for col, title, width, stretch, anchor in (("pick", "", 36, False, "center"), ("term", "詞", 260, True, "w"),
                                               ("count", "出現次數", 80, False, "e")):
        tree.heading(col, text=title, anchor=anchor)
        tree.column(col, width=int(width * sc), stretch=stretch, anchor=anchor)
    scroll = glass.Scrollbar(body, command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    tree.pack(fill="both", expand=True)

    picked = {}
    cancelled = {"value": False}
    events = queue.Queue()

    def mark(iid):
        tree.set(iid, "pick", "✓" if picked[iid] else "")

    def toggle(e):
        iid = tree.identify_row(e.y)
        if iid:
            picked[iid] = not picked[iid]
            mark(iid)
            update_count()

    def set_all(on):
        for iid in picked:
            picked[iid] = on
            mark(iid)
        update_count()

    def update_count():
        n = sum(picked.values())
        status.config(text=f"共 {len(picked)} 個候選詞，已勾選 {n} 個")

    def add():
        words = [tree.set(iid, "term") for iid, on in picked.items() if on]
        current = load_dictionary()
        new = [w for w in words if w not in current]
        if new:
            save_dictionary(current + new)
        on_added()
        win.destroy()

    def work():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
            text = importer.extract_text(path)
            if not text.strip():
                events.put(("error", "讀不到文字（掃描成圖片的 PDF 無法匯入）"))
                return
            result = importer.candidates(text, cfg, lambda i, n: events.put(("progress", (i, n))),
                                         lambda: cancelled["value"])
            events.put(("done", result))
        except Exception as exc:
            events.put(("error", f"分析失敗：{exc}"))

    def poll():
        if not win.winfo_exists():
            return
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "progress":
                    status.config(text=f"分析中 {value[0]}／{value[1]}")
                elif kind == "error":
                    status.config(text=value, fg=glass.DANGER)
                    return
                else:
                    for term, count in value:
                        iid = tree.insert("", "end", values=("", term, count))
                        picked[iid] = count >= 3  # 出現三次以上的預設勾選
                        mark(iid)
                    update_count()
                    glass.Button(bottom, "加入詞庫", add, kind="accent").pack(side="right")
                    glass.Button(bottom, "全不選", lambda: set_all(False)).pack(side="left")
                    glass.Button(bottom, "全選", lambda: set_all(True)).pack(side="left", padx=8)
                    return
        except queue.Empty:
            pass
        win.after(200, poll)

    def close():
        cancelled["value"] = True
        win.destroy()

    tree.bind("<Button-1>", toggle)
    win.protocol("WM_DELETE_WINDOW", close)
    win.bind("<Escape>", lambda e: close())
    status.config(text="讀取文件中")
    threading.Thread(target=work, daemon=True).start()
    poll()


def open_dictionary(parent):
    import tkinter as tk
    from tkinter import ttk

    import glass

    win = tk.Toplevel(parent)
    win.title("Saydown・詞庫")
    sc = glass.scale(win)
    win.update_idletasks()
    x = parent.winfo_rootx() + parent.winfo_width() - int(400 * sc)
    y = parent.winfo_rooty() + int(60 * sc)
    win.geometry(f"{int(380 * sc)}x{int(500 * sc)}+{max(x, 0)}+{y}")
    win.transient(parent)
    glass.apply(win)
    BG, PANEL = glass.KEY, glass.CARD
    font = (glass.FONT_NAME, 11)

    head = tk.Frame(win, bg=BG)
    head.pack(fill="x", padx=(22, 14), pady=(16, 8))
    tk.Label(head, text="詞庫", bg=BG, fg=glass.INK, font=glass.TITLE, anchor="w").pack(side="left")
    glass.Button(head, "從文件匯入", lambda: open_import(win, refresh), bg=BG).pack(side="right")
    card = glass.Card(win, expand=True)
    card.pack(fill="both", expand=True, padx=14)
    body = card.body

    row = tk.Frame(body, bg=PANEL)
    row.pack(fill="x", pady=(0, 10))
    word = tk.StringVar()
    field, entry = glass.entry(row, word)
    field.pack(side="left", fill="x", expand=True)

    bottom = tk.Frame(body, bg=PANEL)
    bottom.pack(fill="x", side="bottom", pady=(10, 0))
    box = tk.Listbox(body, font=font, activestyle="none", relief="flat", bd=0, highlightthickness=0,
                     bg=PANEL, fg=glass.INK, selectbackground=glass.ACCENT_SOFT, selectforeground=glass.INK)
    scroll = glass.Scrollbar(body, command=box.yview)
    box.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    box.pack(fill="both", expand=True)
    count = tk.Label(bottom, bg=PANEL, fg=glass.MUTED, font=glass.FONT)
    count.pack(side="left")
    tk.Frame(win, bg=BG, height=int(14 * sc)).pack(fill="x")

    def refresh():
        if not win.winfo_exists():
            return
        box.delete(0, "end")
        words = load_dictionary()
        for w in words:
            box.insert("end", w)
        count.config(text=f"{len(words)} 個詞")

    editing = {"word": None}  # 正在修改的詞；None＝輸入框是新增

    def set_editing(target):
        editing["word"] = target
        save_button.set_text("儲存" if target else "新增")
        word.set(target or "")
        if target:
            entry.focus_set()
            entry.select_range(0, "end")

    def add(*_):
        new = word.get().strip()
        old = editing["word"]
        if old is None:
            if add_word(new):
                word.set("")
                refresh()
                box.see("end")
            return
        if not new:
            return
        words = load_dictionary()
        if new != old and new in words:  # 改成已經有的詞：等於合併，把舊的拿掉
            words = [w for w in words if w != old]
        else:
            words = [new if w == old else w for w in words]  # 原地取代，保留順序
        save_dictionary(words)
        set_editing(None)
        refresh()
        if new in words:
            i = words.index(new)
            box.selection_set(i)
            box.see(i)

    def edit(*_):
        picked = box.curselection()
        if picked:
            set_editing(box.get(picked[0]))

    def remove():
        picked = box.curselection()
        if not picked:
            return
        words = load_dictionary()
        target = box.get(picked[0])
        save_dictionary([w for w in words if w != target])
        if editing["word"] == target:
            set_editing(None)
        refresh()

    def escape(_):
        if editing["word"] is not None:
            set_editing(None)
        else:
            win.destroy()

    save_button = glass.Button(row, "新增", add, kind="accent")
    save_button.pack(side="left", padx=(8, 0))
    glass.Button(bottom, "刪除這個詞", remove, kind="danger").pack(side="right")
    glass.Button(bottom, "修改", edit).pack(side="right", padx=(0, 8))
    entry.bind("<Return>", add)
    box.bind("<Double-1>", edit)
    box.bind("<Return>", edit)
    box.bind("<Delete>", lambda e: remove())
    win.bind("<Escape>", escape)
    refresh()
    entry.focus_set()
    return refresh


def run_window():
    import tkinter as tk
    from tkinter import ttk

    import glass

    glass.dpi_aware()
    db = connect()
    root = tk.Tk()
    root.title("Saydown・歷史紀錄")
    sc = glass.scale(root)
    root.geometry(f"{int(1040 * sc)}x{int(640 * sc)}")
    root.minsize(int(780 * sc), int(480 * sc))
    glass.apply(root)
    glass.style(root)
    BG, PANEL, INK, MUTED, ACCENT, FONT = glass.KEY, glass.CARD, glass.INK, glass.MUTED, glass.ACCENT, glass.FONT

    # 上方：標題、搜尋與統計（直接放在玻璃上）
    top = tk.Frame(root, bg=BG)
    top.pack(fill="x", padx=22, pady=(16, 10))
    tk.Label(top, text="歷史紀錄", bg=BG, fg=INK, font=glass.TITLE).pack(side="left")
    query = tk.StringVar()
    search, entry = glass.entry(top, query, width=30, bg=BG, fill=PANEL)
    tk.Label(top, text="搜尋", bg=BG, fg=MUTED, font=FONT).pack(side="left", padx=(26, 8), pady=(4, 0))
    search.pack(side="left", pady=(4, 0))
    stats = tk.Label(top, bg=BG, fg=MUTED, font=FONT)
    dictionary = {"refresh": None}

    def show_dictionary():
        dictionary["refresh"] = open_dictionary(root)

    glass.Button(top, "詞庫", show_dictionary, bg=BG).pack(side="right", pady=(4, 0))
    glass.Button(top, "統計", lambda: open_stats(root), bg=BG).pack(side="right", padx=(0, 8), pady=(4, 0))
    stats.pack(side="right", padx=14, pady=(4, 0))

    body = tk.PanedWindow(root, orient="horizontal", bg=BG, sashwidth=int(10 * sc), bd=0, showhandle=False)
    body.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    # 左：清單，一筆一列
    left_card = glass.Card(body, expand=True, pad=10)
    left = left_card.body
    tree = ttk.Treeview(left, columns=("time", "mode", "app", "text"), show="headings", selectmode="browse")
    for col, title, width, stretch in (
        ("time", "時間", 110, False),
        ("mode", "模式", 70, False),
        ("app", "程式", 90, False),
        ("text", "結果", 300, True),
    ):
        tree.heading(col, text=title, anchor="w")
        tree.column(col, width=width, stretch=stretch, anchor="w")
    scroll = glass.Scrollbar(left, command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")  # 先放捲軸，清單太寬時才不會被擠掉
    tree.pack(side="left", fill="both", expand=True)
    body.add(left_card, minsize=int(420 * sc), width=int(580 * sc))

    # 右：細節
    right_card = glass.Card(body, expand=True)
    right = right_card.body
    body.add(right_card, minsize=int(300 * sc))
    head = tk.Frame(right, bg=PANEL)
    head.pack(fill="x")
    meta = tk.Label(head, bg=PANEL, fg=MUTED, font=FONT, anchor="w", justify="left")
    meta.pack(side="left", fill="x", expand=True)

    def section(title):
        glass.section(right, title, bg=PANEL).pack(fill="x", pady=(12, 4))
        field, box = glass.text_box(right)
        field.pack(fill="both", expand=True)
        return field, box

    _, result_box = section("結果")
    raw_field, raw_box = section("原始辨識")
    sel_label = glass.section(right, "選取的原文", bg=PANEL)
    sel_field, sel_box = glass.text_box(right, height=3)

    buttons = tk.Frame(right, bg=PANEL)
    buttons.pack(fill="x", side="bottom", pady=(8, 0))
    status = tk.Label(right, bg=PANEL, fg=ACCENT, font=FONT, anchor="w")
    status.pack(fill="x", side="bottom", pady=(8, 0))

    rows = {}
    shown = {"id": None}

    def fmt_time(ts):
        dt = datetime.fromtimestamp(ts)
        today = datetime.now().date()
        if dt.date() == today:
            return dt.strftime("今天 %H:%M")
        if dt.date() == today - timedelta(days=1):
            return dt.strftime("昨天 %H:%M")
        return dt.strftime("%m/%d %H:%M")

    def load(*_):
        tree.delete(*tree.get_children())
        rows.clear()
        q = query.get().strip()
        sql = "SELECT * FROM history"
        args = ()
        if q:
            sql += " WHERE raw_text LIKE ? OR result_text LIKE ? OR selected_text LIKE ?"
            args = (f"%{q}%",) * 3
        sql += " ORDER BY created_at DESC LIMIT 500"
        db.row_factory = sqlite3.Row
        for r in db.execute(sql, args):
            mode = "edit" if r["selected_text"] else r["mode"]
            label = mode_label(mode)
            if r["selected_text"] and r["mode"] not in ("cleanup", "ask"):
                label += "・" + mode_label(r["mode"])
            app = r["app"].removesuffix(".exe")
            iid = tree.insert("", "end", values=(fmt_time(r["created_at"]), label, app,
                                                 r["result_text"].replace("\n", " ")))
            rows[iid] = r
        total, words, saved = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(LENGTH(result_text)),0), COALESCE(SUM(audio_seconds),0) FROM history"
        ).fetchone()
        spoken = f"{saved / 60:.0f} 分鐘" if saved >= 60 else f"{saved:.0f} 秒"
        stats.config(text=f"共 {total} 筆　{words:,} 字　錄音 {spoken}")
        children = tree.get_children()
        if children:
            tree.selection_set(children[0])
            tree.focus(children[0])
        else:
            show(None)

    def put(box, text):
        box.config(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        if box is not result_box:  # 結果可以直接改，改完存回紀錄
            box.config(state="disabled")

    def show(r):
        if r is None:
            meta.config(text="")
            for box in (result_box, raw_box):
                put(box, "")
            sel_label.pack_forget()
            sel_field.pack_forget()
            return
        dt = datetime.fromtimestamp(r["created_at"]).strftime("%m/%d %H:%M")
        parts = [dt]
        if r["app"]:
            parts.append(r["app"].removesuffix(".exe"))
        parts.append(f"錄音 {r['audio_seconds']:.1f} 秒")
        parts.append(f"處理 {r['asr_seconds'] + r['llm_seconds']:.1f} 秒")
        meta.config(text="　".join(parts))
        put(result_box, r["result_text"])
        put(raw_box, r["raw_text"])
        shown["id"] = r["id"]
        if r["selected_text"]:
            sel_label.pack(fill="x", pady=(12, 4), after=raw_field)
            sel_field.pack(fill="both", expand=True, after=sel_label)
            put(sel_box, r["selected_text"])
        else:
            sel_label.pack_forget()
            sel_field.pack_forget()

    def current():
        sel = tree.selection()
        return rows.get(sel[0]) if sel else None

    def copy(field):
        r = current()
        if r is None:
            return
        root.clipboard_clear()
        root.clipboard_append(r[field])
        status.config(text="已複製")
        root.after(1500, lambda: status.config(text=""))

    def delete():
        r = current()
        if r is None:
            return
        db.execute("DELETE FROM history WHERE id = ?", (r["id"],))
        db.commit()
        load()

    glass.Button(buttons, "複製結果", lambda: copy("result_text"), kind="accent").pack(side="left")
    glass.Button(buttons, "複製原始辨識", lambda: copy("raw_text")).pack(side="left", padx=8)

    def add_selected_word():
        for box in (result_box, raw_box, sel_box):
            try:
                word = box.get("sel.first", "sel.last")
            except tk.TclError:
                continue
            if add_word(word):
                status.config(text=f"已加入詞庫：{word.strip()}")
            else:
                status.config(text="詞庫已有這個詞")
            root.after(2000, lambda: status.config(text=""))
            return
        status.config(text="沒有反白的文字")
        root.after(2000, lambda: status.config(text=""))

    glass.Button(buttons, "加入詞庫", add_selected_word).pack(side="left")
    glass.Button(head, "刪除", delete, kind="danger").pack(side="right", before=meta)

    def flash(text, ms=2500):
        status.config(text=text)
        root.after(ms, lambda: status.config(text="") if status.cget("text") == text else None)

    def save_edit(_=None):
        """結果框改完（離開文字框或換一筆）就存回紀錄，並把改正的詞加入詞庫。"""
        old_row = next((r for r in rows.values() if r["id"] == shown["id"]), None)
        if old_row is None:
            return
        new = result_box.get("1.0", "end-1c")
        old = old_row["result_text"]
        if new == old or not new.strip():
            return
        db.execute("UPDATE history SET result_text = ? WHERE id = ?", (new, old_row["id"]))
        db.commit()
        refresh_row(old_row["id"])
        flash("已儲存修改")

        def learn_words():
            import learn

            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    cfg = json.load(f)
                if not cfg.get("auto_learn", True) or not learn.looks_like_correction(old, new):
                    return
                added = [t for t in learn.extract_terms(old, new, cfg) if add_word(t)]
            except Exception:
                return
            if added:
                def done():
                    flash("已加入詞庫：" + "、".join(added), 4000)
                    if dictionary["refresh"]:
                        dictionary["refresh"]()

                root.after(0, done)

        threading.Thread(target=learn_words, daemon=True).start()

    def refresh_row(row_id):
        db.row_factory = sqlite3.Row
        fresh = db.execute("SELECT * FROM history WHERE id = ?", (row_id,)).fetchone()
        for iid, r in list(rows.items()):
            if r["id"] == row_id and fresh is not None:
                rows[iid] = fresh
                values = list(tree.item(iid, "values"))
                values[3] = fresh["result_text"].replace("\n", " ")
                tree.item(iid, values=values)

    result_box.bind("<FocusOut>", save_edit, add="+")

    last_id = {"value": None}

    def poll():
        """Saydown寫入新紀錄時自動更新清單，視窗開著也會看到最新一筆。"""
        try:
            newest = db.execute("SELECT MAX(id) FROM history").fetchone()[0]
        except sqlite3.Error:
            newest = last_id["value"]
        if newest != last_id["value"] and root.focus_get() is not result_box:  # 正在改結果就先不重整
            if last_id["value"] is not None:
                load()
            last_id["value"] = newest
        root.after(1500, poll)

    tree.bind("<<TreeviewSelect>>", lambda e: (save_edit(), show(current())))
    tree.bind("<Double-1>", lambda e: copy("result_text"))
    root.bind("<Control-c>", lambda e: copy("result_text") if root.focus_get() in (tree, None) else None)
    query.trace_add("write", load)
    root.bind("<Escape>", lambda e: root.destroy())
    load()
    poll()
    entry.focus_set()
    root.mainloop()


if __name__ == "__main__":
    if sys.stdout is None:  # pythonw
        import os

        sys.stdout = sys.stderr = open(os.devnull, "w")
    run_window()
