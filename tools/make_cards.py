"""Playing-card artwork for the draw animation (one card per suit).

Each card follows the layout of the traditional double-headed German deck:
two suit symbols at the top, a half-length figure with a seasonal scene, and the
same half rotated by 180 degrees below. Herz = spring, Schelln = summer,
Gras = autumn, Eichel = winter.

The symbols reference the suit symbols (#eichel, #gras, #herz, #schelln) of the
same sprite and are included by tools/make_suits.py.
"""

INK = "#1c1c1c"
SKIN = "#f2c8a2"
SKIN_D = "#d9a27c"
WHITE = "#fbfaf4"
RED = "#c8352a"
BLUE = "#3c6db0"
GREEN = "#4f8f3a"
GOLD = "#e3b23c"
BROWN = "#8a5a2b"

W, H = 200, 340
MID = H / 2


def landscape(season):
    """Background strip between the suits and the middle of the card."""
    if season == "winter":
        sky, hills, ground = "#e3edf5", "#cdd9e4", "#f6f8fb"
    elif season == "summer":
        sky, hills, ground = "#d5e9f3", "#9fc06a", "#e6c25a"
    elif season == "autumn":
        sky, hills, ground = "#dcebf2", "#8db65e", "#79a94f"
    else:
        sky, hills, ground = "#d6ecf5", "#9dcd6d", "#a8d46f"
    out = [
        f'<rect x="9" y="84" width="182" height="{MID - 84}" fill="{sky}"/>',
        f'<path d="M9 118 C34 104 52 110 70 114 C92 100 118 102 136 112 C156 104 176 106 191 114 V{MID} H9 Z" fill="{hills}"/>',
        f'<path d="M9 130 C50 124 150 124 191 130 V{MID} H9 Z" fill="{ground}"/>',
    ]
    if season == "spring":
        # rose bushes and a small pavilion
        for x, y in ((24, 146), (172, 148), (44, 158), (154, 160)):
            out.append(f'<ellipse cx="{x}" cy="{y}" rx="13" ry="9" fill="{GREEN}" stroke="{INK}" stroke-width="1"/>')
            out.append("".join(f'<circle cx="{x + dx}" cy="{y + dy}" r="2.4" fill="#d8323c"/>'
                               for dx, dy in ((-6, -2), (0, -4), (6, -1), (-2, 3), (4, 3))))
        out.append(f'<rect x="20" y="104" width="14" height="14" fill="{WHITE}" stroke="{INK}" stroke-width="1"/>'
                   f'<path d="M17 105 L27 96 L37 105 Z" fill="{RED}" stroke="{INK}" stroke-width="1"/>')
    elif season == "summer":
        # stubble rows and sheaves on the field
        out.append(f'<path d="M14 140 H186 M18 150 H182 M12 160 H188" stroke="#c99a2e" stroke-width="1.4"/>')
        for x in (26, 170):
            out.append(f'<path d="M{x} 152 L{x - 7} 128 M{x} 152 L{x} 126 M{x} 152 L{x + 7} 128" stroke="#b8862a" stroke-width="2.4"/>'
                       f'<path d="M{x - 6} 142 H{x + 6}" stroke="{RED}" stroke-width="2"/>')
    elif season == "autumn":
        # vineyard rows with grapes
        for y in (138, 150, 162):
            out.append(f'<path d="M12 {y} H188" stroke="#3f6f2a" stroke-width="3" stroke-dasharray="7 4"/>')
            out.append("".join(f'<circle cx="{x}" cy="{y + 3}" r="2.1" fill="#6b2d6b"/>' for x in range(18, 186, 22)))
    else:
        # snowy house and a bare tree
        out.append(f'<rect x="18" y="104" width="22" height="16" fill="#c98f5a" stroke="{INK}" stroke-width="1"/>'
                   f'<path d="M14 106 L29 94 L44 106 Z" fill="{WHITE}" stroke="{INK}" stroke-width="1"/>'
                   f'<rect x="26" y="110" width="6" height="10" fill="#5a3a1c"/>')
        out.append(f'<path d="M174 160 V108 M174 128 L162 116 M174 120 L186 108 M174 140 L184 132 M162 116 L158 106 M186 108 L190 100" '
                   f'stroke="#5a3a1c" stroke-width="3" stroke-linecap="round" fill="none"/>')
        out.append(f'<path d="M12 150 C40 144 60 152 90 148" stroke="#c9d6e2" stroke-width="2" fill="none"/>')
    return "".join(out)


