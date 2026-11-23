"""Ukázková (vymyšlená) data pro režim --demo a testy. Nic odtud nepochází z reálných zdrojů."""
import io
import re
import urllib.parse
from datetime import date, timedelta

OBEC_ICO = "00100001"
SKOLA_ICO = "70000001"
KOD_OBCE = "999999"
WEBS = {OBEC_ICO: "https://obec.demo/", SKOLA_ICO: "https://skola.demo"}  # adresy webů, jak je uvádí Hlídač státu


def _d(days):
    return (date.today() - timedelta(days=days)).isoformat()


def _subject(ico, name, legal, founded="1992-01-01", kod="777777"):
    return {"ico": ico, "obchodniJmeno": name, "pravniForma": legal, "datumVzniku": founded,
            "sidlo": {"textovaAdresa": "Ukázková 1, 123 45 Ukázkov", "kodObce": kod}}


def _ares_all():
    return {
        OBEC_ICO: _subject(OBEC_ICO, "Obec Ukázkov", "801", "1990-11-24", KOD_OBCE),
        "00100002": _subject("00100002", "Městys Ukázkov Nový", "801", "1990-11-24", "888888"),
        SKOLA_ICO: _subject(SKOLA_ICO, "Základní škola a mateřská škola Ukázkov, příspěvková organizace", "331", "2003-01-01"),
        "44444444": _subject("44444444", "Světla Rychle s.r.o.", "112", _d(90 + 200)),
    }


def fake_json(url, data):
    path = urllib.parse.urlparse(url)
    if "ares.gov.cz" in path.netloc:
        if path.path.endswith("/vyhledat"):
            seat = ((data or {}).get("sidlo") or {}).get("kodObce")
            if seat is not None:  # hledání příspěvkových organizací podle sídla
                if str(seat) == "888888":
                    return {"ekonomickeSubjekty": [_subject("70000008", "Základní škola Ukázkov Nový, příspěvková organizace", "331", "2001-01-01", "888888"),
                                                   _subject("70000009", "Technické služby Nový, příspěvková organizace", "331", "2001-01-01", "888888")]}
                return {"ekonomickeSubjekty": []}
            q = (data or {}).get("obchodniJmeno", "").lower()
            allv = [v for v in _ares_all().values() if v["pravniForma"] == "801" and q in v["obchodniJmeno"].lower()]
            return {"pocetCelkem": len(allv), "ekonomickeSubjekty": allv}
        ico = path.path.rsplit("/", 1)[-1]
        allv = _ares_all()
        if ico in allv:
            return allv[ico]
        return _subject(ico, f"Firma {ico}", "112", "2005-05-05")
    if "data.csu.gov.cz" in path.netloc:
        if "/katalog/v1/sady/" in path.path:
            return {"kod": "OBY02E", "verze": "4", "ukazatele": [{"kod": "2406P", "nazev": "Population as at 1. 1. (start-period population)"}],
                    "variantyDimenze": [
                        {"kod": "UZ5ALLOKR", "typDimenzeKod": "VUZEMI", "urovneDimenze": [{"kodUrovne": "OBEC", "pocetPolozek": 6271}]},
                        {"kod": "UZ596H", "typDimenzeKod": "VUZEMI", "urovneDimenze": [{"kodUrovne": "OBEC", "pocetPolozek": 1}, {"kodUrovne": "MOMC", "pocetPolozek": 57}]},
                        {"kod": "CasRB", "typDimenzeKod": "REF_CAS"}, {"kod": "POHL2", "typDimenzeKod": "POHLAVI"},
                        {"kod": "VekSkupZakl", "typDimenzeKod": "VEK"}]}
        if path.path.endswith("/vlastni"):
            kod = data["radky"][0]["filtr"][0]["zobrazitPolozky"][0]
            if kod != KOD_OBCE:
                raise_ = __import__("hlidacobce.net", fromlist=["ApiError"]).ApiError("HTTP 404", 404)
                raise raise_
            sexes, ages, years = ["Total", "Male", "Female"], ["Total", "0–14", "15–64", "65+"], [str(y) for y in range(2020, 2025)]
            return {"version": "2.0", "class": "dataset", "id": ["IndicatorType", "POHL2", "VekSkupZakl", "UZ5ALLOKR", "CasRB"],
                    "size": [1, 3, 4, 1, 5], "role": {"time": ["CasRB"]},
                    "dimension": {
                        "IndicatorType": {"category": {"index": ["2406P"], "label": {"2406P": "Population as at 1. 1."}}},
                        "POHL2": {"category": {"index": {"0": 0, "1": 1, "2": 2}, "label": {"0": sexes[0], "1": sexes[1], "2": sexes[2]}}},
                        "VekSkupZakl": {"category": {"index": ["VEKC", "A", "B", "C"], "label": dict(zip(["VEKC", "A", "B", "C"], ages))}},
                        "UZ5ALLOKR": {"category": {"index": [KOD_OBCE], "label": {KOD_OBCE: "Ukázkov"}}},
                        "CasRB": {"category": {"index": years, "label": {y: y for y in years}}}},
                    "value": [1000 + 10 * i + (i % 7) for i in range(60)]}
    if "hlidacstatu.cz" in path.netloc:
        q = urllib.parse.parse_qs(path.query)
        page = int(q.get("strana", ["1"])[0])
        m = re.search(r"ico:(\d+)", q.get("dotaz", [""])[0])
        ico = m.group(1) if m else ""
        items = _obec_contracts() if ico == OBEC_ICO else _school_contracts() if ico == SKOLA_ICO else []
        return {"total": len(items), "results": items if page == 1 else []}
    raise ValueError(f"demo: neznámá adresa {url}")


