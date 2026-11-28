"""Veškerý síťový přístup na jednom místě (kvůli testům a režimu --demo)."""
import gzip
import io
import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "hlidacobce/0.1 (+https://github.com/ottapav/hlidacobce)"
DEMO = False


class ApiError(Exception):
    """Chyba při volání vnějšího zdroje; text je určen uživateli."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def set_demo(flag):
    global DEMO
    DEMO = bool(flag)


def http_json(url, headers=None, data=None, retries=3, timeout=30):
    if DEMO:
        from . import demo
        return demo.fake_json(url, data)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    h = {"User-Agent": UA, "Accept": "application/json"}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as ex:
            if ex.code in (400, 401, 403, 404, 429):  # opakování nepomůže nebo ho řídí volající
                raise ApiError(f"HTTP {ex.code} při volání {_host(url)}{_body_hint(ex)}", ex.code) from ex
            last = ex
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as ex:
            last = ex
        time.sleep(1.5 * (attempt + 1))
    if isinstance(last, urllib.error.HTTPError):
        raise ApiError(f"Zdroj {_host(url)} vrátil HTTP {last.code}{_body_hint(last)}", last.code)
    raise ApiError(f"Zdroj {_host(url)} není dostupný ({type(last).__name__})")


class _Raw(io.RawIOBase):
    def __init__(self, src, resp=None):
        super().__init__()
        self._src, self._resp = src, resp

    def readable(self):
        return True

    def readinto(self, b):
        data = self._src.read(len(b))
        b[:len(data)] = data
        return len(data)

    def close(self):
        try:
            self._src.close()
            if self._resp is not None:
                self._resp.close()
        finally:
            super().close()


def open_stream(url, timeout=180):
    """Otevře velký soubor (CSV/XML) pro streamované čtení; komprimovaný přenos (gzip) je výrazně rychlejší.
    Vrací binární buffered soubor, volající ho zavře (with)."""
    if DEMO:
        from . import demo
        return demo.fake_stream(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as ex:
        raise ApiError(f"Soubor z {_host(url)} se nepodařilo stáhnout (HTTP {ex.code})", ex.code) from ex
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        raise ApiError(f"Soubor z {_host(url)} se nepodařilo stáhnout ({type(ex).__name__})") from ex
    src = gzip.GzipFile(fileobj=resp) if resp.headers.get("Content-Encoding", "").lower() == "gzip" else resp
    return io.BufferedReader(_Raw(src, resp), 1 << 20)


def _body_hint(ex):
    """Začátek těla chybové odpovědi (např. text chyby API) – jen pro diagnostiku, zkrácený a bez zalomení."""
    try:
        body = ex.read(300).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""
    body = " ".join(body.split())
    return f": {body}" if body else ""


def _host(url):
    return urllib.parse.urlparse(url).hostname or url


def check_public_url(url):
    """Povolí jen veřejné http(s) adresy (ochrana před dotazy do vnitřní sítě)."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Neplatná adresa, povolené jsou jen http a https.")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror as ex:
        raise ValueError("Adresu se nepodařilo přeložit.") from ex
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("Adresa míří do vnitřní sítě, není povolena.")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _decode(raw, content_type):
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I) or re.search(rb"charset=[\"']?([\w-]+)", raw[:3000], re.I)
    enc = None
    if m:
        enc = m.group(1).decode("ascii", "ignore") if isinstance(m.group(1), bytes) else m.group(1)
    for e in ([enc] if enc else []) + ["utf-8", "cp1250"]:
        try:
            return raw.decode(e)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def fetch_page(url, timeout=15, max_bytes=1_500_000):
    """Stáhne HTML stránku. Vrací (konečná adresa, text)."""
    if DEMO:
        from . import demo
        return demo.fake_page(url)
    check_public_url(url)
    opener = urllib.request.build_opener(_SafeRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.5"})
    try:
        with opener.open(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "")
            if ctype and "html" not in ctype.lower() and "text" not in ctype.lower():
                raise ApiError("Adresa nevrací HTML stránku.")
            raw = r.read(max_bytes)
            return r.geturl(), _decode(raw, ctype)
    except urllib.error.HTTPError as ex:
        raise ApiError(f"Web vrátil HTTP {ex.code}", ex.code) from ex
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        raise ApiError(f"Web není dostupný ({type(ex).__name__})") from ex
