"""Saydown 的圖示：漸層綠圓角方塊，上面是白色線條對話框（尾巴朝下＝say → down），框裡一對豆豆眼。

系統匣用不同底色表示狀態；視窗與捷徑用 saydown.ico（直接執行這個檔案會重新產生）。
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

BASE = Path(__file__).resolve().parent
ICO_PATH = BASE / "saydown.ico"

# 狀態底色：左上、右下兩色做斜向漸層
STATES = {
    "idle": ("#7fdcae", "#239a72"),  # 漸層綠
    "loading": ("#c9ced8", "#8d94a3"),
    "recording": ("#ff9aa8", "#de4a63"),
    "processing": ("#ffd27a", "#e89424"),
    "error": ("#c3a2f0", "#7a4fc4"),
}


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _gradient(n, a, b):
    a, b = _hex(a), _hex(b)
    small = Image.new("RGB", (64, 64))
    for y in range(64):
        for x in range(64):
            t = (x + y) / 126
            small.putpixel((x, y), tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    return small.resize((n, n), Image.BICUBIC)


def draw(size=256, state="idle"):
    ss = 4 if size <= 64 else 2
    n = size * ss
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    tile = Image.new("L", (n, n), 0)
    ImageDraw.Draw(tile).rounded_rectangle((0, 0, n - 1, n - 1), int(n * 0.24), fill=255)
    img.paste(_gradient(n, *STATES[state]), (0, 0), tile)

    # 對話框外形（框＋朝左下的尾巴），線條＝外形減去往內縮的外形
    shape = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(shape)
    box = (n * 0.17, n * 0.20, n * 0.83, n * 0.70)
    d.rounded_rectangle(box, int(n * 0.21), fill=255)
    d.polygon([(n * 0.29, n * 0.60), (n * 0.47, n * 0.66), (n * 0.25, n * 0.84)], fill=255)
    stroke = max(3, int(n * 0.058)) | 1  # 線條粗細；小尺寸也要看得到
    if size <= 24:
        stroke = int(n * 0.085) | 1
    # 用模糊＋門檻做內縮，邊角比 MinFilter 圓潤
    inner = shape.filter(ImageFilter.GaussianBlur(stroke / 2)).point(lambda v: 255 if v > 250 else 0)
    inner = inner.filter(ImageFilter.MinFilter(3))
    line = ImageChops.subtract(shape, inner)
    white = Image.new("RGBA", (n, n), (255, 255, 255, 255))
    img.paste(white, (0, 0), line)

    # 豆豆眼：白色直立小橢圓
    d = ImageDraw.Draw(img)
    ew, eh = n * (0.058 if size > 24 else 0.075), n * (0.078 if size > 24 else 0.095)
    cy = n * 0.45
    for cx in (n * 0.39, n * 0.61):
        d.ellipse((cx - ew / 2, cy - eh / 2, cx + ew / 2, cy + eh / 2), fill="white")
    return img.resize((size, size), Image.LANCZOS)


def tray(state):
    return draw(64, state)


def save_ico():
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    big = draw(256)
    big.save(ICO_PATH, sizes=[(s, s) for s in sizes], append_images=[draw(s) for s in sizes[:-1]])
    big.save(BASE / "saydown.png")


if __name__ == "__main__":
    save_ico()
