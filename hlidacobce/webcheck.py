"""Jednorázová kontrola webu: dostupnost a hledání povinně zveřejňovaných informací.

Je to heuristika: hledá klíčová slova v textu stránek a odkazů. "Nenalezeno" neznamená "nezveřejněno"
(web může být tvořený JavaScriptem, dokumenty mohou ležet jinde). Citace zákonů jsou orientační.
"""
import re
import time
import urllib.parse
from . import net, wikidata
from .cards import card, cell_link, table, today_str
from .htmlutil import parse_html
from .util import fold

MAX_PAGES = 18
SRC = "Web organizace (jednorázová kontrola)"
SLOW_MS = 3000
HLIDAC_SUBJEKT = "https://www.hlidacstatu.cz/subjekt/{ico}"
# odkazy, které nejsou web samotného subjektu (sociální sítě, mapy, rejstříky…)
NOT_SITE = re.compile(r"(^|\.)(hlidacstatu\.cz|saleskit\.com|ipinfo\.io|wikidata\.org|youtube\.com|youtu\.be|facebook\.com|twitter\.com|x\.com|instagram\.com|linkedin\.com|"
                      r"google\.[a-z.]+|mapy\.cz|github\.com|justice\.cz|ares\.gov\.cz|wikipedia\.org|czso\.cz|csu\.gov\.cz)$", re.I)

# (id, název, regulární výraz nad textem bez diakritiky, právní opora)
CHECKS = {
    "ms": [
        ("rad", "Školní řád / vnitřní řád", r"skolni rad|vnitrni rad|rad skoly", "zák. 561/2004 Sb., § 30 odst. 1 a 4 (na přístupném místě ve škole + dálkový přístup, § 5 odst. 3)"),
        ("svp", "Školní vzdělávací program", r"skolni vzdelavaci program|\bsvp\b|\bsvp pv\b|\brvp\b", "zák. 561/2004 Sb., § 5 odst. 3 (dálkový přístup)"),
        ("uplata", "Výše úplaty za předškolní vzdělávání", r"uplat|poplatek za predskolni|stravne", "zák. 561/2004 Sb., § 123; vyhl. 14/2005 Sb., § 6 (zveřejnit do 30. 6.)"),
        ("kriteria", "Kritéria přijímání / zápis do MŠ", r"kriteri|zapis do|prijimani|prijeti do", "zák. 561/2004 Sb., § 34 odst. 2"),
        ("vz", "Výroční zpráva o činnosti školy", r"vyrocni zprava", "zák. 561/2004 Sb., § 10 odst. 3; vyhl. 15/2005 Sb., § 7"),
        ("poradenstvi", "Informace o poradenských službách", r"poradensk|specialni pedagog|logoped", "vyhl. 72/2005 Sb., § 2a"),
        ("rozpocet", "Rozpočet a střednědobý výhled (příspěvková organizace)", r"rozpocet|stredn[eě]dob", "zák. 250/2000 Sb., § 28, § 28a"),
        ("info", "Informace podle zákona o svobodném přístupu k informacím", r"106/1999|svobodn\w* pristup|poskytovani informaci|zadost o informac", "zák. 106/1999 Sb., § 5 odst. 1"),
        ("gdpr", "Kontakt na pověřence pro ochranu osobních údajů", r"poverenec|gdpr|ochrana osobnich udaju|ochrane osobnich udaju", "nařízení (EU) 2016/679, čl. 37 odst. 7"),
        ("pristupnost", "Prohlášení o přístupnosti webu", r"prohlaseni o pristupnosti|pristupnost webu|pristupnost internetovych", "zák. 99/2019 Sb."),
    ],
    "zs": [
        ("rad", "Školní řád (a vnitřní řád družiny/jídelny)", r"skolni rad|vnitrni rad|rad skoly|rad druziny|rad skolni", "zák. 561/2004 Sb., § 30 odst. 1, 2 a 4"),
        ("svp", "Školní vzdělávací program", r"skolni vzdelavaci program|\bsvp\b|\brvp\b", "zák. 561/2004 Sb., § 5 odst. 3 (dálkový přístup)"),
        ("kriteria", "Zápis do 1. třídy / kritéria přijímání", r"zapis do|zapis k povinn|kriteri|prijimani", "zák. 561/2004 Sb., § 36, § 46"),
        ("vz", "Výroční zpráva o činnosti školy", r"vyrocni zprava", "zák. 561/2004 Sb., § 10 odst. 3; vyhl. 15/2005 Sb., § 7"),
        ("poradenstvi", "Informace o poradenských službách", r"poradensk|vychovn\w* poradce|specialni pedagog|skolni psycholog", "vyhl. 72/2005 Sb., § 2a"),
        ("rozpocet", "Rozpočet a střednědobý výhled (příspěvková organizace)", r"rozpocet|stredn[eě]dob", "zák. 250/2000 Sb., § 28, § 28a"),
        ("info", "Informace podle zákona o svobodném přístupu k informacím", r"106/1999|svobodn\w* pristup|poskytovani informaci|zadost o informac", "zák. 106/1999 Sb., § 5 odst. 1"),
        ("gdpr", "Kontakt na pověřence pro ochranu osobních údajů", r"poverenec|gdpr|ochrana osobnich udaju|ochrane osobnich udaju", "nařízení (EU) 2016/679, čl. 37 odst. 7"),
        ("pristupnost", "Prohlášení o přístupnosti webu", r"prohlaseni o pristupnosti|pristupnost webu|pristupnost internetovych", "zák. 99/2019 Sb."),
    ],
    "obec": [
        ("deska", "Úřední deska", r"uredni deska|uredni desk", "zák. 128/2000 Sb., § 26 (včetně elektronické úřední desky)"),
        ("rozpocet", "Rozpočet obce", r"rozpocet", "zák. 250/2000 Sb., § 11 (návrh zveřejnit alespoň 15 dnů před projednáním)"),
        ("vyhled", "Střednědobý výhled rozpočtu", r"stredn[eě]dob\w* vyhled|rozpoctov\w* vyhled", "zák. 250/2000 Sb., § 3"),
        ("zaverecny", "Závěrečný účet", r"zaverecn\w* ucet", "zák. 250/2000 Sb., § 17 odst. 6"),
        ("zapisy", "Zápisy / usnesení zastupitelstva", r"zapis\w* z|usneseni|zastupitelstv", "zák. 128/2000 Sb., § 95"),
        ("vyhlasky", "Obecně závazné vyhlášky", r"obecne zavazn|vyhlask", "zák. 128/2000 Sb., § 12; sbírka právních předpisů ÚSC (zák. 35/2021 Sb.)"),
        ("info", "Povinně zveřejňované informace", r"povinne zverejn|106/1999|svobodn\w* pristup|poskytovani informaci", "zák. 106/1999 Sb., § 5 odst. 1"),
        ("gdpr", "Kontakt na pověřence pro ochranu osobních údajů", r"poverenec|gdpr|ochrana osobnich udaju|ochrane osobnich udaju", "nařízení (EU) 2016/679, čl. 37 odst. 7"),
        ("pristupnost", "Prohlášení o přístupnosti webu", r"prohlaseni o pristupnosti|pristupnost webu|pristupnost internetovych", "zák. 99/2019 Sb."),
    ],
}

