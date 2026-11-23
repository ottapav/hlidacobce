"""Registr smluv (Hlídač státu): stažení smluv a signály ke kontrole -> karty."""
import json
import os
import re
import time
import urllib.parse
from collections import defaultdict
from datetime import date, timedelta

from . import ares, net
from .cards import (bullets, card, cell_link, cell_right, heading, kv, table, text, today_str)
from .util import czk, cz_date, norm_ico, num, parse_date, pick

SRC = "Hlídač státu – Registr smluv"

# Limity zakázek malého rozsahu (bez DPH). Ověřte aktuální znění zákona o zadávání veřejných zakázek.
LIMIT_SERVICES = 2_000_000
LIMIT_WORKS = 6_000_000
NEAR_LIMIT_RATIO = 0.90
SPLIT_WINDOW_DAYS = 365
LATE_PUBLISH_DAYS = 30
CONCENTRATION_SHARE = 0.30
CONCENTRATION_MIN_N = 3
NEW_COMPANY_DAYS = 365
ARES_TOP_SUPPLIERS = 15
MAX_PAGES = 40

HLIDAC_API = "https://api.hlidacstatu.cz/api/v2"
HLIDAC_SEARCH_PATH = "/Smlouvy/Hledat"

OBEC_NOTE = ("Registr smluv neobsahuje smlouvy do 50 000 Kč bez DPH a obce do 3 000 obyvatel mají zákonnou výjimku, "
             "takže chybějící smlouvy nemusí znamenat nic špatného.")
SCHOOL_NOTE = ("Podle metodiky MŠMT se povinnost zveřejňovat smlouvy v registru týká jen škol zřizovaných obcemi "
               "s rozšířenou působností nebo krajem. U ostatních škol jsou smlouvy v registru dobrovolné nebo chybí.")


def token():
    return os.environ.get("HLIDAC_TOKEN", "").strip()


def fetch_contracts(ico, since, tok):
    query = f"ico:{ico} AND podepsano:[{since:%Y-%m-%d} TO *]"
    headers = {"Authorization": f"Token {tok}"}
    out, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = f"{HLIDAC_API}{HLIDAC_SEARCH_PATH}?" + urllib.parse.urlencode({"dotaz": query, "strana": page})
        try:
            data = net.http_json(url, headers=headers)
        except net.ApiError as ex:
            if ex.code in (401, 403):
                raise net.ApiError("Hlídač státu odmítl token (401/403). Zkontrolujte HLIDAC_TOKEN na https://www.hlidacstatu.cz/api", ex.code) from ex
            if ex.code in (400, 404):
                raise net.ApiError(f"API Hlídače státu vrátilo {ex.code}. Ověřte cestu a parametry ve Swaggeru "
                                   "(https://api.hlidacstatu.cz/swagger/index.html) a upravte HLIDAC_SEARCH_PATH v contracts.py.", ex.code) from ex
            raise
        items = data if isinstance(data, list) else pick(data, "results", "items", "data") or []
        fresh = 0
        for it in items:
            sid = str(pick(it, "id", "idVerze", "idSmlouvy") or json.dumps(it, sort_keys=True, default=str))
            if sid in seen:
                continue
            seen.add(sid)
            out.append(it)
            fresh += 1
        total = num(pick(data, "total")) if isinstance(data, dict) else None
        if not fresh or (total and len(out) >= total):
            break
        if not net.DEMO:
            time.sleep(0.3)
    return out


