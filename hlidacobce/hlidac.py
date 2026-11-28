"""Společný klient REST API Hlídače státu (v2): token, stránkované hledání s deduplikací a jednotné chybové hlášky.

Používá ho Registr smluv (contracts.py) i dotace a veřejné zakázky (funding.py). Cesty a dotazy jsou konstanty v těch modulech.
"""
import json
import os
import threading
import time
import urllib.parse

from . import net
from .cards import card
from .util import find_first, num, pick

API = "https://api.hlidacstatu.cz/api/v2"
TOKEN_URL = "https://www.hlidacstatu.cz/api"
PAUSE_S = 0.8  # minimální odstup mezi voláními API


def token():
    return os.environ.get("HLIDAC_TOKEN", "").strip()


def missing_token_card(title, source, what="data"):
    return card(title, source, "error", None,
                f"Chybí API token Hlídače státu (proměnná prostředí HLIDAC_TOKEN), {what} nelze načíst. Token získáte po registraci na {TOKEN_URL}.",
                links=[("Získat token", TOKEN_URL)])


_gate = threading.Lock()
_last = [0.0]
BACKOFF_S = (3, 8, 20)  # čekání po odpovědi 429 (příliš mnoho požadavků)


def _throttle():
    """Všechna volání API (ze všech záložek a návštěvníků) jdou přes jednu bránu s minimálním odstupem, ať nenarazíme na limit."""
    if net.DEMO:
        return
    with _gate:
        wait = _last[0] + PAUSE_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def get(path, query, tok, page=1, retries=3):
    """Jedna stránka výsledků. Při 429 počká a zkusí znovu; 401/403 = odmítnutý token."""
    headers = {"Authorization": f"Token {tok}"}
    url = f"{API}{path}?" + urllib.parse.urlencode({"dotaz": query, "strana": page})
    for attempt in range(len(BACKOFF_S) + 1):
        _throttle()
        try:
            return net.http_json(url, headers=headers, retries=retries)
        except net.ApiError as ex:
            if ex.code in (401, 403):
                raise net.ApiError(f"Hlídač státu odmítl token (HTTP {ex.code}). Zkontrolujte HLIDAC_TOKEN na {TOKEN_URL}", ex.code) from ex
            if ex.code == 429 and attempt < len(BACKOFF_S):
                time.sleep(0 if net.DEMO else BACKOFF_S[attempt])
                continue
            raise


def search(path, query, tok, max_pages=20, retries=3):
    """Projde všechny stránky výsledků hledání `path` pro `query`. Vrací seznam položek bez duplicit.

    Chyby: 401/403 -> odmítnutý token, 429 -> počká a opakuje, ostatní chyby API se předají dál (s kódem, aby volající mohl zkusit jinou variantu)."""
    out, seen = [], set()
    for page in range(1, max_pages + 1):
        data = get(path, query, tok, page, retries)
        items = data if isinstance(data, list) else (find_first(data, ["results", "items", "data"]) if isinstance(data, dict) else None) or []
        fresh = 0
        for it in items:
            key = str(pick(it, "id", "idVerze", "idSmlouvy") or json.dumps(it, sort_keys=True, default=str))  # jen horní úroveň: vnořené id bývají sdílená
            if key not in seen:
                seen.add(key)
                out.append(it)
                fresh += 1
        total = num(data.get("total")) if isinstance(data, dict) else None
        if not fresh or (total and len(out) >= total):
            break
    return out
