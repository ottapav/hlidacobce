#!/usr/bin/env python3
"""Hlídač obce – spuštění: python3 app.py [--port 8765] [--no-browser] [--demo]"""
import argparse
import os
import sys

from hlidacobce import net, server


def main():
    for stream in (sys.stdout, sys.stderr):  # logy hostingu nesmí spadnout na znacích s diakritikou
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Hlídač obce: přehled veřejných zdrojů o obci, škole a školce (spouští se na zavolání).")
    hosted = bool(os.environ.get("PORT"))  # Render a podobné hostingy nastavují PORT
    ap.add_argument("--host", default="0.0.0.0" if hosted else "127.0.0.1", help="adresa, na které server poslouchá")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8765)), help="port (výchozí $PORT, jinak 8765; 0 = libovolný volný)")
    ap.add_argument("--no-browser", action="store_true", default=hosted, help="neotevírat prohlížeč")
    ap.add_argument("--demo", action="store_true", help="vymyšlená data, nic se nestahuje z internetu")
    a = ap.parse_args()
    net.set_demo(a.demo or os.environ.get("HLIDACOBCE_DEMO") == "1")
    server.serve(a.port, not a.no_browser, a.host)


if __name__ == "__main__":
    main()
