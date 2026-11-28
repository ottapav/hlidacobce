"""Školy a školky zřizované obcí: zjišťují se automaticky, nic se nezadává ručně.

Zdroje v pořadí: (1) Hlídač státu – stránka Vazby obce (podřízené organizace), (2) ARES – příspěvkové organizace se sídlem v obci.
Oba jsou ověřeny naživo. Rejstřík škol MŠMT jsem odstranil: soubor s otevřenými daty je z cloudu nedostupný (HTTP 403/404)."""
import re

from . import ares, net
from .htmlutil import parse_html
from .util import fold, norm_ico


def classify(name, typ=""):
    """Vrací množinu {'ms','zs'} podle názvu a druhu zařízení."""
    f = fold(f"{name} {typ}")
    kinds = set()
    if "materska skola" in f or re.search(r"\bms\b", f):
        kinds.add("ms")
    if "zakladni skola" in f or re.search(r"\bzs\b", f):
        kinds.add("zs")
    return kinds


HLIDAC_VAZBY = "https://www.hlidacstatu.cz/subjekt/Vazby/{ico}"


def schools_from_hlidac(obec_ico):
    """Podřízené organizace obce ze stránky Vazby na Hlídači státu (vedeno podle obchodního rejstříku).
    Z odkazů na subjekty vybere ty, jejichž název vypadá jako škola/školka. Struktura stránky nebyla ověřena naživo."""
    ico = norm_ico(obec_ico)
    _, html = net.fetch_page(HLIDAC_VAZBY.format(ico=ico))
    names = {}
    for href, text in parse_html(html).links:
        m = re.search(r"/subjekt/(?:index/)?(\d{8})(?:[/?#]|$)", href, re.I)
        if m and m.group(1) != ico and len(text) > len(names.get(m.group(1), "")):
            names[m.group(1)] = text
    return [{"ico": i, "name": n, "red_izo": "", "kinds": sorted(classify(n)), "web": "", "address": "", "source": "Hlídač státu"}
            for i, n in names.items() if classify(n)]


def schools_from_ares(obec_ico):
    """Příspěvkové organizace se sídlem v obci (ARES), vybrané podle názvu. Nemusí jít vždy o zřizovatele obec."""
    kod = ares.basic(norm_ico(obec_ico))["kod_obce"]
    if not kod:
        raise net.ApiError("ARES nevrátil kód obce")
    out = []
    for b in ares.search_by_seat(kod, "331"):
        k = classify(b["name"])
        if k and b["ico"] != norm_ico(obec_ico):
            out.append({"ico": b["ico"], "name": b["name"], "red_izo": "", "kinds": sorted(k), "web": "",
                        "address": b["address"], "source": "ARES (sídlo v obci)"})
    return out


def schools_for_obec(obec_ico, kind):
    """Školy (kind='zs') nebo školky (kind='ms') obce. Zdroje v pořadí: Hlídač státu (podřízené organizace),
    ARES (příspěvkové organizace se sídlem v obci). Když žádný nic nenajde, chyba obsahuje důvody."""
    problems = []
    for name, fn in (("Hlídač státu", schools_from_hlidac), ("ARES", schools_from_ares)):
        try:
            found = [e for e in fn(obec_ico) if kind in e["kinds"]]
        except (net.ApiError, ValueError) as ex:
            problems.append(f"{name}: {ex}")
            continue
        if found:
            return found
        problems.append(f"{name}: nenalezeno žádné takové zařízení")
    raise net.ApiError("Školu se nepodařilo najít automaticky (" + "; ".join(problems) + ").")
