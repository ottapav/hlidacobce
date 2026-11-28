"""Samodiagnostika: jednou zkusí každý externí zdroj a vrátí STRUKTURU skutečných odpovědí (klíče, počty, začátek textu).

Slouží k ověření předpokladů o cizích API přímo z nasazení (shell vývojáře k nim často nemá přístup). Token se nikdy nevypisuje.
Spouští se ručně na /api/selftest; nic neběží periodicky.
"""
import io
import re
import time
import urllib.parse
from datetime import date, timedelta

from . import ares, contracts, csu, elections, funding, hlidac, net, schools, webcheck
from .htmlutil import parse_html
from .util import find_first, norm_ico

DEFAULT_ICO = "00235873"  # Velký Osek – jen výchozí vzorek pro diagnostiku
BIG_ICO = "00064581"  # Hlavní město Praha: zadavatel, který má zakázky určitě


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
    data = hlidac.get(path, query, tok, retries=1)
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
        steps.append(_step(f"Zakázky {path} (obec)", lambda p=path: _hlidac_path(p, funding.ZAKAZKY_QUERIES[0].format(ico=ico), tok)))
        steps.append(_step(f"Zakázky {path} (velký zadavatel: Praha)", lambda p=path: _hlidac_path(p, funding.ZAKAZKY_QUERIES[0].format(ico=BIG_ICO), tok)))
    return steps


def _page_steps(ico):
    def subjekt():
        _, html = net.fetch_page(webcheck.HLIDAC_SUBJEKT.format(ico=ico))
        links = parse_html(html).links
        ext = [(h, t) for h, t in links if re.match(r"https?://", h or "", re.I) and "hlidacstatu.cz" not in h]
        return {"html_chars": len(html), "links": len(links), "external_links": [f"{h} | {t[:40]}" for h, t in ext[:15]]}

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
            with net.open_stream(elections.result_url(year, kod), timeout=30) as r:
                raw = r.read(60000)
            out = {"bytes_read": len(raw), "has_ZAPSANI_VOLICI": b"ZAPSANI_VOLICI" in raw}
            try:
                res = elections.parse_result(io.BytesIO(raw))
                out["parsed"] = {"registered": res["registered"], "voted": res["voted"], "parties": len(res["parties"]),
                                 "party_sample": res["parties"][:3]} if res else None
            except elections.ResultError as ex:
                out["server_error"] = str(ex)
            tail = raw[raw.find(b"<VOLEBNI_STRANA"):][:600] if b"<VOLEBNI_STRANA" in raw else b""
            out["party_xml_sample"] = " ".join(tail.decode("utf-8", "replace").split())
            return out
        return _step(f"volby {year}", run)
    return [one(y) for y in elections.YEARS]


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


def _web(ico, name):
    def run():
        cands, errors = webcheck._candidates(ico)
        return {"candidates": {h: {"url": u, "trusted_wikidata": t} for h, (u, t) in cands.items()}, "source_errors": errors,
                "verdict": webcheck.find_site(ico, name)}
    return _step("Web: kandidáti a ověření (Wikidata + Hlídač)", run)


CSI_PORTAL = "https://portal.csicr.cz/"
CSI_CSV = "https://opendata.csicr.cz/Transformation/Download/137"  # otevřená data ČŠI: inspekční zprávy (REDIZO, Jmeno, DatumOd, DatumDo, LinkIZ, PortalLink)


