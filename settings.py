"""Saydown的設定視窗：改了立即寫回 config.json，Saydown一秒內自動套用（含快捷鍵）。"""

import json
import os
import sys
import time

import requests

import paths

paths.ensure_data()
BASE = paths.DATA
CONFIG_PATH = paths.CONFIG_PATH

MAIN_KEYS = [
    ("right alt", "右 Alt"),
    ("right ctrl", "右 Ctrl"),
    ("f8", "F8"),
    ("f9", "F9"),
    ("mouse x2", "滑鼠側鍵（前）"),
    ("mouse x1", "滑鼠側鍵（後）"),
    ("mouse middle", "滑鼠中鍵"),
]
FORMAL_KEYS = [("", "不使用"), ("f10", "F10"), ("f9", "F9"), ("f8", "F8"), ("f11", "F11"), ("f12", "F12")]
TRANSLATE_TO = [("", "不翻譯"), ("en", "英文"), ("ja", "日文"), ("ko", "韓文"), ("vi", "越南文"), ("id", "印尼文"),
                ("th", "泰文"), ("es", "西班牙文"), ("fr", "法文"), ("de", "德文")]
DEVICES = [("auto", "自動"), ("cuda", "顯示卡（GPU）"), ("cpu", "CPU（較慢，用小模型）")]
TONES = [("formal", "正式"), ("chat", "聊天"), ("cleanup", "一般")]
APP_NAMES = {
    "outlook.exe": "Outlook",
    "olk.exe": "Outlook（新版）",
    "thunderbird.exe": "Thunderbird",
    "line.exe": "LINE",
    "linelauncher.exe": "LINE（啟動器）",
    "ms-teams.exe": "Teams",
    "teams.exe": "Teams（舊版）",
    "discord.exe": "Discord",
    "slack.exe": "Slack",
    "telegram.exe": "Telegram",
    "whatsapp.exe": "WhatsApp",
    "messenger.exe": "Messenger",
    "winword.exe": "Word",
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
}


def load():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def update(**fields):
    """讀最新的設定檔、只改指定欄位再寫回，不會蓋掉Saydown或詞庫視窗剛存的其他欄位。"""
    cfg = load()
    cfg.update(fields)
    tmp = CONFIG_PATH.with_name(f"config.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    for attempt in range(10):
        try:
            os.replace(tmp, CONFIG_PATH)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05)


def ollama_models(cfg):
    base = cfg.get("ollama_url", "http://127.0.0.1:11434/api/chat").rsplit("/api/", 1)[0]
    try:
        tags = requests.get(base + "/api/tags", timeout=2).json()
        return sorted(m["name"] for m in tags.get("models", []) if "embed" not in m["name"])
    except (requests.RequestException, ValueError):
        return []


def split_hotkeys(hotkeys):
    main = next((k for k, m in hotkeys.items() if m == "cleanup"), "right alt")
    formal = next((k for k, m in hotkeys.items() if m == "formal"), "")
    return main, formal