def normalize(raw, ico):
    def party(p):
        pico = norm_ico(pick(p, "ico", "icoOsoby"))
        name = pick(p, "nazev", "jmeno", "obchodniJmeno", default="") or ""
        return {"ico": pico, "name": name, "key": pico or name or "(neuvedeno)"}

    plat = pick(raw, "platce") or {}
    prij = pick(raw, "prijemce") or []
    if isinstance(prij, dict):
        prij = [prij]
    parties = [party(p) for p in ([plat] if plat else []) + list(prij)]
    others = [p for p in parties if p["ico"] != ico] or [{"ico": "", "name": "(neuvedeno)", "key": "(neuvedeno)"}]
    bez, vat = num(pick(raw, "hodnotaBezDph", "cenaBezDph")), num(pick(raw, "hodnotaVcetneDph", "cenaSDph", "calculatedPriceWithVATinCZK"))
    sid = str(pick(raw, "id", "idVerze", "idSmlouvy", default=""))
    return {
        "id": sid,
        "subject": pick(raw, "predmet", "nazev", default="(předmět neuveden)"),
        "signed": parse_date(pick(raw, "datumUzavreni", "podepsano")),
        "published": parse_date(pick(raw, "casZverejneni", "zverejneno")),
        "value": bez or (vat / 1.21 if vat else None),
        "parties": others,
        "url": f"https://www.hlidacstatu.cz/Detail/{sid}" if sid else "",
    }


# ---------------------------------------------------------------- kontroly
def party_names(c):
    return ", ".join(p["name"] or p["ico"] for p in c["parties"])


def check_late(cs):
    rows = []
    for c in cs:
        if c["signed"] and c["published"]:
            delay = (c["published"] - c["signed"]).days
            if delay > LATE_PUBLISH_DAYS:
                rows.append((delay, c))
    rows.sort(key=lambda r: -r[0])
    return rows


def check_near_limit(cs):
    rows = []
    for c in cs:
        v = c["value"]
        if not v:
            continue
        for label, lim in (("dodávky/služby", LIMIT_SERVICES), ("stavební práce", LIMIT_WORKS)):
            if lim * NEAR_LIMIT_RATIO <= v < lim:
                rows.append((label, lim, c))
    rows.sort(key=lambda r: -(r[2]["value"] or 0))
    return rows


def check_splitting(cs):
    by = defaultdict(list)
    for c in cs:
        if c["value"] and c["value"] < LIMIT_SERVICES and c["signed"]:
            for p in c["parties"]:
                by[p["key"]].append((p, c))
    res = []
    for key, lst in by.items():
        lst.sort(key=lambda t: t[1]["signed"])
        best = None
        for i in range(len(lst)):
            start = lst[i][1]["signed"]
            win = [c for _, c in lst[i:] if (c["signed"] - start).days <= SPLIT_WINDOW_DAYS]
            total = sum(c["value"] for c in win)
            if len(win) >= 2 and total >= LIMIT_SERVICES and (best is None or total > best[0]):
                best = (total, win)
        if best:
            res.append((lst[0][0]["name"] or key, best[0], best[1]))
    res.sort(key=lambda r: -r[1])
    return res


def check_concentration(cs):
    tot = sum(c["value"] for c in cs if c["value"])
    by = defaultdict(lambda: {"sum": 0.0, "n": 0, "name": "", "ico": ""})
    for c in cs:
        if not c["value"]:
            continue
        for p in c["parties"]:
            d = by[p["key"]]
            d["sum"] += c["value"]
            d["n"] += 1
            d["name"], d["ico"] = p["name"], p["ico"]
    rows = [(d, d["sum"] / tot) for d in by.values()
            if tot and d["sum"] / tot >= CONCENTRATION_SHARE and d["n"] >= CONCENTRATION_MIN_N]
    rows.sort(key=lambda r: -r[1])
    return rows, tot


def check_amendments(cs):
    rx = re.compile(r"\bdodat(ek|ky|ku|ků)\b", re.I)
    return [c for c in cs if rx.search(str(c["subject"]))]


