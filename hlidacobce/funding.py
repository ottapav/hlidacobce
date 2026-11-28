"""Dotace a veřejné zakázky z Hlídače státu (REST API v2). EXPERIMENTÁLNÍ.

Cesty, parametry dotazu a názvy polí jsem naživo neověřil (dokumentace REST API nebyla dostupná). Proto jsou cesty a varianty dotazu
konstanty níže a pole se hledají tolerantně v celé (i vnořené) odpovědi. Když API nevrátí použitelná data, karta to řekne a odkáže na web.
"""
from collections import defaultdict
from datetime import date

from . import hlidac, net
from .cards import bars, card, cell_link, cell_right, heading, kv, table, today_str
from .util import czk, cz_date, find_first, num, parse_date

SRC = "Hlídač státu – Dotace"
SRC_Z = "Hlídač státu – Veřejné zakázky"
DOTACE_PATH = "/Dotace/Hledat"
ZAKAZKY_PATHS = ("/VerejneZakazky/Hledat", "/Zakazky/Hledat")
DOTACE_QUERIES = ("ico:{ico}",)
ZAKAZKY_QUERIES = ("icoZadavatel:{ico}", "ico:{ico}")
MAX_PAGES = 20


def _text(v):
    if isinstance(v, dict):
        v = find_first(v, ["nazev", "jmeno", "obchodniJmeno", "name"]) or ""
    if isinstance(v, list):
        return ", ".join(t for t in (_text(x) for x in v[:4]) if t)
    return str(v) if v is not None else ""


def fetch_all(paths, queries, tok, ico):
    """Projde cesty a varianty dotazu; vrací (položky, použitý dotaz). Chyba 400/404 = zkusit další variantu."""
    last = None
    for path in paths:
        for q in (x.format(ico=ico) for x in queries):
            try:
                return hlidac.search(path, q, tok, max_pages=MAX_PAGES, retries=1), q
            except net.ApiError as ex:
                if ex.code in (401, 403):
                    raise
                last = ex
    raise net.ApiError(f"API Hlídače státu nevrátilo použitelnou odpověď ({last}). Cesta nebo dotaz se mohou lišit od dokumentace.")


# ------------------------------------------------------------------ dotace
def norm_subsidy(raw):
    d = parse_date(find_first(raw, ["datumPodpisu", "datumRozhodnuti", "datumUzavreni"]))
    year = find_first(raw, ["rokRozhodnuti", "approvedYear", "rok", "year"])
    try:
        year = int(float(year)) if year is not None else (d.year if d else None)
    except (TypeError, ValueError):
        year = d.year if d else None
    return {"year": year,
            "amount": num(find_first(raw, ["castkaSchvalena", "schvalenaCastka", "subsidyAmount", "castkaRozhodnuta", "vyseDotace", "castka", "amount"])),
            "project": _text(find_first(raw, ["nazevProjektu", "projectName", "displayProject", "projectDescription", "projekt", "nazev"])),
            "program": _text(find_first(raw, ["nazevProgramu", "programName", "dotacniProgram", "program", "category"])),
            "provider": _text(find_first(raw, ["poskytovatelNazev", "subsidyProvider", "poskytovatel", "dotacePoskytovatel"]))}


