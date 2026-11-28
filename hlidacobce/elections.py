"""Výsledky voleb do zastupitelstev obcí (volby.cz, ČSÚ): účast voličů v čase jako graf.

Zdroj: otevřená data volby.cz, XML „výsledky jednoho zastupitelstva“ (https://www.volby.cz/pls/kvRRRR/vysledky_obec?cislo_obce=KOD,
dokumentace KV2022_XML).
Struktura ověřena naživo (Velký Osek 2018 a 2022): OBEC > VYSLEDEK > UCAST (ZAPSANI_VOLICI, VYDANE_OBALKY, ODEVZDANE_OBALKY, PLATNE_HLASY)
a VOLEBNI_STRANA (NAZEV_STRANY, HLASY). Bez parametru datumvoleb server vrací jen „aktuální volby“, proto se zadává první den voleb.
Čtení je přesto tolerantní (u atributů s mandáty jsem přesný název neověřil). Kód zastupitelstva = kód obce (u měst s obvody se liší).
"""
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from . import net
from .cards import bars, card, cell_right, heading, table, today_str
from .util import thousands

# Starší ročníky: služba volby.cz bez parametru datumvoleb vrací jen „aktuální volby“ (naživo ověřeno: „V aktuálních volbách se v obci nevolí“),
# správný je PRVNÍ den voleb (ověřeno 2022 a 2018; druhý den vrací „žádné volby se nekonaly“; 2014 a 2010 odvozeno z termínů voleb).
OLD_DATES = {2022: "20220923", 2018: "20181005", 2014: "20141010", 2010: "20101015"}
# Volby 2026 (9.–10. 10. 2026) mají jiné rozhraní: statické XML podle kódu zastupitelstva (dokumentace volby.gov.cz/opendata/kv2026).
URLS = {2026: "https://volby.gov.cz/appdata/kv2026/20261009/odata/zastup/vysledky_obec_{kod}.xml",
        **{y: f"https://www.volby.cz/pls/kv{y}/vysledky_obec?cislo_obce={{kod}}&datumvoleb={d}" for y, d in OLD_DATES.items()}}
YEARS = tuple(URLS)
SRC = "volby.cz (Český statistický úřad)"


def _num(v):
    try:
        return int(float(str(v).replace(" ", "").replace(",", ".")))
    except (TypeError, ValueError):
        return None


class ResultError(Exception):
    """volby.cz vrátily XML s elementem CHYBA (např. neplatné číslo zastupitelstva)."""


def parse_result(stream):
    """Vrací {registered, voted, valid, name, parties:[{name,votes,mandates}]} nebo None, pokud chybí údaje o účasti.
    Když server vrátí chybové XML (element CHYBA), vyvolá ResultError s jeho textem."""
    root = ET.parse(stream).getroot()
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1].upper() == "CHYBA":
            raise ResultError(" ".join(filter(None, [(el.text or "").strip(), *(f"{k}={v}" for k, v in el.attrib.items())])) or "bez popisu")
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
        hk = next((k for k in a if "HLAS" in k and "PROC" not in k), None)
        if not nm or not (mk or hk):
            continue
        row = {"name": nm, "votes": _num(a.get(hk)) if hk else None, "mandates": _num(a[mk]) if mk else None}
        old = parties.get(nm)
        if not old or (row["votes"] or 0) > (old["votes"] or 0):
            parties[nm] = row
    return {"registered": reg, "voted": voted, "valid": valid, "parties": list(parties.values())}


def result_url(year, kod):
    return URLS[year].format(kod=re.sub(r"\D", "", str(kod)))


def _fetch(year, kod):
    """(rok, výsledek nebo None, důvod)."""
    try:
        with net.open_stream(result_url(year, kod), timeout=30) as r:
            res = parse_result(r)
        return year, res, None if res else "v odpovědi chybí údaje o účasti"
    except net.ApiError as ex:
        return year, None, "nekonalo se" if ex.code in (400, 404) else str(ex)
    except ResultError as ex:
        return year, None, f"volby.cz vrátily: {ex}"
    except ET.ParseError:
        return year, None, "odpověď není platné XML"


def election_card(kod):
    title = "Komunální volby – účast voličů"
    links = [("volby.cz", "https://www.volby.cz"),
             ("Dokumentace XML (KV2022)", "https://volby.gov.cz/opendata/kv2022/KV2022_XML.htm")]
    if not kod:
        return card(title, SRC, "error", None, "ARES nevrátil kód obce, výsledky voleb nelze dohledat.", links=links)
    links.insert(1, ("XML výsledků této obce (2026)", result_url(2026, kod)))
    with ThreadPoolExecutor(max_workers=len(YEARS)) as ex:
        results = sorted(ex.map(lambda y: _fetch(y, kod), YEARS))
    data = [(y, d) for y, d, _ in results if d]
    problems = [f"{y}: {why}" for y, d, why in results if not d and why and why != "nekonalo se"]
    if not data:
        return card(title, SRC, "warn", today_str(),
                    "Výsledky voleb pro tuto obec se nepodařilo načíst." + (" Důvody: " + "; ".join(problems) + "." if problems else
                                                                          " Obec nemusí mít volby v nabízených ročnících nebo má kód zastupitelstva jiný než kód obce."),
                    links=links)
    cats = [str(y) for y, _ in data]
    voted = [d["voted"] for _, d in data]
    non = [max(d["registered"] - d["voted"], 0) for _, d in data]
    rows = [[str(y), cell_right(thousands(d["registered"])), cell_right(thousands(d["voted"])), cell_right(thousands(max(d["registered"] - d["voted"], 0))),
             cell_right(f"{100 * d['voted'] / d['registered']:.1f} %")] for y, d in data]
    blocks = [bars("Zapsaní voliči: kolik z nich volilo a kolik ne", cats, [("Volilo", voted), ("Nevolilo", non)], stacked=True, unit="voličů"),
              table(["Volby", "Zapsaných voličů", "Volilo", "Nevolilo", "Účast"], rows)]
    y, last = data[-1]
    parties = sorted(last["parties"], key=lambda p: (-(p["mandates"] or 0), -(p["votes"] or 0)))
    if parties:
        blocks += [heading(f"Volby {y}: kandidátky"),
                   table(["Volební strana / kandidátka", "Hlasů", "Mandátů"],
                         [[p["name"], cell_right("–" if p["votes"] is None else thousands(p["votes"])),
                           cell_right("–" if p["mandates"] is None else str(p["mandates"]))] for p in parties[:15]])]
    notes = ["Nevolilo = zapsaní voliči minus odevzdané obálky. Zapsaní voliči jsou ti ve stálém seznamu v době voleb.",
             "Účast je ověřena na živých datech volby.cz (2018, 2022); mandáty se čtou z atributů XML tolerantně."]
    if problems:
        notes.append("Nenačteno: " + "; ".join(problems))
    return card(title, SRC, "info", today_str(), f"Voleb do zastupitelstva obce v nabízených ročnících: {len(data)}.", blocks, links, notes)
