/* Carry-trade corridor engine of the site. The same formula as src/carry_corridor.py::corridor
   (parity test tests/test_carry_corridor.py, to 1e-6). ES3 syntax: runs in node and in Windows cscript.
   The labels are the English versions of the Python position labels (src/site_i18n.py). */
var POSITION_LABELS = ["corridor broken: the lower bound is above the upper bound",
                       "below the corridor: risk of outflows into the carry trade",
                       "above the corridor: risk of excessive inflows and harm to credit",
                       "inside the corridor"];

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