def subsidy_card(ico):
    title = "Dotace (Hlídač státu)"
    links = [("Dotace subjektu na Hlídači státu", f"https://www.hlidacstatu.cz/dotace/hledat?q=ico:{ico}")]
    tok = hlidac.token()
    if not tok:
        return hlidac.missing_token_card(title, SRC, "dotace")
    try:
        raw, _ = fetch_all((DOTACE_PATH,), DOTACE_QUERIES, tok, ico)
    except net.ApiError as ex:
        return card(title, SRC, "error", None, str(ex), links=links)
    subs = [norm_subsidy(r) for r in raw]
    total = sum(s["amount"] for s in subs if s["amount"])
    by_year = defaultdict(float)
    for s in subs:
        if s["year"] and s["amount"]:
            by_year[s["year"]] += s["amount"]
    blocks = [kv([("Počet dotací", len(subs)), ("z toho s uvedenou částkou", sum(1 for s in subs if s["amount"])), ("Součet částek", czk(total))])]
    if len(by_year) >= 2:
        ys = sorted(by_year)
        blocks.append(bars("Součet dotací podle roku (Kč)", ys, [("Částka", [by_year[y] for y in ys])], unit="Kč"))
    top = sorted([s for s in subs if s["amount"]], key=lambda s: -s["amount"])[:10]
    blocks += [heading("10 největších dotací"),
               table(["Rok", "Projekt", "Program", "Poskytovatel", "Částka"],
                     [[str(s["year"] or "–"), s["project"][:90], s["program"][:60], s["provider"][:50], cell_right(czk(s["amount"]))] for s in top],
                     "Žádná dotace s uvedenou částkou." if subs else "Hlídač státu žádné dotace neeviduje.")]
    return card(title, SRC, "info" if subs else "warn", today_str(), "Dotace, kde je subjekt příjemcem (podle IČO).", blocks, links,
                ["EXPERIMENTÁLNÍ: cesta API a názvy polí nebyly ověřeny naživo; porovnejte součty s webem Hlídače státu.",
                 "Částky jsou podle rozhodnutí o dotaci, ne nutně skutečně vyplacené."])


# ------------------------------------------------------------------ zakázky
def norm_tender(raw):
    d = parse_date(find_first(raw, ["datumUverejneni", "datumZahajeni", "datumZverejneni", "datum", "publicationDate"]))
    return {"date": d,
            "name": _text(find_first(raw, ["nazevZakazky", "nazev", "name", "predmet"])),
            "value": num(find_first(raw, ["konecnaHodnotaBezDph", "hodnotaBezDph", "finalPrice", "predpokladanaHodnotaBezDph",
                                          "predpokladanaHodnota", "hodnota", "cena"])),
            "supplier": _text(find_first(raw, ["dodavatele", "vitezove", "winners", "dodavatel"])),
            "state": _text(find_first(raw, ["stav", "stavVz", "state"])),
            "url": next((u for u in [find_first(raw, ["url", "odkaz", "detailUrl"])] if isinstance(u, str) and u.startswith("http")), "")}


def tender_card(ico):
    title = "Veřejné zakázky (Hlídač státu)"
    links = [("Subjekt na Hlídači státu", f"https://www.hlidacstatu.cz/subjekt/{ico}")]
    tok = hlidac.token()
    if not tok:
        return hlidac.missing_token_card(title, SRC_Z, "zakázky")
    try:
        raw, q = fetch_all(ZAKAZKY_PATHS, ZAKAZKY_QUERIES, tok, ico)
    except net.ApiError as ex:
        return card(title, SRC_Z, "error", None, str(ex), links=links)
    ts = [norm_tender(r) for r in raw]
    total = sum(t["value"] for t in ts if t["value"])
    by_year = defaultdict(float)
    for t in ts:
        if t["date"] and t["value"]:
            by_year[t["date"].year] += t["value"]
    blocks = [kv([("Počet zakázek", len(ts)), ("z toho s uvedenou hodnotou", sum(1 for t in ts if t["value"])), ("Součet hodnot", czk(total))])]
    if len(by_year) >= 2:
        ys = sorted(by_year)
        blocks.append(bars("Hodnota zakázek podle roku zveřejnění (Kč)", ys, [("Hodnota", [by_year[y] for y in ys])], unit="Kč"))
    latest = sorted(ts, key=lambda t: t["date"] or date.min, reverse=True)[:10]
    blocks += [heading("10 nejnovějších zakázek"),
               table(["Zveřejněno", "Zakázka", "Dodavatel", "Stav", "Hodnota"],
                     [[cz_date(t["date"]), cell_link(t["name"][:90], t["url"]) if t["url"] else t["name"][:90], t["supplier"][:50], t["state"][:30], cell_right(czk(t["value"]))]
                      for t in latest], "Hlídač státu žádné zakázky neeviduje.")]
    return card(title, SRC_Z, "info" if ts else "warn", today_str(), "Zakázky, kde je subjekt zadavatelem (podle IČO).", blocks, links,
                [f"Použitý dotaz: {q}",
                 "EXPERIMENTÁLNÍ: cesta API, dotaz a názvy polí nebyly ověřeny naživo; porovnejte s webem Hlídače státu."])
