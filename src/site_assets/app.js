/* Sliders and rounds of the site. The formulas are those of src/app.py (ordered_probabilities, score_gradient,
   score_and_delta_band) and src/decision_rule.py::binary_threshold. ES3, so that the pure functions before the first
   immediately invoked block can be checked against Python in cscript (tests/test_site.py). */
function threshold(ratio) { return 1 / (1 + ratio); }
function logistic(v) { if (v >= 0) { return 1 / (1 + Math.exp(-v)); } var e = Math.exp(v); return e / (1 + e); }
function density(v) { var c = Math.max(-700, Math.min(700, v)); var p = 1 / (1 + Math.exp(-c)); return p * (1 - p); }
function linearIndex(m, x) { var eta = 0, i; for (i = 0; i < m.slopes.length; i++) { eta += m.slopes[i] * x[i]; } return eta; }
function orderedProbabilities(m, x) {
  var eta = linearIndex(m, x), pDecrease = logistic(m.cutpoints[0] - eta), pAtMostHold = logistic(m.cutpoints[1] - eta);
  return {Decrease: pDecrease, Hold: pAtMostHold - pDecrease, Increase: 1 - pAtMostHold};
}
function scoreBand(m, x) {
  var p = orderedProbabilities(m, x), eta = linearIndex(m, x), i, j, name, g = [], v = 0;
  var f0 = density(m.cutpoints[0] - eta), f1 = density(m.cutpoints[1] - eta);
  for (i = 0; i < m.names.length; i++) {
    name = m.names[i]; g[i] = 0;
    if (name === "cutpoint[Decrease|Hold]") { g[i] = -f0; }
    else if (name === "cutpoint[Hold|Increase]") { g[i] = -f1; }
    else { for (j = 0; j < m.features.length; j++) { if (m.features[j] === name) { g[i] = (f0 + f1) * x[j]; } } }
  }
  for (i = 0; i < g.length; i++) { for (j = 0; j < g.length; j++) { v += g[i] * m.covariance[i][j] * g[j]; } }
  var score = p.Increase - p.Decrease, se = Math.sqrt(Math.max(v, 0));
  return [score, score - m.z * se, score + m.z * se];
}
/* Round first, then sign: a value that rounds to zero is "0.000", never "-0.000" or "+0.000" (D42). */
function fixed(v, digits) { var s = v.toFixed(digits); return parseFloat(s) === 0 ? (0).toFixed(digits) : s; }
function signed(v, digits) { var s = fixed(v, digits); return (parseFloat(s) > 0 ? "+" : "") + s; }
function pct1(v) { return (v * 100).toFixed(1) + "%"; }
var WEEKDAYS = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"];
var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
function pad2(n) { return (n < 10 ? "0" : "") + n; }
function parseIso(s) { var p = s.split("-"); return new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10)); }
function longDate(s) {
  if (!s) { return "DATE NOT CONFIRMED"; }
  var d = parseIso(s);
  return WEEKDAYS[d.getDay()] + ", " + d.getDate() + " " + MONTHS[d.getMonth()].toUpperCase() + " " + d.getFullYear();
}
function shortDate(s) { if (!s) { return "date not confirmed"; } var d = parseIso(s); return d.getDate() + " " + MONTHS[d.getMonth()] + " " + d.getFullYear(); }
/* As app.load_next_decisions: up to two confirmed dates strictly after today. */
function nextRounds(dates, today, verified) {
  var out = [], i;
  if (verified) { for (i = 0; i < dates.length; i++) { if (dates[i] > today && out.length < 2) { out.push(dates[i]); } } }
  while (out.length < 2) { out.push(null); }
  return out;
}
/* As app.passed_rounds_missing_from_data: meetings after the latest decision in the data that have already taken place. */
function missedRounds(dates, latest, today) {
  var out = [], i;
  for (i = 0; i < dates.length; i++) { if (dates[i] > latest && dates[i] < today) { out.push(dates[i]); } }
  return out;
}
/* Date slider under the track-record chart (D54): reads stored numbers only, computes nothing new. */
function trackReadout(t, i) {
  var a = t.actual[i];
  return {date: t.dates[i], score: signed(t.score[i], 3), decision: a > 0 ? "hike" : (a < 0 ? "cut" : "hold"),
    sample: t.dates[i] >= t.holdout_start ? "holdout (out of sample)" : "in-sample fit",
    stored: !!(t.stored && t.stored.date === t.dates[i])};
}
function trackValueText(t, i) {
  var r = trackReadout(t, i);
  return shortDate(r.date) + ": score " + r.score + ", NBK decision " + r.decision + ", " + r.sample;
}
/* One row of a per-page source index (site_build.write_source_index): field name -> text. */
function sourceRow(index, id) {
  var refs = index.ids[id], row = {}, i;
  if (!refs) { return null; }
  for (i = 0; i < index.fields.length; i++) { row[index.fields[i]] = index.strings[refs[i]]; }
  return row;
}

