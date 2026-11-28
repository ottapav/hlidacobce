"""Drobné pomocné funkce bez závislosti na síti."""
import os
import re
import unicodedata
from datetime import date

EMPTY = (None, "", [], {})


def cache_dir():
    """Adresář pro disková cache (čte se při každém použití, aby šel v testech přepsat proměnnou prostředí)."""
    return os.environ.get("HLIDACOBCE_CACHE", ".hlidacobce_cache")


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


def find_first(obj, names, depth=0):
    """První neprázdná hodnota pod klíčem z `names` (v pořadí priorit; bez ohledu na velikost písmen), hledá i ve vnořených objektech.
    Používá se tam, kde názvy polí cizího API nejsou ověřené."""
    for name in names:
        hit = _dfs(obj, name.lower(), depth)
        if hit not in EMPTY:
            return hit
    return None


def _dfs(obj, key, depth):
    if depth > 4:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() == key and v not in EMPTY:
                return v
        children = [v for v in obj.values() if isinstance(v, (dict, list))]
    elif isinstance(obj, list):
        children = obj[:20]
    else:
        return None
    for v in children:
        r = _dfs(v, key, depth + 1)
        if r not in EMPTY:
            return r
    return None


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


def thousands(n):
    """Celé číslo s mezerou jako oddělovačem tisíců (nezlomitelnou, aby se číslo nerozdělilo na dva řádky)."""
    return f"{int(round(n)):,}".replace(",", "\u00a0")


def czk(v):
    return "–" if v is None else thousands(v) + "\u00a0Kč"


def cz_date(d):
    return "–" if d is None else f"{d.day}. {d.month}. {d.year}"


def fold(s):
    """Malá písmena bez diakritiky - pro hledání klíčových slov."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()
