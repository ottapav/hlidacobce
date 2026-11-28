import json
import os
import tempfile
import threading
import unittest
import urllib.request

os.environ["HLIDACOBCE_CACHE"] = tempfile.mkdtemp()
os.environ["HLIDAC_TOKEN"] = "demo-token"

from hlidacobce import contracts, csu, demo, elections, funding, hlidac, net, schools, server, tabs, util, webcheck  # noqa: E402


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        net.set_demo(True)

    @classmethod
    def tearDownClass(cls):
        net.set_demo(False)


class TestModules(Base):
    def test_search(self):
        r = tabs.search_obce("Ukázkov")
        self.assertEqual({o["ico"] for o in r["obce"]}, {demo.OBEC_ICO, "00100002"})  # i městys je obec
        names = [o["name"] for o in r["obce"]]
        self.assertEqual(names[0], "Obec Ukázkov")

    def test_contract_signals(self):
        cs = contracts.contract_cards(demo.OBEC_ICO)
        titles = {c["title"]: c for c in cs}
        self.assertEqual(titles["Pozdní zveřejnění smluv"]["status"], "warn")
        self.assertEqual(titles["Dodatky ke smlouvám"]["status"], "warn")
        self.assertEqual(titles["Dodavatelé vzniklí krátce před smlouvou"]["status"], "warn")
        self.assertEqual(titles["Možné dělení zakázek"]["status"], "warn")

    def test_missing_token(self):
        old = os.environ.pop("HLIDAC_TOKEN")
        try:
            c = contracts.contract_cards(demo.OBEC_ICO)
            self.assertEqual(c[0]["status"], "error")
        finally:
            os.environ["HLIDAC_TOKEN"] = old

    def test_csu_index(self):
        self.assertEqual(len(csu.load_bulk(demo.KOD_OBCE)["rows"]), 30)
        self.assertEqual(csu.load_bulk("111111")["rows"][0]["value"], "7")  # řádky jiných obcí jsou v indexu také
        self.assertEqual(csu.load_bulk("424242")["rows"], [])

    def test_csu_bulk_real_layout(self):
        import io
        lines = ["Ukazatel,IndicatorType,Pohlaví,POHL2,Roky,CasRB,Území,Uz5ALLOKR,Hodnota"]
        for y in range(2018, 2025):
            for ind, code in (("Počet obyvatel k 1. 1.", "2406P"), ("Střední stav", "9379")):
                for sex, sc in (("Muži", "1"), ("Ženy", "2")):
                    val = str(1000 + y - 2018) if code == "2406P" else ""  # střední stav na úrovni obcí neexistuje
                    lines.append(f"{ind},{code},{sex},{sc},{y},{y},Ukázkov,424242,{val}")
        data = ("\n".join(lines) + "\n").encode()
        orig, db = net.open_stream, csu._db_path(csu.CSU_DATASET)
        net.open_stream = lambda url, timeout=180: io.BytesIO(data)
        os.rename(db, db + ".bak")
        try:
            csu._build(csu.CSU_DATASET)
            info = csu.load_bulk("424242")
            self.assertEqual(len(info["rows"]), 7 * 2)  # jen ukazatel s hodnotou
            self.assertEqual(info["rows"][0]["dims"], ["Počet obyvatel k 1. 1.", "Muži"])  # bez kódových sloupců
            tbl = csu.csu_table_block(info)
            self.assertEqual(tbl["headers"], ["Rok", "Počet obyvatel k 1. 1. / Muži", "Počet obyvatel k 1. 1. / Ženy"])
            self.assertTrue(all(c["text"].strip() not in ("", "–") for r in tbl["rows"] for c in r[1:]))
        finally:
            net.open_stream = orig
            os.replace(db + ".bak", db)

    def test_elections_chart(self):
        c = elections.election_card(demo.KOD_OBCE)
        self.assertEqual(c["status"], "info")
        chart = c["blocks"][0]
        self.assertEqual((chart["type"], chart["stacked"], chart["categories"]), ("bars", True, ["2018", "2022", "2026"]))
        voted, non = chart["series"][0]["values"], chart["series"][1]["values"]
        self.assertEqual(voted, [1010, 1180, 1240])
        self.assertEqual(non, [890, 770, 770])  # zapsaní (1900, 1950, 2010) minus volilo
        self.assertEqual([r[0] for r in c["blocks"][1]["rows"]], ["2018", "2022", "2026"])
        self.assertEqual(c["blocks"][1]["rows"][2][4]["text"], "61.7 %")
        parties = c["blocks"][-1]["rows"]
        self.assertEqual(parties[0][0], "Sdružení nezávislých Ukázkov")
        self.assertNotIn("2014", " ".join(c["notes"]))  # rok, kdy se volby nekonaly/neexistují, není chyba

    def test_elections_unknown_obec_and_bad_xml(self):
        self.assertEqual(elections.election_card("123456")["status"], "warn")
        self.assertEqual(elections.election_card("")["status"], "error")
        import io
        self.assertIsNone(elections.parse_result(io.BytesIO(b"<a><b x='1'/></a>")))

    def test_subsidies_and_tenders(self):
        c = funding.subsidy_card(demo.OBEC_ICO)
        self.assertEqual(c["status"], "info")
        self.assertEqual(c["blocks"][0]["rows"][0], ["Počet dotací", "6"])
        self.assertEqual(c["blocks"][0]["rows"][2][1].replace("\xa0", " "), "6 400 000 Kč")
        by_year = c["blocks"][1]
        self.assertEqual((by_year["type"], by_year["categories"]), ("bars", ["2019", "2020", "2021", "2022", "2023"]))
        self.assertEqual(by_year["series"][0]["values"][-1], 750000.0)
        self.assertEqual(c["blocks"][3]["rows"][0][1], "Kanalizace Ukázkov")
        t = funding.tender_card(demo.OBEC_ICO)  # první cesta v demo vrací 404 -> použije se záložní
        self.assertEqual(t["blocks"][0]["rows"][0], ["Počet zakázek", "4"])
        self.assertEqual(t["blocks"][-1]["rows"][0][1]["text"], "Stavební úpravy ZŠ")  # nejnovější první
        self.assertEqual(funding.subsidy_card("55555555")["status"], "warn")

    def test_funding_without_token(self):
        old = os.environ.pop("HLIDAC_TOKEN")
        try:
            self.assertEqual(funding.subsidy_card(demo.OBEC_ICO)["status"], "error")
            self.assertEqual(funding.tender_card(demo.OBEC_ICO)["status"], "error")
        finally:
            os.environ["HLIDAC_TOKEN"] = old

    def test_find_first_nested(self):
        self.assertEqual(util.find_first({"a": {"B": [{"castka": 5}]}}, ["x", "castka"]), 5)

    def test_csu_api(self):
        info = csu.csu_load(demo.KOD_OBCE)
        self.assertEqual(info["via"], "api")
        self.assertEqual(len(info["rows"]), 60)
        self.assertEqual(info["rows"][0]["dims"], ["Total", "Total"])
        self.assertEqual(csu.discover()["territory"], "UZ5ALLOKR")  # varianta jen s obcemi, ne pražská
        body = csu._query_body(csu.API_DEFAULTS, "538043", csu.API_DEFAULTS)
        self.assertEqual(body["radky"][0]["filtr"][0]["zobrazitPolozky"], ["538043"])
        card = csu.population_card(demo.KOD_OBCE)
        self.assertEqual(card["status"], "info")
        self.assertEqual(len(card["blocks"][0]["rows"]), 5)
        self.assertEqual(len(card["blocks"][0]["headers"]), 13)  # rok + 3 pohlaví x 4 věkové skupiny

    def test_csu_api_failure_falls_back_to_bulk(self):
        c = csu.population_card("111111")  # API pro tuto obec vrací 404 -> záložní soubor
        self.assertEqual(c["status"], "info")
        self.assertEqual(c["blocks"][0]["rows"][0][1]["text"], "7")

    def test_jsonstat_dict_values(self):
        d = {"id": ["T", "S"], "size": [2, 2], "role": {"time": ["T"]},
             "dimension": {"T": {"category": {"index": {"2023": 0, "2024": 1}}}, "S": {"category": {"index": ["a", "b"], "label": {"a": "A", "b": "B"}}}},
             "value": {"0": 1, "3": 4}}
        self.assertEqual(csu.parse_jsonstat(d), [{"year": "2023", "dims": ["A"], "value": "1"}, {"year": "2024", "dims": ["B"], "value": "4"}])

    def test_csu_preparing(self):
        net.set_demo(False)
        csu.USE_API = False
        try:
            with csu._lock:
                old = dict(csu.STATE)
                csu.STATE.update(status="building", error=None, t=0)
            os.rename(csu._db_path(csu.CSU_DATASET), csu._db_path(csu.CSU_DATASET) + ".bak")
            try:
                c = csu.population_card(demo.KOD_OBCE)
                self.assertTrue(c["retry"])
                self.assertEqual(c["status"], "info")
            finally:
                os.rename(csu._db_path(csu.CSU_DATASET) + ".bak", csu._db_path(csu.CSU_DATASET))
                with csu._lock:
                    csu.STATE.update(old)
        finally:
            csu.USE_API = True
            net.set_demo(True)

    def test_csu(self):
        c = csu.population_card(demo.KOD_OBCE)
        self.assertEqual(c["status"], "info")
        self.assertEqual(len(c["blocks"][0]["rows"]), 5)
        self.assertEqual(csu.population_card("")["status"], "error")

    def test_schools_from_hlidac(self):
        zs = schools.schools_for_obec(demo.OBEC_ICO, "zs")
        ms = schools.schools_for_obec(demo.OBEC_ICO, "ms")
        self.assertEqual([s["ico"] for s in zs], [demo.SKOLA_ICO])
        self.assertEqual(sorted(s["ico"] for s in ms), sorted([demo.SKOLA_ICO, "70000003"]))  # technické služby se vyřadí
        self.assertEqual(zs[0]["source"], "Hlídač státu")

    def test_schools_from_ares(self):
        r = schools.schools_for_obec("00100002", "zs")  # Hlídač stránku nemá (404) -> ARES podle sídla
        self.assertEqual([x["ico"] for x in r], ["70000008"])
        self.assertTrue(r[0]["source"].startswith("ARES"))

    def test_schools_error_lists_reasons(self):
        net.set_demo(True)
        orig = schools.load_index
        schools.load_index = lambda: (_ for _ in ()).throw(net.ApiError("HTTP 404"))
        try:
            with self.assertRaises(net.ApiError) as cm:
                schools.schools_for_obec("00100003", "zs")
            self.assertIn("Hlídač státu", str(cm.exception))
            self.assertIn("HTTP 404", str(cm.exception))
        finally:
            schools.load_index = orig

    def test_hlidac_links_case_insensitive(self):
        html = '<a href="/Subjekt/46390529">Masarykova základní škola Velký Osek, okres Kolín</a><a href="/Subjekt/Index/70926735">Mateřská škola Velký Osek</a>'
        orig = net.fetch_page
        net.fetch_page = lambda u: (u, html)
        try:
            r = schools.schools_from_hlidac("00235873")
        finally:
            net.fetch_page = orig
        self.assertEqual({x["ico"]: x["kinds"] for x in r}, {"46390529": ["zs"], "70926735": ["ms"]})

    def test_schools_fallback_to_rejstrik(self):
        r = schools.schools_for_obec("99999999", "ms")  # Hlídač stránku nemá (404) -> rejstřík MŠMT
        self.assertEqual(r[0]["ico"], "70000002")
        self.assertEqual(r[0]["source"], "rejstřík MŠMT")
        zs = schools.parse_rejstrik(__import__("io").BytesIO(demo.XML))[demo.OBEC_ICO][0]
        self.assertEqual(zs["web"], "https://skola.demo")

    def test_overview_pads_contracts_without_value(self):
        raw = demo._obec_contracts()[:2] + [{"Id": 1000 + i, "predmet": f"Bez ceny {i}", "datumUzavreni": demo._d(i + 1),
                                             "casZverejneni": demo._d(i + 1), "platce": {"ico": demo.OBEC_ICO}, "prijemce": []}
                                            for i in range(12)]
        cs = [contracts.normalize(r, demo.OBEC_ICO) for r in raw]
        top = contracts._overview(demo.OBEC_ICO, cs, __import__("datetime").date.today(), "")["blocks"][2]["rows"]
        self.assertEqual(len(top), 10)
        self.assertEqual(top[2][1]["text"], "Bez ceny 0")

    def test_webcheck_school(self):
        cs = webcheck.web_cards("skola.demo", "zs")
        check = cs[1]
        found = {r[0]: r[1] for r in check["blocks"][0]["rows"]}
        self.assertEqual(found["Školní řád (a vnitřní řád družiny/jídelny)"], "nalezeno")
        self.assertEqual(found["Výroční zpráva o činnosti školy"], "nalezeno")
        self.assertEqual(found["Prohlášení o přístupnosti webu"], "nenalezeno")
        self.assertEqual(check["status"], "warn")

    def test_find_site_reliable(self):
        r = webcheck.find_site(demo.OBEC_ICO, "Obec Ukázkov")
        self.assertEqual((r["status"], r["url"]), ("ok", "https://obec.demo/"))  # reklama SalesKit a YouTube se ignorují
        self.assertEqual(webcheck.find_site(demo.SKOLA_ICO, "Základní škola a mateřská škola Ukázkov, příspěvková organizace")["status"], "ok")
        self.assertEqual(webcheck.find_site("70000003", "Mateřská škola Pohádka")["status"], "none")  # jen reklama a odkaz bez popisku
        r = webcheck.find_site("70000005", "Mateřská škola Ukázkov")
        self.assertEqual((r["status"], r["url"], r["candidate"]), ("mismatch", None, "https://other.demo/"))
        self.assertEqual(webcheck.find_site("70000006", "Mateřská škola Ukázkov")["status"], "ambiguous")

    def test_name_tokens(self):
        self.assertEqual(webcheck.name_tokens("Obec Velim"), ["velim"])
        self.assertEqual(webcheck.name_tokens("Masarykova základní škola Velký Osek, okres Kolín"), ["masarykova", "velky", "osek"])
        self.assertEqual(webcheck.name_tokens("Základní škola a mateřská škola, příspěvková organizace"), [])

    def test_web_cards_found_automatically(self):
        cs = webcheck.web_cards_for_ico(demo.SKOLA_ICO, "zs", "Základní škola Ukázkov")
        self.assertEqual([c["title"] for c in cs][0], "Dostupnost webu (jednorázové měření)")
        self.assertIn("https://skola.demo", cs[0]["intro"])
        obec = tabs.tab_obec(demo.OBEC_ICO)["cards"]
        chk = next(c for c in obec if c["title"].startswith("Povinně zveřejňované informace"))
        found = {r[0]: r[1] for r in chk["blocks"][0]["rows"]}
        self.assertEqual((found["Úřední deska"], found["Rozpočet obce"]), ("nalezeno", "nalezeno"))

    def test_web_not_in_hlidac(self):
        for ico in ("70000003", "70000005", "70000006"):
            cs = webcheck.web_cards_for_ico(ico, "ms", "Mateřská škola Ukázkov")
            self.assertEqual((len(cs), cs[0]["status"]), (1, "warn"), ico)
            self.assertIn("nepodařilo spolehlivě dohledat", cs[0]["intro"])
            self.assertNotIn("saleskit", json.dumps(cs))

    def test_webcheck_errors(self):
        self.assertEqual(webcheck.web_cards("neexistuje.demo", "ms")[0]["status"], "error")
        self.assertEqual(webcheck.web_cards("", "ms")[0]["status"], "warn")

    def test_tabs(self):
        for t in (tabs.tab_obec(demo.OBEC_ICO), tabs.tab_csu(demo.OBEC_ICO),
                  tabs.tab_school("ms", demo.SKOLA_ICO)):
            self.assertTrue(t["cards"])
            json.dumps(t)

    def test_ssrf_guard(self):
        net.set_demo(False)
        try:
            for u in ("http://127.0.0.1/", "file:///etc/passwd", "http://localhost:8080"):
                with self.assertRaises(ValueError):
                    net.check_public_url(u)
        finally:
            net.set_demo(True)