def _csi():
    """Průzkum ČŠI: (1) úvodní stránka InspIS PORTÁLU, (2) začátek CSV s inspekčními zprávami, (3) profil jedné školy z PortalLink
    – hledáme kontakty a web a způsob, jak najít školy podle obce a typu zařízení."""
    def portal():
        final, html = net.fetch_page(CSI_PORTAL)
        p = parse_html(html)
        return {"final_url": final, "title": p.title, "html_chars": len(html), "text_start": " ".join(p.parts)[:500],
                "links": [f"{h} | {t[:40]}" for h, t in p.links[:40]]}

    def csv_head():
        with net.open_stream(CSI_CSV, timeout=30) as r:
            raw = r.read(3000)
        return {"bytes_read": len(raw), "start": raw.decode("utf-8", "replace")[:1500]}

    def form():
        final, html = net.fetch_page(CSI_PORTAL + "Search/School")
        p = parse_html(html)
        return {"final_url": final, "title": p.title, "forms": [
            {"action": f["action"], "method": f["method"],
             "fields": [{"tag": x["tag"], "name": x["name"], "type": x["type"], "value": x["value"][:40],
                         "options": [f"{v}={t}" for v, t in x["options"][:25]]} for x in f["fields"] if x["name"] and not x["name"].startswith(("Answer_", "start_", "end_", "txt_"))]}
            for p_ in [p] for f in p_.forms]}

    def search():
        """Zkusí vyhledání škol ve více variantách (číslo stránky, totalFound) podle obce a podle IČO, ať je jasné, co vrátí řádky tabulky."""
        _, html = net.fetch_page(CSI_PORTAL + "Search/School")
        f = parse_html(html).forms[0]
        base = {x["name"]: x["value"] for x in f["fields"] if x["name"] and x["tag"] == "input" and x["type"] == "hidden"
                and not x["name"].startswith("Answer_") and x["name"] not in ("Lat", "Lng", "PouzeSkolySVyplnenymProfilem")}
        base["PouzeSkolySVyplnenymProfilem"] = "false"
        url = urllib.parse.urljoin(CSI_PORTAL + "Search/School", f["action"])
        try:
            ms_ico = next(e["ico"] for e in schools.schools_from_hlidac(DEFAULT_ICO) if "ms" in e["kinds"])
        except (StopIteration, net.ApiError, ValueError):
            ms_ico = ""
        variants = {
            "obec+MŠ, page=1": {"a03City": "Velký Osek", "a17UIVCode": "A", "page": "1"},
            "obec+MŠ, page=1, totalFound=1": {"a03City": "Velký Osek", "a17UIVCode": "A", "page": "1", "totalFound": "1"},
            "obec+MŠ, page=0, totalFound=1": {"a03City": "Velký Osek", "a17UIVCode": "A", "page": "0", "totalFound": "1"},
            "obec bez druhu, page=1": {"a03City": "Velký Osek", "page": "1"},
            "obec+ZŠ, page=1": {"a03City": "Velký Osek", "a17UIVCode": "B", "page": "1"},
            f"IČO MŠ {ms_ico}, page=1": {"a03ICO": ms_ico, "page": "1"},
        }
        out = {}
        for name, extra in variants.items():
            try:
                _, h = net.fetch_page(url, form={**base, **extra})
                pp = parse_html(h)
                links = [f"{hh} | {t[:60]}" for hh, t in pp.links if re.search(r"School", hh or "", re.I)]
                out[name] = {"chars": len(h), "text": " ".join(pp.parts)[:300], "school_links": links[:5],
                             "row_html": h[h.find("</tr>"):][:900] if "</tr>" in h else ""}
            except (net.ApiError, ValueError) as ex:
                out[name] = {"error": str(ex)}
        return out

    def profile():
        """Profil školy podle REDIZO z CSV (https://portal.csicr.cz/School/REDIZO)."""
        with net.open_stream(CSI_CSV, timeout=30) as r:
            raw = r.read(6000).decode("utf-8", "replace")
        m = re.search(r"https?://portal\.csicr\.cz/School/\d+", raw)
        if not m:
            return {"found_link": None, "csv_start": raw[:300]}
        final, html = net.fetch_page(m.group(0))
        p = parse_html(html)
        text = " ".join(p.parts)
        return {"profile_url": m.group(0), "final_url": final, "title": p.title, "html_chars": len(html), "text": text[:1500],
                "external_links": [f"{h} | {t[:40]}" for h, t in p.links if re.match(r"https?://", h or "", re.I) and "csicr.cz" not in h][:10],
                "emails_or_web": re.findall(r"[\w.-]+@[\w.-]+|www\.[\w./-]+", text)[:10]}
    return [_step("ČŠI: úvodní stránka InspIS PORTÁLu", portal), _step("ČŠI: formulář vyhledávání škol", form), _step("ČŠI: zkušební vyhledání (Velký Osek, MŠ)", search), _step("ČŠI: otevřená data – začátek CSV inspekčních zpráv", csv_head),
            _step("ČŠI: profil školy z PortalLink", profile)]


def selftest(ico=DEFAULT_ICO, only=""):
    if only == "csi":  # rychlý průzkum jen ČŠI
        steps = _csi()
        return {"only": "csi", "ok": sum(1 for s in steps if s["ok"]), "failed": sum(1 for s in steps if not s["ok"]), "steps": steps}
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
    steps.append(_web(ico, steps[0].get("name", "")))
    steps += _csi()
    return {"ico": ico, "kod_obce": kod, "demo": net.DEMO, "ok": sum(1 for s in steps if s["ok"]), "failed": sum(1 for s in steps if not s["ok"]), "steps": steps}
