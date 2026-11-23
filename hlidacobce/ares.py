"""ARES - Administrativní registr ekonomických subjektů (Ministerstvo financí)."""
import re

from . import net
from .util import norm_ico, parse_date, pick

ARES = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty"
LEGAL_FORMS = {"801": "obec", "331": "příspěvková organizace"}


def subject(ico):
    return net.http_json(f"{ARES}/{ico}")


def _brief(d):
    sidlo = pick(d, "sidlo") or {}
    return {
        "ico": norm_ico(pick(d, "ico")),
        "name": pick(d, "obchodniJmeno") or "",
        "address": pick(sidlo, "textovaAdresa") or "",
        "kod_obce": str(pick(sidlo, "kodObce", default="") or ""),
        "founded": parse_date(pick(d, "datumVzniku")),
        "legal_form": str(pick(d, "pravniForma", default="") or ""),
    }


def basic(ico):
    return _brief(subject(ico))


def founded(ico):
    try:
        return basic(ico)["founded"]
    except net.ApiError:
        return None


def search_obce(q):
    """Vyhledá obce podle názvu (nebo IČO). Vrací seznam {ico, name, address, kod_obce}."""
    q = q.strip()
    if not q:
        return []
    if re.fullmatch(r"\d{6,8}", q):
        return [basic(norm_ico(q))]
    data = net.http_json(f"{ARES}/vyhledat", data={"obchodniJmeno": q, "start": 0, "pocet": 100})
    items = [_brief(s) for s in (pick(data, "ekonomickeSubjekty") or [])]
    obce = [b for b in items if b["legal_form"] == "801"] or [b for b in items if q.lower() in b["name"].lower()]
    ql = q.lower()
    exact = {ql, f"obec {ql}", f"město {ql}", f"městys {ql}", f"statutární město {ql}"}
    obce.sort(key=lambda b: (b["name"].lower() not in exact, b["name"]))
    return obce[:15]