FOLLOW = re.compile(r"rad|program|uplat|zapis|kriter|zprava|dokument|informac|gdpr|poverenec|pristupnost|deska|rozpocet|"
                    r"kontakt|povinn|vyhled|ucet|vyhlask|usneseni|poradens|ke-stazeni|download|o-skole|o-obci", re.I)


GENERIC = {"obec", "mesto", "mestys", "statutarni", "zakladni", "skola", "materska", "prispevkova", "organizace", "okres", "a", "s", "r", "o", "p",
           "ms", "zs", "skolka", "ceska", "republika", "praha"}
MAX_CANDIDATES = 3


def name_tokens(name):
    """Rozlišující slova z názvu subjektu (bez obecných slov a bez okresu): podle nich se ověřuje, že web patří subjektu."""
    words = re.findall(r"[a-z0-9]+", fold(re.split(r",?\s*okres\b", str(name or ""), flags=re.I)[0]))
    return [w for w in words if w not in GENERIC and len(w) >= 4]


def ico_in_text(hay, ico):
    return bool(re.search(r"(?<!\d)" + re.escape(str(ico).lstrip("0")) + r"(?!\d)", hay))


def _bare_host(url):
    return (urllib.parse.urlparse(url).hostname or "").lower().removeprefix("www.")


def _candidates(ico):
    """Kandidáti na web: {holý host: (url, důvěryhodný)}. Zdroje: Wikidata podle IČO (důvěryhodné, shoda podle identifikátoru) a odkazy
    na stránce subjektu na Hlídači státu (bez popisků; mimo sociální sítě, reklamy a poskytovatele dat). Vrací (kandidáti, chyby zdrojů)."""
    cands, errors = {}, []
    try:
        for url in wikidata.websites_by_ico(ico):
            if re.match(r"^https?://", url, re.I) and not NOT_SITE.search(_bare_host(url)):
                cands.setdefault(_bare_host(url), (url, True))
    except (net.ApiError, KeyError, TypeError, ValueError) as ex:
        errors.append(f"Wikidata: {ex}")
    try:
        _, html = net.fetch_page(HLIDAC_SUBJEKT.format(ico=ico))
        for href, _label in parse_html(html).links:
            host = _bare_host(href) if re.match(r"^https?://", href or "", re.I) else ""
            if host and not NOT_SITE.search(host):
                old = cands.get(host)
                if not old:
                    cands[host] = (href, False)
                elif old[0].lower().startswith("http://") and href.lower().startswith("https://"):
                    cands[host] = (href, old[1])  # stejný web, preferujeme https
    except (net.ApiError, ValueError) as ex:
        errors.append(f"Hlídač státu: {ex}")
    return cands, errors


