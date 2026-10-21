"""自動學詞：貼上後觀察使用者有沒有改字，改了就把正確寫法加入詞庫。

做法和 Typeless 一樣：貼上後用 UI Automation 讀目前輸入框的文字，
之後每隔幾秒再讀一次，直到使用者離開這個輸入框、開始下一段口述或超過時限。
比對貼上的那一段前後差異，小幅修改（像把「視聽室」改成「視聽教室」）才算改字，
交給修稿模型挑出被改正的詞，再檢查一次才加入詞庫。整段改寫、補寫新句子都不學。
"""

import difflib
import json
import re
import threading
import time

import requests

MAX_TEXT = 20000  # 讀不到游標位置、只能讀整個輸入框時，太長就不觀察，避免每次讀取都很慢
NEAR = 3000  # 讀游標前後各幾個字：長文件（論文、Word）也只讀這一小段，貼上的那段一定在裡面
WATCH_SECONDS = 300
POLL_SECONDS = 1.5

_local = threading.local()


def _uia():
    """每條執行緒各自初始化 COM 和 UI Automation。"""
    if getattr(_local, "uia", None) is None:
        import logging

        logging.getLogger("comtypes").setLevel(logging.WARNING)  # 要在 import 前設，載入訊息才不會寫進記錄檔
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA

        _local.mod = UIA
        _local.uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
    return _local.uia, _local.mod


def focused():
    """目前有鍵盤焦點的元件與它的文字；讀不到就回傳 (None, None)。"""
    uia, UIA = _uia()
    el = uia.GetFocusedElement()
    if el is None:
        return None, None
    return el, read(el)


def focused_element():
    uia, _ = _uia()
    return uia.GetFocusedElement()


# 確定不能打字的元件：按鈕、清單（桌面圖示、檔案總管）、選單、樹狀、分頁、整個視窗、沒有文字的文件
NOT_TYPING = {50000, 50007, 50008, 50011, 50019, 50023, 50024, 50030, 50032}


def focus_is_editable():
    """游標是不是在可以打字的地方；看不出來時當作可以（照常貼上、還原剪貼簿）。

    ValuePattern 最準：一般輸入框可寫入，Chrome、Edge 的網頁本體是唯讀。
    沒有的話，有 TextPattern 的編輯區或文件（Word、記事本）算可以打字。
    兩個都沒有時，只有確定不能打字的元件才回傳 False：
    Chromium 系的程式剛開始被查詢時，焦點只回報成空白的 Pane，不能當成沒有輸入框。
    """
    uia, UIA = _uia()
    el = uia.GetFocusedElement()
    if el is None:
        return False
    try:
        pat = el.GetCurrentPattern(10002)  # ValuePattern
        if pat:
            return not pat.QueryInterface(UIA.IUIAutomationValuePattern).CurrentIsReadOnly
        if el.GetCurrentPattern(10014):  # TextPattern
            return True
        return el.CurrentControlType not in NOT_TYPING
    except Exception:
        return True


def read(el):
    uia, UIA = _uia()
    try:
        pat = el.GetCurrentPattern(10014)  # TextPattern：Word、Chrome、記事本等多數編輯區
        if pat:
            tp = pat.QueryInterface(UIA.IUIAutomationTextPattern)
            try:
                sel = tp.GetSelection()
                if sel and sel.Length:
                    near = sel.GetElement(0).Clone()
                    near.MoveEndpointByUnit(0, 0, -NEAR)  # 起點往前（0＝Start、單位 0＝字元）
                    near.MoveEndpointByUnit(1, 0, NEAR)  # 終點往後
                    return near.GetText(-1)
            except Exception:
                pass  # 有些程式不提供游標位置，改讀整個輸入框
            return tp.DocumentRange.GetText(MAX_TEXT + 1)
    except Exception:
        pass
    try:
        pat = el.GetCurrentPattern(10002)  # ValuePattern：單行輸入框
        if pat:
            return pat.QueryInterface(UIA.IUIAutomationValuePattern).CurrentValue
    except Exception:
        pass
    return None


def same_element(a, b):
    try:
        uia, _ = _uia()
        return bool(uia.CompareElements(a, b))
    except Exception:
        return False


def norm(text):
    """各程式回報的換行不一樣（\r\n、\r、\n），統一成 \n 再比較。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def edited_segment(before, pasted, after):
    """在 before 裡找到貼上的那段，回傳它在 after 裡被改成什麼；找不到或沒改回傳 None。"""
    pasted, before, after = norm(pasted), norm(before), norm(after)
    start = before.rfind(pasted)
    if start < 0:
        return None
    end = start + len(pasted)
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    lo = hi = None
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # 原文落在貼上範圍內的相同片段，換算到 after 的位置
            a, b = max(i1, start), min(i2, end)
            if a < b:
                lo = j1 + (a - i1) if lo is None else lo
                hi = j1 + (b - i1)
        elif start <= i1 and i2 <= end and not (tag == "insert" and i1 in (start, end)):
            lo = j1 if lo is None else lo
            hi = max(hi or j2, j2)
    if lo is None or hi is None:
        return None
    segment = after[lo:hi]
    return segment if segment != pasted else None


def looks_like_correction(original, edited):
    """小幅改字才學；整段重寫、只動標點空白、刪掉一大段都不算。"""
    strip = lambda s: re.sub(r"[\s，。、！？；：,.!?;:「」『』（）()]", "", s)
    a, b = strip(original), strip(edited)
    if a == b or not b:
        return False
    ratio = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in
                  difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if tag != "equal")
    return ratio >= 0.6 and changed <= max(12, len(a) // 4)


PROMPT = """使用者用語音輸入得到「原句」，再手動改成「改後」。請找出他改正的詞：
通常是語音辨識聽錯的專有名詞、人名、地名、術語或慣用寫法。
只輸出 JSON 陣列，元素是改後句子裡完整的正確詞（2～15 個字，要能單獨成詞，不要只輸出改動的那一個字）。
只是改語氣、刪字、補標點、增加新內容時，輸出 []。"""

EXAMPLES = [
    ("今天下午三點在視聽室開會", "今天下午三點在視聽教室開會", '["視聽教室"]'),
    ("請大家上傳到怕的", "請大家上傳到 Padlet", '["Padlet"]'),
    ("明天要交作業喔", "明天要交作業，謝謝", "[]"),
]


def extract_terms(original, edited, cfg):
    url = cfg["ollama_url"]
    messages = [{"role": "system", "content": PROMPT}]
    for a, b, out in EXAMPLES:
        messages += [{"role": "user", "content": f"原句：{a}\n改後：{b}"}, {"role": "assistant", "content": out}]
    messages.append({"role": "user", "content": f"原句：{original}\n改後：{edited}"})
    payload = {
        "model": cfg["ollama_model"], "messages": messages, "stream": False, "think": False,
        "keep_alive": "60m", "options": {"temperature": 0, "num_ctx": 8192, "presence_penalty": 0},
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    text = r.json()["message"]["content"]
    match = re.search(r"\[.*?\]", text, re.S)
    try:
        terms = json.loads(match.group(0)) if match else []
    except ValueError:
        return []
    known = set(cfg.get("dictionary", []))
    good = []
    for t in terms:
        t = str(t).strip()
        # 必須真的是改後才出現的寫法，模型不能自己編
        if 2 <= len(t) <= 30 and t in edited and t not in original and t not in known and t not in good:
            good.append(t)
    return good
