# Hlídač obce

Aplikace, která **na zavolání** (nic neběží na pozadí, nic se neplánuje) složí z veřejných zdrojů přehled o obci, její škole a školce.
Nejdřív se zeptá na název obce, teprve potom načte data do karet. Každá karta = jeden zdroj.

| Záložka | Karty |
|---|---|
| **Obec** | ARES (základní údaje), Registr smluv z Hlídače státu (přehled + 6 signálů ke kontrole), volitelná kontrola webu obce (úřední deska, rozpočet, závěrečný účet…), odkazy na MF Monitor, koeficient daně z nemovitých věcí, sbírku vyhlášek |
| **Škola** / **Školka** | zařízení zřizovaná obcí z rejstříku škol MŠMT (nebo ruční zadání IČO), ARES, kontrola webu podle seznamu povinně zveřejňovaných informací (školní řád, ŠVP, úplata, kritéria přijímání, výroční zpráva, GDPR pověřenec, přístupnost…) s právní oporou, Registr smluv, odkazy na ČŠI a rejstříky |
| **ČSÚ** | obyvatelstvo podle pohlaví a věku (otevřená data DataStat), odkazy na SLDB 2021 a Registr ekonomických subjektů |

## Spuštění

Stačí Python 3.9+, žádné závislosti.

```bash
export HLIDAC_TOKEN=...     # token z https://www.hlidacstatu.cz/api (bez něj karty smluv jen vysvětlí, jak token získat)
python3 app.py              # otevře prohlížeč na http://127.0.0.1:8765
python3 app.py --demo       # vymyšlená data, nic se nestahuje z internetu
python3 app.py --port 9000 --no-browser
python3 -m unittest discover -s tests -t .
```

Server poslouchá jen na 127.0.0.1. Velké soubory (ČSÚ, rejstřík škol) se ukládají do `.hlidacobce_cache/` (ČSÚ 120 dní, rejstřík 30 dní); smazáním složky vynutíte nové stažení.

## Co aplikace záměrně nedělá

Měření dostupnosti webů v čase, upozornění na nové smlouvy od minulého spuštění a cokoli, co vyžaduje opakované volání. Karta „Dostupnost webu“ je jen jednorázové měření.

## Upřímně o spolehlivosti

Vývoj proběhl bez přístupu k živým zdrojům, proto platí:

- **Otestováno** na vymyšlených datech (`--demo`): logika signálů, parsery, server, rozhraní.
- **Neověřeno naživo**: cesta a pole API Hlídače státu (`HLIDAC_SEARCH_PATH` v `contracts.py`, pole čte tolerantně), sloupce CSV sady ČSÚ OBY02E (rozpoznávají se podle hlavičky), struktura XML rejstříku škol MŠMT, odpovědi ARES. Když něco nesedí, karta ukáže chybu a odkaz na zdroj; školu lze vždy zadat ručně přes IČO.
- **Kontrola webu je heuristika**: hledá klíčová slova v textu a odkazech. „Nenalezeno“ neznamená „nezveřejněno“ (web může být generovaný JavaScriptem, dokumenty mohou být jinde).
- **Právní opory jsou orientační**, nejde o právní poradenství. Před jakýmkoli závěrem ověřte znění předpisů.
- Registr smluv neobsahuje smlouvy do 50 000 Kč a obce do 3 000 obyvatel mají výjimku; u škol se povinnost týká jen zřizovaných ORP nebo krajem.
- Výsledky jsou signály ke kontrole, ne důkazy pochybení.

## Zdroje

ARES (MF), Hlídač státu, ČSÚ DataStat, rejstřík škol MŠMT, odkazy na MF Monitor, Finanční správu, Sbírku právních předpisů ÚSC (MV), ČŠI.
