#!/usr/bin/env python3
"""Prepare card scans for the draw animation.

Every image in app/static/img/cards/ is picked up by the server at startup; the
dashboard shows four random ones per draw. This script turns a scan into such an
image: the paper tone is neutralised to a warm off-white, the image is scaled to a
fixed width and stored as a compressed JPEG.

Usage:
  python3 tools/prepare_cards.py SCAN [SCAN ...] [--name NAME] [--keep-paper]
  python3 tools/prepare_cards.py STRIP --strip 4 --names a,b,c,d

NAME defaults to the file name of the scan (without extension). With --strip, the
scan contains several cards side by side; each card is cut out along its printed
frame (plus a uniform paper margin). Requires Pillow.
"""
import argparse
import re
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "app/static/img/cards"
PAPER_TARGET = (250, 246, 236)
WIDTH = 480


def paper_tone(im: Image.Image) -> list:
    """Median colour of thin strips just inside the four edges (outside the artwork)."""
    w, h = im.size
    mx, my = max(2, w // 100), max(2, h // 100)
    sx, sy = max(4, w // 40), max(4, h // 40)
    strips = [
        (mx, h // 3, mx + sx, 2 * h // 3),            # left
        (w - mx - sx, h // 3, w - mx, 2 * h // 3),    # right
        (w // 3, my, 2 * w // 3, my + sy),            # top
        (w // 3, h - my - sy, 2 * w // 3, h - my),    # bottom
    ]
    medians = [ImageStat.Stat(im.crop(box)).median for box in strips]
    return [sorted(m[c] for m in medians)[len(medians) // 2] for c in range(3)]


def _dark_profile(gray: Image.Image, box, axis: str) -> list:
    """Share of dark pixels per column (axis="x") or row (axis="y") inside box."""
    x0, y0, x1, y1 = box
    px = gray.load()
    if axis == "x":
        n = max(1, (y1 - y0) // 2)
        return [sum(1 for y in range(y0, y1, 2) if px[x, y] < 100) / n for x in range(x0, x1)]
    n = max(1, (x1 - x0) // 2)
    return [sum(1 for x in range(x0, x1, 2) if px[x, y] < 100) / n for y in range(y0, y1)]


def _outer_peak(values, lo, hi, outermost_first: bool) -> int:
    """Index of the strongest line in values[lo:hi]; among near-equal lines the one
    closest to the card edge wins (printed pips can be as dark as the frame)."""
    best = max(values[lo:hi])
    idx = range(lo, hi) if outermost_first else range(hi - 1, lo - 1, -1)
    return next(i for i in idx if values[i] >= 0.85 * best)


def split_strip(im: Image.Image, count: int) -> list:
    """Cut a scan with `count` cards side by side into single cards, using the printed
    frame of each card (longest dark line near each edge) plus a uniform margin."""
    gray = im.convert("L")
    w, h = im.size
    slice_w = w / count
    cards = []
    for i in range(count):
        sx0, sx1 = round(i * slice_w), round((i + 1) * slice_w)
        cols = _dark_profile(gray, (sx0, int(h * 0.15), sx1, int(h * 0.85)), "x")
        zone = max(4, int(len(cols) * 0.18))
        left = sx0 + _outer_peak(cols, 0, zone, True)
        right = sx0 + _outer_peak(cols, len(cols) - zone, len(cols), False)
        rows = _dark_profile(gray, (left + 6, 0, right - 5, h), "y")
        zone_y = max(4, int(h * 0.15))
        top = _outer_peak(rows, 0, zone_y, True)
        bottom = _outer_peak(rows, h - zone_y, h, False)
        m = round((right - left) * 0.065)
        box = (max(0, left - m), max(0, top - m), min(w, right + m + 1), min(h, bottom + m + 1))
        cards.append(im.crop(box))
    return cards


def neutralise_paper(im: Image.Image) -> Image.Image:
    paper = paper_tone(im)
    lut = []
    for c in range(3):
        f = PAPER_TARGET[c] / max(paper[c], 1)
        lut += [min(255, round(v * f)) for v in range(256)]
    return im.point(lut)


def prepare(src, name: str, keep_paper: bool) -> Path:
    im = src if isinstance(src, Image.Image) else Image.open(src).convert("RGB")
    if not keep_paper:
        im = neutralise_paper(im)
    if im.width > WIDTH:
        im = im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.LANCZOS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{name}.jpg"
    im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return out


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-") or "card"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("scans", nargs="+", type=Path)
    ap.add_argument("--name", help="output name (only with a single scan)")
    ap.add_argument("--keep-paper", action="store_true", help="keep the original paper tone")
    ap.add_argument("--strip", type=int, default=0, help="number of cards side by side in the scan")
    ap.add_argument("--names", help="comma separated output names for --strip")
    a = ap.parse_args()
    if a.strip:
        names = [n.strip() for n in (a.names or "").split(",") if n.strip()]
        if len(a.scans) != 1 or len(names) != a.strip:
            ap.error("--strip needs exactly one scan and as many --names as cards")
        for card, name in zip(split_strip(Image.open(a.scans[0]).convert("RGB"), a.strip), names):
            out = prepare(card, slug(name), a.keep_paper)
            print(f"{a.scans[0]} -> {out.relative_to(ROOT)} {card.size} ({out.stat().st_size // 1024} KB)")
        return
    if a.name and len(a.scans) > 1:
        ap.error("--name only works with a single scan")
    for src in a.scans:
        out = prepare(src, slug(a.name or src.stem), a.keep_paper)
        print(f"{src} -> {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