def check_new_companies(cs, founded_lookup):
    by = defaultdict(lambda: {"sum": 0.0, "first": None, "name": "", "ico": ""})
    for c in cs:
        for p in c["parties"]:
            if p["ico"]:
                d = by[p["ico"]]
                d["sum"] += c["value"] or 0
                d["name"], d["ico"] = p["name"], p["ico"]
                if c["signed"] and (d["first"] is None or c["signed"] < d["first"][0]):
                    d["first"] = (c["signed"], c)
    rows = []
    for d in sorted(by.values(), key=lambda d: -d["sum"])[:ARES_TOP_SUPPLIERS]:
        founded = founded_lookup(d["ico"])
        if founded and d["first"] and (d["first"][0] - founded).days < NEW_COMPANY_DAYS:
            rows.append((d, founded, (d["first"][0] - founded).days))
    return rows


# ---------------------------------------------------------------- karty
def _link(c, n=110):
    t = str(c["subject"])[:n]
    return cell_link(t, c["url"]) if c["url"] else t


def _signal_cards(cs):
    """Vrací seznam (karta) signálů v pořadí zobrazení."""
    late, near, split = check_late(cs), check_near_limit(cs), check_splitting(cs)
    (conc, total), amend = check_concentration(cs), check_amendments(cs)
    newco = check_new_companies(cs, ares.founded)
    asof = today_str()

    def mk(title, intro, headers, rows, empty="Nic nenalezeno."):
        return card(title, SRC, "warn" if rows else "ok", asof, intro, [table(headers, rows, empty)])

    return [
        mk("Pozdní zveřejnění smluv",
           f"Smlouva zveřejněná více než {LATE_PUBLISH_DAYS} dní po uzavření. Zákon o registru smluv stanoví nejzazší lhůtu 3 měsíců.",
           ["Prodleva", "Podepsáno", "Zveřejněno", "Předmět", "Protistrana", "Hodnota"],
           [[cell_right(f"{d} dní"), cz_date(c["signed"]), cz_date(c["published"]), _link(c), party_names(c), cell_right(czk(c["value"]))] for d, c in late]),
        mk("Hodnota těsně pod limitem zakázky malého rozsahu",
           f"Hodnota {int(NEAR_LIMIT_RATIO * 100)}–100 % limitu ({czk(LIMIT_SERVICES)} pro dodávky a služby, {czk(LIMIT_WORKS)} pro stavební práce, bez DPH). Jednotlivě to nemusí nic znamenat, podezřelá je opakovanost.",
           ["Limit", "Podepsáno", "Předmět", "Protistrana", "Hodnota bez DPH"],
           [[f"{lbl} ({czk(lim)})", cz_date(c["signed"]), _link(c), party_names(c), cell_right(czk(c["value"]))] for lbl, lim, c in near]),
        mk("Možné dělení zakázek",
           f"Stejný dodavatel, více smluv pod {czk(LIMIT_SERVICES)}, které dohromady v okně {SPLIT_WINDOW_DAYS} dní limit překračují. Může jít o legitimní opakované objednávky, ale stojí za prověření.",
           ["Dodavatel", "Podepsáno", "Předmět", "Hodnota bez DPH", "Součet"],
           [[n if i == 0 else "", cz_date(c["signed"]), _link(c, 70), cell_right(czk(c["value"])), cell_right(czk(t)) if i == 0 else ""]
            for n, t, w in split for i, c in enumerate(w)]),
        mk("Koncentrace u jednoho dodavatele",
           f"Dodavatel s podílem ≥ {int(CONCENTRATION_SHARE * 100)} % hodnoty všech smluv (alespoň {CONCENTRATION_MIN_N} smlouvy). Celková hodnota smluv: {czk(total)}.",
           ["Dodavatel", "IČO", "Smluv", "Hodnota", "Podíl"],
           [[d["name"], d["ico"], cell_right(str(d["n"])), cell_right(czk(d["sum"])), cell_right(f"{s * 100:.0f} %")] for d, s in conc]),
        mk("Dodavatelé vzniklí krátce před smlouvou",
           f"Z {ARES_TOP_SUPPLIERS} největších dodavatelů ti, kteří vznikli méně než {NEW_COMPANY_DAYS} dní před první smlouvou (datum vzniku z ARES).",
           ["Dodavatel", "IČO", "Vznik firmy", "První smlouva", "Stáří při smlouvě", "Hodnota celkem"],
           [[d["name"], d["ico"], cz_date(f), cz_date(d["first"][0]), cell_right(f"{days} dní"), cell_right(czk(d["sum"]))] for d, f, days in newco]),
        mk("Dodatky ke smlouvám",
           "Smlouvy s „dodatek“ v předmětu. Opakované dodatky bývají cestou ke zvýšení ceny bez nového výběru; porovnejte hodnotu s původní smlouvou.",
           ["Podepsáno", "Předmět", "Protistrana", "Hodnota bez DPH"],
           [[cz_date(c["signed"]), _link(c), party_names(c), cell_right(czk(c["value"]))] for c in amend], "Žádné dodatky."),
    ]