def figure(season):
    """Half-length woman at the centre; seasonal costume and attribute."""
    hair = {"spring": "#e0ac45", "summer": "#9a6532", "autumn": "#5a3517", "winter": "#7a4a22"}[season]
    jacket = RED if season != "summer" else "#d24a2e"
    out = []
    # hair behind the head
    if season != "winter":
        out.append(f'<path d="M86 52 C84 36 116 36 114 52 L116 70 C108 66 92 66 84 70 Z" fill="{hair}" stroke="{INK}" stroke-width="1.2"/>')
    # neck, blouse with puffed sleeves, bodice, apron
    out.append(f'<rect x="95" y="60" width="10" height="12" fill="{SKIN}" stroke="{INK}" stroke-width="1.2"/>')
    out.append(f'<path d="M66 104 C66 84 80 72 100 72 C120 72 134 84 134 104 L130 120 L70 120 Z" fill="{WHITE}" stroke="{INK}" stroke-width="1.5"/>')
    out.append(f'<path d="M84 76 C92 80 108 80 116 76 L122 {MID} H78 Z" fill="{jacket}" stroke="{INK}" stroke-width="1.5"/>')
    out.append(f'<path d="M94 82 L106 90 M106 82 L94 90 M94 94 L106 102 M106 94 L94 102" stroke="{GOLD}" stroke-width="1.3"/>')
    out.append(f'<path d="M80 138 H120 L124 {MID} H76 Z" fill="{BLUE}" stroke="{INK}" stroke-width="1.5"/>')
    out.append(f'<path d="M84 146 H116 M82 156 H118" stroke="#2c548c" stroke-width="1.2"/>')
    # head
    out.append(f'<circle cx="100" cy="50" r="12.5" fill="{SKIN}" stroke="{INK}" stroke-width="1.5"/>')
    out.append(f'<circle cx="95.5" cy="49" r="1.3" fill="{INK}"/><circle cx="104.5" cy="49" r="1.3" fill="{INK}"/>'
               f'<path d="M96.5 55.5 Q100 58 103.5 55.5" stroke="#b5332c" stroke-width="1.4" fill="none"/>'
               f'<circle cx="93" cy="53.5" r="2.2" fill="#f0a39a" opacity=".7"/><circle cx="107" cy="53.5" r="2.2" fill="#f0a39a" opacity=".7"/>')
    # arms (sleeves and forearms reaching to the attribute)
    hands = {"spring": ((88, 124), (112, 124)), "summer": ((86, 122), (116, 112)),
             "autumn": ((92, 112), (108, 120)), "winter": ((88, 118), (122, 92))}[season]
    for (sx, sy), (hx, hy) in (((74, 94), hands[0]), ((126, 94), hands[1])):
        out.append(f'<path d="M{sx} {sy} L{hx} {hy}" stroke="{INK}" stroke-width="9.5" stroke-linecap="round"/>'
                   f'<path d="M{sx} {sy} L{hx} {hy}" stroke="{SKIN}" stroke-width="7" stroke-linecap="round"/>'
                   f'<circle cx="{sx}" cy="{sy - 2}" r="9" fill="{WHITE}" stroke="{INK}" stroke-width="1.3"/>')
    out.append(attribute(season, hair))
    for hx, hy in hands:
        out.append(f'<circle cx="{hx}" cy="{hy}" r="4.2" fill="{SKIN}" stroke="{INK}" stroke-width="1.2"/>')
    out.append(headwear(season))
    return "".join(out)


