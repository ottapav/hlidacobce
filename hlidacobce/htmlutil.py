"""Tolerantní čtení HTML: text, titulek a odkazy (včetně textu těsně před odkazem). Bez síťového přístupu."""
from html.parser import HTMLParser


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.title, self._skip, self._in_title, self._href, self._atxt = [], [], "", 0, False, None, []
        self.link_prev, self._prev = [], ""  # text těsně před každým odkazem (paralelně k self.links)
        self.forms, self._select, self._option = [], None, None  # formuláře: [{action, method, fields:[{tag,name,id,type,value,options}]}]

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            self._href, self._atxt = dict(attrs).get("href"), []
            self._prev = self.parts[-1] if self.parts else ""
        elif tag == "form":
            a = dict(attrs)
            self.forms.append({"action": a.get("action", ""), "method": (a.get("method") or "get").lower(), "fields": []})
        elif tag in ("input", "select", "textarea") and self.forms:
            a = dict(attrs)
            field = {"tag": tag, "name": a.get("name", ""), "id": a.get("id", ""), "type": a.get("type", ""), "value": a.get("value", ""), "options": []}
            self.forms[-1]["fields"].append(field)
            self._select = field if tag == "select" else self._select
        elif tag == "option" and self._select is not None:
            self._option = [dict(attrs).get("value", ""), ""]
            self._select["options"].append(self._option)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "select":
            self._select = self._option = None
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._atxt).strip()))
            self.link_prev.append(self._prev)
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._option is not None:
            self._option[1] += data.strip()
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