def _overview(ico, cs, since, note):
    total = sum(c["value"] for c in cs if c["value"])
    with_val = sorted([c for c in cs if c["value"]], key=lambda c: -c["value"])[:10]
    rest = sorted([c for c in cs if not c["value"]], key=lambda c: c["signed"] or date.min, reverse=True)
    top = with_val + rest[:10 - len(with_val)]
    n_val = sum(1 for c in cs if c["value"])
    head = "10 největších smluv" if len(with_val) >= 10 or not rest else \
        f"Největší smlouvy ({len(with_val)} s uvedenou hodnotou, doplněno nejnovějšími bez hodnoty)"
    return card("Registr smluv – přehled", SRC, "info" if cs else "warn", today_str(),
                f"Smlouvy podepsané od {cz_date(since)}.",
                [kv([("Počet smluv", len(cs)), ("z toho s uvedenou hodnotou", n_val),
                     ("Celková hodnota bez DPH", czk(total))]),
                 heading(head),
                 table(["Podepsáno", "Předmět", "Protistrana", "Hodnota bez DPH"],
                       [[cz_date(c["signed"]), _link(c), party_names(c), cell_right(czk(c["value"]))] for c in top],
                       "V období nejsou v registru žádné smlouvy.")],
                [("Profil na Hlídači státu", f"https://www.hlidacstatu.cz/subjekt/{ico}")],
                [note] + ([f"Hodnotu nemá {len(cs) - n_val} smluv (v registru není uvedena nebo se ji nepodařilo přečíst z odpovědi API)."]
                          if n_val < len(cs) else []))


def _merge(cards_, title):
    blocks, hits = [], 0
    for c in cards_:
        rows = c["blocks"][0]["rows"]
        hits += 1 if rows else 0
        blocks += [heading(f"{c['title']} ({len(rows)})"), text(c["intro"]), c["blocks"][0]]
    return card(title, SRC, "warn" if hits else "ok", today_str(),
                f"Signály s nálezem: {hits} z {len(cards_)}. Nejsou důkazem pochybení, jen důvodem podívat se blíž.", blocks)


def contract_cards(ico, months=12, compact=False, note=OBEC_NOTE):
    tok = token()
    if not tok:
        return [card("Registr smluv (Hlídač státu)", SRC, "error", None,
                     "Chybí API token. Získejte ho po registraci na https://www.hlidacstatu.cz/api, nastavte proměnnou prostředí "
                     "HLIDAC_TOKEN a aplikaci spusťte znovu.", links=[("Získat token", "https://www.hlidacstatu.cz/api")])]
    since = date.today() - timedelta(days=round(months * 30.44))
    try:
        raw = fetch_contracts(ico, since, tok)
    except net.ApiError as ex:
        return [card("Registr smluv (Hlídač státu)", SRC, "error", None, str(ex))]
    cs = [normalize(r, ico) for r in raw]
    cs = [c for c in cs if not c["signed"] or c["signed"] >= since]
    cards_ = [_overview(ico, cs, since, note)]
    if not cs:
        return cards_
    sig = _signal_cards(cs)
    cards_ += [_merge(sig, "Signály ke kontrole")] if compact else sig
    return cards_
