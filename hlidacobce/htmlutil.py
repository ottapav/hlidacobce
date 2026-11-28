"""Tolerantní čtení HTML: text, titulek a odkazy (včetně textu těsně před odkazem). Bez síťového přístupu."""
from html.parser import HTMLParser


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.title, self._skip, self._in_title, self._href, self._atxt = [], [], "", 0, False, None, []
        self.link_prev, self._prev = [], ""  # text těsně před každým odkazem (paralelně k self.links)

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            self._href, self._atxt = dict(attrs).get("href"), []
            self._prev = self.parts[-1] if self.parts else ""

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._atxt).strip()))
            self.link_prev.append(self._prev)
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        s = data.strip()
        if s:
            self.parts.append(s)
            if self._href is not None:
                self._atxt.append(s)


def parse_html(html):
    p = _Page()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - rozbité HTML nesmí shodit kontrolu
        pass
    return p
