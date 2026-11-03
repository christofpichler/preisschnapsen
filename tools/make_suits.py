#!/usr/bin/env python3
"""Generate the playing-card suit symbols (Bavarian pattern) as an SVG sprite.

Original artwork: left half flat, right half hatched. Output:
  app/static/img/suits.svg  - standalone file (reference)
  app/static/js/suits.js    - injects the sprite inline into the page so that
                              clipPath references work in all browsers (including Safari).
Usage: python3 tools/make_suits.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INK = "#141414"
RED = "#d8321f"
YEL = "#f7ea3a"
GRN = "#3c7d2c"
BLU = "#1f35d0"
SW = 2.4        # outline width
HW = 0.95       # hatch line width
HS = 3.0        # hatch spacing


def vlines(x0, x1, y0, y1):
    out, x = [], x0 + HS / 2
    while x < x1:
        out.append(f"M{x:.2f} {y0}V{y1}")
        x += HS
    return f'<path d="{"".join(out)}" stroke="{INK}" stroke-width="{HW}" fill="none"/>'


def hlines(x0, x1, y0, y1):
    out, y = [], y0 + HS / 2
    while y < y1:
        out.append(f"M{x0} {y:.2f}H{x1}")
        y += HS
    return f'<path d="{"".join(out)}" stroke="{INK}" stroke-width="{HW}" fill="none"/>'


def clip(cid, shape):
    return f'<clipPath id="{cid}">{shape}</clipPath>'


def herz():
    p = ("M50 93 C38 79 6 60 6 34 C6 18 17 8 30 8 C40 8 47 14 50 23 "
         "C53 14 60 8 70 8 C83 8 94 18 94 34 C94 60 62 79 50 93 Z")
    return (clip("cl-herz", f'<path d="{p}"/>'),
            f'<path d="{p}" fill="{RED}"/>'
            f'<g clip-path="url(#cl-herz)">{vlines(50, 100, 0, 100)}</g>'
            f'<path d="M50 23 V93" stroke="{INK}" stroke-width="1.1"/>'
            f'<path d="{p}" fill="none" stroke="{INK}" stroke-width="{SW}" stroke-linejoin="round"/>')


def herz_leer():
    p = ("M50 93 C38 79 6 60 6 34 C6 18 17 8 30 8 C40 8 47 14 50 23 "
         "C53 14 60 8 70 8 C83 8 94 18 94 34 C94 60 62 79 50 93 Z")
    return ("", f'<path d="{p}" fill="currentColor" fill-opacity=".14" stroke="currentColor" '
                f'stroke-width="7" stroke-linejoin="round"/>')


def bummerl():
    """Lost game marker: black dot in the same heraldic style as the heart
    (solid left half, hatched right half, ink outline)."""
    c = '<circle cx="50" cy="52" r="34"/>'
    return (clip("cl-bummerl", c),
            f'<circle cx="50" cy="52" r="34" fill="{INK}"/>'
            f'<g clip-path="url(#cl-bummerl)"><rect x="50" y="0" width="50" height="100" fill="#2b2b2b"/>'
            f'{vlines(50, 100, 0, 100)}</g>'
            f'<path d="M50 18 V86" stroke="{INK}" stroke-width="1.1"/>'
            f'<circle cx="50" cy="52" r="34" fill="none" stroke="{INK}" stroke-width="{SW}"/>')


def gras():
    leaf = ("M51 5 C60 16 88 34 91 56 C93 72 82 80 68 79 C61 78 56 75 52 71 "
            "C48 75 42 78 35 79 C21 80 9 71 11 56 C14 34 42 16 51 5 Z")
    stem = "M52 71 C53 81 51 88 45 93 C42 95 40 92 43 90 C47 87 49 81 49 72 Z"
    veins = ("M17 36 C34 33 58 35 82 38 M28 33 l-5 -6 M44 34 l-4 -7 M60 35 l3 -6 M72 36 l4 -6 "
             "M13 50 C36 46 62 48 88 51 M26 48 l-5 -6 M44 47 l-4 -7 M62 48 l3 -7 M76 49 l5 -6 "
             "M14 64 C38 60 64 62 89 65 M28 62 l-4 -6 M46 61 l-4 -7 M64 62 l3 -7 M78 63 l5 -6")
    return (clip("cl-gras", f'<path d="{leaf}"/>'),
            f'<path d="{stem}" fill="{GRN}" stroke="{INK}" stroke-width="1.8" stroke-linejoin="round"/>'
            f'<path d="{leaf}" fill="{GRN}"/>'
            f'<g clip-path="url(#cl-gras)">{vlines(51, 100, 0, 100)}</g>'
            f'<g clip-path="url(#cl-gras)"><path d="{veins}" stroke="{INK}" stroke-width="1.9" stroke-linecap="round" fill="none"/></g>'
            f'<path d="{leaf}" fill="none" stroke="{INK}" stroke-width="{SW}" stroke-linejoin="round"/>')


def eichel():
    nut = "M30 52 V23 A20 20 0 0 1 70 23 V52 Z"
    cup = "M24 52 H76 C80 52 82 55 82 60 C82 73 69 81 50 81 C31 81 18 73 18 60 C18 55 20 52 24 52 Z"
    stem = "M53 79 C55 88 51 94 38 98 C36.5 97.5 36.5 96 38 95.5 C46 92 49 87 48 79 Z"
    drop = lambda x: (f"M{x} 57 C{x-5} 57 {x-5.5} 64 {x+1} 76 "
                      f"C{x+1.2} 68 {x+4.5} 61 {x+2.6} 58.2 C{x+2} 57.4 {x+1} 57 {x} 57 Z")
    return (clip("cl-eichel-n", f'<path d="{nut}"/>') + clip("cl-eichel-c", f'<path d="{cup}"/>'),
            f'<path d="{stem}" fill="{GRN}" stroke="{INK}" stroke-width="1.8" stroke-linejoin="round"/>'
            # nut: left yellow, right red hatched
            f'<g clip-path="url(#cl-eichel-n)"><rect x="0" y="0" width="50" height="60" fill="{YEL}"/>'
            f'<rect x="50" y="0" width="50" height="60" fill="{RED}"/>{vlines(50, 100, 0, 52)}'
            # band: left blue, right black
            f'<rect x="0" y="44" width="50" height="8" fill="{BLU}"/><rect x="50" y="44" width="50" height="8" fill="{INK}"/></g>'
            f'<path d="{nut}" fill="none" stroke="{INK}" stroke-width="{SW}" stroke-linejoin="round"/>'
            f'<path d="M30 44 H70 M50 3 V44" stroke="{INK}" stroke-width="1.4"/>'
            # cup: green, right side hatched, black drops
            f'<path d="{cup}" fill="{GRN}"/>'
            f'<g clip-path="url(#cl-eichel-c)">{vlines(50, 100, 50, 84)}</g>'
            f'<path d="{drop(31)} {drop(47)} {drop(64)}" fill="{INK}"/>'
            f'<path d="{cup}" fill="none" stroke="{INK}" stroke-width="{SW}" stroke-linejoin="round"/>')


def schelln():
    c = '<circle cx="50" cy="49" r="43"/>'
    holes = "".join(
        f'<circle cx="{x}" cy="51" r="6.2" fill="{RED}" stroke="{INK}" stroke-width="1.8"/>'
        f'<path d="M{x-5.6} 49 H{x+5.6} M{x-5.8} 51.5 H{x+5.8} M{x-5} 54 H{x+5}" stroke="{INK}" stroke-width="1.2"/>'
        for x in (28, 50, 72))
    leaves = ("M50 92 C41 88 37 79 41 70 C45 74 49 80 50 92 Z "
              "M50 92 C59 88 63 79 59 70 C55 74 51 80 50 92 Z "
              "M24 80 C27 71 35 66 43 68 C40 76 33 81 24 80 Z "
              "M76 80 C73 71 65 66 57 68 C60 76 67 81 76 80 Z")
    return (clip("cl-schelln", c),
            f'<g clip-path="url(#cl-schelln)">'
            f'<rect x="0" y="0" width="100" height="40" fill="{YEL}"/>'
            f'<rect x="0" y="40" width="100" height="22" fill="{RED}"/>'
            f'<rect x="0" y="62" width="100" height="6" fill="{YEL}"/>'
            f'<rect x="0" y="68" width="100" height="40" fill="{GRN}"/>'
            f'{hlines(50, 100, 6, 40)}{vlines(50, 100, 40, 68)}{hlines(50, 100, 68, 100)}'
            f'<path d="M0 40 H100 M0 62 H100 M0 68 H100 M50 6 V100" stroke="{INK}" stroke-width="1.5"/>'
            f'<path d="{leaves}" fill="{GRN}" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/></g>'
            f'{holes}'
            f'<circle cx="50" cy="11" r="5.2" fill="{YEL}" stroke="{INK}" stroke-width="1.6"/>'
            f'<path d="M50 6 V16 M51.5 7.5 H55 M51.5 10 H55.6 M51.5 12.5 H55.4" stroke="{INK}" stroke-width="1"/>'
            f'<path d="M45 91 C45 98 55 98 55 91" fill="{GRN}" stroke="{INK}" stroke-width="1.8"/>'
            f'<circle cx="50" cy="49" r="43" fill="none" stroke="{INK}" stroke-width="{SW}"/>')


def build():
    defs, syms = [], []
    for name, fn in (("eichel", eichel), ("gras", gras), ("herz", herz), ("herz-leer", herz_leer), ("bummerl", bummerl), ("schelln", schelln)):
        d, body = fn()
        defs.append(d)
        syms.append(f'<symbol id="{name}" viewBox="0 0 100 100">{body}</symbol>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" '
            'style="position:absolute;width:0;height:0;overflow:hidden" aria-hidden="true">'
            f'<defs>{"".join(defs)}</defs>{"".join(syms)}</svg>')


def main():
    svg = build()
    (ROOT / "app/static/img/suits.svg").write_text(svg + "\n", encoding="utf-8")
    js = ("/* Generated by tools/make_suits.py - do not edit by hand. */\n"
          "(function () {\n"
          "  var SVG = " + repr(svg).replace("\\'", "'") + ";\n"
          "  function inject() {\n"
          "    if (document.getElementById('suits-sprite')) return;\n"
          "    var d = document.createElement('div'); d.id = 'suits-sprite'; d.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden';\n"
          "    d.innerHTML = SVG; document.body.insertBefore(d, document.body.firstChild);\n"
          "  }\n"
          "  if (document.body) inject(); else document.addEventListener('DOMContentLoaded', inject);\n"
          "})();\n")
    (ROOT / "app/static/js/suits.js").write_text(js, encoding="utf-8")
    print("ok", len(svg), "bytes")


if __name__ == "__main__":
    main()