def _contract(i, days_ago, pub_delay, val, subj, ico, name, payer=OBEC_ICO):
    return {"Id": 9000 + i, "predmet": subj, "datumUzavreni": _d(days_ago), "casZverejneni": _d(days_ago - pub_delay),
            "hodnotaBezDph": val, "platce": {"ico": payer, "nazev": "Zadavatel"},
            "prijemce": [{"ico": ico, "nazev": name}]}


def _obec_contracts():
    c = _contract
    return [
        c(1, 300, 2, 1_950_000, "Oprava místní komunikace Na Návsi", "11111111", "Stavby Novák s.r.o."),
        c(2, 250, 3, 1_890_000, "Rekonstrukce chodníku u školy", "11111111", "Stavby Novák s.r.o."),
        c(3, 200, 120, 5_800_000, "Přístavba hasičské zbrojnice", "22222222", "Nová Stavební a.s."),
        c(4, 180, 1, 650_000, "Právní služby – paušál", "33333333", "Advokátní kancelář X"),
        c(5, 120, 1, 640_000, "Dodatek č. 1 – právní služby", "33333333", "Advokátní kancelář X"),
        c(6, 90, 45, 1_990_000, "Dodávka a montáž veřejného osvětlení", "44444444", "Světla Rychle s.r.o."),
        c(7, 60, 0, 120_000, "Údržba zeleně", "55555555", "Zahradnictví Dvořák"),
        c(8, 40, 1, 310_000, "Poradenství k dotačním titulům", "11111111", "Stavby Novák s.r.o."),
        c(9, 25, 2, 85_000, "Kopírovací služby", "66666666", "Kopírka s.r.o."),
        c(10, 10, 0, 4_300_000, "Zateplení budovy ZŠ", "22222222", "Nová Stavební a.s."),
    ]


def _school_contracts():
    c = _contract
    return [
        c(51, 100, 1, 95_000, "Dodávka interaktivních tabulí", "77777777", "Školní technika s.r.o.", SKOLA_ICO),
        c(52, 40, 50, 240_000, "Pronájem tělocvičny", "88888888", "Sportovní klub Ukázkov", SKOLA_ICO),
    ]


