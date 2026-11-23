"""Jednorázová kontrola webu: dostupnost a hledání povinně zveřejňovaných informací.

Je to heuristika: hledá klíčová slova v textu stránek a odkazů. "Nenalezeno" neznamená "nezveřejněno"
(web může být tvořený JavaScriptem, dokumenty mohou ležet jinde). Citace zákonů jsou orientační.
"""
import re
import time
import urllib.parse
from html.parser import HTMLParser

from . import net
from .cards import card, cell_link, table, text, today_str
from .util import fold

MAX_PAGES = 18
SRC = "Web organizace (jednorázová kontrola)"
SLOW_MS = 3000
HLIDAC_SUBJEKT = "https://www.hlidacstatu.cz/subjekt/{ico}"
# odkazy, které nejsou web samotného subjektu (sociální sítě, mapy, rejstříky…)
NOT_SITE = re.compile(r"(^|\.)(hlidacstatu\.cz|youtube\.com|youtu\.be|facebook\.com|twitter\.com|x\.com|instagram\.com|linkedin\.com|"
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


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.title, self._skip, self._in_title, self._href, self._atxt = [], [], "", 0, False, None, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            self._href, self._atxt = dict(attrs).get("href"), []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._atxt).strip()))
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        s = data.strip()
        if s:
            self.parts.append(s)
            if self._href is not None:
                self._atxt.append(s)


def parse_html(html):
    p = _Page()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - rozbité HTML nesmí shodit kontrolu
        pass
    return p


def find_site(ico):
    """Adresa webu subjektu ze stránky subjektu na Hlídači státu (sekce Odkazy, „Webová stránka“). Vrací URL nebo None.
    Struktura stránky byla ověřena jen na jednom subjektu; proto se zkouší popisek odkazu, pak odkaz podobný adrese, pak první vhodný."""
    _, html = net.fetch_page(HLIDAC_SUBJEKT.format(ico=ico))
    cands = []
    for href, label in parse_html(html).links:
        if not re.match(r"^https?://", href or "", re.I):
            continue
        host = (urllib.parse.urlparse(href).hostname or "").lower()
        if host and not NOT_SITE.search(host):
            cands.append((href, fold(label)))
    for pred in (lambda l: "webova stranka" in l or l in ("web", "www"),
                 lambda l: l.startswith(("http", "www.")) or "." in l.replace(" ", "")[:60] and " " not in l.strip(),
                 lambda l: True):
        for href, label in cands:
            if pred(label):
                return href
    return None


def web_cards_for_ico(ico, kind):
    """Karty kontroly webu; adresu webu najde sama podle IČO."""
    try:
        url = find_site(ico)
    except (net.ApiError, ValueError) as ex:
        return [card("Web a povinně zveřejňované informace", SRC, "error", today_str(),
                     f"Adresu webu se nepodařilo zjistit (Hlídač státu: {ex}).")]
    return web_cards(url, kind)


def normalize_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", u, re.I):
        u = "https://" + u
    return u


def _same_site(a, b):
    ha, hb = urllib.parse.urlparse(a).hostname or "", urllib.parse.urlparse(b).hostname or ""
    strip = lambda h: h[4:] if h.startswith("www.") else h  # noqa: E731
    return strip(ha) == strip(hb)


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
        if _same_site(final, u) and u not in seen and FOLLOW.search(fold(f"{u} {t}")) \
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


def web_cards(url, kind, name=""):
    """Karty: dostupnost + checklist. Pokud URL chybí, vrací kartu s výzvou."""
    if not normalize_url(url):
        return [card("Web a povinně zveřejňované informace", SRC, "warn", None,
                     "Adresu webu se nepodařilo zjistit: Hlídač státu ji u tohoto subjektu neuvádí, kontrola webu proto neproběhla.")]
    res = crawl(url, MAX_PAGES)
    if not res["ok"]:
        return [card("Dostupnost webu", SRC, "error", today_str(), f"{res['url']} – {res['error']}")]
    total_text = sum(len(p["text"]) for p in res["pages"])
    status = "warn" if res["ms"] > SLOW_MS else "ok"
    notes = [f"Prověřeno {len(res['pages'])} stránek ze stejné domény."]
    if total_text < 400:
        notes.append("Na stránkách je velmi málo textu – web může být generovaný JavaScriptem a výsledek kontroly je pak nespolehlivý.")
    avail = card("Dostupnost webu (jednorázové měření)", SRC, status, today_str(),
                 f"Web {res['url']} (adresa z Hlídače státu). Úvodní stránka odpověděla za {res['ms']} ms (limit pro označení za pomalou: {SLOW_MS} ms).",
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
