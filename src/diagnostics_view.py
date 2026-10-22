"""Read-only Streamlit diagnostics built from saved out-of-sample artifacts."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from src.hashing import normalized_sha256


def load_diagnostic_artifacts(project_dir, expected_data_sha256=None):
    """Load expected reports without failing the app on missing/incomplete files."""
    root = Path(project_dir)
    legacy = root / "outputs" / "legacy"
    specs = {
        "results": (legacy / "mvp_backtest_results.json", "json"),
        "validity": (legacy / "mvp_validity_report.json", "json"),
        "period_predictions": (legacy / "mvp_period_predictions.csv", "csv"),
    }
    loaded, issues = {}, []
    for key, (path, kind) in specs.items():
        if not path.is_file():
            issues.append(f"Missing diagnostic artifact: {path.name}")
            continue
        try:
            loaded[key] = json.loads(path.read_text(encoding="utf-8")) if kind == "json" else pd.read_csv(path)
        except (OSError, ValueError, json.JSONDecodeError, pd.errors.ParserError) as error:
            issues.append(f"Could not read {path.name}: {error}")
    if "results" in loaded:
        saved_hash = loaded["results"].get("input", {}).get("sha256")
        if expected_data_sha256 and saved_hash != expected_data_sha256:
            issues.append("Saved diagnostics do not match the current input CSV; stale results are hidden")
            loaded["results"]["period_comparison"] = []
            loaded["period_predictions"] = pd.DataFrame()
        period_reports = loaded["results"].get("period_comparison")
        if not isinstance(period_reports, list) or not period_reports:
            issues.append("Backtest result has no usable period_comparison section")
            loaded["results"]["period_comparison"] = []
        else:
            period_keys = {"test_period_months", "status", "train_n", "test_n", "train_class_distribution", "actual_class_distribution", "models"}
            model_keys = {"model", "accuracy", "balanced_accuracy", "macro_f1", "confusion_matrix_actual_rows_predicted_columns", "predicted_class_distribution"}
            malformed = any(
                not isinstance(item, dict) or not period_keys.issubset(item) or not isinstance(item.get("models"), list) or not item.get("models")
                or any(not isinstance(model, dict) or not model_keys.issubset(model) for model in item.get("models", []))
                for item in period_reports
            )
            if malformed:
                issues.append("Period comparison artifact is incomplete; period diagnostics are hidden")
                loaded["results"]["period_comparison"] = []
    if "period_predictions" in loaded and not {"test_period_months", "decision_date", "actual"}.issubset(loaded["period_predictions"].columns):
        issues.append("Period prediction artifact is missing required columns")
    return loaded, issues


def probability_diagnostics(frame, model_name, class_order):
    """Summarize only saved out-of-sample probabilities for one model/window."""
    probability_columns = [f"probability_{model_name}_{label}" for label in class_order]
    required = {"actual", f"predicted_{model_name}", *probability_columns}
    if frame.empty or not required.issubset(frame.columns):
        return None
    probs = frame[probability_columns].to_numpy(dtype=float)
    if not np.isfinite(probs).all() or ((probs < 0) | (probs > 1)).any() or not np.allclose(probs.sum(axis=1), 1, atol=1e-8, rtol=0):
        return None
    actual = frame["actual"].astype(str).to_numpy()
    predicted = frame[f"predicted_{model_name}"].astype(str).to_numpy()
    maximum = probs.max(axis=1)
    rows = [{"Class": label, "Mean predicted probability": float(probs[:, index].mean()), "n": len(frame)} for index, label in enumerate(class_order)]
    max_summary = {
        "n": int(len(frame)),
        "minimum": float(maximum.min()),
        "median": float(np.median(maximum)),
        "maximum": float(maximum.max()),
    }
    threshold_rows = []
    for threshold in (0.5, 0.7, 0.9):
        selected = maximum > threshold
        count = int(selected.sum())
        threshold_rows.append({
            "Threshold": f"> {threshold:.0%}",
            "n above threshold": count,
            "Share of forecasts": count / len(frame),
            "Correct / n": f"{int((predicted[selected] == actual[selected]).sum())} / {count}" if count >= 5 else "Insufficient n (<5)",
            "Accuracy": float((predicted[selected] == actual[selected]).mean()) if count >= 5 else np.nan,
        })
    indicator = np.column_stack([actual == label for label in class_order]).astype(float)
    brier = float(np.mean(np.sum((probs - indicator) ** 2, axis=1)))
    return {
        "n": int(len(frame)),
        "mean_probabilities": pd.DataFrame(rows),
        "max_probability": max_summary,
        "thresholds": pd.DataFrame(threshold_rows),
        "multiclass_brier": brier,
    }


def error_table(period_frame, source_data, features):
    if period_frame.empty or source_data.empty:
        return pd.DataFrame()
    required = {"decision_date", "actual", "predicted_Logistic Regression", "predicted_Random Forest"}
    if not required.issubset(period_frame.columns):
        return pd.DataFrame()
    dates = source_data[["decision_date", *features]].copy()
    dates["decision_date"] = pd.to_datetime(dates["decision_date"])
    dates = dates.sort_values("decision_date")
    for feature in ("corporate_lending", "household_lending"):
        if feature in dates:
            dates[f"{feature}_decision_interval_growth_pct"] = dates[feature].pct_change(fill_method=None) * 100.0
    frame = period_frame.copy()
    frame["decision_date"] = pd.to_datetime(frame["decision_date"])
    frame = frame.merge(dates, on="decision_date", how="left", validate="many_to_one")
    for model_name in ("Logistic Regression", "Random Forest"):
        frame[f"{model_name} correct"] = frame[f"predicted_{model_name}"] == frame["actual"]
    cutoff = dates["decision_date"].max() - pd.DateOffset(months=int(period_frame["test_period_months"].iloc[0]))
    training = dates.loc[dates["decision_date"] < cutoff]
    for feature in ("corporate_lending", "household_lending"):
        if feature not in frame or feature not in training:
            continue
        low, high = training[feature].min(), training[feature].max()
        frame[f"{feature}_outside_train_range"] = (frame[feature] < low) | (frame[feature] > high)
    range_flags = [column for column in frame if column.endswith("_outside_train_range")]
    frame["out_of_range_feature_count"] = frame[range_flags].sum(axis=1) if range_flags else 0
    for model_name in ("Logistic Regression", "Random Forest"):
        probability_columns = [f"probability_{model_name}_{label}" for label in ("Increase", "Hold", "Decrease")]
        if probability_columns and set(probability_columns).issubset(frame.columns):
            frame[f"{model_name} max_probability"] = frame[probability_columns].max(axis=1)
    return frame


def feature_range_summary(data, features, months):
    cutoff = data["decision_date"].max() - pd.DateOffset(months=int(months))
    train = data.loc[data["decision_date"] < cutoff]
    test = data.loc[data["decision_date"] >= cutoff]
    rows = []
    for feature in features:
        values = train[feature].dropna()
        held = test[feature]
        lo, hi = values.min(), values.max()
        rows.append({
            "Feature": feature,
            "Train n": int(len(train)),
            "Train missing": int(train[feature].isna().sum()),
            "Train min": lo,
            "Train max": hi,
            "Train median": values.median(),
            "Test n": int(len(test)),
            "Test missing": int(held.isna().sum()),
            "Test min": held.min(),
            "Test max": held.max(),
            "Test median": held.median(),
            "Test outside train range": int(((held < lo) | (held > hi)).sum()),
        })
    return pd.DataFrame(rows)


def render_diagnostics_tab(st, project_dir, data, features, feature_labels, class_order):
    st.subheader("Saved chronological evaluations")
    source_path = Path(project_dir) / "data" / "processed" / "nbk_decisions_clean.csv"
    expected_hash = normalized_sha256(source_path) if source_path.is_file() else None
    artifacts, issues = load_diagnostic_artifacts(project_dir, expected_hash)
    for issue in issues:
        st.warning(issue)
    result = artifacts.get("results", {})
    validity = artifacts.get("validity", {})
    periods = result.get("period_comparison", [])
    predictions = artifacts.get("period_predictions", pd.DataFrame())

    st.subheader("Extrapolation warning")
    if not data.empty and "decision_date" in data:
        dates = pd.to_datetime(data["decision_date"])
        cutoff = dates.max() - pd.DateOffset(months=24)
        training_rows = data.loc[dates < cutoff]
        test_rows = data.loc[dates >= cutoff]
        range_cols = st.columns(2)
        range_counts = {}
        for column, feature in zip(range_cols, ("corporate_lending", "household_lending")):
            if feature not in data or training_rows[feature].dropna().empty:
                column.metric(feature.replace("_", " ").title(), "Unavailable")
                continue
            train_max = training_rows[feature].max()
            count = int((test_rows[feature] > train_max).sum())
            range_counts[feature] = count
            column.metric(
                feature.replace("_", " ").title() + " above train max",
                f"{count} / {len(test_rows)}",
            )
        if range_counts:
            st.caption(
                "The model receives values beyond the training range; this may reduce forecast reliability. "
                "This association does not establish that extrapolation caused prediction errors."
            )
    else:
        st.info("The source data is unavailable for the 24-month feature-range check.")

    evaluated_periods = [item for item in periods if item.get("status") == "EVALUATED"]
    if len(evaluated_periods) > 1:
        window_rows = []
        for period in evaluated_periods:
            model_lookup = {item.get("model"): item for item in period.get("models", [])}
            row = {"Test window (months)": period.get("test_period_months"), "Test n": period.get("test_n")}
            for model_name, short_name in (("Hold benchmark", "Always Hold"), ("Logistic Regression", "Logistic Regression"), ("Random Forest (additional comparison)", "Random Forest")):
                report = model_lookup.get(model_name)
                row[f"{short_name} accuracy"] = report.get("accuracy") if report else np.nan
                if model_name != "Hold benchmark" and report:
                    distribution = report.get("predicted_class_distribution", {})
                    row[f"{short_name} most predicted"] = max(
                        class_order,
                        key=lambda label: distribution.get(label, {}).get("count", 0),
                    )
            window_rows.append(row)
        st.markdown("**Performance across chronological windows**")
        st.dataframe(
            pd.DataFrame(window_rows).style.format(
                {column: "{:.3f}" for column in ("Always Hold accuracy", "Logistic Regression accuracy", "Random Forest accuracy")}
            ),
            hide_index=True,
            width="stretch",
        )
        st.caption("Results vary by test window. The 36- and 48-month windows are sensitivity checks, not model-selection periods.")

    if periods:
        summary_rows = []
        for period in periods:
            actual = period.get("actual_class_distribution", {})
            train = period.get("train_class_distribution", {})
            for model in period.get("models", []):
                summary_rows.append({
                    "Months": period.get("test_period_months"),
                    "Status": period.get("status"),
                    "Train n": period.get("train_n"),
                    "Test n": period.get("test_n"),
                    "Train classes (I/H/D)": " / ".join(str(train.get(k, {}).get("count", 0)) for k in class_order),
                    "Actual test (I/H/D)": " / ".join(str(actual.get(k, {}).get("count", 0)) for k in class_order),
                    "Model": model.get("model"),
                    "Accuracy": model.get("accuracy"),
                    "Balanced accuracy": model.get("balanced_accuracy"),
                    "Macro F1": model.get("macro_f1"),
                    "Predicted (I/H/D)": " / ".join(str(model.get("predicted_class_distribution", {}).get(k, {}).get("count", 0)) for k in class_order),
                })
        st.dataframe(pd.DataFrame(summary_rows), hide_index=True, width="stretch")
        period_options = [int(item["test_period_months"]) for item in periods if item.get("status") == "EVALUATED"]
        if period_options:
            selected_period = st.selectbox("Diagnostic test period", period_options, index=period_options.index(24) if 24 in period_options else 0)
            selected_report = next(item for item in periods if item.get("test_period_months") == selected_period)
            st.caption(
                f"Primary estimate: 24 months. The 36- and 48-month windows are sensitivity analyses; "
                "they are not selected by performance. Confusion matrices use actual rows and predicted columns, "
                f"class order {', '.join(class_order)}."
            )
            model_options = [model["model"] for model in selected_report.get("models", [])]
            if model_options:
                selected_model = st.selectbox("Confusion matrix model", model_options, key="period_matrix_model")
                model_report = next(item for item in selected_report["models"] if item["model"] == selected_model)
                matrix_values = model_report.get("confusion_matrix_actual_rows_predicted_columns")
                try:
                    matrix = pd.DataFrame(
                        matrix_values,
                        index=pd.Index(class_order, name="Actual / Predicted"),
                        columns=class_order,
                    )
                    st.dataframe(matrix, width="stretch")
                except (TypeError, ValueError):
                    st.warning("Saved confusion matrix is missing or malformed.")
            st.caption("Each period is a separate, overlapping chronological evaluation, not an independent sample.")

            st.subheader("Expanding-window stability folds")
            stability = validity.get("Stability", {})
            fold_metrics = stability.get("fold_metrics", [])
            fold_predictions = stability.get("fold_predictions", [])
            if fold_metrics and fold_predictions:
                fold_rows = []
                fold_frame = pd.DataFrame(fold_predictions)
                for row in fold_metrics:
                    model_name = row["model"]
                    predicted_col = "Logistic Regression" if model_name == "Logistic Regression" else "Hold benchmark"
                    subset = fold_frame.loc[fold_frame["fold"] == row["fold"]]
                    counts = subset[predicted_col].value_counts().reindex(class_order, fill_value=0)
                    fold_rows.append({**row, "predicted Increase / Hold / Decrease": " / ".join(str(int(counts[c])) for c in class_order)})
                st.dataframe(pd.DataFrame(fold_rows), hide_index=True, width="stretch")
                st.caption("Validation blocks contain six observations and expanding training sets overlap; these folds are descriptive stability checks, not independent tests.")
            else:
                st.info("Stability-fold results are missing or incomplete in the saved validity report.")

            current_period = predictions.loc[predictions.get("test_period_months", pd.Series(dtype=int)) == selected_period] if not predictions.empty else pd.DataFrame()
            st.subheader("Out-of-sample probability diagnostics")
            if current_period.empty:
                st.warning("No saved out-of-sample probabilities are available for this period.")
            else:
                for model_name in ("Logistic Regression", "Random Forest"):
                    diagnostics = probability_diagnostics(current_period, model_name, class_order)
                    if diagnostics is None:
                        st.warning(f"{model_name}: probability columns are missing or invalid; no probability diagnostics shown.")
                        continue
                    st.markdown(f"**{model_name} (n={diagnostics['n']})**")
                    st.dataframe(diagnostics["mean_probabilities"], hide_index=True, width="stretch")
                    maximum = diagnostics["max_probability"]
                    st.write(f"Maximum probability: min {maximum['minimum']:.3f}, median {maximum['median']:.3f}, max {maximum['maximum']:.3f} (n={maximum['n']}).")
                    st.write(f"Multiclass Brier score (sum of squared class errors, mean over rows): {diagnostics['multiclass_brier']:.4f} (n={diagnostics['n']}).")
                    st.dataframe(diagnostics["thresholds"].style.format({"Share of forecasts": "{:.1%}", "Accuracy": "{:.3f}"}), hide_index=True, width="stretch")
                st.caption("Probabilities are out-of-sample for the selected chronological window. Calibration plots are omitted: these test sets are too small for reliable calibration interpretation.")

            st.subheader("Row-level error analysis")
            error_rows = error_table(current_period, data, features)
            if error_rows.empty:
                st.info("Row-level predictions or source feature rows are incomplete.")
            else:
                actual_filter = st.selectbox("Actual class filter", ["All", *class_order], key="diagnostic_actual_filter")
                error_filter = st.selectbox("Prediction filter", ["All", "Incorrect only"], key="diagnostic_error_filter")
                if actual_filter != "All":
                    error_rows = error_rows.loc[error_rows["actual"] == actual_filter]
                if error_filter == "Incorrect only":
                    error_rows = error_rows.loc[~(error_rows["Logistic Regression correct"] & error_rows["Random Forest correct"])]
                display_cols = ["decision_date", "actual", "predicted_Logistic Regression", *[f"probability_Logistic Regression_{c}" for c in class_order], "Logistic Regression correct", "Logistic Regression max_probability", "predicted_Random Forest", *[f"probability_Random Forest_{c}" for c in class_order], "Random Forest correct", "Random Forest max_probability", *features, "corporate_lending_decision_interval_growth_pct", "household_lending_decision_interval_growth_pct", "corporate_lending_outside_train_range", "household_lending_outside_train_range", "out_of_range_feature_count"]
                display_cols = [column for column in display_cols if column in error_rows.columns]
                display_frame = error_rows[display_cols].rename(columns={
                    f"probability_{model}_{label}": f"{model.replace('Logistic Regression', 'LR').replace('Random Forest', 'RF')} P({label})"
                    for model in ("Logistic Regression", "Random Forest")
                    for label in class_order
                })
                st.dataframe(display_frame, hide_index=True, width="stretch")
                st.caption(f"Rows shown: {len(error_rows)}. Only saved test predictions are included; no training predictions are mixed in.")
                out_range = error_rows.loc[error_rows.get("out_of_range_feature_count", 0) > 0]
                if len(out_range) == len(error_rows):
                    st.info("All displayed rows have at least one lending feature outside the training range; an inside-versus-outside error comparison is not possible in this slice.")
                elif len(out_range):
                    st.write(f"Out-of-range rows: {len(out_range)}; LR errors among them: {int((~out_range['Logistic Regression correct']).sum())}; RF errors among them: {int((~out_range['Random Forest correct']).sum())}.")
                class_error_rows = []
                for actual_class, group in error_rows.groupby("actual", sort=False):
                    class_error_rows.append({
                        "Actual class": actual_class, "n": len(group),
                        "LR correct": int(group["Logistic Regression correct"].sum()),
                        "RF correct": int(group["Random Forest correct"].sum()),
                        "LR mean max probability (correct)": group.loc[group["Logistic Regression correct"], "Logistic Regression max_probability"].mean(),
                        "LR mean max probability (wrong)": group.loc[~group["Logistic Regression correct"], "Logistic Regression max_probability"].mean(),
                        "RF mean max probability (correct)": group.loc[group["Random Forest correct"], "Random Forest max_probability"].mean(),
                        "RF mean max probability (wrong)": group.loc[~group["Random Forest correct"], "Random Forest max_probability"].mean(),
                    })
                st.dataframe(pd.DataFrame(class_error_rows), hide_index=True, width="stretch")
                confidence_rows = []
                for model_name in ("Logistic Regression", "Random Forest"):
                    column = f"{model_name} max_probability"
                    if column not in error_rows:
                        continue
                    for correct in (True, False):
                        values = error_rows.loc[error_rows[f"{model_name} correct"] == correct, column].dropna()
                        confidence_rows.append({
                            "Model": model_name, "Outcome": "Correct" if correct else "Incorrect",
                            "n": len(values), "Mean max probability": values.mean(),
                            "Median max probability": values.median(), "Minimum": values.min(), "Maximum": values.max(),
                        })
                st.markdown("**Maximum predicted probability by correctness**")
                st.dataframe(pd.DataFrame(confidence_rows), hide_index=True, width="stretch")

            st.subheader("Train versus test feature ranges")
            ranges = feature_range_summary(data, features, selected_period)
            ranges["Feature"] = ranges["Feature"].map(lambda name: feature_labels.get(name, name))
            st.dataframe(ranges, hide_index=True, width="stretch")
            shifted = ranges.loc[ranges["Test outside train range"] > 0, "Feature"].tolist()
            if shifted:
                st.warning("Test observations outside the training range: " + ", ".join(shifted) + ". This flags range shift, not a cause or unit error.")
            st.caption("Column names and numeric values do not establish source units or publication dates; those remain unverified.")
    else:
        st.info("Period-comparison artifact is unavailable or incomplete. Run run_all.py to regenerate it.")

    st.subheader("Credit lending structural-change diagnostics")
    break_path = Path(project_dir) / "outputs" / "legacy" / "mvp_structural_break_summary.json"
    candidate_path = Path(project_dir) / "outputs" / "legacy" / "mvp_structural_break_candidates.csv"
    if break_path.is_file():
        try:
            break_report = json.loads(break_path.read_text(encoding="utf-8"))
            st.caption(break_report.get("sample", "Scope metadata unavailable."))
            source_status = break_report.get("raw_monthly_sources_present", {})
            st.write("Raw monthly credit source files present:", source_status)
            if break_report.get("frequency_limitation"):
                st.warning(break_report["frequency_limitation"])
            for feature in ("corporate_lending", "household_lending"):
                series = data[["decision_date", feature]].copy().sort_values("decision_date").set_index("decision_date")
                st.markdown(f"**{feature.replace('_', ' ').title()} — decision-date observations**")
                st.line_chart(series.rename(columns={feature: "Level (source unit unverified)"}))
                log_series = np.log(series.where(series > 0)).rename(columns={feature: "Log level"})
                st.line_chart(log_series)
            break_rows = []
            for item in break_report.get("tests", []):
                break_rows.append({
                    "Feature": item.get("feature"), "Form": item.get("form"), "Test": item.get("test"),
                    "n": item.get("n"), "Candidate break": item.get("selected_date"),
                    "sup-F": item.get("sup_f_statistic"),
                    "Moving-block bootstrap p": item.get("moving_block_bootstrap_pvalue"),
                    "Status": item.get("status"),
                })
            if break_rows:
                st.dataframe(pd.DataFrame(break_rows), hide_index=True, width="stretch")
                st.caption("The candidate date is selected by scanning unknown break dates. Reported bootstrap p-values apply to the sup-F scan within that one series/form; they are exploratory and not adjusted across all series/forms. Slope confidence intervals are omitted because break-date selection uncertainty is not modeled.")
                slope_rows = []
                for item in break_report.get("tests", []):
                    slopes = item.get("segment_slopes")
                    if item.get("form") == "level" and item.get("test") == "intercept_and_trend" and slopes:
                        slope_rows.append({
                            "Feature": item.get("feature"), "Selected date": item.get("selected_date"),
                            "Before n": slopes["before"]["n"], "Level slope before / year": slopes["before"]["slope_per_year"],
                            "After n": slopes["after"]["n"], "Level slope after / year": slopes["after"]["slope_per_year"],
                        })
                if slope_rows:
                    st.dataframe(pd.DataFrame(slope_rows), hide_index=True, width="stretch")
            if candidate_path.is_file():
                with st.expander("All admissible break scan dates"):
                    st.dataframe(pd.read_csv(candidate_path), hide_index=True, width="stretch")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            st.warning(f"Structural-break diagnostics are unavailable or malformed: {error}")
    else:
        st.info("No saved structural-break diagnostic is available. Run run_all.py to create it.")

    st.subheader("Diagnostic feature specifications")
    spec_path = Path(project_dir) / "outputs" / "legacy" / "mvp_alternative_specifications.json"
    if spec_path.is_file():
        try:
            spec_report = json.loads(spec_path.read_text(encoding="utf-8"))
            rows = spec_report.get("results", [])
            if rows:
                table = pd.DataFrame(rows)
                shown = [column for column in ("period_months", "specification", "model", "status", "train_n", "test_n", "accuracy", "balanced_accuracy", "macro_f1", "multiclass_brier", "confusion_matrix_actual_rows_predicted_columns") if column in table]
                st.dataframe(table[shown], hide_index=True, width="stretch")
                st.caption("Current levels, logarithmic lending levels and decision-interval growth are fixed diagnostic variants. The log and growth transforms use observed values only; the existing sklearn pipeline fits imputation/scaling only on each training slice. Results do not select a new production specification.")
            else:
                st.info("No alternative specification results are available in the saved artifact.")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            st.warning(f"Alternative specification results are unavailable or malformed: {error}")
    else:
        st.info("Alternative specifications have not been run.")

    st.subheader("Source, units and data-join validity")
    st.write("Source files and Excel workbooks are absent from the current working tree; they remain marked deleted in Git. The existing data/raw/SOURCES.md lists prior units inferred from source headers, but explicitly says the publisher, series identifiers and provenance are unauthenticated. Consequently, row-level source reconciliation, date-match verification and definitive unit confirmation cannot be completed from the available project files.")
    st.caption("Forecast factor labels retain the unit claims recorded in SOURCES.md and mark them unverified. The decision-date feature panel supports descriptive comparisons only; it cannot substitute for the missing monthly source series.")
