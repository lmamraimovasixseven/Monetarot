/* Ползунки сайта. Порог p* = 1 / (1 + r) — та же формула, что src/decision_rule.py::binary_threshold(1, r). */
function threshold(ratio) { return 1 / (1 + ratio); }

(function () {
  var ratio = document.getElementById("ratio");
  if (ratio) {
    var pcut = parseFloat(ratio.getAttribute("data-pcut"));
    var update = function () {
      var r = parseFloat(ratio.value), p = threshold(r);
      document.getElementById("ratio-out").textContent = r.toFixed(2);
      document.getElementById("ratio-text").textContent = "Порог p* = " + p.toFixed(3) + "; P(снижение) = " + pcut.toFixed(3) +
        " → " + (pcut > p ? "удлинять дюрацию" : "не удлинять дюрацию") + ".";
    };
    ratio.addEventListener("input", update); update();
  }
  var form = document.getElementById("corridor");
  if (form && typeof corridor === "function") {
    var ids = ["rate", "ru", "cn", "prem", "cap"];
    var redraw = function () {
      var v = {}, i;
      for (i = 0; i < ids.length; i++) { v[ids[i]] = parseFloat(document.getElementById("c-" + ids[i]).value);
        document.getElementById("o-" + ids[i]).textContent = v[ids[i]].toFixed(2); }
      var credit = JSON.parse(form.getAttribute("data-credit"));
      var res = corridor(v.rate, parseFloat(form.getAttribute("data-inflation")), {"Россия": v.ru, "Китай": v.cn}, v.prem, v.cap, credit);
      document.getElementById("corridor-out").textContent = "Коридор: " + res.lower.toFixed(2) + "–" + res.upper.toFixed(2) +
        "%; реальный дифференциал к РФ " + res.differentials["Россия"].toFixed(2) + ", к КНР " + res.differentials["Китай"].toFixed(2) +
        " п.п.; " + res.label + ".";
    };
    for (var k = 0; k < ids.length; k++) { document.getElementById("c-" + ids[k]).addEventListener("input", redraw); }
    redraw();
  }
  var select = document.getElementById("asof-t");
  if (select) {
    var show = function () {
      var blocks = document.querySelectorAll(".asof");
      for (var j = 0; j < blocks.length; j++) { blocks[j].hidden = blocks[j].getAttribute("data-t") !== select.value; }
    };
    select.addEventListener("change", show); select.value = select.options[select.options.length - 1].value; show();
  }
})();