CSV = ("hodnota,pohlavi_txt,vek_txt,rok,uzemi_kod,uzemi_txt\n" +
       "".join(f"{v + (y - 2020) * 5},{p},{a},{y},{KOD_OBCE},Ukázkov\n"
               for y in range(2020, 2025) for p, base in (("muži", 0), ("ženy", 12)) for a, v in (("0–14", 310 - base), ("15–64", 1480 - base), ("65+", 520 + base))) +
       "7,muži,0–14,2024,111111,Jinde\n"
       f",muži,0–14,2024,{KOD_OBCE},Ukázkov\n")  # prázdná hodnota se nesmí zobrazit

XML = f"""<?xml version="1.0" encoding="utf-8"?>
<VREJ>
  <PravnickaOsoba>
    <RedIzo>600000001</RedIzo><ICO>{SKOLA_ICO}</ICO>
    <RedPlnyNazev>Základní škola a mateřská škola Ukázkov, příspěvková organizace</RedPlnyNazev>
    <WWW>https://skola.demo</WWW>
    <Zrizovatele><Zrizovatel><ZrizICO>{OBEC_ICO}</ZrizICO><ZrizNazev>Obec Ukázkov</ZrizNazev></Zrizovatel></Zrizovatele>
    <SkolyZarizeni>
      <SkolaZarizeni><SkolaDruhTyp>Základní škola</SkolaDruhTyp><SkolaPlnyNazev>Základní škola Ukázkov</SkolaPlnyNazev></SkolaZarizeni>
      <SkolaZarizeni><SkolaDruhTyp>Mateřská škola</SkolaDruhTyp><SkolaPlnyNazev>Mateřská škola Ukázkov</SkolaPlnyNazev></SkolaZarizeni>
    </SkolyZarizeni>
  </PravnickaOsoba>
  <PravnickaOsoba>
    <RedIzo>600000002</RedIzo><ICO>70000002</ICO>
    <RedPlnyNazev>Mateřská škola Jinde</RedPlnyNazev>
    <Zrizovatele><Zrizovatel><ZrizICO>99999999</ZrizICO></Zrizovatel></Zrizovatele>
    <SkolyZarizeni><SkolaZarizeni><SkolaDruhTyp>Mateřská škola</SkolaDruhTyp><SkolaPlnyNazev>Mateřská škola Jinde</SkolaPlnyNazev></SkolaZarizeni></SkolyZarizeni>
  </PravnickaOsoba>
</VREJ>
""".encode("utf-8")


def fake_stream(url):
    if "data.csu.gov.cz" in url:
        return io.BytesIO(CSV.encode("utf-8"))
    if "rejstriky.msmt.cz" in url:
        return io.BytesIO(XML)
    raise ValueError(f"demo: neznámý soubor {url}")


def _html(title, body, links=()):
    a = "".join(f'<a href="{h}">{t}</a> ' for h, t in links)
    return f"<html><head><title>{title}</title></head><body><nav>{a}</nav><main>{body}</main><script>var x='skolni rad';</script></body></html>"


