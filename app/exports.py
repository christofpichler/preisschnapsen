"""CSV export and print view (A4 landscape) modelled on the paper list."""
from __future__ import annotations

import csv
import io
from html import escape
from typing import Any, Dict

from .engine import SYM


def _money(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _cell_text(c: Dict[str, Any]) -> str:
    return c["text"]


def csv_export(t: Dict[str, Any], d: Dict[str, Any]) -> bytes:
    nrounds = d["current_round"]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Nr.", "Name", "NG", "NK"] + [f"R{i}" for i in range(1, nrounds + 1)] + ["Status", "Platz"])
    for p in d["players"]:
        ng = _money(t["ng_amount"]) if p["ng_paid"] else "offen"
        nk = ""
        if p["nk_bought"]:
            nk = _money(t["nk_amount"]) if p["nk_paid"] else "offen"
        elif p["nk_bought"] is False:
            nk = "nein"
        cells = [p["cells"][r]["text"] if r in p["cells"] else "" for r in range(1, nrounds + 1)]
        status = {"out": "ausgeschieden R" + str(p["elim_round"]), "active": "im Spiel", "nk_open": "NK offen"}[p["status"]]
        place = "" if p.get("place_from") is None else (
            str(p["place_from"]) if p["place_from"] == p["place_to"] else f"{p['place_from']}-{p['place_to']}")
        w.writerow([p["number"], p["name"], ng, nk] + cells + [status, place])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def _cell_html(c: Dict[str, Any]) -> str:
    k = c["kind"]
    if k == "bye":
        return '<span class="f">F</span>'
    num = escape(str(c["table"]))
    if k == "win":
        return f"{num}+"
    if k == "loss1":
        return f"{num}–"
    if k == "loss2":
        return f'{num}<span class="nk">–</span>'
    return f"{num}…"


def print_html(t: Dict[str, Any], d: Dict[str, Any]) -> str:
    nrounds = max(d["current_round"], 1)
    P = {p["id"]: p for p in d["players"]}
    rows = []
    for p in d["players"]:
        ng = _money(t["ng_amount"]) if p["ng_paid"] else "–"
        nk = ("" if not p["nk_bought"] else (_money(t["nk_amount"]) if p["nk_paid"] else "offen"))
        tds = "".join(f"<td>{_cell_html(p['cells'][r]) if r in p['cells'] else ''}</td>" for r in range(1, nrounds + 1))
        cls = "out" if p["status"] == "out" else ""
        nm = escape(p["name"]) + (f" <i>({escape(p['nickname'])})</i>" if p["nickname"] else "")
        rows.append(f'<tr class="{cls}"><td class="n">{p["number"]}</td><td class="nm">{nm}</td>'
                    f'<td>{ng}</td><td>{nk}</td>{tds}</tr>')
    head = "".join(f"<th>{r}</th>" for r in range(1, nrounds + 1))
    pl = []
    for g in d["ranking"]["groups"]:
        if g["active"] and not d["finished"]:
            continue
        if len(g["players"]) == 1:
            if g["place_from"] == 1 and d["finished"] and d["winner"]:
                pl.append(f"<li><b>Sieger:</b> {escape(P[g['players'][0]]['name'])}</li>")
            continue
        names = " – ".join(escape(P[i]["name"]) for i in g["players"])
        done = "" if g["decided"] else " <i>(offen)</i>"
        if g["decided"] and len(g["players"]) == 2:
            names = f"{escape(P[g['players'][0]]['name'])} schlägt {escape(P[g['players'][1]]['name'])}"
        pl.append(f"<li>{escape(g['pl_label'])} {names}{done}</li>")
    c = d["cash"]
    cash = (f"NG: {c['ng_count']} &times; {_money(c['ng_amount'])} = {_money(c['ng_sum'])} &euro; &nbsp; "
            f"NK: {c['nk_count']} &times; {_money(c['nk_amount'])} = {_money(c['nk_sum'])} &euro; &nbsp; "
            f"<b>Gesamt: {_money(c['total'])} &euro;</b> (offen: {_money(c['open'])} &euro;)")
    sub = " &middot; ".join(x for x in (escape(t["date"]), escape(t["place"])) if x)
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(t['name'])} – Druckansicht</title>
<style>
@page {{ size: A4 landscape; margin: 10mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Source Sans 3", Arial, sans-serif; color: #111; margin: 14px; font-size: 12px; }}
h1 {{ font-family: "Alegreya SC", Georgia, serif; font-size: 24px; margin: 0 0 2px; }}
.sub {{ color: #444; margin-bottom: 8px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #555; padding: 2px 4px; text-align: center; height: 20px; position: relative; }}
th {{ background: #eee; }}
td.nm {{ text-align: left; white-space: nowrap; }} td.n {{ width: 26px; }}
tr.out td::after {{ content: ""; position: absolute; left: 0; right: 0; top: 50%; border-top: 2px solid #d00; }}
.nk {{ display: inline-block; border: 1.5px solid #d00; color: #d00; border-radius: 50%; width: 15px; height: 15px; line-height: 12px; font-weight: 700; margin-left: 1px; }}
.f {{ display: inline-block; border: 1.5px solid #080; color: #080; border-radius: 50%; width: 16px; height: 16px; line-height: 13px; font-weight: 700; }}
h2 {{ font-size: 14px; margin: 10px 0 3px; }} ul {{ margin: 0; padding-left: 18px; columns: 2; }}
.noprint {{ margin-bottom: 8px; }} button {{ font-size: 16px; padding: 8px 18px; }}
@media print {{ .noprint {{ display: none; }} body {{ margin: 0; }} }}
</style></head><body>
<div class="noprint"><button onclick="window.print()">Drucken</button></div>
<h1>{escape(t['name'])}</h1><div class="sub">{sub}</div>
<table><thead><tr><th>Nr.</th><th>Name</th><th>NG</th><th>NK</th>{head}</tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<h2>Platzierungsspiele</h2><ul>{''.join(pl) or '<li>–</li>'}</ul>
<h2>Kassa</h2><div>{cash}</div>
</body></html>"""
