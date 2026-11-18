"""Exploratory omitted-variable check (D50): foreign policy rates added to the frozen ordered logit.

`python run.py ovb` writes model/extensions/ovb_check.json and outputs/ovb_check.md. It does not touch
model/artifact.json, so the artifact hash recorded in the forecast log stays the same.

* Controls: the Bank of Russia key rate, the China policy rate (BIS; LPR 1Y / benchmark lending rate) and the
  ECB deposit facility rate. Each is the calendar-day mean of the month (external_data.monthly_step_rate, as for
  the corridor), kept as a level in percent, and aligned to decision month minus the assumed release lag, as the
  six factors are (ingest.apply_release_lag). Policy rates are already rates in percent, like inflation and
  consumption, which the specification keeps as levels; the 12-month log growth of the specification is for
  positive stock levels and is undefined for the negative ECB rate of 2015-2022.
* Same usable decisions and the same chronological estimation/holdout split as the frozen model. The frozen fit
  is re-run and must reproduce the artifact coefficients within the stored replication tolerance.
* Specifications: each control alone and all three together. Coefficients with HC0 standard errors; LR and HC0
  Wald tests of the added controls (Holm over the four Wald tests); VIF with the controls; holdout RMSE ratio to
  Always Hold, RPS and Diebold-Mariano tests of each extended model against the frozen model. BFGS with a Newton
  fallback when BFGS does not converge (D33/D34).
* Cross-check with another dependent variable: the change of the base rate in percentage points at each decision,
  OLS with HC1 standard errors on the same estimation sample, with the six factors and with all three controls.

All results are exploratory: they were obtained after the holdout had been seen, and the verdict of the preregistration
does not change.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import chi2, norm
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tools.tools import add_constant

from src import external_data
from src.ingest import ASSUMED_LAG_MONTHS, apply_release_lag
from src.model import (ALPHA, ARTIFACT_PATH, DATA_PATH, FEATURES, HOLDOUT_SHARE, MODEL_PANEL_PATH, SEED,
                       _fit_ordered, _named_parameter_covariance, _predict_probabilities)
from src.robust_eval import dm_test, ordinal_rps

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "model" / "extensions" / "ovb_check.json"
REPORT_PATH = ROOT / "outputs" / "ovb_check.md"
CONTROLS = {"ru_key_rate": "Bank of Russia key rate",
            "cn_policy_rate": "China policy rate (BIS; LPR 1Y / benchmark lending rate)",
            "ecb_deposit_rate": "ECB deposit facility rate"}
SPECIFICATIONS = {"frozen": [], "plus_ru_key_rate": ["ru_key_rate"], "plus_cn_policy_rate": ["cn_policy_rate"],
                  "plus_ecb_deposit_rate": ["ecb_deposit_rate"], "plus_all_three": list(CONTROLS)}
# Which optimizer produced a fit depends on the platform and the library versions (D33/D34): BFGS may stop early on one
# platform and be finished by Newton there, with estimates equal within the cross-platform tolerance (D55).
OPTIMIZER_LABELS = ("bfgs", "newton (after BFGS did not converge)")
LABEL = ("Exploratory: added on 2026-11-16 after the holdout had been seen, at the instructor's request. "
         "The frozen specification, its holdout verdict and the pre-registration do not change.")


def control_series(directory: Path = external_data.EXTERNAL_DIR) -> dict[str, pd.Series]:
    """Monthly calendar-day mean of each control rate (percent, level)."""
    return {name: external_data.monthly_step_rate(external_data.read_raw(name, directory)) for name in CONTROLS}


def build_panel(model_panel_path: Path = MODEL_PANEL_PATH, decisions_path: Path = DATA_PATH,
                directory: Path = external_data.EXTERNAL_DIR) -> pd.DataFrame:
    """Usable decisions of the frozen model with the three controls and the base-rate change (pp)."""
    panel = pd.read_csv(model_panel_path)
    usable = panel.dropna(subset=FEATURES + ["y"]).copy().reset_index(drop=True)
    usable["decision_date"] = pd.to_datetime(usable.decision_date, errors="raise")
    for name, series in control_series(directory).items():
        usable[name] = apply_release_lag(series, usable.decision_date, lag_months=ASSUMED_LAG_MONTHS).to_numpy()
    decisions = pd.read_csv(decisions_path, parse_dates=["decision_date"])
    change = (decisions.base_rate_after - decisions.base_rate_before).rename("rate_change_pp")
    usable = usable.merge(pd.concat([decisions.decision_date, change], axis=1), on="decision_date", how="left")
    return usable


def split(usable: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    holdout_n = int(math.ceil(HOLDOUT_SHARE * len(usable)))
    estimation_n = len(usable) - holdout_n
    return usable.iloc[:estimation_n].reset_index(drop=True), usable.iloc[estimation_n:].reset_index(drop=True)


def _coefficients(model, fitted, covariance, names: list[str]) -> tuple[dict[str, dict[str, float]], list[str], np.ndarray]:
    params = np.asarray(fitted.params, dtype=float)
    labels, estimates, named_cov = _named_parameter_covariance(model, params, covariance, feature_names=names)
    se = np.sqrt(np.maximum(np.diag(named_cov), 0))
    rows = {}
    for label, estimate, error in zip(labels, estimates, se):
        if label not in names:
            continue
        z = float(estimate / error) if error > 0 else float("nan")
        rows[label] = {"estimate": float(estimate), "hc0_se": float(error), "z": z, "p_value": float(2 * norm.sf(abs(z)))}
    return rows, labels, named_cov


def vif(train: pd.DataFrame, names: list[str]) -> dict[str, float]:
    design = add_constant(train[names].astype(float), has_constant="add").to_numpy()
    return {name: float(variance_inflation_factor(design, column)) for column, name in enumerate(names, start=1)}


def _wald(estimates: np.ndarray, covariance: np.ndarray) -> tuple[float, int, float]:
    statistic = float(estimates @ np.linalg.pinv(covariance) @ estimates)
    return statistic, len(estimates), float(chi2.sf(statistic, len(estimates)))


def fit_specification(train: pd.DataFrame, holdout: pd.DataFrame, controls: list[str]) -> dict[str, Any]:
    names = FEATURES + controls
    model, fitted, covariance = _fit_ordered(train, seed=SEED, feature_names=names, newton_fallback=True)
    converged = bool(fitted.mle_retvals.get("converged", False))
    coefficients, labels, named_cov = _coefficients(model, fitted, covariance, names)
    probabilities = _predict_probabilities(model, np.asarray(fitted.params, dtype=float), holdout, feature_names=names)
    actual = holdout.y.to_numpy(dtype=int)
    expected = probabilities[:, 2] - probabilities[:, 0]
    result = {"controls": controls, "converged": converged,
              "optimizer": OPTIMIZER_LABELS[1] if fitted.mle_settings.get("optimizer") == "newton" else OPTIMIZER_LABELS[0],
              "log_likelihood": float(fitted.llf), "coefficients": coefficients,
              "_squared_error": (expected - actual) ** 2, "_rps": ordinal_rps(probabilities, actual)}
    if controls:
        index = [labels.index(name) for name in controls]
        estimates = np.array([coefficients[name]["estimate"] for name in controls])
        statistic, df, p = _wald(estimates, named_cov[np.ix_(index, index)])
        result["wald_hc0"] = {"statistic": statistic, "df": df, "p_value": p}
        result["vif"] = vif(train, names)
    return result


def _holdout_metrics(spec: dict[str, Any], frozen: dict[str, Any], hold_squared: np.ndarray, hold_rps: np.ndarray) -> dict[str, Any]:
    rmse = float(np.sqrt(spec["_squared_error"].mean()))
    out = {"rmse": rmse, "rmse_ratio_to_always_hold": rmse / float(np.sqrt(hold_squared.mean())),
           "rps": float(spec["_rps"].mean()), "rps_always_hold": float(hold_rps.mean())}
    if spec is not frozen:
        out["rmse_ratio_to_frozen"] = rmse / float(np.sqrt(frozen["_squared_error"].mean()))
        for key, loss in (("dm_squared_error_vs_frozen", "_squared_error"), ("dm_rps_vs_frozen", "_rps")):
            test = dm_test(spec[loss], frozen[loss])
            out[key] = {k: test[k] for k in ("n", "mean_loss_difference", "statistic", "p_value")}
    return out


def ols_cross_check(train: pd.DataFrame, controls: list[str]) -> dict[str, Any]:
    names = FEATURES + controls
    design = sm.add_constant(train[names].astype(float), has_constant="add")
    fitted = sm.OLS(train.rate_change_pp.astype(float), design).fit(cov_type="HC1")
    return {"n": int(fitted.nobs), "r2": float(fitted.rsquared),
            "coefficients": {name: {"estimate": float(fitted.params[name]), "hc1_se": float(fitted.bse[name]),
                                    "p_value": float(fitted.pvalues[name])} for name in names}}


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def run(model_panel_path: Path = MODEL_PANEL_PATH, decisions_path: Path = DATA_PATH,
        directory: Path = external_data.EXTERNAL_DIR, artifact_path: Path = ARTIFACT_PATH) -> dict[str, Any]:
    usable = build_panel(model_panel_path, decisions_path, directory)
    missing = {name: int(usable[name].isna().sum()) for name in CONTROLS if usable[name].isna().any()}
    if missing or usable.rate_change_pp.isna().any():
        raise ValueError(f"controls or rate change missing for usable decisions: {missing}")
    train, holdout = split(usable)
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    fits = {key: fit_specification(train, holdout, controls) for key, controls in SPECIFICATIONS.items()}
    frozen = fits["frozen"]

    tolerance = float(artifact["replication_tolerance"]["coefficients_absolute"])
    reproduced = max(abs(frozen["coefficients"][f]["estimate"] - float(artifact["model"]["parameters"][f])) for f in FEATURES)
    if reproduced > tolerance:
        raise ValueError(f"the frozen fit does not reproduce the artifact coefficients (max difference {reproduced})")

    actual = holdout.y.to_numpy(dtype=int)
    hold_squared = actual.astype(float) ** 2
    hold_rps = ordinal_rps(np.tile([0.0, 1.0, 0.0], (len(actual), 1)), actual)

    # Tests of the added controls: LR against the frozen fit and HC0 Wald; Holm over the four Wald tests.
    extended = [key for key in SPECIFICATIONS if key != "frozen"]
    for key in extended:
        lr = max(0.0, 2 * (fits[key]["log_likelihood"] - frozen["log_likelihood"]))
        fits[key]["lr"] = {"statistic": lr, "df": len(SPECIFICATIONS[key]), "p_value": float(chi2.sf(lr, len(SPECIFICATIONS[key])))}
    holm = multipletests([fits[key]["wald_hc0"]["p_value"] for key in extended], method="holm")[1]
    for key, p in zip(extended, holm):
        fits[key]["wald_hc0"]["p_value_holm"] = float(p)

    specifications, changes = {}, {}
    for key, fit in fits.items():
        entry = {k: v for k, v in fit.items() if not k.startswith("_")}
        entry["holdout"] = _holdout_metrics(fit, frozen, hold_squared, hold_rps)
        specifications[key] = entry
        if key == "frozen":
            continue
        rows = {}
        for feature in FEATURES:
            base, new = frozen["coefficients"][feature], fit["coefficients"][feature]
            rows[feature] = {"estimate_change": new["estimate"] - base["estimate"],
                             "relative_change": (new["estimate"] - base["estimate"]) / abs(base["estimate"]),
                             "sign_flip": int(_sign(new["estimate"]) != _sign(base["estimate"])),
                             "significance_change": int((new["p_value"] < ALPHA) != (base["p_value"] < ALPHA))}
        changes[key] = rows

    ols = {"six_factors": ols_cross_check(train, []), "six_factors_plus_all_three": ols_cross_check(train, list(CONTROLS))}
    for key, logit_key in (("six_factors", "frozen"), ("six_factors_plus_all_three", "plus_all_three")):
        ols[key]["same_sign_as_ordered_logit"] = {
            f: int(_sign(ols[key]["coefficients"][f]["estimate"]) == _sign(fits[logit_key]["coefficients"][f]["estimate"]))
            for f in FEATURES}

    frozen_ratio = specifications["frozen"]["holdout"]["rmse_ratio_to_always_hold"]
    artifact_ratio = float(artifact["benchmark_comparison"]["rmse_ratio_model_to_hold"])
    summary = {
        "sign_flips": sum(row["sign_flip"] for rows in changes.values() for row in rows.values()),
        "sign_flips_of_frozen_significant": sum(row["sign_flip"] for rows in changes.values() for f, row in rows.items()
                                                if frozen["coefficients"][f]["p_value"] < ALPHA),
        "frozen_significant_factors": sum(int(frozen["coefficients"][f]["p_value"] < ALPHA) for f in FEATURES),
        "significance_changes": sum(row["significance_change"] for rows in changes.values() for row in rows.values()),
        "controls_significant_after_holm": sum(int(specifications[k]["wald_hc0"]["p_value_holm"] < ALPHA) for k in extended),
        "extended_specifications": len(extended),
        "factor_comparisons": len(extended) * len(FEATURES),
        "max_abs_relative_change": max(abs(row["relative_change"]) for rows in changes.values() for row in rows.values()),
        "holdout_conclusion_changes": sum(int((specifications[k]["holdout"]["rmse_ratio_to_always_hold"] < 1) != (frozen_ratio < 1))
                                          for k in extended),
        "dm_squared_error_p_below_alpha": sum(int((specifications[k]["holdout"]["dm_squared_error_vs_frozen"]["p_value"] or 1) < ALPHA)
                                              for k in extended),
        "max_vif_all_three": max(specifications["plus_all_three"]["vif"].values()),
        "ols_same_signs_six_factors": sum(ols["six_factors"]["same_sign_as_ordered_logit"].values()),
        "ols_same_signs_with_controls": sum(ols["six_factors_plus_all_three"]["same_sign_as_ordered_logit"].values()),
        "ols_significant_six_factors": sum(int(c["p_value"] < ALPHA) for f, c in ols["six_factors"]["coefficients"].items() if f in FEATURES),
    }
    return {
        "label": LABEL, "seed": SEED, "alpha": ALPHA,
        "sample": {"usable_n": len(usable), "estimation_n": len(train), "holdout_n": len(holdout),
                   "estimation_start": train.decision_date.min().date().isoformat(),
                   "estimation_end": train.decision_date.max().date().isoformat(),
                   "holdout_start": holdout.decision_date.min().date().isoformat(),
                   "holdout_end": holdout.decision_date.max().date().isoformat(),
                   "release_lag_months": ASSUMED_LAG_MONTHS},
        "controls": CONTROLS,
        "control_transformation": ("calendar-day mean of the month (external_data.monthly_step_rate), level in percent, "
                                   "aligned to decision month minus the assumed release lag like the six factors"),
        "frozen_reproduction": {"max_abs_coefficient_difference": reproduced, "tolerance": tolerance,
                                "holdout_ratio_difference": abs(frozen_ratio - artifact_ratio)},
        "specifications": specifications, "coefficient_changes": changes,
        "tests": {"wald": "HC0 Wald test that the added control slopes are zero; Holm over the four extended specifications",
                  "lr": "likelihood ratio against the frozen fit (classical, not robust)",
                  "dm": "HLN-corrected Diebold-Mariano, extended model minus frozen model; a negative mean difference favours the extended model"},
        "ols_cross_check": ols, "summary": summary,
    }


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    return value


def report(result: dict[str, Any]) -> str:
    f = lambda v, d=3: "n/a" if v is None else f"{v:.{d}f}"  # noqa: E731
    s, specs = result["sample"], result["specifications"]
    lines = ["# Omitted-variable check (exploratory)", "", result["label"], "",
             f"Usable decisions {s['usable_n']}: estimation {s['estimation_n']} ({s['estimation_start']} to {s['estimation_end']}), "
             f"holdout {s['holdout_n']} ({s['holdout_start']} to {s['holdout_end']}). Controls: {', '.join(result['controls'].values())}; "
             f"{result['control_transformation']}.", "",
             "## Six coefficients by specification (HC0 standard errors)", "",
             "| Factor | " + " | ".join(SPECIFICATIONS) + " |", "|---|" + "---|" * len(SPECIFICATIONS)]
    for feature in FEATURES:
        cells = [f"{f(specs[k]['coefficients'][feature]['estimate'])} ({f(specs[k]['coefficients'][feature]['hc0_se'])}; p {f(specs[k]['coefficients'][feature]['p_value'])})"
                 for k in SPECIFICATIONS]
        lines.append(f"| {feature} | " + " | ".join(cells) + " |")
    lines += ["", "## Added controls", "", "| Specification | Control estimates (p) | HC0 Wald (df) | p | Holm p | LR | LR p | max VIF |",
              "|---|---|---|---|---|---|---|---|"]
    for key in list(SPECIFICATIONS)[1:]:
        e = specs[key]
        est = "; ".join(f"{c} {f(e['coefficients'][c]['estimate'])} ({f(e['coefficients'][c]['p_value'])})" for c in e["controls"])
        lines.append(f"| {key} | {est} | {f(e['wald_hc0']['statistic'])} ({e['wald_hc0']['df']}) | {f(e['wald_hc0']['p_value'])} | "
                     f"{f(e['wald_hc0']['p_value_holm'])} | {f(e['lr']['statistic'])} | {f(e['lr']['p_value'])} | {f(max(e['vif'].values()), 2)} |")
    lines += ["", "## Holdout", "", "| Specification | RMSE ratio to Always Hold | RPS | DM sq. error vs frozen (p) | DM RPS vs frozen (p) |", "|---|---|---|---|---|"]
    for key in SPECIFICATIONS:
        h = specs[key]["holdout"]
        dm = lambda name: "—" if name not in h else f"{f(h[name]['statistic'])} ({f(h[name]['p_value'])})"  # noqa: E731
        lines.append(f"| {key} | {f(h['rmse_ratio_to_always_hold'])} | {f(h['rps'])} | {dm('dm_squared_error_vs_frozen')} | {dm('dm_rps_vs_frozen')} |")
    lines += ["", "## Cross-check: base-rate change in percentage points, OLS with HC1", "",
              "| Factor | OLS six factors (p) | OLS with controls (p) | Same sign as ordered logit (six / with controls) |", "|---|---|---|---|"]
    o = result["ols_cross_check"]
    for feature in FEATURES:
        a, b = o["six_factors"]["coefficients"][feature], o["six_factors_plus_all_three"]["coefficients"][feature]
        same = f"{'yes' if o['six_factors']['same_sign_as_ordered_logit'][feature] else 'no'} / {'yes' if o['six_factors_plus_all_three']['same_sign_as_ordered_logit'][feature] else 'no'}"
        lines.append(f"| {feature} | {f(a['estimate'])} ({f(a['p_value'])}) | {f(b['estimate'])} ({f(b['p_value'])}) | {same} |")
    lines += ["", "Generated by `python run.py ovb` into model/extensions/ovb_check.json; model/artifact.json is not changed.", ""]
    return "\n".join(lines)


def main() -> int:
    result = _clean(run())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    REPORT_PATH.write_text(report(result), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} and {REPORT_PATH.relative_to(ROOT)}: " + json.dumps(result["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
