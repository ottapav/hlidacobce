"""Samodiagnostika: jednou zkusí každý externí zdroj a vrátí STRUKTURU skutečných odpovědí (klíče, počty, začátek textu).

Slouží k ověření předpokladů o cizích API přímo z nasazení (shell vývojáře k nim často nemá přístup). Token se nikdy nevypisuje.
Spouští se ručně na /api/selftest; nic neběží periodicky.
"""
import re
import time
import urllib.parse
from datetime import date, timedelta

from . import ares, contracts, csu, elections, funding, hlidac, net, schools, webcheck
from .htmlutil import parse_html
from .util import find_first, norm_ico

DEFAULT_ICO = "00235873"  # Velim – jen výchozí vzorek pro diagnostiku


def _shape(data, depth=0):
    """Stručný popis struktury JSON: typy a klíče, bez dat."""
    if isinstance(data, dict):
        return {k: (_shape(v, depth + 1) if depth < 2 else type(v).__name__) for k, v in list(data.items())[:25]}
    if isinstance(data, list):
        return [f"list[{len(data)}]"] + ([_shape(data[0], depth + 1)] if data else [])
    return type(data).__name__


def _step(name, fn):
    t0 = time.monotonic()
    try:
        detail = fn()
        return {"step": name, "ok": True, "ms": round((time.monotonic() - t0) * 1000), **detail}
    except Exception as ex:  # noqa: BLE001 - diagnostika nesmí selhat na jednom kroku
        return {"step": name, "ok": False, "ms": round((time.monotonic() - t0) * 1000), "error": f"{type(ex).__name__}: {ex}"}


def _hlidac_path(path, query, tok):
    url = f"{hlidac.API}{path}?" + urllib.parse.urlencode({"dotaz": query, "strana": 1})
    data = net.http_json(url, headers={"Authorization": f"Token {tok}"}, retries=1, timeout=30)
    items = data if isinstance(data, list) else (find_first(data, ["results", "items", "data"]) if isinstance(data, dict) else None) or []
    return {"query": query, "path": path, "top_level": _shape(data) if isinstance(data, dict) else f"list[{len(data)}]",
            "items_on_page": len(items), "first_item": _shape(items[0]) if items else None}


def _hlidac_steps(ico):
    tok = hlidac.token()
    if not tok:
        return [{"step": "Hlídač státu API", "ok": False, "error": "HLIDAC_TOKEN není nastaven"}]
    since = date.today() - timedelta(days=365)
    steps = [_step("Smlouvy", lambda: _hlidac_path(contracts.SEARCH_PATH, f"ico:{ico}", tok)),
             _step("Smlouvy (dotaz s datem jako v aplikaci)",
                   lambda: _hlidac_path(contracts.SEARCH_PATH, f"ico:{ico} AND podepsano:[{since:%Y-%m-%d} TO *]", tok)),
             _step("Dotace", lambda: _hlidac_path(funding.DOTACE_PATH, funding.DOTACE_QUERIES[0].format(ico=ico), tok))]
    for path in funding.ZAKAZKY_PATHS:
        for q in funding.ZAKAZKY_QUERIES:
            steps.append(_step(f"Zakázky {path} [{q.split(':')[0]}]", lambda p=path, q=q: _hlidac_path(p, q.format(ico=ico), tok)))
    return steps


def _page_steps(ico):
    def subjekt():
        _, html = net.fetch_page(webcheck.HLIDAC_SUBJEKT.format(ico=ico))
        links = parse_html(html).links
        ext = [(h, t) for h, t in links if re.match(r"https?://", h or "", re.I) and "hlidacstatu.cz" not in h]
        return {"html_chars": len(html), "links": len(links), "web_candidates": webcheck.find_site(ico, "")["status"],
                "labels_found": sum(1 for _, t in links if webcheck.LABEL.search(webcheck.fold(t))),
                "external_links": [f"{h} | {t[:40]}" for h, t in ext[:15]]}

    def vazby():
        _, html = net.fetch_page(schools.HLIDAC_VAZBY.format(ico=ico))
        links = parse_html(html).links
        subj = [(h, t) for h, t in links if re.search(r"/subjekt/", h or "", re.I)]
        return {"html_chars": len(html), "links": len(links), "subject_links": len(subj),
                "subject_link_samples": [f"{h} | {t[:50]}" for h, t in subj[:6]],
                "schools_found": len(schools.schools_from_hlidac(ico))}
    return [_step("Hlídač: stránka subjektu (web)", subjekt), _step("Hlídač: Vazby (podřízené organizace)", vazby)]


