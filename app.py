#!/usr/bin/env python3
"""Hlídač obce – spuštění: python3 app.py [--port 8765] [--no-browser] [--demo]"""
import argparse

from hlidacobce import net, server


def main():
    ap = argparse.ArgumentParser(description="Hlídač obce: přehled veřejných zdrojů o obci, škole a školce (spouští se na zavolání).")
    ap.add_argument("--port", type=int, default=8765, help="port lokálního serveru (výchozí 8765, 0 = libovolný volný)")
    ap.add_argument("--no-browser", action="store_true", help="neotevírat prohlížeč")
    ap.add_argument("--demo", action="store_true", help="vymyšlená data, nic se nestahuje z internetu")
    a = ap.parse_args()
    net.set_demo(a.demo)
    server.serve(a.port, not a.no_browser)


if __name__ == "__main__":
    main()
