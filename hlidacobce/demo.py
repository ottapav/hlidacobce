"""Ukázková (vymyšlená) data pro režim --demo a testy. Nic odtud nepochází z reálných zdrojů."""
import io
import re
import urllib.parse
from datetime import date, timedelta

OBEC_ICO = "00100001"
SKOLA_ICO = "70000001"
KOD_OBCE = "999999"


def _d(days):
    return (date.today() - timedelta(days=days)).isoformat()


def _subject(ico, name, legal, founded="1992-01-01", kod=KOD_OBCE):
    return {"ico": ico, "obchodniJmeno": name, "pravniForma": legal, "datumVzniku": founded,
            "sidlo": {"textovaAdresa": "Ukázková 1, 123 45 Ukázkov", "kodObce": kod}}


def _ares_all():
    return {
        OBEC_ICO: _subject(OBEC_ICO, "Obec Ukázkov", "801", "1990-11-24"),
        "00100002": _subject("00100002", "Městys Ukázkov Nový", "801", "1990-11-24", "888888"),
        SKOLA_ICO: _subject(SKOLA_ICO, "Základní škola a mateřská škola Ukázkov, příspěvková organizace", "331", "2003-01-01"),
        "44444444": _subject("44444444", "Světla Rychle s.r.o.", "112", _d(90 + 200)),
    }


def fake_json(url, data):
    path = urllib.parse.urlparse(url)
    if "ares.gov.cz" in path.netloc:
        if path.path.endswith("/vyhledat"):
            q = (data or {}).get("obchodniJmeno", "").lower()
            allv = [v for v in _ares_all().values() if v["pravniForma"] == "801" and q in v["obchodniJmeno"].lower()]
            return {"pocetCelkem": len(allv), "ekonomickeSubjekty": allv}
        ico = path.path.rsplit("/", 1)[-1]
        allv = _ares_all()
        if ico in allv:
            return allv[ico]
        return _subject(ico, f"Firma {ico}", "112", "2005-05-05")
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
       "7,muži,0–14,2024,111111,Jinde\n")

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
