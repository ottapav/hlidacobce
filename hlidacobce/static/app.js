"use strict";
(function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var state = { obec: null, loaded: {} };
  var LABELS = { ok: "V pořádku", warn: "Ke kontrole", info: "Informace", link: "Jen odkaz", error: "Chyba" };

  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined && txt !== null) e.textContent = txt;
    return e;
  }
  function safeUrl(u) { return /^https?:\/\//i.test(u || "") ? u : null; }
  function link(text, url) {
    var u = safeUrl(url);
    if (!u) return document.createTextNode(text);
    var a = el("a", null, text);
    a.href = u; a.target = "_blank"; a.rel = "noopener noreferrer";
    return a;
  }
  function getJSON(url) {
    return fetch(url).then(function (r) {
      return r.json().catch(function () { return { error: "Neplatná odpověď serveru." }; });
    }).catch(function () { return { error: "Server aplikace neodpovídá." }; });
  }
  function qs(o) {
    return Object.keys(o).map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(o[k] || ""); }).join("&");
  }

  /* ---------- vykreslení karet ---------- */
  function cell(td, c) {
    if (c && typeof c === "object") {
      if (c.align === "right") td.className = "r";
      if (c.url) td.appendChild(link(c.text, c.url)); else td.textContent = c.text;
    } else td.textContent = c == null ? "" : String(c);
  }
  var NS = "http://www.w3.org/2000/svg";
  function sv(tag, attrs, txt) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (txt !== undefined) e.textContent = txt;
    return e;
  }
  function fmt(n) { return Math.round(n).toLocaleString("cs-CZ"); }
  function compact(n) {
    if (n >= 1e6) return (n / 1e6).toLocaleString("cs-CZ", { maximumFractionDigits: 1 }) + " mil.";
    if (n >= 1e4) return (n / 1e3).toLocaleString("cs-CZ", { maximumFractionDigits: 0 }) + " tis.";
    return fmt(n);
  }
  function barsBlock(b) {
    var W = 600, H = 300, L = 62, R = 12, T = 28, B = 42, pw = W - L - R, ph = H - T - B, n = b.categories.length;
    var totals = b.categories.map(function (_, i) {
      return b.stacked ? b.series.reduce(function (a, s) { return a + (s.values[i] || 0); }, 0)
                       : Math.max.apply(null, b.series.map(function (s) { return s.values[i] || 0; }));
    });
    var max = Math.max.apply(null, totals.concat([1])), band = pw / n, bw = Math.min(band * 0.6, 90);
    var wrap = el("div", "chart");
    if (b.title) wrap.appendChild(el("h3", null, b.title));
    var svg = sv("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": b.title || "Graf" });
    var desc = b.categories.map(function (c, i) {
      return c + ": " + b.series.map(function (s) { return s.name + " " + fmt(s.values[i] || 0); }).join(", ");
    }).join("; ");
    svg.appendChild(sv("title", {}, b.title || "Graf"));
    svg.appendChild(sv("desc", {}, desc));
    [0, 0.5, 1].forEach(function (f) {
      var y = T + ph - ph * f;
      svg.appendChild(sv("line", { x1: L, x2: W - R, y1: y, y2: y, class: "ax" }));
      svg.appendChild(sv("text", { x: L - 6, y: y + 4, "text-anchor": "end" }, compact(max * f)));
    });
    b.categories.forEach(function (c, i) {
      var cx = L + band * i + band / 2, x = cx - bw / 2, base = T + ph;
      svg.appendChild(sv("text", { x: cx, y: H - 18, "text-anchor": "middle" }, c));
      var series = b.stacked ? b.series : [b.series[0]];
      var acc = 0;
      series.forEach(function (s, k) {
        var v = s.values[i] || 0, h = ph * v / max, y = b.stacked ? base - ph * (acc + v) / max : base - h;
        acc += v;
        if (h <= 0) return;
        var r = sv("rect", { x: x, y: y, width: bw, height: h, class: "seg" + Math.min(k, 2) });
        r.appendChild(sv("title", {}, c + " – " + s.name + ": " + fmt(v) + (b.unit ? " " + b.unit : "")));
        svg.appendChild(r);
        if (h >= 18) svg.appendChild(sv("text", { x: cx, y: y + h / 2 + 4, "text-anchor": "middle", class: "lbl" + Math.min(k, 2) }, b.stacked ? fmt(v) : compact(v)));
      });
      svg.appendChild(sv("text", { x: cx, y: base - ph * totals[i] / max - 6, "text-anchor": "middle", class: "tot" }, b.stacked ? fmt(totals[i]) : ""));
    });
    wrap.appendChild(svg);
    if (b.stacked || b.series.length > 1) {
      var lg = el("div", "legend");
      b.series.forEach(function (s, k) {
        var item = el("span"), sw = el("i", "seg" + Math.min(k, 2));
        item.appendChild(sw); item.appendChild(document.createTextNode(s.name));
        lg.appendChild(item);
      });
      if (b.stacked) lg.appendChild(el("span", null, "Číslo nad sloupcem = celkem"));
      wrap.appendChild(lg);
    }
    return wrap;
  }
  function block(b) {
    var d;
    if (b.type === "bars") return barsBlock(b);
    if (b.type === "heading") return el("h3", null, b.text);
    if (b.type === "text") return el("p", null, b.text);
    if (b.type === "kv") {
      d = el("dl", "kv");
      b.rows.forEach(function (r) { d.appendChild(el("dt", null, r[0])); d.appendChild(el("dd", null, r[1])); });
      return d;
    }
    if (b.type === "table") {
      if (!b.rows.length) return el("p", "muted", b.empty);
      var wrap = el("div", "scroll"), t = el("table"), thead = el("thead"), hr = el("tr"), tb = el("tbody");
      b.headers.forEach(function (h) { hr.appendChild(el("th", null, h)); });
      thead.appendChild(hr); t.appendChild(thead);
      b.rows.forEach(function (r) {
        var tr = el("tr");
        r.forEach(function (c) { var td = el("td"); cell(td, c); tr.appendChild(td); });
        tb.appendChild(tr);
      });
      t.appendChild(tb); wrap.appendChild(t);
      return wrap;
    }
    return el("span");
  }
  function renderCard(c) {
    var s = el("section", "card"), h = el("h2", null, c.title);
    h.appendChild(el("span", "badge s-" + c.status, LABELS[c.status] || c.status));
    s.appendChild(h);
    s.appendChild(el("div", "meta", c.source + (c.asof ? " · stav k " + c.asof : "")));
    if (c.intro) s.appendChild(el("p", null, c.intro));
    c.blocks.forEach(function (b) { s.appendChild(block(b)); });
    if (c.links.length) {
      var l = el("p", "links");
      c.links.forEach(function (x) { l.appendChild(link(x.text, x.url)); });
      s.appendChild(l);
    }
    if (c.notes.length) {
      var n = el("div", "notes");
      c.notes.forEach(function (x) { n.appendChild(el("p", null, x)); });
      s.appendChild(n);
    }
    return s;
  }
  function showCards(target, data) {
    target.textContent = "";
    if (data.error) { target.appendChild(el("p", "msg err", data.error)); return; }
    (data.cards || []).forEach(function (c) { target.appendChild(renderCard(c)); });
  }
  var MAX_RETRIES = 40, RETRY_MS = 8000;
  function load(target, url, done, attempt) {
    attempt = attempt || 0;
    if (!attempt) {
      target.dataset.url = url;
      target.textContent = "";
      target.appendChild(el("p", "loading", "Načítám data ze zdrojů, může to trvat desítky sekund…"));
    }
    getJSON(url).then(function (d) {
      if (attempt && target.dataset.url !== url) return;  // mezitím se načítá jiná obec/záložka
      showCards(target, d);
      if (done) done(d);
      var waiting = (d.cards || []).some(function (c) { return c.retry; });
      if (waiting && attempt < MAX_RETRIES) {
        setTimeout(function () { if (target.dataset.url === url) load(target, url, done, attempt + 1); }, RETRY_MS);
      }
    });
    target.dataset.url = url;
  }

  /* ---------- krok 1: výběr obce ---------- */
  $("#search-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var msg = $("#search-msg"), list = $("#results"), btn = e.target.querySelector("button");
    list.textContent = ""; msg.className = "msg"; msg.textContent = "Hledám v ARES…"; btn.disabled = true;
    getJSON("/api/obce?" + qs({ q: $("#q").value })).then(function (d) {
      btn.disabled = false;
      if (d.error) { msg.className = "msg err"; msg.textContent = d.error; return; }
      if (!d.obce.length) { msg.textContent = "Nic jsem nenašel. Zkuste přesnější název nebo IČO obce."; return; }
      msg.textContent = d.obce.length === 1 ? "Nalezena 1 obec:" : "Vyberte obec:";
      d.obce.forEach(function (o) {
        var li = el("li"), b = el("button"), s = el("small", null, "IČO " + o.ico + " · " + o.address);
        b.type = "button"; b.appendChild(document.createTextNode(o.name)); b.appendChild(s);
        b.addEventListener("click", function () { chooseObec(o); });
        li.appendChild(b); list.appendChild(li);
      });
    });
  });

  function chooseObec(o) {
    state.obec = o; state.loaded = {};
    ["obec", "zs", "ms", "csu"].forEach(function (k) { $("#c-" + k).textContent = ""; });
    document.querySelectorAll(".school-picker").forEach(function (p) { p.textContent = ""; });
    $("#obec-name").textContent = o.name;
    $("#obec-ico").textContent = "IČO " + o.ico;
    $("#step-search").hidden = true; $("#step-main").hidden = false;
    selectTab("obec");
  }
  $("#change").addEventListener("click", function () {
    $("#step-main").hidden = true; $("#step-search").hidden = false; $("#q").focus();
  });

  /* ---------- záložky ---------- */
  var TABS = ["obec", "zs", "ms", "csu"];
  function selectTab(name, focus) {
    TABS.forEach(function (t) {
      var on = t === name, b = $("#t-" + t);
      b.setAttribute("aria-selected", on ? "true" : "false");
      b.tabIndex = on ? 0 : -1;
      $("#p-" + t).hidden = !on;
      if (on && focus) b.focus();
    });
    if (state.loaded[name]) return;
    state.loaded[name] = true;
    if (name === "obec") loadObec();
    else if (name === "csu") load($("#c-csu"), "/api/tab/csu?" + qs({ ico: state.obec.ico }));
    else initPicker(name);
  }
  document.querySelectorAll(".tabs [role=tab]").forEach(function (b) {
    b.addEventListener("click", function () { selectTab(b.dataset.tab); });
    b.addEventListener("keydown", function (e) {
      var i = TABS.indexOf(b.dataset.tab);
      if (e.key === "ArrowRight") { e.preventDefault(); selectTab(TABS[(i + 1) % TABS.length], true); }
      if (e.key === "ArrowLeft") { e.preventDefault(); selectTab(TABS[(i + TABS.length - 1) % TABS.length], true); }
    });
  });

  /* ---------- záložka Obec ---------- */
  function loadObec() { load($("#c-obec"), "/api/tab/obec?" + qs({ ico: state.obec.ico })); }

  /* ---------- záložky Škola / Školka: zařízení se najdou samy, nic se nezadává ručně ---------- */
  function loadSchool(kind, s) {
    load($("#c-" + kind), "/api/tab/school?" + qs({ kind: kind, ico: s.ico }));
  }
  function initPicker(kind) {
    var box = $(".school-picker[data-kind=" + kind + "]"), word = kind === "zs" ? "školu" : "školku";
    box.textContent = "";
    box.appendChild(el("p", "loading", "Hledám " + word + " zřizovanou obcí…"));
    getJSON("/api/schools?" + qs({ obec: state.obec.ico, kind: kind })).then(function (d) {
      box.textContent = "";
      var list = d.schools || [];
      if (d.error) { box.appendChild(el("p", "msg err", d.error)); return; }
      if (!list.length) { box.appendChild(el("p", "muted", "Pro tuto obec jsem nenašel žádnou " + word + "."));  return; }
      if (list.length === 1) {
        box.appendChild(el("p", null, list[0].name + " (IČO " + list[0].ico + ", zdroj: " + (list[0].source || "registr") + ")"));
      } else {
        var sel = el("select"), lab = el("label", null, "Nalezeno " + list.length + " zařízení, vyberte:");
        sel.id = "sel-" + kind; sel.setAttribute("aria-label", "Vyberte " + word); lab.htmlFor = sel.id;
        list.forEach(function (s, i) { var o = el("option", null, s.name + " (IČO " + s.ico + ")"); o.value = String(i); sel.appendChild(o); });
        sel.addEventListener("change", function () { loadSchool(kind, list[+sel.value]); });
        box.appendChild(lab); box.appendChild(sel);
      }
      loadSchool(kind, list[0]);
    });
  }

  getJSON("/api/status").then(function (s) { if (s && s.demo) $("#demo").hidden = false;
    if (s && s.version) $("#ver").textContent = "Verze " + s.version + (s.commit ? " · nasazený commit " + s.commit : ""); });
})();
