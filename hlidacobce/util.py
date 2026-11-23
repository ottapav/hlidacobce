"""Drobné pomocné funkce bez závislosti na síti."""
import re
import unicodedata
from datetime import date


def pick(d, *keys, default=None):
    """Hodnota z dictu podle první existující varianty klíče (bez ohledu na velikost písmen)."""
    if not isinstance(d, dict):
        return default
    low = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        v = low.get(k.lower())
        if v not in (None, ""):
            return v
    return default


def parse_date(v):
    if not v:
        return None
    s = str(v)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", s)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def norm_ico(v):
    s = re.sub(r"\D", "", str(v or ""))
    return s.zfill(8) if s else ""


def czk(v):
    return "–" if v is None else f"{v:,.0f}".replace(",", " ") + " Kč"


def cz_date(d):
    return "–" if d is None else f"{d.day}. {d.month}. {d.year}"


def fold(s):
    """Malá písmena bez diakritiky - pro hledání klíčových slov."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()
