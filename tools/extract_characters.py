#!/usr/bin/env python3
"""從角色設定圖裁切動畫素材（去白底、輸出 WebP）。

來源：assets/characters/allan_sheet.jpg、assets/characters/arale_sheet.jpg
輸出：presentation/img/{allan,arale}_*.webp
用法：python3 tools/extract_characters.py [--preview build/chars.png]
需求：pip install pillow numpy
"""
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "characters"
OUT = ROOT / "presentation" / "img"

# (名稱, 來源檔, 裁切框 x0, y0, x1, y1)
CROPS = [
    # Allan Lo：正面全身＋表情包
    ("allan_full", "allan_sheet.jpg", (84, 86, 764, 1462)),
    ("allan_smile", "allan_sheet.jpg", (764, 790, 1024, 1126)),
    ("allan_laugh", "allan_sheet.jpg", (1072, 790, 1332, 1126)),
    ("allan_think", "allan_sheet.jpg", (1378, 790, 1634, 1126)),
    ("allan_oops", "allan_sheet.jpg", (1642, 790, 1968, 1126)),
    ("allan_surprised", "allan_sheet.jpg", (764, 1128, 1024, 1468)),
    ("allan_idea", "allan_sheet.jpg", (1042, 1128, 1334, 1468)),
    ("allan_wink", "allan_sheet.jpg", (1382, 1128, 1642, 1468)),
    ("allan_talk", "allan_sheet.jpg", (1704, 1128, 1958, 1468)),
    # 阿拉蕾：全身＋表情格（格線內縮）
    ("arale_full", "arale_sheet.jpg", (74, 804, 408, 1472)),
    ("arale_happy", "arale_sheet.jpg", (437, 807, 795, 1113)),
    ("arale_think", "arale_sheet.jpg", (823, 807, 1181, 1113)),
    ("arale_surprised", "arale_sheet.jpg", (1210, 807, 1568, 1113)),
    ("arale_oops", "arale_sheet.jpg", (1595, 807, 1952, 1113)),
    ("arale_talk", "arale_sheet.jpg", (437, 1143, 795, 1449)),
    ("arale_sad", "arale_sheet.jpg", (823, 1143, 1181, 1449)),
    ("arale_wink", "arale_sheet.jpg", (1210, 1143, 1568, 1449)),
    ("arale_cheer", "arale_sheet.jpg", (1595, 1143, 1952, 1449)),
]