class TestRefactor(Base):
    def test_guard_isolates_failures(self):
        def boom():
            raise RuntimeError("chyba v kódu")
        cs = tabs._guard("Zdroj", "test", boom)
        self.assertEqual([c["status"] for c in cs], ["error"])
        self.assertNotIn("chyba v kódu", json.dumps(cs, ensure_ascii=False))  # interní text se uživateli neukazuje
        orig = funding.tender_card
        funding.tender_card = lambda ico: 1 / 0
        try:
            data = tabs.tab_obec(demo.OBEC_ICO)  # jedna rozbitá karta nesmí zničit záložku
        finally:
            funding.tender_card = orig
        statuses = {c["title"]: c["status"] for c in data["cards"]}
        self.assertEqual(statuses["Veřejné zakázky (Hlídač státu)"], "error")
        self.assertIn("Základní údaje (ARES)", statuses)
        self.assertIn("Dotace (Hlídač státu)", statuses)

    def test_tab_order_is_stable(self):
        titles = [c["title"] for c in tabs.tab_obec(demo.OBEC_ICO)["cards"]]
        self.assertEqual(titles[0], "Základní údaje (ARES)")
        self.assertLess(titles.index("Dotace (Hlídač státu)"), titles.index("Veřejné zakázky (Hlídač státu)"))
        self.assertLess(titles.index("Veřejné zakázky (Hlídač státu)"), titles.index("MF – Monitor státní pokladny (rozpočet obce)"))

    def test_hlidac_search_dedupes_and_pages(self):
        items = hlidac.search("/Smlouvy/Hledat", "ico:%s" % demo.OBEC_ICO, "demo-token")
        ids = [str(util.pick(i, "id", "idVerze", "idSmlouvy")) for i in items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(items)

    def test_missing_token_card(self):
        c = hlidac.missing_token_card("T", "S", "dotace")
        self.assertEqual(c["status"], "error")
        self.assertIn("HLIDAC_TOKEN", c["intro"])

    def test_util(self):
        self.assertEqual(util.thousands(1234567), "1\u00a0234\u00a0567")
        self.assertEqual(util.find_first({"A": [{"b": {"C": 1}}]}, ["x", "c"]), 1)
        self.assertIsNone(util.find_first({"a": 1}, ["zzz"]))


class TestServer(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.srv = server.make_server(0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        super().tearDownClass()

    def get(self, path, host=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers={"Host": host} if host else {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as ex:
            return ex.code, ex.read()

    def test_static(self):
        for p, mark in (("/", "Hlídač obce".encode()), ("/static/app.js", b"use strict"), ("/static/style.css", b"--bg")):
            s, b = self.get(p)
            self.assertEqual(s, 200)
            self.assertIn(mark, b)
        self.assertEqual(self.get("/static/..%2fserver.py")[0], 404)

    def test_api(self):
        s, b = self.get("/api/obce?q=Uk%C3%A1zkov")
        self.assertEqual(json.loads(b)["obce"][0]["ico"], demo.OBEC_ICO)
        self.assertEqual(self.get("/api/obce?q=a")[0], 200)
        d = json.loads(self.get(f"/api/schools?obec={demo.OBEC_ICO}&kind=ms")[1])
        self.assertEqual(len(d["schools"]), 2)
        for path in (f"/api/tab/obec?ico={demo.OBEC_ICO}", f"/api/tab/csu?ico={demo.OBEC_ICO}",
                     f"/api/tab/school?kind=zs&ico={demo.SKOLA_ICO}&web=skola.demo"):
            s, b = self.get(path)
            self.assertEqual(s, 200)
            self.assertTrue(json.loads(b)["cards"])
        self.assertEqual(self.get("/api/tab/obec?ico=abc")[0], 400)
        # adresu webu od uživatele server nepřijímá (žádné ruční zadání, žádné SSRF)
        s, b = self.get(f"/api/tab/school?kind=zs&ico={demo.SKOLA_ICO}&web=http://127.0.0.1:1/")
        self.assertNotIn("127.0.0.1", b.decode())
        self.assertEqual(self.get("/api/nic")[0], 404)

    def test_head_and_http11(self):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        for path in ("/", "/healthz", "/api/status"):
            c.request("HEAD", path)
            r = c.getresponse()
            self.assertEqual(r.status, 200)
            self.assertEqual(r.read(), b"")
            self.assertEqual(r.version, 11)
        c.request("GET", "/healthz")  # totéž spojení (keep-alive) funguje dál
        r = c.getresponse()
        self.assertEqual((r.status, r.read()), (200, b"ok"))
        c.close()

    def test_host_header(self):
        self.assertEqual(self.get("/api/status", host="evil.example")[0], 403)


if __name__ == "__main__":
    unittest.main()


class TestHosted(unittest.TestCase):
    def test_rate_limit(self):
        server._hits.clear()
        ok = [server.rate_limited("1.2.3.4", now=100.0 + i * 0.1) for i in range(server.RATE_LIMIT + 3)]
        self.assertEqual(ok[:server.RATE_LIMIT], [False] * server.RATE_LIMIT)
        self.assertTrue(all(ok[server.RATE_LIMIT:]))
        self.assertFalse(server.rate_limited("1.2.3.4", now=200.0))  # po minutě znovu povoleno
        self.assertFalse(server.rate_limited("5.6.7.8", now=100.5))

    def test_public_bind_healthz_and_host(self):
        net.set_demo(True)
        srv = server.make_server(0, "0.0.0.0")
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            for path, host in (("/healthz", "hlidacobce.onrender.com"), ("/api/status", "hlidacobce.onrender.com")):
                req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Host": host})
                with urllib.request.urlopen(req) as r:
                    self.assertEqual(r.status, 200)
        finally:
            srv.shutdown()
            srv.server_close()
            net.set_demo(False)
