"""Wikidata: oficiální web subjektu podle IČO (vlastnost P4156 „IČO“, P856 „oficiální web“). Ověřeno naživo na obci Velký Osek.

Shoda je podle identifikátoru, ne podle jména, proto je zdroj důvěryhodný. Pokrývá hlavně obce; školy tu bývají jen výjimečně."""
import urllib.parse

from . import net
from .util import norm_ico

SPARQL = "https://query.wikidata.org/sparql"


def websites_by_ico(ico):
    ico = norm_ico(ico)  # jen číslice, takže se do dotazu nedá vložit nic jiného
    if not ico:
        return []
    query = f'SELECT ?web WHERE {{ ?s wdt:P4156 "{ico}" . ?s wdt:P856 ?web }} LIMIT 5'
    data = net.http_json(f"{SPARQL}?" + urllib.parse.urlencode({"query": query, "format": "json"}), retries=1, timeout=20)
    return [b["web"]["value"] for b in data["results"]["bindings"] if "web" in b]
