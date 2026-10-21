"""Images for articles, drawn locally with Pillow (free): a featured image and three in-article graphics.

Style: dark navy, signal blue (#16A6F0), a faint grid, monospace labels. Change the colours below to match
your brand. The footer shows your site's address.
"""
import os
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import settings

BG, PANEL, PANEL2, LINE = "#08121C", "#0F1E2E", "#132638", "#1E3A52"
BLUE, BLUE_D, BLUE_F = "#16A6F0", "#0E6FA3", "#0B3550"
WHITE, MUTED, DIM = "#F2F6FA", "#9FB3C6", "#5F778C"
S = 2  # draw at 2x for sharp text
FONTS = {
    "H": ["C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "R": ["C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
          "/System/Library/Fonts/Supplemental/Arial.ttf"],
    "M": ["C:/Windows/Fonts/consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"],
    "MB": ["C:/Windows/Fonts/consolab.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"],
}


def host() -> str:
    return re.sub(r"^https?://", "", settings.SITE_URL).strip("/") or "your-site.example"


@lru_cache(maxsize=64)
def font(kind: str, size: int):
    for f in FONTS[kind]:
        if os.path.exists(f):
            return ImageFont.truetype(f, size * S)
    return ImageFont.load_default()


class Canvas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.im = Image.new("RGB", (w * S, h * S), BG)
        self.d = ImageDraw.Draw(self.im)
        for x in range(0, w, 40):
            self.d.line([(x * S, 0), (x * S, h * S)], fill="#0B1824", width=1)
        for y in range(0, h, 40):
            self.d.line([(0, y * S), (w * S, y * S)], fill="#0B1824", width=1)

    def text(self, xy, s, f, fill=WHITE, anchor="la"):
        self.d.text((xy[0] * S, xy[1] * S), s, font=f, fill=fill, anchor=anchor)

    def rect(self, box, fill=None, outline=None, width=1, r=0):
        b = [v * S for v in box]
        if r:
            self.d.rounded_rectangle(b, radius=r * S, fill=fill, outline=outline, width=width * S)
        else:
            self.d.rectangle(b, fill=fill, outline=outline, width=width * S)

    def wrap(self, s: str, f, width: int) -> list[str]:
        lines, cur = [], ""
        for w in s.split():
            t = (cur + " " + w).strip()
            if self.d.textlength(t, font=f) <= width * S:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        return lines + ([cur] if cur else [])

    def para(self, xy, s, f, width, lh, fill=MUTED, max_lines=6) -> int:
        lines = self.wrap(s, f, width)[:max_lines]
        for i, line in enumerate(lines):
            self.text((xy[0], xy[1] + i * lh), line, f, fill)
        return len(lines) * lh

    def header(self, kicker, title, sub):
        self.rect((80, 80, 92, 92), fill=BLUE)
        self.text((104, 76), kicker.upper(), font("M", 18), BLUE)
        y = 116
        for line in self.wrap(title, font("H", 44), self.w - 160)[:2]:
            self.text((80, y), line, font("H", 44), WHITE)
            y += 56
        if sub:
            self.para((80, y + 6), sub, font("R", 22), self.w - 160, 30, MUTED, 2)

    def footer(self, note=""):
        note = note or host()
        self.rect((80, self.h - 52, 90, self.h - 42), fill=BLUE)
        self.text((102, self.h - 56), note, font("M", 16), DIM)

    def save(self, path: Path) -> Path:
        self.im.save(path, optimize=True)
        return path


def featured(spec: dict, path: Path) -> Path:
    c = Canvas(1200, 630)
    c.text((70, 70), (spec.get("kicker") or "PRACTICAL GUIDE").upper(), font("M", 20), BLUE)
    y = 112
    for line in c.wrap(spec.get("headline") or "", font("H", 76), 700)[:3]:
        c.text((66, y), line, font("H", 76), WHITE)
        y += 92
    c.para((70, y + 18), spec.get("subhead") or "", font("R", 30), 660, 40, MUTED, 2)
    # signal motif: concentric arcs + nodes
    cx, cy = 980, 330
    for i, r in enumerate((60, 110, 160, 210)):
        c.d.arc([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], 200, 340 + i * 5,
                fill=BLUE if i == 0 else (BLUE_D if i < 3 else LINE), width=5 * S)
    for i, (dx, dy) in enumerate([(-150, 120), (-40, 170), (90, 140), (160, 40)]):
        c.rect((cx + dx - 9, cy + dy - 9, cx + dx + 9, cy + dy + 9), fill=BLUE if i % 2 == 0 else BLUE_D, r=4)
    c.rect((cx - 16, cy - 16, cx + 16, cy + 16), fill=BLUE, r=6)
    c.rect((70, 560, 82, 572), fill=BLUE)
    c.text((94, 553), host(), font("M", 20), MUTED)
    return c.save(path)


