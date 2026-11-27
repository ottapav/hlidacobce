"""Sestavení karet pro jednotlivé záložky. Každá záložka se načítá až na vyžádání (jednorázově)."""
from . import ares, contracts, csu, elections, funding, net, schools, sources, webcheck
from .cards import card, kv, today_str
from .util import cz_date, norm_ico

KIND_LABEL = {"zs": "Základní škola", "ms": "Mateřská škola"}


def _err(title, source, ex):
    return card(title, source, "error", None, str(ex))


def identity_card(b, title="Základní údaje (ARES)"):
    return card(title, "ARES – Ministerstvo financí", "info", today_str(), None,
                [kv([("Název", b["name"]), ("IČO", b["ico"]), ("Sídlo", b["address"]),
                     ("Právní forma (kód)", f"{b['legal_form']} ({ares.LEGAL_FORMS.get(b['legal_form'], 'jiná')})"),
                     ("Datum vzniku", cz_date(b["founded"])), ("Kód obce (ČSÚ)", b["kod_obce"])])],
                [("Záznam v ARES", f"{ares.ARES}/{b['ico']}")])


def search_obce(q):
    try:
        return {"obce": [{k: v for k, v in o.items() if k != "founded"} for o in ares.search_obce(q)], "error": None}
    except (net.ApiError, ValueError) as ex:
        return {"obce": [], "error": str(ex)}


def tab_obec(ico):
    ico = norm_ico(ico)
    out, name = [], ""
    try:
        b = ares.basic(ico)
        name = b["name"]
        out.append(identity_card(b))
    except net.ApiError as ex:
        out.append(_err("Základní údaje (ARES)", "ARES", ex))
    out += contracts.contract_cards(ico, months=12, note=contracts.OBEC_NOTE)
    out += [funding.subsidy_card(ico), funding.tender_card(ico)]
    out += webcheck.web_cards_for_ico(ico, "obec", name)
    out += sources.obec_link_cards(ico)
    return {"cards": out}


def tab_csu(ico):
    ico = norm_ico(ico)
    try:
        b = ares.basic(ico)
    except net.ApiError as ex:
        return {"cards": [_err("Základní údaje (ARES)", "ARES", ex)]}
    cards_ = [elections.election_card(b["kod_obce"]), csu.population_card(b["kod_obce"])] + sources.csu_link_cards()
    return {"cards": cards_}


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
    out, name = [], ""
    try:
        b = ares.basic(ico)
        name = b["name"]
        out.append(identity_card(b, f"{KIND_LABEL[kind]} – základní údaje (ARES)"))
    except net.ApiError as ex:
        out.append(_err("Základní údaje (ARES)", "ARES", ex))
    out += webcheck.web_cards_for_ico(ico, kind, name)
    out += contracts.contract_cards(ico, months=12, compact=True, note=contracts.SCHOOL_NOTE)
    out += [funding.subsidy_card(ico), funding.tender_card(ico)]
    out += sources.school_link_cards(kind)
    return {"cards": out}
