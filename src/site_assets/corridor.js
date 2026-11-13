/* Движок коридора carry trade для сайта. Та же формула, что src/carry_corridor.py::corridor
   (тест сверки tests/test_carry_corridor.py, до 1e-6). Синтаксис ES3: работает в node и в Windows cscript. */
var POSITION_LABELS = ["коридор сломан: нижняя граница выше верхней",
                       "ниже коридора: риск оттока в carry trade",
                       "выше коридора: риск избыточного притока и вреда кредиту",
                       "внутри коридора"];

function corridor(nbkRate, kzInflation, partners, premium, cap, creditZero) {
  var kzReal = nbkRate - kzInflation, maxPartner = null, name, differentials = {}, count = 0;
  for (name in partners) {
    if (partners.hasOwnProperty(name) && partners[name] !== null) {
      differentials[name] = kzReal - partners[name];
      if (maxPartner === null || partners[name] > maxPartner) { maxPartner = partners[name]; }
      count += 1;
    }
  }
  if (count === 0) { return {status: "unknown", kzReal: kzReal, lower: null, upper: null, code: -1, differentials: differentials}; }
  var lower = kzInflation + maxPartner + premium;
  var inflow = kzInflation + maxPartner + cap, upper = inflow, binding = "inflow_cap";
  if (creditZero !== null && kzInflation + creditZero < inflow) { upper = kzInflation + creditZero; binding = "credit"; }
  var code;
  if (lower > upper) { code = 0; } else if (nbkRate < lower) { code = 1; } else if (nbkRate > upper) { code = 2; } else { code = 3; }
  return {status: "ok", kzReal: kzReal, lower: lower, upper: upper, binding: binding, code: code,
          label: POSITION_LABELS[code], differentials: differentials};
}
