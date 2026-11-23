"""Lokální HTTP server: statické UI + JSON API. Poslouchá jen na 127.0.0.1 a každé volání je jednorázové."""
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, contracts, net, tabs

STATIC = os.path.join(os.path.dirname(__file__), "static")
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}
ICO_RE = re.compile(r"^\d{6,8}$")
LOOPBACK = ("127.0.0.1", "localhost", "::1")

# Ochrana veřejné instance: limit požadavků na IP a počtu souběžně běžících (pomalých) načtení karet.
RATE_LIMIT = int(os.environ.get("HLIDACOBCE_RATE_LIMIT", "40"))        # požadavků na /api za minutu a IP
MAX_CONCURRENT = int(os.environ.get("HLIDACOBCE_MAX_CONCURRENT", "4"))  # souběžných načtení záložek
_hits, _hits_lock = {}, threading.Lock()
_slots = threading.BoundedSemaphore(MAX_CONCURRENT)


def rate_limited(ip, now=None):
    now = time.monotonic() if now is None else now
    with _hits_lock:
        if len(_hits) > 5000:
            _hits.clear()
        q = [t for t in _hits.get(ip, []) if now - t < 60]
        limited = len(q) >= RATE_LIMIT
        if not limited:
            q.append(now)
        _hits[ip] = q
        return limited


class Handler(BaseHTTPRequestHandler):
    server_version = f"hlidacobce/{__version__}"
    protocol_version = "HTTP/1.1"  # proxy (Render) čekají HTTP/1.1; každá odpověď má Content-Length
    timeout = 30                   # neaktivní spojení se po 30 s zavřou

    def log_message(self, fmt, *args):
        if os.environ.get("HLIDACOBCE_VERBOSE"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- pomocné
    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        head_only = self.command == "HEAD"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _host_ok(self):
        """Na loopbacku ověřujeme Host (ochrana před DNS rebindingem); na veřejném hostingu ne."""
        if self.server.server_address[0] not in LOOPBACK:
            return True
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("127.0.0.1", "localhost", "[::1]")

    def _client_ip(self):
        """IP klienta za proxy: preferujeme hlavičky hostingu, jinak první adresu z X-Forwarded-For."""
        for h in ("True-Client-IP", "CF-Connecting-IP"):
            v = (self.headers.get(h) or "").strip()
            if v:
                return v
        fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return fwd or self.client_address[0]

    # -- routování
    def do_HEAD(self):  # health checky a uptime monitory často používají HEAD
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            return self._json({"error": "Nepovolený Host."}, 403)
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self._static("index.html")
            if u.path.startswith("/static/"):
                return self._static(u.path[len("/static/"):])
            if u.path == "/healthz":
                return self._send(200, "ok", "text/plain; charset=utf-8")
            if u.path.startswith("/api/"):
                if u.path != "/api/status" and rate_limited(self._client_ip()):
                    return self._json({"error": "Příliš mnoho požadavků, zkuste to za minutu."}, 429)
                return self._api(u.path[5:], q)
        except Exception:  # noqa: BLE001 - chyba jedné karty nesmí shodit server
            traceback.print_exc()
            return self._json({"error": "Interní chyba aplikace, podrobnosti jsou v terminálu."}, 500)
        self._json({"error": "Nenalezeno."}, 404)

    def _static(self, name):
        if not re.fullmatch(r"[\w.-]+", name) or os.path.splitext(name)[1] not in TYPES:
            return self._json({"error": "Nenalezeno."}, 404)
        try:
            with open(os.path.join(STATIC, name), "rb") as f:
                body = f.read()
        except OSError:
            return self._json({"error": "Nenalezeno."}, 404)
        self._send(200, body, TYPES[os.path.splitext(name)[1]])

    def _ico(self, q, key="ico"):
        v = re.sub(r"\s", "", q.get(key, ""))
        return v if ICO_RE.match(v) else None

    def _api(self, route, q):
        if route == "status":
            return self._json({"version": __version__, "demo": net.DEMO, "token": bool(contracts.token())})
        if route == "obce":
            term = q.get("q", "").strip()
            if len(term) < 2:
                return self._json({"obce": [], "error": "Zadejte alespoň 2 znaky."})
            return self._json(tabs.search_obce(term))
        if route == "schools":
            ico = self._ico(q, "obec")
            if not ico:
                return self._json({"error": "Neplatné IČO obce."}, 400)
            return self._json(tabs.list_schools(ico, q.get("kind", "")))
        ico = self._ico(q)
        if route.startswith("tab/"):
            if not ico:
                return self._json({"error": "Neplatné IČO."}, 400)
            if not _slots.acquire(timeout=20):
                return self._json({"error": "Server je teď vytížený, zkuste to za chvíli."}, 503)
            try:
                return self._tab(route[4:], ico, q)
            finally:
                _slots.release()
        self._json({"error": "Nenalezeno."}, 404)

    def _tab(self, tab, ico, q):
        web = q.get("web", "").strip()[:300]
        if tab == "obec":
            return self._json(tabs.tab_obec(ico, web))
        if tab == "csu":
            return self._json(tabs.tab_csu(ico))
        if tab == "school":
            return self._json(tabs.tab_school(q.get("kind", ""), ico, web, q.get("red_izo", "")[:20]))
        self._json({"error": "Nenalezeno."}, 404)


def make_server(port=8765, host="127.0.0.1"):
    return ThreadingHTTPServer((host, port), Handler)


def serve(port=8765, open_browser=True, host="127.0.0.1"):
    srv = make_server(port, host)
    url = f"http://{host}:{srv.server_address[1]}/"
    print(f"Hlídač obce {__version__} běží na {url}  (Ctrl+C ukončí)", flush=True)
    if net.DEMO:
        print("REŽIM DEMO: všechna data jsou vymyšlená, nic se nestahuje z internetu.")
    elif not contracts.token():
        print("Upozornění: není nastaven HLIDAC_TOKEN, karty Registru smluv budou jen vysvětlovat, jak token získat.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nKonec.")
    finally:
        srv.server_close()
