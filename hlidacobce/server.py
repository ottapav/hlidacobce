"""Lokální HTTP server: statické UI + JSON API. Poslouchá jen na 127.0.0.1 a každé volání je jednorázové."""
import json
import os
import re
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, contracts, net, tabs

STATIC = os.path.join(os.path.dirname(__file__), "static")
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}
ICO_RE = re.compile(r"^\d{6,8}$")


class Handler(BaseHTTPRequestHandler):
    server_version = f"hlidacobce/{__version__}"

    def log_message(self, fmt, *args):
        if os.environ.get("HLIDACOBCE_VERBOSE"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- pomocné
    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("127.0.0.1", "localhost", "[::1]")

    # -- routování
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
            if u.path.startswith("/api/"):
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
            tab, web = route[4:], q.get("web", "").strip()[:300]
            if tab == "obec":
                return self._json(tabs.tab_obec(ico, web))
            if tab == "csu":
                return self._json(tabs.tab_csu(ico))
            if tab == "school":
                return self._json(tabs.tab_school(q.get("kind", ""), ico, web, q.get("red_izo", "")[:20]))
        self._json({"error": "Nenalezeno."}, 404)


def make_server(port=8765):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port=8765, open_browser=True):
    srv = make_server(port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"Hlídač obce {__version__} běží na {url}  (Ctrl+C ukončí)")
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