def attribute(season, hair):
    if season == "spring":
        # flower basket
        flowers = "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c}" stroke="{INK}" stroke-width=".8"/>'
                          for x, y, r, c in ((90, 118, 4.5, "#d8323c"), (99, 115, 5, "#f07aa0"), (108, 118, 4.5, "#d8323c"),
                                             (95, 121, 3.5, GOLD), (104, 121, 3.5, "#ffffff")))
        return (f'<path d="M86 104 C86 90 114 90 114 104" stroke="{BROWN}" stroke-width="2.6" fill="none"/>'
                + flowers +
                f'<path d="M82 122 H118 L113 142 H87 Z" fill="#c08a45" stroke="{INK}" stroke-width="1.4"/>'
                f'<path d="M84 128 H116 M85 134 H115 M92 122 L94 142 M100 122 V142 M108 122 L106 142" stroke="#8a5a2b" stroke-width="1"/>')
    if season == "summer":
        # wheat sheaf held diagonally and a sickle
        stalks = "".join(f'<path d="M{80 + i * 2} {150 - i} L{116 + i * 2} {98 - i}" stroke="#c9952e" stroke-width="1.6"/>' for i in range(6))
        ears = "".join(f'<ellipse cx="{118 + i * 3}" cy="{96 - i * 2}" rx="2.4" ry="5" transform="rotate(35 {118 + i * 3} {96 - i * 2})" fill="{GOLD}" stroke="{INK}" stroke-width=".6"/>' for i in range(6))
        return (stalks + ears +
                f'<path d="M92 128 L100 136" stroke="{RED}" stroke-width="3"/>'
                f'<path d="M62 116 C56 98 70 86 84 92 C74 92 66 100 70 114 Z" fill="#d7dde2" stroke="{INK}" stroke-width="1.2"/>'
                f'<path d="M70 114 L86 122" stroke="{BROWN}" stroke-width="3.2" stroke-linecap="round"/>')
    if season == "autumn":
        # wine tub with grapes and a stomping pole
        grapes = "".join(f'<circle cx="{x}" cy="{y}" r="3" fill="#6b2d6b" stroke="{INK}" stroke-width=".6"/>'
                         for x, y in ((86, 130), (92, 128), (98, 130), (104, 128), (110, 130), (116, 129), (89, 133), (101, 133), (113, 133)))
        return (f'<path d="M100 96 V136" stroke="{BROWN}" stroke-width="4" stroke-linecap="round"/>'
                f'<path d="M76 132 H124 L120 {MID} H80 Z" fill="#a8743c" stroke="{INK}" stroke-width="1.5"/>'
                f'<path d="M78 142 H122 M79 156 H121" stroke="#5a3a1c" stroke-width="2.4"/>'
                f'<ellipse cx="100" cy="132" rx="24" ry="5" fill="#4d1f4d" stroke="{INK}" stroke-width="1.4"/>' + grapes)
    # winter: bundle of firewood over the right shoulder
    sticks = "".join(f'<path d="M{100 + i * 3} {120 - i * 2} L{150 + i * 2} {70 - i * 3}" stroke="{c}" stroke-width="3.2" stroke-linecap="round"/>'
                     for i, c in enumerate(("#6b4320", "#8a5a2b", "#5a3517", "#7a4a22")))
    return sticks + f'<path d="M118 100 L128 108" stroke="{RED}" stroke-width="2.4"/>'


def headwear(season):
    if season in ("spring", "summer"):
        band = RED if season == "summer" else "#3c7d2c"
        flowers = ("".join(f'<circle cx="{x}" cy="34" r="2.6" fill="#d8323c" stroke="{INK}" stroke-width=".6"/>' for x in (93, 99, 105))
                   if season == "spring" else "")
        return (f'<path d="M89 38 C89 26 111 26 111 38 Z" fill="#ecd17c" stroke="{INK}" stroke-width="1.3"/>'
                f'<path d="M88 35.5 H112" stroke="{band}" stroke-width="2.6"/>' + flowers +
                f'<ellipse cx="100" cy="39" rx="25" ry="6" fill="#f0d886" stroke="{INK}" stroke-width="1.3"/>')
    if season == "autumn":
        return (f'<path d="M88 42 C92 34 108 34 112 42" stroke="{RED}" stroke-width="3.2" fill="none"/>'
                f'<circle cx="100" cy="35" r="5" fill="#5a3517" stroke="{INK}" stroke-width="1"/>')
    # winter headscarf
    return (f'<path d="M85 52 C83 32 117 32 115 52 C116 60 112 66 108 68 L100 64 L92 68 C88 66 84 60 85 52 Z" '
            f'fill="none" stroke="{INK}" stroke-width="1.5"/>'
            f'<path d="M85 52 C83 32 117 32 115 52 L117 58 C112 46 88 46 83 58 Z" fill="#4a78b8" stroke="{INK}" stroke-width="1.4"/>'
            f'<path d="M84 56 C86 64 92 70 100 72 C108 70 114 64 116 56 L118 66 C112 74 88 74 82 66 Z" fill="#4a78b8" stroke="{INK}" stroke-width="1.4"/>'
            f'<path d="M98 70 L92 80 M102 70 L108 80" stroke="#2f5a92" stroke-width="2.4" stroke-linecap="round"/>')


SEASON = {"herz": "spring", "schelln": "summer", "gras": "autumn", "eichel": "winter"}