def _steps(c, items):
    n = max(1, len(items))
    gap, x0, y0 = 32, 80, 320
    pw = (c.w - 160 - gap * (n - 1)) / n
    ph = 120 + max(34 * len(c.wrap(it.get("label", ""), font("H", 26), pw - 48)[:2])
                   + 32 * len(c.wrap(it.get("text", ""), font("R", 23), pw - 48)[:8]) for it in items)
    ph = min(ph, 470)
    y0 = max(300, (270 + 820 - ph) / 2)  # centre the row in the space under the title
    for i, it in enumerate(items):
        x = x0 + i * (pw + gap)
        c.rect((x, y0, x + pw, y0 + ph), fill=PANEL, outline=LINE, r=12)
        c.text((x + 24, y0 + 24), f"{i + 1:02d}", font("MB", 24), BLUE)
        yy = y0 + 66
        for line in c.wrap(it.get("label", ""), font("H", 26), pw - 48)[:2]:
            c.text((x + 24, yy), line, font("H", 26), WHITE)
            yy += 34
        c.para((x + 24, yy + 10), it.get("text", ""), font("R", 23), pw - 48, 32, MUTED, 8)
        if i < n - 1:
            ax, ay = x + pw + 6, y0 + ph / 2
            c.d.polygon([(ax * S, (ay - 10) * S), ((ax + 20) * S, ay * S), (ax * S, (ay + 10) * S)], fill=BLUE)


def _bars(c, items, unit):
    vals = [float(it.get("value") or 0) for it in items] or [1]
    vmax = max(vals) or 1
    rh, tx0, tx1 = min(96, 460 // max(1, len(items))), 640, 1380
    top = max(300, (270 + 820 - rh * len(items)) / 2)
    for i, it in enumerate(items):
        y = top + i * rh
        c.para((80, y + 6), it.get("label", ""), font("H", 24), 520, 30, WHITE, 2)
        w = (tx1 - tx0) * vals[i] / vmax
        c.rect((tx0, y + 6, tx1, y + 46), fill="#0F1C2B", r=6)
        c.rect((tx0, y + 6, tx0 + max(w, 8), y + 46), fill=BLUE if i == vals.index(max(vals)) else BLUE_D, r=6)
        v = vals[i]
        label = (f"£{v:,.0f}" if unit == "£" else f"{v:,.0f}%" if unit == "%" else f"{v:,.0f} {unit}".strip())
        c.text((tx1 + 24, y + 10), label, font("MB", 26), WHITE)


def _checklist(c, items):
    cols = 2 if len(items) > 4 else 1
    per = -(-len(items) // cols)
    cw = (c.w - 160 - 40 * (cols - 1)) / cols
    for i, it in enumerate(items):
        col, row = divmod(i, per)
        x, y = 80 + col * (cw + 40), max(300, (270 + 820 - per * 112) / 2) + row * 112
        c.rect((x, y, x + cw, y + 92), fill=PANEL, outline=LINE, r=10)
        c.rect((x + 24, y + 30, x + 56, y + 62), outline=BLUE, width=3, r=6)
        c.d.line([((x + 31) * S, (y + 46) * S), ((x + 38) * S, (y + 54) * S), ((x + 50) * S, (y + 37) * S)],
                 fill=BLUE, width=4 * S)
        c.para((x + 76, y + 20 if len(c.wrap(it.get("label", ""), font("R", 22), cw - 100)) > 1 else y + 31),
               it.get("label", ""), font("R", 22), cw - 100, 28, WHITE, 2)


def _compare(c, items):
    cw = (c.w - 200) / 2
    f = font("R", 26)
    ph = 110 + max(sum(36 * len(c.wrap(p, f, cw - 90)[:2]) + 24 for p in (it.get("points") or [])[:6])
                   for it in items[:2])
    top = max(290, (270 + 820 - ph) / 2)
    for i, it in enumerate(items[:2]):
        x = 80 + i * (cw + 40)
        c.rect((x, top, x + cw, top + ph), fill=PANEL if i else "#0A1A2A", outline=BLUE if i == 0 else LINE,
               width=2, r=12)
        c.text((x + 30, top + 28), it.get("label", ""), font("H", 32), BLUE if i == 0 else WHITE)
        y = top + 96
        for p in (it.get("points") or [])[:6]:
            c.rect((x + 30, y + 13, x + 42, y + 25), fill=BLUE if i == 0 else DIM)
            y += c.para((x + 60, y), p, f, cw - 90, 36, WHITE if i == 0 else MUTED, 2) + 24


def graphic(spec: dict, path: Path) -> Path:
    c = Canvas(1600, 900)
    c.header(spec.get("kicker") or "PRACTICAL GUIDE", spec.get("title", ""), spec.get("subtitle", ""))
    items = spec.get("items") or []
    kind = spec.get("kind")
    if kind == "bars":
        _bars(c, items[:6], spec.get("unit", ""))
    elif kind == "checklist":
        _checklist(c, items[:8])
    elif kind == "compare":
        _compare(c, items)
    else:
        _steps(c, items[:5])
    c.footer(spec.get("footer") or host())
    return c.save(path)
