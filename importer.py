"""從 Word／PDF／純文字檔挑出值得加入詞庫的詞（專有名詞、術語、英文縮寫、人名…）。

做法：抽出全文 → 依段落切成幾千字一塊 → 每塊請修稿模型列出「語音辨識容易寫錯、需要正確寫法」的詞
→ 合併、只留真的出現在原文裡的詞，依出現次數排序。英文詞與縮寫另外用規則抓，模型漏掉也補得回來。
全部在本機處理，不上傳。
"""

import json
import re
import zipfile
from collections import Counter
from xml.etree import ElementTree

import requests

CHUNK = 2500
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

PROMPT = """你會收到一段文件內容。請挑出「用語音輸入時，辨識系統容易寫錯、需要記住正確寫法」的詞：
專有名詞、人名、機構與學校名稱、課程或計畫名稱、學術術語、英文詞、縮寫、產品或軟體名稱。
不要挑一般常用詞（例如：學生、老師、活動、研究、分析、問題），也不要挑整句話。
每個詞照原文寫法，2～15 個字。只輸出 JSON 陣列，例如 ["專業學習社群", "PLC", "Canva"]；沒有就輸出 []。"""

ENGLISH = re.compile(r"(?<![A-Za-z])[A-Za-z][A-Za-z0-9+#.\-]*(?: [A-Z][A-Za-z0-9+#.\-]*)*(?![A-Za-z])")
# 不是「詞」的東西：引用年份「教育部（2024）」、網址、四位以上數字（日期、編號）、純數字
NOISE = re.compile(r"[（(）)]|\w\.\w+\.\w|https?:|www\.|\d{4,}|^\d+$")
COMMON_ENGLISH = {"the", "and", "of", "to", "in", "for", "on", "with", "a", "an", "is", "are", "et", "al", "pp",
                  "vol", "no", "doi", "http", "https", "www", "com", "org", "edu", "tw", "p"}


def extract_text(path):
    path = str(path)
    low = path.lower()
    if low.endswith(".docx"):
        with zipfile.ZipFile(path) as z:
            root = ElementTree.fromstring(z.read("word/document.xml"))
        paras = []
        for p in root.iter(W + "p"):
            paras.append("".join(t.text or "" for t in p.iter(W + "t")))
        return "\n".join(x for x in paras if x.strip())
    if low.endswith(".pdf"):
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def chunks(text):
    """依段落切塊，每塊不超過 CHUNK 字（單一段落太長就硬切）。"""
    block = ""
    for para in text.split("\n"):
        while len(para) > CHUNK:
            yield para[:CHUNK]
            para = para[CHUNK:]
        if len(block) + len(para) > CHUNK and block:
            yield block
            block = ""
        block += para + "\n"
    if block.strip():
        yield block


def ask_model(piece, cfg):
    payload = {
        "model": cfg["ollama_model"],
        "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": piece}],
        "stream": False, "think": False, "keep_alive": "60m",
        "options": {"temperature": 0, "num_ctx": 8192, "presence_penalty": 0},
    }
    r = requests.post(cfg["ollama_url"], json=payload, timeout=120)
    r.raise_for_status()
    match = re.search(r"\[.*\]", r.json()["message"]["content"], re.S)
    try:
        return [str(x).strip() for x in json.loads(match.group(0))] if match else []
    except ValueError:
        return []


def english_terms(text):
    """英文詞與縮寫：出現兩次以上、不是常見虛詞的才算。"""
    found = Counter(m.group(0).strip(".-") for m in ENGLISH.finditer(text))
    return [w for w, n in found.items()
            if n >= 2 and len(w) >= 2 and w.split()[0].lower() not in COMMON_ENGLISH]  # 「for Education」不算詞


def candidates(text, cfg, progress=None, cancelled=lambda: False):
    """回傳 [(詞, 出現次數)]，次數多的在前；已在詞庫的不列。progress(完成塊數, 總塊數)。"""
    pieces = list(chunks(text))
    picked = set()
    for i, piece in enumerate(pieces):
        if cancelled():
            break
        try:
            picked.update(ask_model(piece, cfg))
        except requests.RequestException:
            pass  # 某一塊失敗就略過，不影響其他塊
        if progress:
            progress(i + 1, len(pieces))
    picked.update(english_terms(text))
    known = {w.lower() for w in cfg.get("dictionary", [])}
    result = []
    for term in picked:
        if not (2 <= len(term) <= 30) or term.lower() in known or NOISE.search(term):
            continue
        count = text.count(term)
        if count:  # 模型自己編、原文沒有的詞不要
            result.append((term, count))
    result.sort(key=lambda x: (-x[1], x[0]))
    return result