def remove_white(im: Image.Image, thr=232):
    """從邊緣做 flood fill，把連通的近白色背景變透明（角色內部的白色不受影響）。"""
    rgb = np.asarray(im.convert("RGB")).astype(np.int16)
    h, w, _ = rgb.shape
    white = (rgb.min(axis=2) >= thr) & ((rgb.max(axis=2) - rgb.min(axis=2)) < 22)
    bg = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if white[y, x] and not bg[y, x]:
                bg[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if white[y, x] and not bg[y, x]:
                bg[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and white[ny, nx] and not bg[ny, nx]:
                bg[ny, nx] = True; q.append((ny, nx))
    alpha = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    out = im.convert("RGBA")
    out.putalpha(alpha)
    bbox = out.getbbox()
    return out.crop(bbox), bbox


def save(im: Image.Image, name: str, height: int):
    if im.height > height:
        im = im.resize((round(im.width * height / im.height), height), Image.LANCZOS)
    im.save(OUT / f"{name}.webp", "WEBP", quality=88, method=6)
    return im


MANIFEST = {}


def _layer(size, draw_fn, ss=4):
    """在放大畫布上繪製再縮小，得到平滑邊緣的 RGBA 圖層。"""
    big = Image.new("RGBA", (size[0] * ss, size[1] * ss), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(big), lambda v: int(round(v * ss)))
    return big.resize(size, Image.LANCZOS)


def erase_mouth(im: Image.Image, cover):
    """用周邊膚色蓋掉原本的嘴，並保留麥克風等深色物件。"""
    cx, cy, rx, ry = cover
    a = np.asarray(im).astype(np.float64)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    e = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    inside = e <= 1.0
    ring = (e > 1.15) & (e <= 2.2)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    skin = ring & (r > 235) & (g > 175) & (r - b > 60) & (a[..., 3] > 250)
    out = a.copy()
    keep = (r < 150) & (b > r - 15) & (xx > cx + rx * 0.75)   # 麥克風（偏藍的深色）保留
    fill = np.median(a[skin][:, :3], axis=0)                  # 這張圖膚色均勻，取周邊中位數即可
    for c in range(3):
        out[..., c] = np.where(inside & ~keep, fill[c], a[..., c])
    res = Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGBA")
    m = Image.fromarray((inside & ~keep).astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(1.5))
    return Image.composite(res, im, m)


def mouth_frames(base: Image.Image, cx, top, half_w, depth, cover=None):
    """以 base 為底產生嘴型：depth 為張開深度（像素），0 表示閉嘴微笑。
    skin/cover：先用膚色蓋掉原本的嘴（cover = (x0, y0, x1, y1)）。"""
    im = base.copy()
    if cover:
        im = erase_mouth(im, cover)
    def draw(d, k):
        x0, x1 = cx - half_w, cx + half_w
        if depth <= 0:
            d.arc([k(x0), k(top - 8), k(x1), k(top + 8)], 20, 160, fill=(70, 30, 30, 255), width=k(2.6))
            return
        pts = []
        for i in range(41):
            t = i / 40
            x = x0 + (x1 - x0) * t
            pts.append((x, top + 4 * np.sin(np.pi * t)))
        for i in range(40, -1, -1):
            t = i / 40
            x = x0 + (x1 - x0) * t
            pts.append((x, top + 4 * np.sin(np.pi * t) + depth * np.sin(np.pi * t) ** 0.8))
        poly = [(k(x), k(y)) for x, y in pts]
        d.polygon(poly, fill=(92, 26, 34, 255))
        tw = half_w * 0.55
        d.ellipse([k(cx - tw), k(top + depth * 0.45), k(cx + tw), k(top + depth * 1.15)], fill=(236, 110, 120, 255))
        d.line(poly + [poly[0]], fill=(40, 20, 22, 255), width=k(2.2), joint="curve")
        if depth > 7:
            d.chord([k(cx - half_w * 0.6), k(top - 1), k(cx + half_w * 0.6), k(top + 7)], 0, 180, fill=(255, 255, 255, 235))
    # 嘴巴圖層裁在臉內，避免透明區域被畫到
    layer = _layer(im.size, draw)
    im.alpha_composite(layer)
    return im


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sheets = {}
    done = {}
    for name, src, box in CROPS:
        if src not in sheets:
            sheets[src] = Image.open(SRC / src).convert("RGB")
        im, bb = remove_white(sheets[src].crop(box))
        done[name] = save(im, name, 900 if name.endswith("_full") else 520)
        k = done[name].width / im.width
        # 位置資訊（以裁切框為座標系）：讓不同表情在畫面上對齊
        MANIFEST[name] = {"bw": round((box[2] - box[0]) * k), "bh": round((box[3] - box[1]) * k),
                          "x": round(bb[0] * k), "y": round(bb[1] * k), "w": done[name].width, "h": done[name].height}
        print(f"{name:18s} {done[name].size}")

    # 說話嘴型：Allan 以微笑臉為底（閉嘴＝原圖）；阿拉蕾以說話臉為底（張嘴＝原圖）
    base = Image.open(OUT / "allan_smile.webp").convert("RGBA")
    for n, dep in (("allan_m1", 9), ("allan_m2", 17)):
        done[n] = save(mouth_frames(base, cx=125, top=190, half_w=30, depth=dep), n, 520)
    base = Image.open(OUT / "arale_talk.webp").convert("RGBA")
    cover = (171, 173, 37, 20)
    done["arale_m0"] = save(mouth_frames(base, cx=172, top=178, half_w=15, depth=0, cover=cover), "arale_m0", 520)
    done["arale_m1"] = save(mouth_frames(base, cx=172, top=170, half_w=18, depth=11, cover=cover), "arale_m1", 520)
    for n, ref in (("allan_m1", "allan_smile"), ("allan_m2", "allan_smile"), ("arale_m0", "arale_talk"), ("arale_m1", "arale_talk")):
        MANIFEST[n] = dict(MANIFEST[ref])
    import json
    (OUT / "sprites.js").write_text("// 由 tools/extract_characters.py 產生\nwindow.SPRITES = "
                                    + json.dumps(MANIFEST, ensure_ascii=False) + ";\n", encoding="utf-8")
    if "--preview" in sys.argv:
        dst = ROOT / sys.argv[sys.argv.index("--preview") + 1]
        dst.parent.mkdir(parents=True, exist_ok=True)
        cell = 260
        names = list(done)
        cols = 6
        rows = (len(names) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, rows * cell), (40, 60, 90))
        d = ImageDraw.Draw(sheet)
        for i, n in enumerate(names):
            im = done[n].copy(); im.thumbnail((cell - 10, cell - 26))
            x, y = (i % cols) * cell, (i // cols) * cell
            sheet.paste(im, (x + 5, y + 5), im)
            d.text((x + 6, y + cell - 18), n, fill=(255, 255, 0))
        sheet.save(dst)
        print("preview →", dst)


if __name__ == "__main__":
    main()