def find_site(ico, name):
    """Spolehlivě zjistí web subjektu, nebo řekne, proč ne. Vrací dict {status, url, candidate, reason}.

    Kandidáty viz `_candidates`. Přijme se jen web, na jehož úvodní stránce je rozlišující slovo z názvu subjektu nebo jeho IČO,
    a to právě jeden. Víc potvrzených různých webů = nejednoznačné, žádný potvrzený = nepřiřadí se. Nedostupný web se hlásí jako chyba
    jen tehdy, když pochází z důvěryhodného zdroje (Wikidata podle IČO)."""
    cands, errors = _candidates(ico)
    if not cands:
        if errors:
            raise net.ApiError("; ".join(errors))
        return {"status": "none", "url": None, "candidate": None, "reason": "Žádný zdroj (Wikidata, Hlídač státu) u subjektu neuvádí webovou stránku."}
    tokens = name_tokens(name)
    ok, problems, trusted_down = [], [], None
    for host, (cand, trusted) in list(cands.items())[:MAX_CANDIDATES]:
        try:
            final, home = net.fetch_page(cand)
        except (net.ApiError, ValueError) as ex:
            problems.append(f"{cand} se nepodařilo otevřít ({ex})")
            trusted_down = trusted_down or ((cand, ex) if trusted else None)
            continue
        p = parse_html(home)
        hay = fold(f"{final} {p.title} {' '.join(p.parts)}")
        if any(t in hay for t in tokens) or ico_in_text(hay, ico):
            ok.append((host, final))
        else:
            problems.append(f"obsah úvodní stránky {cand} neodpovídá názvu „{name}“" if tokens else
                            f"z názvu nelze odvodit rozlišující slovo a IČO na stránce {cand} není")
    first = next(iter(cands.values()))[0]
    if len(ok) == 1:
        return {"status": "ok", "url": ok[0][1], "candidate": first, "reason": ""}
    if len(ok) > 1:
        return {"status": "ambiguous", "url": None, "candidate": None, "reason": "Vhodných webových stránek je víc: " + ", ".join(h for h, _ in ok) + "."}
    if trusted_down:
        return {"status": "unreachable", "url": trusted_down[0], "candidate": trusted_down[0],
                "reason": f"Web {trusted_down[0]} (z Wikidat podle IČO) se nepodařilo otevřít ({trusted_down[1]})."}
    return {"status": "unverified", "url": None, "candidate": first, "reason": "Nalezené odkazy se nepodařilo potvrdit: " + "; ".join(problems) + "."}


def web_cards_for_ico(ico, kind, name=""):
    """Karty kontroly webu. Adresu webu najde sama; když si není jistá, napíše to a web nekontroluje."""
    title = "Web a povinně zveřejňované informace"
    try:
        r = find_site(ico, name)
    except (net.ApiError, ValueError) as ex:
        return [card(title, SRC, "error", today_str(), f"Web se nepodařilo dohledat (Hlídač státu: {ex}).")]
    if r["status"] == "unreachable":
        return [card("Dostupnost webu (jednorázové měření)", SRC, "error", today_str(), r["reason"], [], [("Adresa webu", r["url"])])]
    if r["status"] != "ok":
        links = [("Nalezená adresa (neověřená)", r["candidate"])] if r["candidate"] else []
        return [card(title, SRC, "warn", today_str(), "Web se nepodařilo spolehlivě dohledat, proto ho nekontroluji. " + r["reason"], [], links,
                     ["Raději nic než špatný web: kontrola se spustí, jen když obsah úvodní stránky odpovídá názvu subjektu nebo jeho IČO."])]
    return web_cards(r["url"], kind)


