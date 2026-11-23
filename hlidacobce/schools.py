"""Rejstřík škol a školských zařízení (MŠMT, otevřená data) -> školy a školky zřizované obcí.

EXPERIMENTÁLNÍ: struktura XML je převzata z veřejně dostupných zpracování, naživo ověřena nebyla.
Parser je tolerantní (hledá značky podle konce názvu). Když selže, lze školu zadat ručně přes IČO.
"""
import json
import os
import re
import threading
import xml.etree.ElementTree as ET
from datetime import date

from . import ares, net, webcheck
from .util import fold, norm_ico

REJSTRIK_URL = "https://rejstriky.msmt.cz/opendata/vrejcelk.xml"
CACHE_DIR = os.environ.get("HLIDACOBCE_CACHE", ".hlidacobce_cache")
INDEX_FILE = "rejstrik_index.json"
_lock = threading.Lock()
CACHE_DAYS = 30


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _texts(el):
    """{lowercase local tag: [texty]} pro všechny potomky."""
    out = {}
    for sub in el.iter():
        t = (sub.text or "").strip()
        if t and len(sub) == 0:
            out.setdefault(_local(sub.tag).lower(), []).append(t)
    return out


def _first(tx, *suffixes):
    for k, v in tx.items():
        if any(k.endswith(s) for s in suffixes):
            return v[0]
    return ""


def classify(name, typ=""):
    """Vrací množinu {'ms','zs'} podle názvu a druhu zařízení."""
    f = fold(f"{name} {typ}")
    kinds = set()
    if "materska skola" in f or re.search(r"\bms\b", f):
        kinds.add("ms")
    if "zakladni skola" in f or re.search(r"\bzs\b", f):
        kinds.add("zs")
    return kinds


def parse_rejstrik(stream):
    """Streamově projde XML a vrátí {zrizovatel_ico: [entity]}, kde entity = {ico, name, red_izo, kinds, web, address}."""
    by_founder = {}
    for _, el in ET.iterparse(stream, events=("end",)):
        if _local(el.tag).lower() != "pravnickaosoba":
            continue
        tx = _texts(el)
        direct = {_local(c.tag).lower(): (c.text or "").strip() for c in el if len(c) == 0}
        ico = norm_ico(direct.get("ico", ""))
        name = (direct.get("redplnynazev") or direct.get("rednazev") or direct.get("plnynazev")
                or direct.get("nazev") or _first(tx, "redplnynazev", "rednazev", "skolaplnynazev"))
        kinds, web = set(), ""
        for z in el.iter():
            if _local(z.tag).lower() in ("skolazarizeni", "skolskezarizeni", "zarizeni"):
                zt = _texts(z)
                kinds |= classify(_first(zt, "skolaplnynazev", "plnynazev", "nazev"), _first(zt, "druhtyp", "skoladruhtyp"))
        kinds |= classify(name)
        for k, v in tx.items():
            if k in ("www", "web", "url") or k.endswith("www") or k.endswith("webadresa"):
                web = v[0]
                break
        founders = {norm_ico(v) for k, vals in tx.items() if k.endswith("zrizico") for v in vals}
        ent = {"ico": ico, "name": name, "red_izo": direct.get("redizo", "") or _first(tx, "redizo"), "kinds": sorted(kinds), "web": web,
               "address": _first(tx, "adresa", "textovaadresa")}
        if ico and kinds:
            for f in founders:
                by_founder.setdefault(f, []).append(ent)
        el.clear()
    return by_founder


def load_index(force=False):
    with _lock:  # velký soubor se nesmí stahovat paralelně
        return _load_index(force)


def _load_index(force):
    path = os.path.join(CACHE_DIR, INDEX_FILE)
    if not force:
        try:
            with open(path, encoding="utf-8") as f:
                cached = json.load(f)
            if (date.today() - date.fromisoformat(cached["fetched"])).days <= CACHE_DAYS:
                return cached["index"]
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            pass
    with net.open_stream(REJSTRIK_URL) as r:
        try:
            index = parse_rejstrik(r)
        except ET.ParseError as ex:
            raise net.ApiError(f"Rejstřík škol se nepodařilo zpracovat (XML: {ex}).") from ex
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"fetched": date.today().isoformat(), "index": index}, f, ensure_ascii=False)
    except OSError:
        pass
    return index


HLIDAC_VAZBY = "https://www.hlidacstatu.cz/subjekt/Vazby/{ico}"


def schools_from_hlidac(obec_ico):  # noqa: D401
    """Podřízené organizace obce ze stránky Vazby na Hlídači státu (vedeno podle obchodního rejstříku).
    Z odkazů na subjekty vybere ty, jejichž název vypadá jako škola/školka. Struktura stránky nebyla ověřena naživo."""
    ico = norm_ico(obec_ico)
    _, html = net.fetch_page(HLIDAC_VAZBY.format(ico=ico))
    names = {}
    for href, text in webcheck.parse_html(html).links:
        m = re.search(r"/subjekt/(\d{8})(?:[/?#]|$)", href)
        if m and m.group(1) != ico and len(text) > len(names.get(m.group(1), "")):
            names[m.group(1)] = text
    return [{"ico": i, "name": n, "red_izo": "", "kinds": sorted(classify(n)), "web": "", "address": "", "source": "Hlídač státu"}
            for i, n in names.items() if classify(n)]


def schools_for_obec(obec_ico, kind):
    """Školy (kind='zs') nebo školky (kind='ms') zřizované obcí.
    Nejdřív Hlídač státu (rychlé, jedna malá stránka); když nic nenajde nebo selže, rejstřík škol MŠMT (velký soubor)."""
    try:
        found = schools_from_hlidac(obec_ico)
        if found:
            return [e for e in found if kind in e["kinds"]]
    except (net.ApiError, ValueError):
        pass
    idx = load_index()
    return [dict(e, source="rejstřík MŠMT") for e in idx.get(norm_ico(obec_ico), []) if kind in e["kinds"]]


def school_by_ico(ico, kind):
    """Ruční zadání: údaje z ARES (název, adresa); web musí doplnit uživatel."""
    b = ares.basic(norm_ico(ico))
    return {"ico": b["ico"], "name": b["name"], "red_izo": "", "kinds": [kind], "web": "", "address": b["address"]}
