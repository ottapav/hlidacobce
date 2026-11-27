"""Struktura karty, kterou server posílá do prohlížeče.

Karta = jeden zdroj údajů:
  {"title", "source", "status", "asof", "intro", "blocks": [...], "links": [{"text","url"}], "notes": [...], "retry": bool}
status: ok | warn | info | link | error
Bloky: heading, text, list, kv, table, bars (sloupcový graf, kreslí klient jako SVG). Buňka tabulky je text nebo {"text", "url"} či {"text", "align"}.
"""
from datetime import date

from .util import cz_date


def card(title, source, status="info", asof=None, intro=None, blocks=None, links=None, notes=None, retry=False):
    return {
        "title": title,
        "source": source,
        "status": status,
        "asof": asof,
        "intro": intro,
        "blocks": blocks or [],
        "links": [{"text": t, "url": u} for t, u in (links or [])],
        "notes": notes or [],
        "retry": bool(retry),  # klient kartu po chvíli načte znovu (data se připravují)
    }


def today_str():
    return cz_date(date.today())


def heading(text):
    return {"type": "heading", "text": text}


def text(s):
    return {"type": "text", "text": s}


def bullets(items):
    return {"type": "list", "items": list(items)}


def kv(rows):
    return {"type": "kv", "rows": [[k, "–" if v in (None, "") else str(v)] for k, v in rows]}


def table(headers, rows, empty="Nic nenalezeno."):
    return {"type": "table", "headers": headers, "rows": rows, "empty": empty}


def cell_link(text_, url):
    return {"text": text_, "url": url}


def cell_right(text_):
    return {"text": text_, "align": "right"}


def bars(title, categories, series, stacked=False, unit=""):
    """Sloupcový graf. series = [(název, [hodnoty pro každou kategorii])]; stacked=True skládá série na sebe (součet = celek)."""
    return {"type": "bars", "title": title, "categories": [str(c) for c in categories], "stacked": bool(stacked), "unit": unit,
            "series": [{"name": n, "values": [None if v is None else float(v) for v in vals]} for n, vals in series]}