def _volby(kod):
    def one(year):
        def run():
            with net.open_stream(elections.URL.format(year=year, kod=kod), timeout=30) as r:
                raw = r.read(40000)
            m = re.findall(rb"<(\w+)([^>]*)>", raw[:4000])
            return {"bytes_read": len(raw), "first_tags": [f"{t.decode()} {a.decode()[:120]}".strip() for t, a in m[:6]],
                    "has_ZAPSANI_VOLICI": b"ZAPSANI_VOLICI" in raw, "raw_start": " ".join(raw[:500].decode("utf-8", "replace").split())}
        return _step(f"volby.cz {year}", run)
    return [one(y) for y in (2022, 2018)]


def _csu(kod):
    def cat():
        return {"config": csu.discover()}

    def api():
        info = csu.load_api(kod)
        return {"rows": len(info["rows"]), "sample": info["rows"][:2]}
    return [_step("ČSÚ DataStat: katalog", cat), _step("ČSÚ DataStat: dotaz na obec", api)]


def _ares(ico, kod):
    def basic():
        b = ares.basic(ico)
        return {"name": b["name"], "kod_obce": b["kod_obce"], "legal_form": b["legal_form"]}

    def seat():
        found = ares.search_by_seat(kod, "331")
        return {"count": len(found), "samples": [b["name"] for b in found[:5]]}
    return [_step("ARES: základní údaje", basic), _step("ARES: příspěvkové organizace se sídlem v obci", seat)]


def _msmt_index():
    _, html = net.fetch_page("https://rejstriky.msmt.cz/opendata/")
    links = [(h, t) for h, t in parse_html(html).links if re.search(r"\.(xml|zip|csv|gz)\b|opendata", h or "", re.I)]
    return {"html_chars": len(html), "links": [f"{h} | {t[:40]}" for h, t in links[:25]]}


def _wikidata(ico, name):
    """Průzkum: má Wikidata u obce oficiální web (P856) a podle které vlastnosti jde najít obec přes IČO?"""
    q = urllib.parse.urlencode({"action": "wbsearchentities", "search": name, "language": "cs", "format": "json", "limit": 5})
    found = net.http_json(f"https://www.wikidata.org/w/api.php?{q}", retries=1, timeout=20).get("search", [])
    out = []
    for e in found[:3]:
        ent = net.http_json(f"https://www.wikidata.org/wiki/Special:EntityData/{e['id']}.json", retries=1, timeout=20)["entities"][e["id"]]
        claims = ent.get("claims", {})
        web = [c.get("mainsnak", {}).get("datavalue", {}).get("value") for c in claims.get("P856", [])]
        ids = {p: [c.get("mainsnak", {}).get("datavalue", {}).get("value") for c in cs][:2] for p, cs in claims.items()
               if any(str(c.get("mainsnak", {}).get("datavalue", {}).get("value")) in (ico, ico.lstrip("0")) for c in cs)}
        out.append({"id": e["id"], "label": e.get("label"), "description": e.get("description"), "P856_web": web, "properties_with_ico": ids})
    return {"entities": out}


def _msmt():
    def head():
        with net.open_stream(schools.REJSTRIK_URL, timeout=30) as r:
            raw = r.read(3000)
        return {"bytes_read": len(raw), "start": raw[:200].decode("utf-8", "replace")}
    return [_step("MŠMT rejstřík (jen začátek souboru)", head)]


def selftest(ico=DEFAULT_ICO):
    ico = norm_ico(ico) or DEFAULT_ICO
    steps = _ares(ico, "0")[:1]
    kod = steps[0].get("kod_obce") or ""
    if kod:
        steps = _ares(ico, kod)
    else:
        steps.append({"step": "ARES: příspěvkové organizace", "ok": False, "error": "chybí kód obce"})
    steps += _hlidac_steps(ico) + _page_steps(ico)
    if kod:
        steps += _volby(kod) + _csu(kod)
    steps += [_step("MŠMT: stránka s otevřenými daty", _msmt_index)] + _msmt()
    steps.append(_step("Wikidata: web obce", lambda: _wikidata(ico, steps[0].get("name", "").replace("Obec ", "").replace("Město ", ""))))
    return {"ico": ico, "kod_obce": kod, "demo": net.DEMO, "ok": sum(1 for s in steps if s["ok"]), "failed": sum(1 for s in steps if not s["ok"]), "steps": steps}