def fake_page(url):
    p = urllib.parse.urlparse(url)
    host, path = p.netloc, p.path.rstrip("/") or "/"
    if host == "www.hlidacstatu.cz":
        ms = re.fullmatch(r"/[Ss]ubjekt/(\d{8})", path)
        if ms and ms.group(1) in WEBS:
            body = ('<div class="odkazy"><span>Webová stránka</span> '
                    f'<a href="{WEBS[ms.group(1)]}">{WEBS[ms.group(1)]}</a> '
                    '<a href="https://www.youtube.com/playlist?list=x">Záznamy zastupitelstva</a> '
                    '<a href="https://www.saleskit.com/cs">Vyzkoušejte SalesKit</a></div>')
            return url, _html("Subjekt", body)
        if ms and ms.group(1) == "70000005":  # popisek je, ale web patří jinému subjektu
            return url, _html("Subjekt", '<span>Webová stránka</span> <a href="https://other.demo/">https://other.demo/</a>')
        if ms and ms.group(1) == "70000006":  # dva různé weby
            return url, _html("Subjekt", '<span>Webová stránka</span> <a href="https://a.demo/">a</a> <span>Webová stránka</span> <a href="https://b.demo/">b</a>')
        if ms:  # jen reklama a odkaz bez popisku
            return url, _html("Subjekt", '<a href="https://www.saleskit.com/cs">SalesKit</a> <span>Zdroj</span> <a href="https://random.demo/">odkaz</a>')
        m = re.fullmatch(r"/subjekt/Vazby/(\d{8})", path)
        if m and m.group(1) == OBEC_ICO:
            body = ('<h2>Podřízené organizace</h2>'
                    f'<a href="/subjekt/{SKOLA_ICO}">Základní škola a mateřská škola Ukázkov, příspěvková organizace</a> '
                    '<a href="/subjekt/70000003">Mateřská škola Pohádka, příspěvková organizace</a> '
                    '<a href="/subjekt/70000009">Technické služby Ukázkov, příspěvková organizace</a> '
                    '<a href="/subjekt/00100002">Městys Ukázkov Nový</a> <a href="/subjekt/Vazby/00100001">Vazby</a>')
            return url, _html("Vazby", body)
        from . import net
        raise net.ApiError("Web vrátil HTTP 404", 404)
    if host == "skola.demo":
        nav = [("/skolni-rad", "Školní řád"), ("/dokumenty", "Dokumenty ke stažení"), ("/zapis", "Zápis do 1. třídy"),
               ("/kontakt", "Kontakt"), ("/informace", "Informace")]
        pages = {
            "/": _html("Základní škola Ukázkov", "<h1>Vítejte</h1><p>Aktuality ze školy.</p>", nav),
            "/skolni-rad": _html("Školní řád", "<p>Školní řád a vnitřní řád školní družiny platný od 1. 9.</p>", nav),
            "/dokumenty": _html("Dokumenty", '<a href="/files/vz.pdf">Výroční zpráva o činnosti školy 2024</a> '
                                '<a href="/files/svp.pdf">Školní vzdělávací program</a>', nav),
            "/zapis": _html("Zápis", "<p>Kritéria přijímání a termín zápisu do 1. třídy.</p>", nav),
            "/kontakt": _html("Kontakt", "<p>Pověřenec pro ochranu osobních údajů: kontakt na GDPR pověřence.</p>", nav),
            "/informace": _html("Informace", "<p>Žádost o informace podle zákona 106/1999 Sb. – poskytování informací.</p>", nav),
        }
    elif host == "other.demo":
        pages = {"/": _html("Jiná firma s.r.o.", "<h1>Něco úplně jiného</h1>")}
    elif host in ("a.demo", "b.demo"):
        pages = {"/": _html("Ukázkov", "<p>Ukázkov</p>")}
    elif host == "obec.demo":
        nav = [("/uredni-deska", "Úřední deska"), ("/rozpocet", "Rozpočet a závěrečný účet")]
        pages = {
            "/": _html("Obec Ukázkov", "<h1>Obec Ukázkov</h1>", nav),
            "/uredni-deska": _html("Úřední deska", "<p>Úřední deska obce. Povinně zveřejňované informace.</p>", nav),
            "/rozpocet": _html("Rozpočet", "<p>Rozpočet 2025 a závěrečný účet za rok 2024.</p>", nav),
        }
    else:
        from . import net
        raise net.ApiError("Web není dostupný (demo)")
    if path not in pages:
        from . import net
        raise net.ApiError("Web vrátil HTTP 404", 404)
    return f"{p.scheme}://{host}{path}", pages[path]
