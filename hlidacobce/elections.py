"""Výsledky voleb do zastupitelstev obcí (volby.cz, ČSÚ): účast voličů v čase jako graf.

Zdroj: otevřená data volby.cz, XML „výsledky jednoho zastupitelstva“ (https://www.volby.cz/pls/kvRRRR/vysledky_obec?cislo_obce=KOD,
dokumentace KV2022_XML). Názvy atributů (ZAPSANI_VOLICI, ODEVZDANE_OBALKY, PLATNE_HLASY…) jsou převzaty ze zavedené konvence
volby.cz, ale přesné schéma XSD jsem neověřil, proto je čtení tolerantní. Kód zastupitelstva = kód obce (u měst s obvody se liší).
"""
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from . import net
from .cards import bars, card, cell_right, table, text, heading, today_str
from .util import cz_date

URL = "https://www.volby.cz/pls/kv{year}/vysledky_obec?cislo_obce={kod}"
YEARS = (2026, 2022, 2018, 2014, 2010)
SRC = "volby.cz (Český statistický úřad)"


def _num(v):
    try:
        return int(float(str(v).replace(" ", "").replace(",", ".")))
    except (TypeError, ValueError):
        return None


def parse_result(stream):
    """Vrací {registered, voted, valid, name, parties:[{name,votes,mandates}]} nebo None, pokud chybí údaje o účasti."""
    root = ET.parse(stream).getroot()
    ucast = []
    for el in root.iter():
        a = {k.upper(): v for k, v in el.attrib.items()}
        if "ZAPSANI_VOLICI" in a:
            ucast.append((el.tag.rsplit("}", 1)[-1].upper(), a))
    named = [a for t, a in ucast if t == "UCAST"] or [a for _, a in ucast]
    if not named:
        return None
    reg = sum(_num(a.get("ZAPSANI_VOLICI")) or 0 for a in named)
    voted = sum((_num(a.get("ODEVZDANE_OBALKY")) if _num(a.get("ODEVZDANE_OBALKY")) is not None else _num(a.get("VYDANE_OBALKY"))) or 0 for a in named)
    valid = sum(_num(a.get("PLATNE_HLASY")) or 0 for a in named)
    if reg <= 0:
        return None
    parties = {}
    for el in root.iter():
        a = {k.upper(): v for k, v in el.attrib.items()}
        nm = next((a[k] for k in ("NAZ_STR", "NAZEV_STRANY", "NAZEV_STR", "NAZEV") if a.get(k)), None)
        mk = next((k for k in a if "MANDAT" in k), None)
        if not nm or not mk:
            continue
        hk = next((k for k in a if "HLAS" in k and "PROC" not in k), None)
        row = {"name": nm, "votes": _num(a.get(hk)) if hk else None, "mandates": _num(a[mk])}
        old = parties.get(nm)
        if not old or (row["votes"] or 0) > (old["votes"] or 0):
            parties[nm] = row
    return {"registered": reg, "voted": voted, "valid": valid, "parties": list(parties.values())}


def _fetch(year, kod):
    try:
        with net.open_stream(URL.format(year=year, kod=kod), timeout=30) as r:
            return year, parse_result(r), None
    except net.ApiError as ex:
        return year, None, ("nekonalo se" if ex.code in (400, 404) else str(ex))
    except ET.ParseError:
        return year, None, "odpověď není platné XML (volby se v obci nemusely konat)"


def election_card(kod):
    title = "Komunální volby – účast voličů"
    links = [("volby.cz", "https://www.volby.cz"),
             ("Dokumentace XML (KV2022)", "https://volby.gov.cz/opendata/kv2022/KV2022_XML.htm")]
    if kod:
        links.insert(1, ("XML výsledků této obce (2022)", URL.format(year=2022, kod=kod)))
    if not kod:
        return card(title, SRC, "error", None, "ARES nevrátil kód obce, výsledky voleb nelze dohledat.", links=links)
    with ThreadPoolExecutor(max_workers=len(YEARS)) as ex:
        results = sorted(ex.map(lambda y: _fetch(y, kod), YEARS))
    data = [(y, d) for y, d, _ in results if d]
    problems = [f"{y}: {why}" for y, d, why in results if not d and why and why != "nekonalo se"]
    if not data:
        return card(title, SRC, "warn", today_str(),
                    "Výsledky voleb pro tuto obec se nepodařilo načíst." + (" Důvody: " + "; ".join(problems) + "." if problems else
                                                                          " Obec nemusí mít volby v nabízených ročnících nebo má kód zastupitelstva jiný než kód obce."),
                    links=links, notes=["Formát XML jsem naživo neověřil."])
    cats = [str(y) for y, _ in data]
    voted = [d["voted"] for _, d in data]
    non = [max(d["registered"] - d["voted"], 0) for _, d in data]
    rows = [[str(y), cell_right(f"{d['registered']:,}".replace(",", " ")), cell_right(f"{d['voted']:,}".replace(",", " ")),
             cell_right(f"{max(d['registered'] - d['voted'], 0):,}".replace(",", " ")),
             cell_right(f"{100 * d['voted'] / d['registered']:.1f} %")] for y, d in data]
    blocks = [bars("Zapsaní voliči: kolik z nich volilo a kolik ne", cats, [("Volilo", voted), ("Nevolilo", non)], stacked=True, unit="voličů"),
              table(["Volby", "Zapsaných voličů", "Volilo", "Nevolilo", "Účast"], rows)]
    y, last = data[-1]
    parties = sorted([p for p in last["parties"] if p["mandates"] is not None], key=lambda p: (-(p["mandates"] or 0), -(p["votes"] or 0)))
    if parties:
        blocks += [heading(f"Volby {y}: mandáty"),
                   table(["Volební strana / kandidátka", "Hlasů", "Mandátů"],
                         [[p["name"], cell_right("–" if p["votes"] is None else f"{p['votes']:,}".replace(",", " ")), cell_right(str(p["mandates"]))] for p in parties[:15]])]
    notes = ["Nevolilo = zapsaní voliči minus odevzdané obálky. Zapsaní voliči jsou ti ve stálém seznamu v době voleb.",
             "EXPERIMENTÁLNÍ: struktura XML nebyla ověřena naživo. Údaje porovnejte s volby.cz."]
    if problems:
        notes.append("Nenačteno: " + "; ".join(problems))
    return card(title, SRC, "info", today_str(), f"Voleb do zastupitelstva obce v nabízených ročnících: {len(data)}.", blocks, links, notes)
