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
function signed(v, digits) { return (v >= 0 ? "+" : "") + v.toFixed(digits); }
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
function shortDate(s) { if (!s) { return "date not confirmed"; } var d = parseIso(s); return pad2(d.getDate()) + " " + MONTHS[d.getMonth()] + " " + d.getFullYear(); }
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
      byId("sc-out").textContent = value.toFixed(2);
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
      byId("sc-min").textContent = s.min.toFixed(2); byId("sc-max").textContent = s.max.toFixed(2);
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
    var ids = ["rate", "ru", "cn", "prem", "cap"];
    var redrawCorridor = function () {
      var v = {}, i;
      for (i = 0; i < ids.length; i++) { v[ids[i]] = parseFloat(byId("c-" + ids[i]).value);
        byId("o-" + ids[i]).textContent = v[ids[i]].toFixed(2); }
      var credit = JSON.parse(form.getAttribute("data-credit"));
      var res = corridor(v.rate, parseFloat(form.getAttribute("data-inflation")), {"Russia": v.ru, "China": v.cn}, v.prem, v.cap, credit);
      byId("corridor-out").textContent = "Corridor: " + res.lower.toFixed(2) + "–" + res.upper.toFixed(2) +
        "%; real differential to Russia " + res.differentials["Russia"].toFixed(2) + " pp, to China " + res.differentials["China"].toFixed(2) +
        " pp; " + res.label + ".";
    };
    for (var n = 0; n < ids.length; n++) { byId("c-" + ids[n]).addEventListener("input", redrawCorridor); }
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
})();
