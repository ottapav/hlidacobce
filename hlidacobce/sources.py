"""Karty, které jen odkazují na zdroje bez ověřeného strojového přístupu (status 'link')."""
from .cards import card


def _link_card(title, source, intro, links, notes=None, asof=None):
    return card(title, source, "link", asof, intro, [], links, notes)


def obec_link_cards(ico):
    return [
        _link_card("MF – Monitor státní pokladny (rozpočet obce)", "Ministerstvo financí – Státní pokladna",
                   "Příjmy z daní a poplatků, výdaje, hospodaření a dluh obce po položkách rozpočtové skladby.",
                   [("Územní Monitor", "https://monitor.statnipokladna.gov.cz/uzemni-samosprava"),
                    ("Otevřená data – FinM", "https://monitor.statnipokladna.gov.cz/api/opendata/monitor/FinM"),
                    ("Portál otevřených dat MF – hospodaření obcí", "https://data.mf.gov.cz/topics/hospodareni-obci")],
                   ["Strukturu otevřených dat FinM jsem neověřil, proto jen odkazy."]),
        _link_card("MF / Finanční správa – koeficient daně z nemovitých věcí", "Ministerstvo financí, Finanční správa ČR",
                   "Místní koeficient, kterým obec upravuje daň z nemovitých věcí.",
                   [("Vyhledání koeficientů", "https://adisspr.mfcr.cz/dpr/adis/idpr_reg/dne/koef/vyhledani.faces"),
                    ("Informace Finanční správy", "https://financnisprava.gov.cz/cs/dane/dane/dan-z-nemovitych-veci")],
                   ["Seznam ke stažení jsem nenašel; vyhledání je ruční."]),
        _link_card("MV – Sbírka právních předpisů ÚSC (vyhlášky obce)", "Ministerstvo vnitra",
                   "Obecně závazné vyhlášky obce včetně místních poplatků (zák. 565/1990 Sb.).",
                   [("Sbírka právních předpisů", "https://sbirkapp.gov.cz"),
                    ("Povinnost zveřejnění", "https://mv.gov.cz/povinnost-zverejneni-obecne-zavaznych-pravnich-predpisu-uzemnich-samospravnych-celku")],
                   ["API ani strojový export jsem neověřil."]),
        _link_card("Hlídač státu – profil obce", "Hlídač státu",
                   "Smlouvy, dotace, veřejné zakázky a další přehledy k subjektu.",
                   [("Profil na Hlídači státu", f"https://www.hlidacstatu.cz/subjekt/{ico}")]),
    ]


def csu_link_cards():
    return [
        _link_card("ČSÚ – Sčítání lidu, domů a bytů 2021", "Český statistický úřad",
                   "Vzdělání, národnost, domácnosti, bytový fond, dojížďka a ekonomická aktivita obyvatel obce.",
                   [("Výsledky sčítání – otevřená data", "https://scitani.gov.cz/prvni-vysledky-scitani-2021-v-otevrenych-datech"),
                    ("Dokumentace datových sad", "https://csu.gov.cz/vysledky-scitani-2021-otevrena-data-dokumentace")],
                   ["Přímý odkaz na soubor pro konkrétní obec jsem neověřil."], "stav k 26. 3. 2021"),
        _link_card("ČSÚ – Registr ekonomických subjektů", "Český statistický úřad",
                   "Firmy a podnikatelé se sídlem v obci.",
                   [("Registr ekonomických subjektů", "https://apl.czso.cz/res/"), ("DataStat", "https://data.csu.gov.cz")],
                   ["Webová aplikace, automatické načtení tu není."]),
        _link_card("ČSÚ – Veřejná databáze a statistika obcí", "Český statistický úřad",
                   "Další ukazatele za obce (bydlení, pracovní trh, životní prostředí).",
                   [("Veřejná databáze", "https://vdb.czso.cz")]),
    ]


def school_link_cards(kind):
    what = "školy" if kind == "zs" else "školky"
    return [
        _link_card("Česká školní inspekce – inspekční zprávy", "Česká školní inspekce",
                   f"Inspekční zprávy a výsledky kontrol {what}.",
                   [("InspIS PORTÁL", "https://portal.csicr.cz")], ["Vyhledání podle názvu nebo IZO je ruční."]),
        _link_card("MŠMT – Rejstřík škol a školských zařízení", "Ministerstvo školství, mládeže a tělovýchovy",
                   "Zápis ve školském rejstříku: zřizovatel, kapacita, obory, místa poskytování vzdělávání.",
                   [("Rejstřík škol", "https://rejstriky.msmt.cz/rejskol/"),
                    ("Otevřená data rejstříku", "https://rejstriky.msmt.cz/opendata/")],
                   None),
        _link_card("Veřejný rejstřík – příspěvková organizace", "Ministerstvo spravedlnosti",
                   "Zřizovací listina, statutární orgán, sídlo a další údaje.",
                   [("Veřejné rejstříky", "https://or.justice.cz/ias/ui/rejstrik")]),
    ]
