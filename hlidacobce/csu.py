"""Český statistický úřad – otevřená data (DataStat), úroveň obcí. EXPERIMENTÁLNÍ: struktura CSV nebyla ověřena naživo.

Rychlost: velký CSV soubor se stáhne a projde JEDNOU (komprimovaný přenos, streamování) do lokálního indexu SQLite
pro všechny obce. Dotaz na konkrétní obec je pak okamžitý. Příprava indexu běží na pozadí (spouští se při startu
serveru), karta mezitím ukáže, že se data připravují, a klient ji po chvíli načte znovu.
"""
import csv
import io
import json
import os
import re
import sqlite3
import threading
import time
from datetime import date

from . import net
from .cards import card, table, cell_right
from .util import cz_date

CSU_DATASET = "OBY02E"  # obyvatelstvo podle pohlaví a základních věkových skupin (úroveň obcí)
CSU_URL = "https://data.csu.gov.cz/opendata/sady/{kod}/distribuce/csv"
CSU_CACHE_DAYS = 120
CSU_YEARS = 5
MAX_COLS = 14
RETRY_AFTER_ERROR_S = 120
CACHE_DIR = os.environ.get("HLIDACOBCE_CACHE", ".hlidacobce_cache")
SRC = "Český statistický úřad (DataStat)"

_lock = threading.Lock()
STATE = {"status": "idle", "error": None, "t": 0.0}  # idle | building | error


class Preparing(Exception):
    """Index dat se ještě připravuje."""


def _db_path(dataset):
    return os.path.join(CACHE_DIR, f"csu_{dataset}.sqlite")


def _fresh(dataset):
    try:
        age = (time.time() - os.path.getmtime(_db_path(dataset))) / 86400
        return age <= CSU_CACHE_DAYS
    except OSError:
        return False


def _norm_key(v):
    k = str(v).strip().lstrip("0")
    return k if k.isdigit() and len(k) >= 5 else ""  # kódy obcí mají 5-6 číslic; kratší kódy jsou vyšší celky


def _build(dataset):
    url = CSU_URL.format(kod=dataset)
    path = _db_path(dataset)
    tmp = path + ".tmp"
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    try:
        db.execute("create table rows(k text, year text, dims text, value text)")
        db.execute("create table meta(k text primary key, v text)")
        batch = []
        with net.open_stream(url) as r:
            reader = csv.reader(io.TextIOWrapper(r, encoding="utf-8-sig", newline=""))
            header = next(reader)
            low = [h.strip().lower() for h in header]
            terr = [i for i, h in enumerate(low) if re.match(r"^(uz|vuzemi)|obec|územ|uzemi", h)]
            if not terr:
                raise net.ApiError("Soubor ČSÚ neobsahuje rozpoznatelný územní sloupec (hlavička: " + ", ".join(header[:8]) + ").")
            val_i = low.index("hodnota") if "hodnota" in low else len(header) - 1
            year_i = next((i for i, h in enumerate(low) if re.search(r"^cas|rok|year", h)), None)
            other = [i for i in range(len(header)) if i not in terr and i != val_i and i != year_i]
            for row in reader:
                if len(row) <= val_i:
                    continue
                keys = {_norm_key(row[i]) for i in terr if i < len(row)} - {""}
                if not keys:
                    continue
                year = row[year_i].strip() if year_i is not None else ""
                dims = json.dumps([row[i].strip() for i in other], ensure_ascii=False)
                for k in keys:
                    batch.append((k, year, dims, row[val_i].strip()))
                if len(batch) >= 5000:
                    db.executemany("insert into rows values (?,?,?,?)", batch)
                    batch.clear()
        db.executemany("insert into rows values (?,?,?,?)", batch)
        db.execute("create index ix_k on rows(k)")
        meta = {"fetched": date.today().isoformat(), "url": url, "header": header,
                "territory_columns": [header[i] for i in terr], "other_columns": [header[i] for i in other]}
        db.execute("insert into meta values ('info', ?)", (json.dumps(meta, ensure_ascii=False),))
        db.commit()
    except BaseException:
        db.close()
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    db.close()
    os.replace(tmp, path)


