/* Russia, China, ECB page (D59). Redraws the stored monthly series embedded in the page (series on or off, nominal or
   real, date range, crosshair readout), picks among the stored what-if rows and filters the event tables. Nothing is
   estimated here: every value comes from the JSON or the tables written by src/site_partners.py. ES5. */
(function () {
  var byId = function (id) { return document.getElementById(id); };
  var all = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var press = function (buttons, chosen) { buttons.forEach(function (b) { b.setAttribute("aria-pressed", b === chosen ? "true" : "false"); }); };
  var fix = function (v, d) { var s = v.toFixed(d); return parseFloat(s) === 0 ? (0).toFixed(d) : s; };
  var sgn = function (v, d) { var s = fix(v, d); return (parseFloat(s) > 0 ? "+" : "") + s; };
  var NS = "http://www.w3.org/2000/svg";
  var svgEl = function (name, attrs, text) {
    var n = document.createElementNS(NS, name), k;
    for (k in attrs) { if (attrs.hasOwnProperty(k)) { n.setAttribute(k, attrs[k]); } }
    if (text) { n.textContent = text; }
    return n;
  };

  var tip = document.createElement("div");
  tip.className = "chart-tip";
  tip.setAttribute("aria-hidden", "true");
  tip.hidden = true;
  document.body.appendChild(tip);

  /* A. Line charts: partner rates and spreads. */
  all("figure.pchart").forEach(function (fig) {
    var data = JSON.parse(fig.querySelector(".pdata").textContent), g = data.geom;
    var W = g[0], H = g[1], L = g[2], R = g[3], T = g[4], B = g[5];
    var svg = fig.querySelector("svg"), ticks = svg.querySelector(".pticks"), cursor = svg.querySelector(".pcursor");
    var zero = svg.querySelector(".pzero"), plot = fig.querySelector(".pplot"), read = fig.querySelector(".pread");
    var keys = Object.keys(data.labels), on = {}, mode = "nominal", range = "all", view = null, at = -1;
    keys.forEach(function (k) { on[k] = true; });
    all(".chart-tools", fig).forEach(function (n) { n.hidden = false; });
    var seriesButtons = all("[data-series]", fig), modeButtons = all("[data-mode]", fig), rangeButtons = all("[data-range]", fig);

    var draw = function () {
      var s = data.modes[mode], n = data.months.length, start = range === "5y" ? Math.max(0, n - 60) : range === "2y" ? Math.max(0, n - 24) : 0;
      var lo = Infinity, hi = -Infinity, i, v;
      keys.forEach(function (k) {
        if (!on[k] || !s[k]) { return; }
        for (i = start; i < n; i++) { v = s[k][i]; if (v !== null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }
      });
      if (data.zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
      if (lo === Infinity) { lo = 0; hi = 1; }
      var pad = (hi - lo) * 0.06 || 1;
      lo -= pad; hi += pad;
      var span = Math.max(n - 1 - start, 1);
      var x = function (j) { return L + (W - L - R) * (j - start) / span; };
      var y = function (val) { return T + (H - T - B) * (hi - val) / (hi - lo); };
      keys.forEach(function (k) {
        var path = svg.querySelector(".ps-" + k), d = [], pen = "M", j;
        if (!path) { return; }
        if (on[k] && s[k]) {
          for (j = start; j < n; j++) {
            if (s[k][j] === null) { pen = "M"; continue; }
            d.push(pen + x(j).toFixed(1) + "," + y(s[k][j]).toFixed(1));
            pen = "L";
          }
        }
        path.setAttribute("d", d.join(" "));
      });
      while (ticks.firstChild) { ticks.removeChild(ticks.firstChild); }
      var steps = [0.5, 1, 2, 5, 10, 20], step = steps[steps.length - 1];
      for (i = 0; i < steps.length; i++) { if ((hi - lo) / steps[i] <= 6) { step = steps[i]; break; } }
      for (v = Math.floor(lo / step + 1) * step; v < hi; v += step) {
        ticks.appendChild(svgEl("line", {x1: L, y1: y(v).toFixed(1), x2: W - R, y2: y(v).toFixed(1), "class": "pgrid"}));
        ticks.appendChild(svgEl("text", {x: L - 4, y: (y(v) + 4).toFixed(1), "text-anchor": "end"}, fix(v, v === Math.round(v) ? 0 : 1) + data.unit));
      }
      var every = range === "all" ? 2 : 1;
      for (i = start; i < n; i++) {
        var m = data.months[i];
        if (m.slice(5) === "01" && parseInt(m.slice(0, 4), 10) % every === (every === 2 ? 1 : 0)) {
          ticks.appendChild(svgEl("text", {x: x(i).toFixed(1), y: H - 10, "text-anchor": "middle"}, m.slice(0, 4)));
        }
      }
      if (zero) { zero.setAttribute("y1", y(0).toFixed(1)); zero.setAttribute("y2", y(0).toFixed(1)); }
      view = {start: start, n: n, x: x, span: span};
      if (at >= 0) { show(Math.max(start, Math.min(n - 1, at)), null); }
    };

    var show = function (i, event) {
      at = i;
      var s = data.modes[mode], parts = [], k;
      for (var q = 0; q < keys.length; q++) {
        k = keys[q];
        if (on[k] && s[k] && s[k][i] !== null) { parts.push(data.labels[k] + " " + fix(s[k][i], 2) + data.unit); }
      }
      var text = data.months[i] + " (" + mode + "): " + (parts.length ? parts.join("; ") : "no stored value for the series shown");
      read.textContent = text;
      cursor.setAttribute("x1", view.x(i).toFixed(1));
      cursor.setAttribute("x2", view.x(i).toFixed(1));
      cursor.setAttribute("visibility", "visible");
      if (event) {
        tip.textContent = text;
        tip.hidden = false;
        var vw = document.documentElement.clientWidth;
        tip.style.left = Math.max(8, Math.min(event.clientX + 12, vw - tip.offsetWidth - 8)) + "px";
        tip.style.top = Math.max(8, event.clientY - tip.offsetHeight - 12) + "px";
      }
    };
    var indexAt = function (clientX) {
      var r = svg.getBoundingClientRect(), sx = (clientX - r.left) * W / r.width;
      return Math.max(view.start, Math.min(view.n - 1, Math.round(view.start + (sx - L) / (W - L - R) * view.span)));
    };
    plot.addEventListener("mousemove", function (e) { show(indexAt(e.clientX), e); });
    plot.addEventListener("mouseleave", function () { tip.hidden = true; });
    plot.addEventListener("touchstart", function (e) { if (e.touches[0]) { show(indexAt(e.touches[0].clientX), e.touches[0]); } }, {passive: true});
    plot.addEventListener("touchmove", function (e) { if (e.touches[0]) { show(indexAt(e.touches[0].clientX), e.touches[0]); } }, {passive: true});
    plot.addEventListener("touchend", function () { tip.hidden = true; });
    plot.addEventListener("blur", function () { tip.hidden = true; });
    plot.addEventListener("keydown", function (e) {
      var i = at < 0 ? view.n - 1 : at, moves = {ArrowLeft: -1, ArrowRight: 1, PageUp: -12, PageDown: 12};
      if (moves.hasOwnProperty(e.key)) { i += moves[e.key]; } else if (e.key === "Home") { i = view.start; } else if (e.key === "End") { i = view.n - 1; } else { return; }
      e.preventDefault();
      show(Math.max(view.start, Math.min(view.n - 1, i)), null);
    });

    var syncSeries = function () {
      seriesButtons.forEach(function (b) {
        var k = b.getAttribute("data-series"), has = !!data.modes[mode][k];
        b.disabled = !has;
        b.setAttribute("aria-pressed", has && on[k] ? "true" : "false");
        b.title = has ? "" : "Nominal only: no euro-area inflation is stored";
      });
    };
    seriesButtons.forEach(function (b) {
      b.addEventListener("click", function () { var k = b.getAttribute("data-series"); on[k] = !on[k]; syncSeries(); draw(); });
    });
    modeButtons.forEach(function (b) {
      b.addEventListener("click", function () { mode = b.getAttribute("data-mode"); press(modeButtons, b); syncSeries(); draw(); });
    });
    rangeButtons.forEach(function (b) {
      b.addEventListener("click", function () { range = b.getAttribute("data-range"); press(rangeButtons, b); draw(); });
    });
    syncSeries();
    draw();
  });

  /* B. Move one partner rate: shows one of the stored what-if rows (exploratory, not used for the forecast). */
  var wi = byId("wi-picker");
  if (wi) {
    wi.hidden = false;
    var choice = {partner: null, variant: null, move: null};
    var groups = {partner: all("[data-partner]", wi).filter(function (b) { return b.tagName === "BUTTON"; }),
                  variant: all("button[data-variant]", wi), move: all("button[data-move]", wi)};
    var pickRow = function () {
      all(".wi-readout", wi).forEach(function (r) {
        var keep = r.getAttribute("data-partner") === choice.partner && r.getAttribute("data-variant") === choice.variant &&
          r.getAttribute("data-move") === choice.move;
        r.style.display = keep ? "" : "none";
      });
    };
    Object.keys(groups).forEach(function (name) {
      groups[name].forEach(function (b) {
        b.addEventListener("click", function () { choice[name] = b.getAttribute("data-" + name); press(groups[name], b); pickRow(); });
      });
      if (groups[name].length) { choice[name] = groups[name][0].getAttribute("data-" + name); }
    });
    pickRow();
  }

  /* C. Event tables: one partner at a time with JavaScript; all three without it. */
  var ev = byId("ev-picker");
  if (ev) {
    ev.hidden = false;
    var evButtons = all("button[data-partner]", ev);
    var pickPartner = function (b) {
      press(evButtons, b);
      all(".ev-partner").forEach(function (t) { t.style.display = t.getAttribute("data-partner") === b.getAttribute("data-partner") ? "" : "none"; });
    };
    evButtons.forEach(function (b) { b.addEventListener("click", function () { pickPartner(b); }); });
    if (evButtons.length) { pickPartner(evButtons[0]); }
  }

  /* D. ECB slider: drives only the readout "NBK base rate minus ECB deposit rate" (nominal), not the corridor band. */
  var ecb = byId("c-ecb"), rate = byId("c-rate"), ecbOut = byId("ecb-out");
  if (ecb && rate && ecbOut) {
    ecb.value = ecb.defaultValue;
    var ecbRead = function () {
      var e = parseFloat(ecb.value), r = parseFloat(rate.value);
      if (byId("o-ecb")) { byId("o-ecb").textContent = fix(e, 2); }
      ecbOut.textContent = "NBK base rate minus ECB deposit rate, nominal, not part of the corridor definition: " + fix(r, 2) +
        " − " + fix(e, 2) + " = " + sgn(r - e, 2) + " pp (your slider values).";
    };
    ecb.addEventListener("input", ecbRead);
    rate.addEventListener("input", ecbRead);
    ecbRead();
  }
}());
