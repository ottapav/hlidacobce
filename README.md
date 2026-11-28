# Hlídač obce

Aplikace, která **na zavolání** (nic neběží na pozadí, nic se neplánuje) složí z veřejných zdrojů přehled o obci, její škole a školce.
Nejdřív se zeptá na název obce, teprve potom načte data do karet. Každá karta = jeden zdroj.

| Záložka | Karty |
|---|---|
| **Obec** | ARES (základní údaje), Registr smluv z Hlídače státu (přehled + 6 signálů ke kontrole), dotace a veřejné zakázky (Hlídač státu, graf podle let), kontrola webu obce (úřední deska, rozpočet, závěrečný účet…), odkazy na MF Monitor, koeficient daně z nemovitých věcí, sbírku vyhlášek |
| **Škola** / **Školka** | zařízení zřizovaná obcí (Hlídač státu, záloha ARES), ARES, kontrola webu podle seznamu povinně zveřejňovaných informací (školní řád, ŠVP, úplata, kritéria přijímání, výroční zpráva, GDPR pověřenec, přístupnost…) s právní oporou, Registr smluv, dotace a zakázky, odkazy na ČŠI a rejstříky |
| **ČSÚ** | **komunální volby: graf zapsaných voličů, kolik volilo a kolik ne** (volby.cz, ročníky 2010–2026) a mandáty posledních voleb, obyvatelstvo podle pohlaví a věku (DataStat API, výběr jedné obce; záloha: celý CSV soubor), odkazy na SLDB 2021 a Registr ekonomických subjektů |

## Spuštění

Stačí Python 3.9+, žádné závislosti.

```bash
export HLIDAC_TOKEN=...     # token z https://www.hlidacstatu.cz/api (bez něj karty smluv jen vysvětlí, jak token získat)
python3 app.py              # otevře prohlížeč na http://127.0.0.1:8765
python3 app.py --demo       # vymyšlená data, nic se nestahuje z internetu
python3 app.py --port 9000 --no-browser
python3 -m unittest discover -s tests -t .
```

Server poslouchá jen na 127.0.0.1. Výsledky ČSÚ (po obcích) a velké soubory (záložní CSV ČSÚ jako index SQLite, rejstřík škol) se ukládají do `.hlidacobce_cache/` (ČSÚ 120 dní, rejstřík 30 dní); smazáním složky vynutíte nové stažení.

## Nasazení na Render

Repozitář obsahuje `render.yaml` (web service, `python app.py`, health check `/healthz`) a nemá žádné závislosti.
Aplikace sama pozná hosting podle proměnné `PORT`: poslouchá na `0.0.0.0` a neotevírá prohlížeč.

1. V Render dashboardu (Environment) nastavte `HLIDAC_TOKEN`. Bez něj fungují ostatní karty, karty smluv jen vysvětlí, jak token získat.
2. Volitelně `HLIDACOBCE_DEMO=1` (vymyšlená data), `HLIDACOBCE_RATE_LIMIT` (požadavků/min/IP, výchozí 40), `HLIDACOBCE_MAX_CONCURRENT` (souběžných načtení, výchozí 4).
3. Cache velkých souborů je v `/tmp`, takže po restartu nebo uspání free instance se ČSÚ a rejstřík škol stahují znovu (první načtení záložky pak trvá déle).

Veřejná instance používá váš token Hlídače státu, proto je zapnutý limit požadavků na IP a adresy webů zadané uživatelem se stahují jen z veřejných IP adres (ochrana před dotazy do vnitřní sítě).

## Struktura kódu

| Modul | Úloha |
|---|---|
| `net.py` | veškerý síťový přístup (JSON, streamy, stránky s ochranou proti SSRF, režim demo) |
| `util.py`, `cards.py`, `htmlutil.py` | pomocné funkce, stavební kameny karet, čtení HTML |
| `ares.py`, `hlidac.py`, `wikidata.py`, `schools.py` | klienti zdrojů: ARES, sdílený klient Hlídače státu (omezení rychlosti, opakování při 429), Wikidata (web obce podle IČO), školy (Hlídač → ARES) |
| `contracts.py`, `funding.py`, `elections.py`, `csu.py`, `webcheck.py`, `sources.py` | jednotlivé zdroje, každý vrací karty |
| `tabs.py` | skládá karty do záložek; každý zdroj je izolovaný (chyba jedné karty neshodí záložku) a nezávislé zdroje běží souběžně |
| `diag.py` | samodiagnostika `/api/selftest?ico=…`: z nasazení zkusí každý externí zdroj a vrátí strukturu odpovědí (bez dat a tokenu) |
| `server.py`, `static/` | HTTP server, omezení požadavků, UI |

Nový zdroj = nová funkce vracející kartu (nebo seznam karet) a jeden řádek v příslušné `tab_*` v `tabs.py`.

## Co aplikace záměrně nedělá

Měření dostupnosti webů v čase, upozornění na nové smlouvy od minulého spuštění a cokoli, co vyžaduje opakované volání. Karta „Dostupnost webu“ je jen jednorázové měření.

## Upřímně o spolehlivosti

Vývoj proběhl bez přístupu k živým zdrojům, proto platí:

- **Otestováno** na vymyšlených datech (`--demo`): logika signálů, parsery, server, rozhraní.
- **Neověřeno naživo**: cesta a pole API Hlídače státu (`SEARCH_PATH` v `contracts.py`, pole čte tolerantně), dotaz na DataStat API (kódy dimenzí jsou z katalogu sady OBY02E, formát odpovědi JSON-stat ověřen jen na vzorku) a záložní CSV ČSÚ (sloupce se rozpoznávají podle hlavičky), názvy atributů v XML volby.cz (adresa a parametry jsou z oficiální dokumentace KV2022, schéma XSD ne), termíny voleb 2014 a 2010 pro volby.cz (parametr `datumvoleb`; pro 2022 a 2018 ověřeno) a název atributu s mandáty ve výsledcích voleb. Když něco nesedí, karta ukáže chybu a odkaz na zdroj; nic se nezadává ručně: školy i adresy webů se zjišťují z registrů.
- **Kontrola webu je heuristika**: hledá klíčová slova v textu a odkazech. „Nenalezeno“ neznamená „nezveřejněno“ (web může být generovaný JavaScriptem, dokumenty mohou být jinde).
- **Právní opory jsou orientační**, nejde o právní poradenství. Před jakýmkoli závěrem ověřte znění předpisů.
- Registr smluv neobsahuje smlouvy do 50 000 Kč a obce do 3 000 obyvatel mají výjimku; u škol se povinnost týká jen zřizovaných ORP nebo krajem.
- Výsledky jsou signály ke kontrole, ne důkazy pochybení.

## Zdroje

ARES (MF), Hlídač státu, ČSÚ DataStat, Wikidata, odkazy na MF Monitor, Finanční správu, Sbírku právních předpisů ÚSC (MV), ČŠI.