def _run_build(dataset):
    try:
        _build(dataset)
        with _lock:
            STATE.update(status="idle", error=None)
    except Exception as ex:  # noqa: BLE001 - chyba na pozadí se ukáže na kartě
        with _lock:
            STATE.update(status="error", error=str(ex) or type(ex).__name__, t=time.time())


def ensure_index(dataset=CSU_DATASET, wait=False):
    """Zajistí, že lokální index existuje a je čerstvý; jinak spustí jeho přípravu."""
    if _fresh(dataset):
        return
    with _lock:
        if STATE["status"] == "building":
            started = False
        elif STATE["status"] == "error" and time.time() - STATE["t"] < RETRY_AFTER_ERROR_S:
            raise net.ApiError(f"Data ČSÚ se nepodařilo připravit: {STATE['error']}")
        else:
            STATE.update(status="building", error=None, t=time.time())
            started = True
    if started:
        if wait:
            _run_build(dataset)
        else:
            threading.Thread(target=_run_build, args=(dataset,), daemon=True).start()
    if wait:
        while STATE["status"] == "building":
            time.sleep(0.2)
        if STATE["status"] == "error":
            raise net.ApiError(f"Data ČSÚ se nepodařilo připravit: {STATE['error']}")


def warm_up(dataset=CSU_DATASET):
    """Při startu serveru spustí přípravu indexu na pozadí (v demo režimu nic)."""
    if net.DEMO:
        return
    try:
        ensure_index(dataset)
    except net.ApiError:
        pass


def csu_load(kod, dataset=CSU_DATASET):
    """Řádky pro danou obec z lokálního indexu. Vyvolá Preparing, dokud se index připravuje."""
    if not kod:
        raise ValueError("chybí kód obce")
    ensure_index(dataset, wait=net.DEMO)
    if not _fresh(dataset):
        raise Preparing()
    db = sqlite3.connect(_db_path(dataset))
    try:
        meta = json.loads(db.execute("select v from meta where k='info'").fetchone()[0])
        rows = [{"year": y, "dims": json.loads(d), "value": v}
                for y, d, v in db.execute("select year, dims, value from rows where k=?", (kod.lstrip("0"),))]
    finally:
        db.close()
    meta["rows"] = rows
    return meta


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
    title = "Obyvatelstvo podle pohlaví a věku"
    links = [("DataStat – sada OBY02E", "https://data.csu.gov.cz/opendata/sady/OBY02E"),
             ("Soubor CSV (celá ČR)", CSU_URL.format(kod=CSU_DATASET))]
    if not kod:
        return card(title, SRC, "error", None, "ARES nevrátil kód obce, nelze dohledat řádky v datech ČSÚ.", links=links)
    try:
        info = csu_load(kod)
    except Preparing:
        return card(title, SRC, "info", None,
                    "Data ČSÚ se právě připravují: jednorázově se stahuje a zpracovává soubor za všechny obce (obvykle několik minut, "
                    "u dalších obcí už je výsledek okamžitý). Karta se načte sama.",
                    links=links, retry=True)
    except (net.ApiError, ValueError, OSError, sqlite3.Error, csv.Error, StopIteration) as ex:
        return card(title, SRC, "error", None, f"Data ČSÚ se nepodařilo načíst: {ex}", links=links)
    asof = cz_date(date.fromisoformat(info["fetched"]))
    if not info["rows"]:
        return card(title, SRC, "warn", asof,
                    f"V souboru ČSÚ nebyly pro kód obce {kod} nalezeny řádky. Zkontrolujte sloupce: "
                    f"územní = {', '.join(info['territory_columns']) or 'žádný nenalezen'}.",
                    links=links, notes=["Struktura souboru nebyla ověřena naživo; sloupce se poznávají podle hlavičky."])
    return card(title, SRC, "info", asof,
                f"Posledních {CSU_YEARS} let podle sady {CSU_DATASET}. Sloupce = kombinace dalších dimenzí sady.",
                [csu_table_block(info)], links,
                ["EXPERIMENTÁLNÍ: sloupce CSV jsou rozpoznávány heuristicky. Hodnoty před použitím porovnejte s oficiální tabulkou na webu ČSÚ."])