def run_window():
    import tkinter as tk
    from tkinter import ttk

    import glass

    glass.dpi_aware()
    cfg = load()
    root = tk.Tk()
    root.title("Saydown・設定")
    sc = glass.scale(root)
    tall = min(int(900 * sc), root.winfo_screenheight() - int(80 * sc))  # 筆電螢幕矮，不要超出畫面
    root.geometry(f"{int(560 * sc)}x{tall}")
    root.minsize(int(520 * sc), min(int(760 * sc), tall))
    glass.apply(root)
    glass.style(root)
    BG, PANEL, INK, MUTED, ACCENT, FONT = glass.KEY, glass.CARD, glass.INK, glass.MUTED, glass.ACCENT, glass.FONT

    head = tk.Frame(root, bg=BG)
    head.pack(fill="x", padx=22, pady=(16, 2))
    tk.Label(head, text="設定", bg=BG, fg=INK, font=glass.TITLE).pack(side="left")
    status = tk.Label(head, bg=BG, fg=ACCENT, font=glass.FONT_BOLD)
    status.pack(side="right", pady=(8, 0))

    def saved(**fields):
        try:
            update(**fields)
            status.config(text="已儲存", fg=ACCENT)
        except OSError as e:
            status.config(text=f"儲存失敗：{e}", fg=glass.DANGER)
        root.after(1500, lambda: status.config(text=""))

    def card(title, expand=False):
        glass.section(root, title).pack(fill="x", padx=24, pady=(12, 4))
        c = glass.Card(root, expand=expand)
        c.pack(fill="both" if expand else "x", expand=expand, padx=14)
        return c.body

    def row(parent, label):
        line = tk.Frame(parent, bg=PANEL)
        line.pack(fill="x", pady=5)
        tk.Label(line, text=label, bg=PANEL, fg=INK, font=FONT, width=12, anchor="w").pack(side="left")
        return line

    # ---- 快捷鍵 ----
    keys = card("快捷鍵")
    main, formal = split_hotkeys(cfg.get("hotkeys", {}))
    main_var = tk.StringVar(value=dict(MAIN_KEYS).get(main, main))
    formal_var = tk.StringVar(value=dict(FORMAL_KEYS).get(formal, formal or "不使用"))

    def save_hotkeys(*_):
        main_key = {v: k for k, v in MAIN_KEYS}.get(main_var.get(), main_var.get())
        formal_key = {v: k for k, v in FORMAL_KEYS}.get(formal_var.get(), "")
        # 手動加在設定檔的其他快捷鍵（例如翻英文鍵）原樣保留，只換這兩個
        hotkeys = {k: m for k, m in load().get("hotkeys", {}).items() if m not in ("cleanup", "formal")}
        hotkeys.pop(main_key, None)
        hotkeys[main_key] = "cleanup"
        if formal_key and formal_key != main_key:
            hotkeys.pop(formal_key, None)
            hotkeys[formal_key] = "formal"
        saved(hotkeys=hotkeys)

    line = row(keys, "說話鍵")
    field, box = glass.combo(line, main_var, [v for _, v in MAIN_KEYS])
    field.pack(side="left")
    box.bind("<<ComboboxSelected>>", save_hotkeys)
    line = row(keys, "正式語氣鍵")
    field, box = glass.combo(line, formal_var, [v for _, v in FORMAL_KEYS])
    field.pack(side="left")
    box.bind("<<ComboboxSelected>>", save_hotkeys)

    # ---- 辨識與修稿 ----
    engine = card("辨識與修稿")
    device_var = tk.StringVar(value=dict(DEVICES).get(cfg.get("whisper_device", "auto"), "自動"))
    line = row(engine, "語音辨識")
    field, box = glass.combo(line, device_var, [v for _, v in DEVICES], width=22)
    field.pack(side="left")
    box.bind("<<ComboboxSelected>>",
             lambda e: saved(whisper_device={v: k for k, v in DEVICES}[device_var.get()]))

    polish = tk.BooleanVar(value=cfg.get("polish", True))
    models = ollama_models(cfg)
    model_var = tk.StringVar(value=cfg.get("ollama_model", ""))
    line = row(engine, "修稿")
    glass.Toggle(line, polish, lambda: (saved(polish=polish.get()), refresh_polish())).pack(side="left")
    polish_hint = tk.Label(line, bg=PANEL, fg=MUTED, font=FONT)
    polish_hint.pack(side="left", padx=(12, 0))
    line = row(engine, "修稿模型")
    field, model_box = glass.combo(line, model_var, models, width=26)
    field.pack(side="left")
    model_box.bind("<<ComboboxSelected>>", lambda e: saved(ollama_model=model_var.get()))

    def refresh_polish():
        on = polish.get()
        model_box.config(state="readonly" if on and models else "disabled")
        if not on:
            polish_hint.config(text="直接貼上辨識結果，不需要 Ollama")
        elif not models:
            polish_hint.config(text="找不到 Ollama 或修稿模型")
        else:
            polish_hint.config(text="")

    refresh_polish()

    # ---- 輸出 ----
    out = card("輸出")
    current = cfg.get("translate_to")
    if current is None:  # 舊設定只有 translate: true（＝英文）
        current = "en" if cfg.get("translate", False) else ""
    translate = tk.StringVar(value=dict(TRANSLATE_TO).get(current, "不翻譯"))
    beep = tk.BooleanVar(value=cfg.get("beep", True))
    keep = tk.BooleanVar(value=cfg.get("history", True))
    live = tk.BooleanVar(value=cfg.get("live_preview", True))
    learn = tk.BooleanVar(value=cfg.get("auto_learn", True))
    days = tk.StringVar(value=str(cfg.get("history_keep_days", 30)))

    line = row(out, "翻譯")
    field, box = glass.combo(line, translate, [v for _, v in TRANSLATE_TO], width=10)
    field.pack(side="left")
    box.bind("<<ComboboxSelected>>",
             lambda e: saved(translate_to={v: k for k, v in TRANSLATE_TO}[translate.get()]))
    line = row(out, "提示音")
    glass.Toggle(line, beep, lambda: saved(beep=beep.get())).pack(side="left")
    line = row(out, "即時預覽")
    glass.Toggle(line, live, lambda: saved(live_preview=live.get())).pack(side="left")
    line = row(out, "自動學詞")
    glass.Toggle(line, learn, lambda: saved(auto_learn=learn.get())).pack(side="left")
    line = row(out, "歷史紀錄")
    glass.Toggle(line, keep, lambda: saved(history=keep.get())).pack(side="left")
    tk.Label(line, text="保留", bg=PANEL, fg=MUTED, font=FONT).pack(side="left", padx=(18, 6))

    def save_days(*_):
        try:
            value = max(1, min(3650, int(days.get())))
        except ValueError:
            return
        saved(history_keep_days=value)

    field, spin = glass.entry(line, days, width=5)
    field.pack(side="left")
    spin.bind("<FocusOut>", save_days)
    spin.bind("<Return>", save_days)
    tk.Label(line, text="天", bg=PANEL, fg=MUTED, font=FONT).pack(side="left", padx=6)

    # ---- 依程式切換語氣 ----
    tones = card("依程式切換語氣", expand=True)
    tone_names = dict(TONES)
    tree = ttk.Treeview(tones, columns=("app", "tone"), show="headings", height=5, selectmode="browse")
    tree.heading("app", text="程式", anchor="w")
    tree.heading("tone", text="語氣", anchor="w")
    tree.column("app", width=260, anchor="w")
    tree.column("tone", width=100, anchor="w")

    def refresh_tones():
        tree.delete(*tree.get_children())
        table = load().get("app_tones", {})
        for app, tone in sorted(table.items(), key=lambda kv: APP_NAMES.get(kv[0], kv[0]).lower()):
            name = APP_NAMES.get(app, app.removesuffix(".exe"))
            tree.insert("", "end", iid=app, values=(name, tone_names.get(tone, tone)))

    add = tk.Frame(tones, bg=PANEL)
    add.pack(fill="x", side="bottom", pady=(10, 0))
    scroll = glass.Scrollbar(tones, command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    tree.pack(fill="both", expand=True)
    app_var = tk.StringVar()
    tone_var = tk.StringVar(value="正式")
    field, entry = glass.entry(add, app_var, width=20)
    field.pack(side="left")
    field, _ = glass.combo(add, tone_var, [v for _, v in TONES], width=6)
    field.pack(side="left", padx=8)

    def add_tone(*_):
        app = app_var.get().strip().lower()
        if not app:
            return
        if not app.endswith(".exe"):
            app += ".exe"
        table = load().get("app_tones", {})
        table[app] = {v: k for k, v in TONES}[tone_var.get()]
        saved(app_tones=table)
        app_var.set("")
        refresh_tones()

    def remove_tone():
        picked = tree.selection()
        if not picked:
            return
        table = load().get("app_tones", {})
        table.pop(picked[0], None)
        saved(app_tones=table)
        refresh_tones()

    glass.Button(add, "新增", add_tone, kind="accent").pack(side="left")
    glass.Button(add, "刪除", remove_tone, kind="danger").pack(side="right")
    entry.bind("<Return>", add_tone)
    refresh_tones()

    tk.Frame(root, bg=BG, height=int(14 * sc)).pack(fill="x")
    root.bind("<Escape>", lambda e: root.destroy())
    root.mainloop()


if __name__ == "__main__":
    if sys.stdout is None:  # pythonw
        sys.stdout = sys.stderr = open(os.devnull, "w")
    run_window()