def card(suit):
    season = SEASON[suit]
    clip_id = f"cl-half-{suit}"
    half_id = f"half-{suit}"
    half = (f'<g id="{half_id}" clip-path="url(#{clip_id})">'
            + landscape(season) + figure(season) +
            f'<use href="#{suit}" x="15" y="12" width="60" height="60"/>'
            f'<use href="#{suit}" x="125" y="12" width="60" height="60"/></g>')
    defs = f'<clipPath id="{clip_id}"><rect x="9" y="9" width="182" height="{MID - 9}"/></clipPath>'
    body = (f'<rect x="2" y="2" width="{W - 4}" height="{H - 4}" rx="14" fill="{WHITE}" stroke="{INK}" stroke-width="2.5"/>'
            + half +
            f'<use href="#{half_id}" transform="rotate(180 {W / 2} {MID})"/>'
            f'<path d="M9 {MID} H191" stroke="{INK}" stroke-opacity=".25" stroke-width="1"/>'
            f'<rect x="9" y="9" width="182" height="{H - 18}" rx="9" fill="none" stroke="{INK}" stroke-opacity=".35" stroke-width="1.2"/>')
    return defs, f'<symbol id="karte-{suit}" viewBox="0 0 {W} {H}">{body}</symbol>'


def _rosette(cx, cy, r, petal, centre):
    """Four-petal rosette with a centre dot."""
    petals = "".join(
        f'<ellipse cx="{cx}" cy="{cy - r * .55:.2f}" rx="{r * .32:.2f}" ry="{r * .55:.2f}" '
        f'transform="rotate({a} {cx} {cy})" fill="{petal}"/>' for a in (0, 90, 180, 270))
    return petals + f'<circle cx="{cx}" cy="{cy}" r="{r * .26:.2f}" fill="{centre}"/>'


def card_back():
    """Back side in the style of 19th century packs: warm paper, black frame, fine
    lattice with rosettes in red and blue, central cartouche. Aspect ratio matches
    the scanned fronts (0.58)."""
    bw, bh = 200, 345
    paper, red, blue, ink = "#faf6ec", "#9b2b22", "#2f4f7f", "#222222"
    cell = 16
    pattern = (f'<pattern id="back-pat" width="{cell}" height="{cell}" patternUnits="userSpaceOnUse">'
               f'<rect width="{cell}" height="{cell}" fill="{paper}"/>'
               f'<path d="M0 0 L{cell} {cell} M{cell} 0 L0 {cell}" stroke="{red}" stroke-width=".7" stroke-opacity=".75"/>'
               + _rosette(cell / 2, cell / 2, 4.6, red, blue)
               + "".join(f'<circle cx="{x}" cy="{y}" r="1.1" fill="{blue}"/>' for x, y in ((0, 0), (cell, 0), (0, cell), (cell, cell)))
               + '</pattern>')
    cx, cy = bw / 2, bh / 2
    big = "".join(
        f'<ellipse cx="{cx}" cy="{cy - 15}" rx="6.5" ry="15" transform="rotate({a} {cx} {cy})" '
        f'fill="{red if a % 90 == 0 else blue}" stroke="{ink}" stroke-width=".6"/>' for a in range(0, 360, 45))
    body = (f'<rect x="1.5" y="1.5" width="{bw - 3}" height="{bh - 3}" rx="12" fill="{paper}" stroke="#00000022" stroke-width="1"/>'
            f'<rect x="10" y="10" width="{bw - 20}" height="{bh - 20}" rx="7" fill="none" stroke="{ink}" stroke-width="1.4"/>'
            f'<rect x="16" y="16" width="{bw - 32}" height="{bh - 32}" rx="3" fill="url(#back-pat)" stroke="{red}" stroke-width="1.2"/>'
            f'<rect x="19" y="19" width="{bw - 38}" height="{bh - 38}" rx="2" fill="none" stroke="{red}" stroke-width=".5"/>'
            f'<ellipse cx="{cx}" cy="{cy}" rx="46" ry="60" fill="{paper}" stroke="{red}" stroke-width="2.2"/>'
            f'<ellipse cx="{cx}" cy="{cy}" rx="41" ry="55" fill="none" stroke="{blue}" stroke-width=".9"/>'
            + big +
            f'<circle cx="{cx}" cy="{cy}" r="7" fill="{paper}" stroke="{ink}" stroke-width=".8"/>'
            + _rosette(cx, cy, 6, red, blue)
            + "".join(_rosette(cx, cy + dy, 4, blue, red) for dy in (-44, 44))
            + "".join(_rosette(cx + dx, cy, 3.4, blue, red) for dx in (-31, 31)))
    return pattern, f'<symbol id="karte-rueckseite" viewBox="0 0 {bw} {bh}">{body}</symbol>'


def build():
    """Returns (defs, symbols) for inclusion in the sprite."""
    defs, syms = [], []
    for suit in ("herz", "schelln", "gras", "eichel"):
        d, s = card(suit)
        defs.append(d)
        syms.append(s)
    back_defs, back = card_back()
    defs.append(back_defs)
    syms.append(back)
    return "".join(defs), "".join(syms)
