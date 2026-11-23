"""Český statistický úřad – otevřená data (DataStat), úroveň obcí. EXPERIMENTÁLNÍ: struktura CSV nebyla ověřena naživo."""
import csv
import io
import json
import os
import re
import threading
from datetime import date

from . import net
from .cards import card, heading, kv, table, cell_right, today_str, text
from .util import cz_date

CSU_DATASET = "OBY02E"  # obyvatelstvo podle pohlaví a základních věkových skupin (úroveň obcí)
CSU_URL = "https://data.csu.gov.cz/opendata/sady/{kod}/distribuce/csv"
CSU_CACHE_DAYS = 120
CSU_YEARS = 5
MAX_COLS = 14
CACHE_DIR = os.environ.get("HLIDACOBCE_CACHE", ".hlidacobce_cache")
SRC = "Český statistický úřad (DataStat)"
_lock = threading.Lock()


def _cache_path(kod, dataset):
    return os.path.join(CACHE_DIR, f"csu_{dataset}_{re.sub(r'[^0-9A-Za-z]', '', kod)}.json")


def csu_load(kod, dataset=CSU_DATASET):
    with _lock:  # velký soubor se nesmí stahovat paralelně
        return _csu_load(kod, dataset)


def _csu_load(kod, dataset):
    """Stáhne CSV ČSÚ a uloží jen řádky pro danou obec. Výsledek se cachuje na disk."""
    if not kod:
        raise ValueError("chybí kód obce")
    path = _cache_path(kod, dataset)
    try:
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
        if (date.today() - date.fromisoformat(cached["fetched"])).days <= CSU_CACHE_DAYS:
            return cached
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        pass
    url = CSU_URL.format(kod=dataset)
    rows = []
    with net.open_stream(url) as r:
        reader = csv.reader(io.TextIOWrapper(r, encoding="utf-8-sig", newline=""))
        header = next(reader)
        low = [h.strip().lower() for h in header]
        terr = [i for i, h in enumerate(low) if re.match(r"^(uz|vuzemi)|obec|územ|uzemi", h)]
        val_i = low.index("hodnota") if "hodnota" in low else len(header) - 1
        year_i = next((i for i, h in enumerate(low) if re.search(r"^cas|rok|year", h)), None)
        other = [i for i in range(len(header)) if i not in terr and i != val_i and i != year_i]
        target = kod.lstrip("0")
        for row in reader:
            if len(row) > val_i and any(row[i].strip().lstrip("0") == target for i in terr if i < len(row)):
                rows.append({"year": row[year_i].strip() if year_i is not None else "",
                             "dims": [row[i].strip() for i in other], "value": row[val_i].strip()})
    info = {"fetched": date.today().isoformat(), "url": url, "header": header,
            "territory_columns": [header[i] for i in terr], "other_columns": [header[i] for i in other], "rows": rows}
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False)
    except OSError:
        pass
    return info


def fmt_num(s):
    try:
        return f"{int(float(s)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return s


def csu_table_block(info):
    rows = info["rows"]
    years = sorted({r["year"] for r in rows})[-CSU_YEARS:]

    def combo(r):
        return " / ".join(x for x in r["dims"] if x)
    cols = sorted({combo(r) for r in rows})[:MAX_COLS]
    val = {(r["year"], combo(r)): r["value"] for r in rows}
    body = [[y] + [cell_right(fmt_num(val.get((y, c), "–"))) for c in cols] for y in years]
    return table(["Rok"] + cols, body, "ČSÚ pro tuto obec nevrátil žádné řádky.")


def population_card(kod):
    links = [("DataStat – sada OBY02E", "https://data.csu.gov.cz/opendata/sady/OBY02E"),
             ("Soubor CSV (celá ČR)", CSU_URL.format(kod=CSU_DATASET))]
    if not kod:
        return card("Obyvatelstvo podle pohlaví a věku", SRC, "error", None,
                    "ARES nevrátil kód obce, nelze dohledat řádky v datech ČSÚ.", links=links)
    try:
        info = csu_load(kod)
    except (net.ApiError, ValueError, OSError, StopIteration, csv.Error) as ex:
        return card("Obyvatelstvo podle pohlaví a věku", SRC, "error", None,
                    f"Data ČSÚ se nepodařilo načíst: {ex}", links=links)
    if not info["rows"]:
        return card("Obyvatelstvo podle pohlaví a věku", SRC, "warn", cz_date(date.fromisoformat(info["fetched"])),
                    f"V souboru ČSÚ nebyly pro kód obce {kod} nalezeny řádky. Zkontrolujte sloupce: "
                    f"územní = {', '.join(info['territory_columns']) or 'žádný nenalezen'}.",
                    links=links, notes=["Struktura souboru nebyla ověřena naživo; sloupce se poznávají podle hlavičky."])
    return card("Obyvatelstvo podle pohlaví a věku", SRC, "info", cz_date(date.fromisoformat(info["fetched"])),
                f"Posledních {CSU_YEARS} let podle sady {CSU_DATASET}. Sloupce = kombinace dalších dimenzí sady.",
                [csu_table_block(info)], links,
                ["EXPERIMENTÁLNÍ: sloupce CSV jsou rozpoznávány heuristicky. Hodnoty před použitím porovnejte s oficiální tabulkou na webu ČSÚ."])