(function () {
  var byId = function (id) { return document.getElementById(id); };
  var ratio = byId("ratio");
  if (ratio) {
    var pcut = parseFloat(ratio.getAttribute("data-pcut"));
    var update = function () {
      var r = parseFloat(ratio.value), p = threshold(r);
      byId("ratio-out").textContent = r.toFixed(2);
      byId("ratio-text").textContent = "Threshold p* = " + p.toFixed(3) + "; P(cut) = " + pcut.toFixed(3) +
        " → " + (pcut > p ? "extend duration" : "do not extend duration") + ".";
    };
    ratio.addEventListener("input", update); update();
  }

  var cards = byId("round-cards");
  if (cards) {
    var d = new Date(), today = d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
    var dates = JSON.parse(cards.getAttribute("data-rounds")), latest = cards.getAttribute("data-latest");
    var verified = cards.getAttribute("data-verified") === "true";
    var rounds = nextRounds(dates, today, verified), heads = cards.querySelectorAll(".forecast-date"), k;
    for (k = 0; k < heads.length; k++) { heads[k].textContent = longDate(rounds[k]); }
    if (byId("next-decision")) { byId("next-decision").textContent = shortDate(rounds[0]); }
    byId("rounds-message").textContent = !verified ? "Decision dates are not marked as verified in the calendar." :
      (rounds[1] ? "" : "Fewer than two confirmed future decision dates are available.");
    var missed = missedRounds(dates, latest, today), box = byId("freshness");
    if (box && missed.length) {
      box.textContent = "Data are out of date: the NBK meeting(s) of " + missed.join(", ") + " already took place, but the data end at " +
        "the decision of " + latest + ". The forecast cards are therefore not for the next meeting after the latest outcome. Add the new " +
        "decision and factor months to data/raw/ and run `python run.py all`.";
      box.hidden = false;
    }
  }

  var modelNode = byId("model-json");
  if (modelNode) {
    var m = JSON.parse(modelNode.textContent), factor = byId("sc-factor"), slider = byId("sc-value");
    var base = orderedProbabilities(m, m.latest), baseScore = base.Increase - base.Decrease, classes = ["Increase", "Hold", "Decrease"];
    var redraw = function () {
      var i = parseInt(factor.value, 10), x = m.latest.slice(0), value = parseFloat(slider.value);
      x[i] = value;
      var p = orderedProbabilities(m, x), band = scoreBand(m, x), c;
      byId("sc-out").textContent = fixed(value, 2);
      byId("sc-score").textContent = signed(band[0], 3);
      byId("sc-delta").textContent = signed(band[0] - baseScore, 3) + " vs latest";
      byId("sc-band").textContent = "95% delta-method band: [" + signed(Math.max(-1, band[1]), 3) + ", " + signed(Math.min(1, band[2]), 3) + "]";
      for (c = 0; c < classes.length; c++) {
        byId("sc-p-" + classes[c]).textContent = pct1(p[classes[c]]);
        byId("sc-d-" + classes[c]).textContent = signed((p[classes[c]] - base[classes[c]]) * 100, 1) + " pp";
      }
    };
    var choose = function () {
      var s = m.slider[parseInt(factor.value, 10)];
      slider.min = s.min; slider.max = s.max; slider.value = s.baseline;  // as in Render: a newly chosen factor starts at its latest value
      byId("sc-name").textContent = m.labels[parseInt(factor.value, 10)];
      byId("sc-min").textContent = fixed(s.min, 2); byId("sc-max").textContent = fixed(s.max, 2);
      redraw();
    };
    factor.addEventListener("change", choose); slider.addEventListener("input", redraw); choose();
  }

  var tabs = document.querySelectorAll(".design-tab");
  if (tabs.length) {
    var panels = document.querySelectorAll(".design-panel");
    var pick = function (key) {
      var j;
      for (j = 0; j < tabs.length; j++) { tabs[j].setAttribute("aria-pressed", tabs[j].getAttribute("data-design") === key ? "true" : "false"); }
      for (j = 0; j < panels.length; j++) { panels[j].hidden = panels[j].getAttribute("data-design") !== key; }
    };
    for (var t = 0; t < tabs.length; t++) { tabs[t].addEventListener("click", function () { pick(this.getAttribute("data-design")); }); }
    pick(tabs[0].getAttribute("data-design"));
  }

  var form = byId("corridor");
  if (form && typeof corridor === "function") {
    var ids = ["rate", "ru", "cn", "prem", "cap"].concat(byId("c-infl") ? ["infl"] : []), partnerData = form.getAttribute("data-partner-data") === "true";
    var missingPartners = form.getAttribute("data-missing") || "";
    var redrawCorridor = function () {
      var v = {}, i;
      for (i = 0; i < ids.length; i++) { v[ids[i]] = parseFloat(byId("c-" + ids[i]).value);
        byId("o-" + ids[i]).textContent = fixed(v[ids[i]], 2); }
      var credit = JSON.parse(form.getAttribute("data-credit"));
      var res = corridor(v.rate, v.infl === undefined ? parseFloat(form.getAttribute("data-inflation")) : v.infl, {"Russia": v.ru, "China": v.cn}, v.prem, v.cap, credit);
      /* D59: how far the rate is from the bound it crosses (or from the lower bound when inside). */
      var gap = res.code === 1 ? "; " + fixed(res.lower - v.rate, 2) + " pp below the lower bound" : res.code === 2 ? "; " +
        fixed(v.rate - res.upper, 2) + " pp above the upper bound" : res.code === 3 ? "; " + fixed(v.rate - res.lower, 2) + " pp above the lower bound" : "";
      var bounds = "Corridor: " + fixed(res.lower, 2) + "–" + fixed(res.upper, 2) + "%";
      /* Without partner data the verdict would rest on assumed partner rates: only the bounds are shown (D42). */
      byId("corridor-out").textContent = !partnerData ? bounds + ". Illustration with your assumptions; no partner data" +
        (missingPartners ? " for " + missingPartners : "") + "." :
        bounds + "; real differential to Russia " + fixed(res.differentials["Russia"], 2) + " pp, to China " +
        fixed(res.differentials["China"], 2) + " pp; " + res.label + gap + ".";
    };
    for (var n = 0; n < ids.length; n++) {
      var input = byId("c-" + ids[n]);
      input.value = input.defaultValue;  /* start from the values in the page (current NBK rate), not a value the browser restored */
      input.addEventListener("input", redrawCorridor);
    }
    redrawCorridor();
  }

  var select = byId("asof-t");
  if (select) {
    var show = function () {
      var blocks = document.querySelectorAll(".asof");
      for (var j = 0; j < blocks.length; j++) { blocks[j].hidden = blocks[j].getAttribute("data-t") !== select.value; }
    };
    select.addEventListener("change", show); select.value = select.options[select.options.length - 1].value; show();
  }

  /* Clickable numbers (D54): each data-ledger number opens its evidence-ledger row. The per-page index
     (data/sources-<page>.json) is fetched on the first click only; opened from a file, the window shows the id, the
     value on the page and the link to the CSV. */
  if (typeof document.addEventListener !== "function" || typeof document.querySelector !== "function") { return; }
  var el = function (tag, text, cls) {
    var node = document.createElement(tag);
    if (text) { node.textContent = text; }
    if (cls) { node.className = cls; }
    return node;
  };
  var current = document.querySelector('nav a[aria-current="page"]');
  var indexUrl = "data/sources-" + (current ? current.getAttribute("href") : "index.html").replace(/\.html$/, "") + ".json";
  var csvUrl = "data/evidence_ledger.csv", sourceIndex = null, loading = null, pop = null, opener = null;
  var clickable = function (root) {
    var nums = (root || document).querySelectorAll("[data-ledger]"), i;
    for (i = 0; i < nums.length; i++) {
      /* chart marks (SVG) open the window by click; keyboard users reach the same numbers in the tables and readouts */
      if (!nums[i].ownerSVGElement && (" " + nums[i].className + " ").indexOf(" src-link ") < 0) {
        nums[i].className += " src-link";
        nums[i].setAttribute("tabindex", "0");
        nums[i].setAttribute("role", "button");
        nums[i].setAttribute("aria-haspopup", "dialog");
        nums[i].setAttribute("title", "Show source");
      }
    }
  };
  var loadIndex = function (done) {
    if (sourceIndex) { done(sourceIndex); return; }
    if (!window.fetch || location.protocol === "file:") {
      done(null, "Source details need the page to be opened over http(s); from a file only the id and the value are shown.");
      return;
    }
    if (!loading) {
      loading = fetch(indexUrl).then(function (r) { if (!r.ok) { throw new Error("HTTP " + r.status); } return r.json(); });
    }
    loading.then(function (data) { sourceIndex = data; done(data); },
      function (e) { loading = null; done(null, "Source details could not be loaded (" + e.message + "). The CSV below has every row."); });
  };
  var closePop = function () {
    if (pop && !pop.hidden) { pop.hidden = true; if (opener) { opener.focus(); } opener = null; }
  };
  var place = function (target) {
    var r = target.getBoundingClientRect(), vw = document.documentElement.clientWidth, vh = window.innerHeight;
    var left = Math.max(8, Math.min(r.left, vw - pop.offsetWidth - 8)), top = r.bottom + 6;
    if (top + pop.offsetHeight > vh - 8) { top = Math.max(8, r.top - pop.offsetHeight - 6); }
    pop.style.left = left + "px";
    pop.style.top = top + "px";
  };
  var openPop = function (target) {
    var id = target.getAttribute("data-ledger");
    if (!pop) {
      pop = el("div", "", "src-pop");
      pop.id = "src-pop";
      pop.setAttribute("role", "dialog");
      pop.setAttribute("aria-labelledby", "src-pop-title");
      pop.hidden = true;
      document.body.appendChild(pop);
      document.addEventListener("keydown", function (e) { if (e.key === "Escape" || e.keyCode === 27) { closePop(); } });
      document.addEventListener("mousedown", function (e) {
        var onNumber = e.target.closest && e.target.closest("[data-ledger]");
        if (!pop.hidden && !pop.contains(e.target) && !onNumber) { closePop(); }
      });
    }
    opener = target;
    pop.innerHTML = "";
    var head = el("div", "", "src-head"), title = el("p", "Source of this number", "src-title"), close = el("button", "Close", "src-close");
    title.id = "src-pop-title";
    close.type = "button";
    close.setAttribute("aria-label", "Close the source window");
    close.addEventListener("click", closePop);
    head.appendChild(title);
    head.appendChild(close);
    var list = el("dl"), note = el("p", "Loading the source details ...", "caption");
    var add = function (label, value) { list.appendChild(el("dt", label)); list.appendChild(el("dd", value)); };
    add("Ledger id", id);
    add("Shown on the page", target.getAttribute("data-shown") || target.textContent);
    var link = el("a", "Download the full evidence ledger (CSV)");
    link.href = csvUrl;
    link.setAttribute("download", "");
    pop.appendChild(head);
    pop.appendChild(list);
    pop.appendChild(note);
    pop.appendChild(link);
    pop.hidden = false;
    place(target);
    close.focus();
    loadIndex(function (data, problem) {
      if (opener !== target) { return; }
      var row = data ? sourceRow(data, id) : null, labels, k;
      if (!row) {
        note.textContent = problem || "This id is not in the source index of this page; the CSV below has every row.";
      } else {
        note.parentNode.removeChild(note);
        labels = {value: "Value", source: "Source", retrieved: "Retrieved", transformation: "Transformation", script: "Script", used_in: "Used in"};
        for (k = 0; k < data.fields.length; k++) { add(labels[data.fields[k]] || data.fields[k], row[data.fields[k]]); }
        add("Trace it", "python run.py trace " + id);
      }
      place(target);
    });
  };
  clickable();
  document.addEventListener("click", function (e) {
    var target = e.target.closest ? e.target.closest("[data-ledger]") : null;
    if (!target) { return; }
    e.preventDefault();
    if (pop && !pop.hidden && opener === target) { closePop(); } else { openPop(target); }
  });
  document.addEventListener("keydown", function (e) {
    var t = e.target;
    if (t && t.getAttribute && t.getAttribute("data-ledger") && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openPop(t); }
  });

  var reduced = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var press = function (buttons, chosen) { for (var j = 0; j < buttons.length; j++) { buttons[j].setAttribute("aria-pressed", buttons[j] === chosen ? "true" : "false"); } };
  var all = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var unhide = function (sel, root) { all(sel, root).forEach(function (n) { n.hidden = false; }); };

  /* Shared tooltip for chart bars and probability rows (D56): text from the element's data-tip, i.e. values already shown. */
  var tip = el("div", "", "chart-tip");
  tip.setAttribute("aria-hidden", "true");
  tip.hidden = true;
  document.body.appendChild(tip);
  var showTip = function (text, x, y) {
    tip.textContent = text;
    tip.hidden = false;
    var vw = document.documentElement.clientWidth;
    tip.style.left = Math.max(8, Math.min(x + 12, vw - tip.offsetWidth - 8)) + "px";
    tip.style.top = Math.max(8, y - tip.offsetHeight - 10) + "px";
  };
  var hideTip = function () { tip.hidden = true; };
  var tipFor = function (e) {
    var t = e.target.closest ? e.target.closest("[data-tip]") : null;
    if (!t) { return; }
    var r = t.getBoundingClientRect();
    showTip(t.getAttribute("data-tip"), e.clientX || r.left, e.clientY || r.top);
  };
  document.addEventListener("mouseover", tipFor);
  document.addEventListener("focusin", tipFor);
  document.addEventListener("mouseout", function (e) { if (e.target.closest && e.target.closest("[data-tip]")) { hideTip(); } });
  document.addEventListener("focusout", hideTip);

  /* A. Track record of the score (D54 slider, D56 chart): the chart is redrawn from the stored series in the page. */
  var trackBox = byId("track-slider");
  if (trackBox) {
    var pos = byId("tr-pos"), outBox = byId("tr-out"), tdata = null, fig = byId("track-record"), svg = fig ? fig.querySelector("svg") : null;
    try { tdata = JSON.parse(byId("track-json").textContent); } catch (err) { tdata = null; }
    trackBox.hidden = false;
    if (!tdata || !svg) {
      pos.disabled = true;
      outBox.textContent = "The date slider could not read its data; the chart above shows every decision.";
    } else {
      var NS = "http://www.w3.org/2000/svg", C = tdata.colors, W = 640, H = 300, LEFT = 44, RIGHT = 10, TOP = 14, BOTTOM = 34;
      var NAMES = {"-1": "Decrease", "0": "Hold", "1": "Increase"}, range = "all", firstDraw = true, xOf = null, shown = [];
      var dayOf = function (s) { var q = s.split("-"); return Date.UTC(+q[0], +q[1] - 1, +q[2]) / 864e5; };
      var days = tdata.dates.map(dayOf);
      var yOf = function (v) { return TOP + (H - TOP - BOTTOM) * (1.05 - v) / 2.1; };
      var mk = function (tag, attrs, text) {
        var node = document.createElementNS(NS, tag), k;
        for (k in attrs) { if (attrs.hasOwnProperty(k)) { node.setAttribute(k, attrs[k]); } }
        if (text) { node.textContent = text; }
        return node;
      };
      var num = function (id, text) { var s = el("span", text, "num"); s.setAttribute("data-ledger", id); return s; };
      var line = function (label, parts) {
        var p = el("p"), j;
        p.appendChild(el("strong", label + ": "));
        for (j = 0; j < parts.length; j++) { p.appendChild(typeof parts[j] === "string" ? document.createTextNode(parts[j]) : parts[j]); }
        outBox.appendChild(p);
      };
      var showTrack = function () {
        var i = parseInt(pos.value, 10), r = trackReadout(tdata, i), s = tdata.stored, cursor = byId("tr-cursor");
        var dot = svg.querySelector('.tr-dot[data-i="' + i + '"]');
        if (cursor) {
          cursor.setAttribute("visibility", dot ? "visible" : "hidden");
          if (dot) { cursor.setAttribute("x1", dot.getAttribute("cx")); cursor.setAttribute("x2", dot.getAttribute("cx")); }
        }
        pos.setAttribute("aria-valuetext", trackValueText(tdata, i));
        outBox.innerHTML = "";
        line("Decision", [shortDate(r.date)]);
        line("Score", [num("dashboard:track_record/score/" + i, r.score)]);
        line("The NBK decided", [r.decision]);
        line("Sample", [r.sample]);
        if (r.stored) {
          line("Model probabilities", ["cut ", num("dashboard:probabilities/Decrease", pct1(s.p.Decrease)), ", hold ",
            num("dashboard:probabilities/Hold", pct1(s.p.Hold)), ", hike ", num("dashboard:probabilities/Increase", pct1(s.p.Increase))]);
          line("95% band of the score", [num("dashboard:band/0", signed(s.band[0], 3)), " to ", num("dashboard:band/1", signed(s.band[1], 3))]);
        } else {
          line("Model probabilities and 95% band", ["not stored for this date"]);
        }
        clickable(outBox);
      };
      var drawTrack = function () {
        var last = tdata.dates[tdata.dates.length - 1].split("-"), back = range === "3y" ? 3 : (range === "12m" ? 1 : null);
        var from = back === null ? -Infinity : Date.UTC(+last[0] - back, +last[1] - 1, +last[2]) / 864e5, i, k, v;
        shown = [];
        for (i = 0; i < days.length; i++) { if (days[i] >= from) { shown.push(i); } }
        var x0 = days[shown[0]], x1 = Math.max(days[shown[shown.length - 1]], x0 + 1);
        xOf = function (d) { return LEFT + (W - LEFT - RIGHT) * (d - x0) / (x1 - x0); };
        all("svg > :not(title)", fig).forEach(function (n) { n.parentNode.removeChild(n); });
        var g = mk("g", {"class": "tr-plot"}), hs = Math.max(dayOf(tdata.holdout_start), x0);
        if (hs <= x1) { g.appendChild(mk("rect", {x: xOf(hs), y: TOP, width: xOf(x1) - xOf(hs), height: H - TOP - BOTTOM, fill: C.shade})); }
        g.appendChild(mk("line", {x1: LEFT, y1: yOf(0), x2: W - RIGHT, y2: yOf(0), stroke: C.axis, "stroke-dasharray": "4 4"}));
        g.appendChild(mk("line", {x1: LEFT, y1: TOP, x2: LEFT, y2: H - BOTTOM, stroke: C.axis}));
        for (v = -1; v <= 1; v += 0.5) { g.appendChild(mk("text", {x: LEFT - 4, y: yOf(v) + 4, "text-anchor": "end", "font-size": 11, fill: C.label}, signed(v, 1))); }
        var y0 = new Date(x0 * 864e5).getUTCFullYear(), y1 = new Date(x1 * 864e5).getUTCFullYear(), years = [];
        for (k = y0 + 1; k <= y1; k++) { years.push(k); }
        if (years.length >= 2) {
          var step = years.length > 5 ? 2 : 1;
          for (k = step - 1; k < years.length; k += step) {
            g.appendChild(mk("text", {x: xOf(Date.UTC(years[k], 0, 1) / 864e5), y: H - 12, "text-anchor": "middle", "font-size": 11, fill: C.label}, String(years[k])));
          }
        } else {
          for (k = 0; k < 2; k++) {
            var d = tdata.dates[shown[k === 0 ? 0 : shown.length - 1]];
            g.appendChild(mk("text", {x: xOf(dayOf(d)), y: H - 12, "text-anchor": k === 0 ? "start" : "end", "font-size": 11, fill: C.label}, shortDate(d)));
          }
        }
        var path = shown.map(function (j, n) { return (n ? "L" : "M") + xOf(days[j]).toFixed(1) + "," + yOf(tdata.score[j]).toFixed(1); }).join(" ");
        var curve = mk("path", {d: path, fill: "none", stroke: C.line, "stroke-width": 2, "class": "tr-line"});
        g.appendChild(curve);
        shown.forEach(function (j) {
          var a = tdata.actual[j], cx = xOf(days[j]), cy = yOf(a), name = NAMES[String(a)];
          var shape = a === 1 ? mk("path", {d: "M" + cx + "," + (cy - 5) + " L" + (cx + 4.5) + "," + (cy + 3) + " L" + (cx - 4.5) + "," + (cy + 3) + " Z"}) :
            (a === -1 ? mk("path", {d: "M" + cx + "," + (cy + 5) + " L" + (cx + 4.5) + "," + (cy - 3) + " L" + (cx - 4.5) + "," + (cy - 3) + " Z"}) :
              mk("rect", {x: cx - 3, y: cy - 3, width: 6, height: 6}));
          shape.setAttribute("fill", C[name]);
          shape.setAttribute("class", "m-" + name);
          g.appendChild(shape);
        });
        shown.forEach(function (j) {
          g.appendChild(mk("circle", {cx: xOf(days[j]).toFixed(1), cy: yOf(tdata.score[j]).toFixed(1), r: 3.5, fill: C.line, "class": "tr-dot",
            "data-i": j, "data-ledger": "dashboard:track_record/score/" + j, "data-shown": signed(tdata.score[j], 3)}));
        });
        g.appendChild(mk("line", {id: "tr-hover", y1: TOP, y2: H - BOTTOM, stroke: C.axis, "stroke-width": 1, visibility: "hidden", "pointer-events": "none"}));
        g.appendChild(mk("line", {id: "tr-cursor", x1: 0, y1: TOP, x2: 0, y2: H - BOTTOM, stroke: C.ink, "stroke-width": 1.5, "stroke-dasharray": "3 3", visibility: "hidden", "pointer-events": "none"}));
        svg.appendChild(g);
        // D57: no draw-in of the line on first view; a redraw after a range change fades in over 120 ms (CSS .tr-plot).
        if (!reduced && !firstDraw) {
          g.style.opacity = "0";
          window.requestAnimationFrame(function () { g.style.opacity = "1"; });
        }
        firstDraw = false;
        showTrack();
      };
      all("[data-range]", trackBox).forEach(function (b, n, list) {
        b.addEventListener("click", function () { range = b.getAttribute("data-range"); press(list, b); drawTrack(); });
      });
      all("[data-class]", trackBox).forEach(function (b) {
        b.addEventListener("click", function () {
          var on = b.getAttribute("aria-pressed") !== "true";
          b.setAttribute("aria-pressed", on ? "true" : "false");
          svg.classList.toggle("hide-" + b.getAttribute("data-class"), !on);
        });
      });
      fig.style.position = "relative";
      svg.style.touchAction = "pan-y";
      var hover = function (e) {
        if (!xOf || !svg.getScreenCTM()) { return; }
        var pt = svg.createSVGPoint(), best = null, gap = Infinity;
        pt.x = e.clientX; pt.y = e.clientY;
        var sx = pt.matrixTransform(svg.getScreenCTM().inverse()).x;
        shown.forEach(function (j) { var dd = Math.abs(xOf(days[j]) - sx); if (dd < gap) { gap = dd; best = j; } });
        if (best === null) { return; }
        var hl = byId("tr-hover"), r = trackReadout(tdata, best);
        hl.setAttribute("x1", xOf(days[best])); hl.setAttribute("x2", xOf(days[best])); hl.setAttribute("visibility", "visible");
        showTip(shortDate(r.date) + ": score " + r.score + "; the NBK decided: " + r.decision, e.clientX, e.clientY);
      };
      svg.addEventListener("pointermove", hover);
      svg.addEventListener("pointerdown", hover);
      svg.addEventListener("pointerleave", function () { var hl = byId("tr-hover"); if (hl) { hl.setAttribute("visibility", "hidden"); } hideTip(); });
      pos.addEventListener("input", showTrack);
      drawTrack();
    }
  }

  /* B. Probability bars of the next decisions (D56): overlay of round 2 on round 1 (D57: the bars no longer grow into view). */
  var roundBox = byId("round-cards");
  if (roundBox) {
    var fills = all(".probability-fill", roundBox);
    fills.forEach(function (f) { f.setAttribute("data-w", f.style.width); });
    all(".probability-row", roundBox).forEach(function (row) {
      var label = row.querySelector(".probability-label"), value = row.querySelector(".probability-value"), ci = row.querySelector(".probability-interval");
      row.setAttribute("data-tip", (label ? label.textContent.replace(/^\W+/, "") : "") + ": " + (value ? value.textContent : "") + (ci ? " (" + ci.textContent + ")" : ""));
    });
    var layout = byId("round-layout");
    if (layout && byId("round-2")) {
      layout.hidden = false;
      var layoutButtons = all("button", layout), note = el("p", "Overlay: filled bars are round 1, outlined bars are round 2.", "caption");
      note.hidden = true;
      layout.appendChild(note);
      layoutButtons.forEach(function (b) {
        b.addEventListener("click", function () {
          var overlay = b.getAttribute("data-layout") === "overlay";
          press(layoutButtons, b);
          if (overlay && !roundBox.querySelector(".probability-ghost")) {
            var second = all("#round-2 .probability-fill", roundBox);
            all("#round-1 .probability-track", roundBox).forEach(function (track, k) {
              var ghost = el("span", "", "probability-ghost");
              ghost.style.width = second[k] ? second[k].getAttribute("data-w") : "0%";
              track.appendChild(ghost);
            });
          }
          roundBox.classList.toggle("overlay", overlay);
          note.hidden = !overlay;
        });
      });
    }
  }

  /* C1. Factor effects: sort by model order, size or name (D56). */
  var fx = byId("fx-chart");
  if (fx) {
    unhide(".chart-tools", fx);
    var fxRows = all(".fx-row", fx), slots = fxRows.map(function (r) { return parseFloat(r.style.transform.split(",")[1]); }).sort(function (a, b) { return a - b; });
    var sortButtons = all("[data-sort]", fx);
    sortButtons.forEach(function (b) {
      b.addEventListener("click", function () {
        var key = b.getAttribute("data-sort"), order = fxRows.slice(0);
        order.sort(function (a, c) {
          if (key === "size") { return parseFloat(c.getAttribute("data-size")) - parseFloat(a.getAttribute("data-size")); }
          if (key === "name") { return a.getAttribute("data-name") < c.getAttribute("data-name") ? -1 : 1; }
          return parseInt(a.getAttribute("data-slot"), 10) - parseInt(c.getAttribute("data-slot"), 10);
        });
        order.forEach(function (r, k) { r.style.transform = "translate(0px," + slots[k] + "px)"; });
        press(sortButtons, b);
      });
    });
  }

  /* C2. Frozen model against one extended model (D56). */
  var ovb = byId("ovb-toggle");
  if (ovb) {
    unhide(".chart-tools", ovb);
    var specButtons = all("[data-spec]", ovb.querySelector(".chart-tools"));
    var pickSpec = function (spec) {
      all(".ovb-row, .ovb-readout", ovb).forEach(function (n) {
        var keep = n.getAttribute("data-spec") === "frozen" || n.getAttribute("data-spec") === spec;
        n.style.display = keep ? "" : "none";
      });
      press(specButtons, specButtons.filter(function (b) { return b.getAttribute("data-spec") === spec; })[0]);
    };
    specButtons.forEach(function (b) { b.addEventListener("click", function () { pickSpec(b.getAttribute("data-spec")); }); });
    if (specButtons.length) { pickSpec(specButtons[0].getAttribute("data-spec")); }
  }

  /* C3. Click panel with the RMSE ratio and the Diebold-Mariano test (D56). */
  var hpButton = byId("holdout-toggle"), hpPanel = byId("holdout-panel");
  if (hpButton && hpPanel) {
    hpButton.hidden = false;
    hpPanel.hidden = true;
    hpButton.setAttribute("aria-expanded", "false");
    hpButton.addEventListener("click", function () {
      var open = hpPanel.hidden;
      hpPanel.hidden = !open;
      hpButton.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* D. Corridor band over time: follows the premium and cap sliders; what-if arithmetic on stored series (D56). */
  var cbData = byId("cb-json"), band = byId("cb-band");
  if (cbData && band && byId("c-prem") && byId("c-cap")) {
    var cb = JSON.parse(cbData.textContent), gm = cb.geom, nb = cb.months.length;
    var bx = function (i) { return gm[2] + (gm[0] - gm[2] - gm[3]) * i / (nb - 1); };
    var by = function (v) { return gm[4] + (gm[1] - gm[4] - gm[5]) * (cb.hi - v) / (cb.hi - cb.lo); };
    var redrawBand = function () {
      var prem = parseFloat(byId("c-prem").value), cap = parseFloat(byId("c-cap").value), up = [], lowPts = [], below = 0, above = 0, i;
      for (i = 0; i < nb; i++) {
        up.push(bx(i).toFixed(1) + "," + by(cb.base[i] + cap).toFixed(1));
        lowPts.unshift(bx(i).toFixed(1) + "," + by(cb.base[i] + prem).toFixed(1));
        if (cb.rate[i] < cb.base[i] + prem) { below += 1; } else if (cb.rate[i] > cb.base[i] + cap) { above += 1; }
      }
      band.setAttribute("d", "M" + up.join(" L") + " L" + lowPts.join(" L") + " Z");
      var lastRate = cb.rate[nb - 1], side = lastRate < cb.base[nb - 1] + prem ? "below the band" : (lastRate > cb.base[nb - 1] + cap ? "above the band" : "inside the band");
      byId("cb-out").textContent = "What-if on stated assumptions, not a model estimate: with a premium of " + fixed(prem, 2) + " pp and a cap of " +
        fixed(cap, 2) + " pp (your assumptions), the NBK rate is below the band in " + below + " of " + nb + " months, inside in " +
        (nb - below - above) + " and above in " + above + "; in " + cb.months[nb - 1] + " it is " + side + ".";
    };
    byId("c-prem").addEventListener("input", redrawBand);
    byId("c-cap").addEventListener("input", redrawBand);
    redrawBand();
  }

  /* E. Sortable, filterable tables and the countdown to a pending decision (D56). */
  all("table.sortable").forEach(function (table) {
    var body = table.tBodies[0];
    all("thead th", table).forEach(function (th, col) {
      var b = el("button", th.textContent, "th-sort");
      b.type = "button";
      th.textContent = "";
      th.appendChild(b);
      th.setAttribute("aria-sort", "none");
      b.addEventListener("click", function () {
        var dir = th.getAttribute("aria-sort") === "ascending" ? -1 : 1, rows = all("tr", body);
        var key = function (r) { var s = r.cells[col] ? r.cells[col].textContent.trim() : ""; var f = parseFloat(s); return isNaN(f) || !/^[-+]?\d/.test(s) ? s.toLowerCase() : f; };
        rows.sort(function (a, c) { var x = key(a), y = key(c); return (x < y ? -1 : x > y ? 1 : 0) * dir; });
        rows.forEach(function (r) { body.appendChild(r); });
        all("thead th", table).forEach(function (h) { h.setAttribute("aria-sort", "none"); });
        th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
      });
    });
  });
  all("input[data-filter]").forEach(function (input) {
    input.parentNode.hidden = false;
    var table = byId(input.getAttribute("data-filter"));
    input.addEventListener("input", function () {
      var q = input.value.toLowerCase();
      all("tbody tr", table).forEach(function (r) { r.hidden = q !== "" && r.textContent.toLowerCase().indexOf(q) < 0; });
    });
  });
  all(".countdown[data-target]").forEach(function (span) {
    var now = new Date(), today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / 864e5;
    var q = span.getAttribute("data-target").split("-"), left = Date.UTC(+q[0], +q[1] - 1, +q[2]) / 864e5 - today;
    span.textContent += left > 0 ? "; " + left + (left === 1 ? " day" : " days") + " to go (counted in your browser)" :
      "; the date has passed and the outcome is not in the data yet";
  });

  /* F1, F4. Read-more cards: the first sentence stays, the rest opens on request (D56). */
  all("p.read-card").forEach(function (p, k) {
    var rest = p.querySelector(".card-rest");
    if (!rest) { return; }
    rest.id = rest.id || "card-rest-" + k;
    var b = el("button", "Read more", "read-more");
    b.type = "button";
    b.setAttribute("aria-expanded", "false");
    b.setAttribute("aria-controls", rest.id);
    rest.hidden = true;
    p.appendChild(b);
    b.addEventListener("click", function () {
      var open = rest.hidden;
      rest.hidden = !open;
      b.setAttribute("aria-expanded", open ? "true" : "false");
      b.textContent = open ? "Show less" : "Read more";
    });
  });

  /* F2. Pipeline: one stage open at a time (D56). */
  var nodes = all(".pipe-node");
  if (nodes.length) {
    var openStage = function (node) {
      nodes.forEach(function (b) {
        var on = b === node && b.getAttribute("aria-expanded") !== "true";
        b.setAttribute("aria-expanded", on ? "true" : "false");
        byId(b.getAttribute("aria-controls")).hidden = !on;
      });
    };
    nodes.forEach(function (b) { b.setAttribute("aria-expanded", "false"); byId(b.getAttribute("aria-controls")).hidden = true; });
    nodes.forEach(function (b) { b.addEventListener("click", function () { openStage(b); }); });
  }

  /* F6. Glossary tips stay on screen; Esc closes the one in focus (D56). */
  all(".gloss").forEach(function (g) {
    var place = function () {
      var t = g.querySelector(".gloss-tip"), vw = document.documentElement.clientWidth;
      g.classList.remove("gloss-closed");
      t.style.left = "0px";
      var r = t.getBoundingClientRect();
      if (r.right > vw - 8) { t.style.left = (vw - 8 - r.right) + "px"; }
    };
    g.addEventListener("mouseenter", place);
    g.addEventListener("focus", place);
    g.addEventListener("keydown", function (e) { if (e.key === "Escape") { g.classList.add("gloss-closed"); } });
  });

  /* F7. "On this page": highlight the section in view (D56). */
  var onLinks = all("nav.onpage a");
  if (onLinks.length && window.IntersectionObserver) {
    var spy = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) { return; }
        onLinks.forEach(function (a) { if (a.getAttribute("href") === "#" + e.target.id) { a.setAttribute("aria-current", "true"); } else { a.removeAttribute("aria-current"); } });
      });
    }, {rootMargin: "0px 0px -70% 0px"});
    onLinks.forEach(function (a) { var t = byId(a.getAttribute("href").slice(1)); if (t) { spy.observe(t); } });
  }
})();