def normalize_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", u, re.I):
        u = "https://" + u
    return u


def crawl(url, max_pages=MAX_PAGES):
    """Stáhne úvodní stránku a až max_pages relevantních stránek ze stejné domény. Vrací dict s výsledkem."""
    url = normalize_url(url)
    t0 = time.monotonic()
    try:
        final, html = net.fetch_page(url)
    except (net.ApiError, ValueError) as ex:
        return {"ok": False, "error": str(ex), "url": url, "pages": [], "ms": None}
    ms = round((time.monotonic() - t0) * 1000)
    pages = []

    def add(u, h):
        p = parse_html(h)
        pages.append({"url": u, "title": " ".join(p.title.split()), "text": fold(" ".join(p.parts)),
                      "links": [(urllib.parse.urljoin(u, href), t) for href, t in p.links
                                if href and not href.startswith(("#", "mailto:", "tel:", "javascript:"))]})
    add(final, html)
    seen, queue = {final.split("#")[0]}, []
    for u, t in pages[0]["links"]:
        u = u.split("#")[0]
        if _bare_host(final) == _bare_host(u) and u not in seen and FOLLOW.search(fold(f"{u} {t}")) \
                and not re.search(r"\.(pdf|docx?|xlsx?|zip|jpe?g|png)$", u, re.I):
            seen.add(u)
            queue.append(u)
    for u in queue[: max_pages - 1]:
        try:
            f2, h2 = net.fetch_page(u)
            add(f2, h2)
        except (net.ApiError, ValueError):
            continue
    return {"ok": True, "url": final, "pages": pages, "ms": ms}


def evaluate(res, kind):
    """Pro každou položku checklistu najde důkaz (stránku nebo odkaz). Vrací seznam dict."""
    out = []
    for cid, label, rx, basis in CHECKS[kind]:
        pat = re.compile(rx)
        hit = None
        for pg in res["pages"]:
            for href, t in pg["links"]:
                if pat.search(fold(f"{t} {href}")):
                    hit = (t or href, href)
                    break
            if hit:
                break
            if pat.search(pg["text"]):
                hit = (pg["title"] or pg["url"], pg["url"])
                break
        out.append({"id": cid, "label": label, "basis": basis, "found": bool(hit), "evidence": hit})
    return out


def web_cards(url, kind):
    """Karty: dostupnost + checklist. Pokud URL chybí, vrací kartu s výzvou."""
    if not normalize_url(url):
        return [card("Web a povinně zveřejňované informace", SRC, "warn", None,
                     "Adresu webu se nepodařilo zjistit, kontrola webu proto neproběhla.")]
    res = crawl(url, MAX_PAGES)
    if not res["ok"]:
        return [card("Dostupnost webu", SRC, "error", today_str(), f"{res['url']} – {res['error']}")]
    total_text = sum(len(p["text"]) for p in res["pages"])
    status = "warn" if res["ms"] > SLOW_MS else "ok"
    notes = [f"Prověřeno {len(res['pages'])} stránek ze stejné domény."]
    if total_text < 400:
        notes.append("Na stránkách je velmi málo textu – web může být generovaný JavaScriptem a výsledek kontroly je pak nespolehlivý.")
    avail = card("Dostupnost webu (jednorázové měření)", SRC, status, today_str(),
                 f"Web {res['url']} (adresa z Wikidat nebo Hlídače státu, potvrzená obsahem stránky). Úvodní stránka odpověděla za {res['ms']} ms (limit pro označení za pomalou: {SLOW_MS} ms).",
                 [], [("Otevřít web", res["url"])], notes + ["Souvislá historie dostupnosti vyžaduje opakované měření, to aplikace nedělá."])
    items = evaluate(res, kind)
    miss = [i for i in items if not i["found"]]
    rows = [[i["label"], "nalezeno" if i["found"] else "nenalezeno",
             cell_link(str(i["evidence"][0])[:70], i["evidence"][1]) if i["found"] else "", i["basis"]] for i in items]
    check = card("Povinně zveřejňované informace – kontrola webu", SRC, "ok" if not miss else "warn", today_str(),
                 f"Nalezeno {len(items) - len(miss)} z {len(items)} položek. „Nenalezeno“ znamená jen, že to kontrola nenašla, ne že to není zveřejněno.",
                 [table(["Položka", "Výsledek", "Kde", "Právní opora (orientační)"], rows)], [],
                 ["Právní opory jsou orientační, nejsem právník. Před jakýmkoli závěrem ověřte znění předpisů a web projděte ručně."])
    return [avail, check]
