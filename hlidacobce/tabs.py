"""Sestavení karet pro jednotlivé záložky. Každá záložka se načítá až na vyžádání (jednorázově).

Zásady: (1) selhání jedné karty (i neočekávaná chyba v kódu) nesmí zničit celou záložku, proto je každý zdroj obalený v `_guard`;
(2) nezávislé zdroje se načítají souběžně ve dvou "drahách" – Hlídač státu (jeden token, proto za sebou) a kontrola webu;
(3) nový zdroj se přidá jednou funkcí vracející seznam karet do seznamu v příslušné `tab_*`."""
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import ares, contracts, csu, elections, funding, net, schools, sources, webcheck
from .cards import card, kv, today_str
from .util import cz_date, norm_ico

KIND_LABEL = {"zs": "Základní škola", "ms": "Mateřská škola"}


def _guard(title, source, fn, *args, **kw):
    """Zavolá `fn` a vždy vrátí seznam karet; neočekávaná výjimka se zaloguje a změní se v chybovou kartu."""
    try:
        res = fn(*args, **kw)
    except Exception:  # noqa: BLE001 - chyba jednoho zdroje nesmí shodit záložku
        traceback.print_exc(file=sys.stderr)
        return [card(title, source, "error", None, "Při zpracování tohoto zdroje došlo k neočekávané chybě (podrobnosti jsou v logu serveru).")]
    return res if isinstance(res, list) else [res]


def _lane(*steps):
    """Posloupnost kroků (title, source, fn, *args) spuštěných za sebou; vrací jejich karty."""
    return [c for title, source, fn, *args in steps for c in _guard(title, source, fn, *args)]


def _parallel(*lanes):
    """Spustí dráhy souběžně a spojí jejich karty v zadaném pořadí."""
    with ThreadPoolExecutor(max_workers=len(lanes)) as pool:
        futures = [pool.submit(lane) for lane in lanes]
        return [c for f in futures for c in f.result()]


def identity_card(b, title="Základní údaje (ARES)"):
    return card(title, "ARES – Ministerstvo financí", "info", today_str(), None,
                [kv([("Název", b["name"]), ("IČO", b["ico"]), ("Sídlo", b["address"]),
                     ("Právní forma (kód)", f"{b['legal_form']} ({ares.LEGAL_FORMS.get(b['legal_form'], 'jiná')})"),
                     ("Datum vzniku", cz_date(b["founded"])), ("Kód obce (ČSÚ)", b["kod_obce"])])],
                [("Záznam v ARES", f"{ares.ARES}/{b['ico']}")])


def _identity(ico, title="Základní údaje (ARES)"):
    """(karta, údaje z ARES nebo None). Při chybě je kartou chybové hlášení."""
    try:
        b = ares.basic(ico)
    except net.ApiError as ex:
        return card(title, "ARES", "error", None, str(ex)), None
    return identity_card(b, title), b


def _hlidac_cards(ico, compact, note):
    return _lane(("Registr smluv (Hlídač státu)", contracts.SRC, contracts.contract_cards, ico, 12, compact, note),
                 ("Dotace (Hlídač státu)", funding.SRC, funding.subsidy_card, ico),
                 ("Veřejné zakázky (Hlídač státu)", funding.SRC_Z, funding.tender_card, ico))


def _web_cards(ico, kind, name):
    return _guard("Web a povinně zveřejňované informace", webcheck.SRC, webcheck.web_cards_for_ico, ico, kind, name)


def search_obce(q):
    try:
        return {"obce": [{k: v for k, v in o.items() if k != "founded"} for o in ares.search_obce(q)], "error": None}
    except (net.ApiError, ValueError) as ex:
        return {"obce": [], "error": str(ex)}


def tab_obec(ico):
    ico = norm_ico(ico)
    ident, b = _identity(ico)
    name = b["name"] if b else ""
    return {"cards": [ident] + _parallel(lambda: _hlidac_cards(ico, False, contracts.OBEC_NOTE), lambda: _web_cards(ico, "obec", name))
            + sources.obec_link_cards(ico)}


def tab_csu(ico):
    ident, b = _identity(norm_ico(ico))
    if not b:
        return {"cards": [ident]}
    kod = b["kod_obce"]
    cards_ = _parallel(lambda: _guard("Komunální volby – účast voličů", elections.SRC, elections.election_card, kod),
                       lambda: _guard("Obyvatelstvo podle pohlaví a věku", csu.SRC, csu.population_card, kod))
    return {"cards": cards_ + sources.csu_link_cards()}


def list_schools(obec_ico, kind):
    if kind not in KIND_LABEL:
        return {"schools": [], "error": "Neznámý druh zařízení."}
    try:
        return {"schools": schools.schools_for_obec(obec_ico, kind), "error": None}
    except net.ApiError as ex:
        return {"schools": [], "error": str(ex)}


def tab_school(kind, ico):
    if kind not in KIND_LABEL:
        return {"cards": [card("Chyba", "aplikace", "error", None, "Neznámý druh zařízení.")]}
    ico = norm_ico(ico)
    ident, b = _identity(ico, f"{KIND_LABEL[kind]} – základní údaje (ARES)")
    name = b["name"] if b else ""
    return {"cards": [ident] + _parallel(lambda: _web_cards(ico, kind, name), lambda: _hlidac_cards(ico, True, contracts.SCHOOL_NOTE))
            + sources.school_link_cards(kind)}
