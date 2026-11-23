"""Struktura karty, kterou server posílá do prohlížeče.

Karta = jeden zdroj údajů:
  {"title", "source", "status", "asof", "intro", "blocks": [...], "links": [{"text","url"}], "notes": [...]}
status: ok | warn | info | link | error
Bloky: heading, text, list, kv, table. Buňka tabulky je text nebo {"text", "url"} či {"text", "align"}.
"""
from datetime import date

from .util import cz_date


def card(title, source, status="info", asof=None, intro=None, blocks=None, links=None, notes=None):
    return {
        "title": title,
        "source": source,
        "status": status,
        "asof": asof,
        "intro": intro,
        "blocks": blocks or [],
        "links": [{"text": t, "url": u} for t, u in (links or [])],
        "notes": notes or [],
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
