"""OLD vs NEW after a data update: `python run.py compare`.

OLD is read with `git show <tag>:model/artifact.json` (and robust_eval.json) from the tag in
COMPARE_TAG; NEW is the current model/artifact.json and model/robust_eval.json. Every value is read
from those files; nothing is typed. Writes outputs/version_comparison.md and
model/version_comparison.json (which the report and the dashboard read for the generated
"effect of the data update" sentence). Without git (a Download ZIP copy) the OLD block of the
committed model/version_comparison.json is reused, so the comparison can still be rebuilt.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import logging

from streamlit.logger import get_logger

get_logger("streamlit.runtime.caching.cache_data_api").setLevel(logging.ERROR)

from src.app import FEATURES, robustness_check_is_comparable, score_and_delta_band  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
COMPARE_TAG = "before-data-update-2026-09-07"
ARTIFACT_PATH = ROOT / "model" / "artifact.json"
ROBUST_PATH = ROOT / "model" / "robust_eval.json"
JSON_PATH = ROOT / "model" / "version_comparison.json"
MD_PATH = ROOT / "outputs" / "version_comparison.md"
ALPHA = 0.05


def _git_show(ref: str, relative: str) -> dict | None:
    if not (ROOT / ".git").exists() or shutil.which("git") is None:
        return None
    result = subprocess.run(["git", "show", f"{ref}:{relative}"], cwd=ROOT, capture_output=True)
    return json.loads(result.stdout.decode("utf-8")) if result.returncode == 0 else None


def _robust_row(robust: dict, spec_id: str, design: str = "holdout_fixed_origin") -> dict:
    rows = ((robust.get("designs") or {}).get(design) or {}).get("specifications") or []
    return next((row for row in rows if row.get("id") == spec_id), {})


def summarize(artifact: dict, robust: dict | None) -> dict[str, Any]:
    """The comparison items of one version, read from its artifact and robust evaluation."""
    robust = robust or {}
    sample = artifact["sample"]
    comparison = artifact["benchmark_comparison"]
    latest = artifact["latest_prediction"]
    features = {name: float(artifact["latest_feature_vector"][name]) for name in FEATURES}
    score, low, high = score_and_delta_band(artifact, features)
    table = artifact["model"].get("coefficient_table", {})
    holm_significant = [name for name in FEATURES if (table.get(name) or {}).get("p_value_holm", 1.0) < ALPHA]
    checks = artifact.get("robustness_checks", {}).get("checks", [])
    comparable = [c for c in checks if robustness_check_is_comparable(c)]
    below_one = [c["specification_id"] for c in comparable if c.get("benchmark_conclusion") == "Model beats Hold"]
    main = _robust_row(robust, "M0")
    boot = main.get("bootstrap_rmse_ratio_vs_hold") or {}
    stability = artifact["diagnostics"].get("parameter_stability", {})
    return {
        "usable_n": sample["usable_n"], "dropped_n": sample["dropped_n"],
        "estimation_n": sample["estimation_n"], "estimation_start": sample["estimation_start"],
        "estimation_end": sample["estimation_end"],
        "holdout_n": sample["holdout_n"], "holdout_start": sample["holdout_start"], "holdout_end": sample["holdout_end"],
        "latest_decision": latest["date"], "headline_score": latest["expected_score"],
        "headline_band_low": max(-1.0, low), "headline_band_high": min(1.0, high),
        "next_probabilities": latest["class_probabilities"],
        "rmse_model": comparison["model"]["rmse"], "rmse_hold": comparison["benchmark_always_hold"]["rmse"],
        "rmse_ratio": comparison["rmse_ratio_model_to_hold"], "winner": comparison["winner"],
        "rmse_ratio_ci_low": boot.get("ci_low"), "rmse_ratio_ci_high": boot.get("ci_high"),
        "dm_p": (main.get("dm_squared_error_vs_hold") or {}).get("p_value"),
        "rps": {key: _robust_row(robust, spec).get("rps") for key, spec in
                (("model", "M0"), ("always_hold", "B0"), ("class_frequency", "B1"), ("persistence", "B2"))},
        "joint_lr_p": artifact["diagnostics"]["joint_slope_lr"]["p_value"],
        "holm_significant_slopes": holm_significant,
        "stability_p": stability.get("p_value"), "stability_result": stability.get("pass_fail"),
        "robustness_comparable": len(comparable), "robustness_ratio_below_one": len(below_one),
        "robustness_ratio_below_one_ids": below_one,
    }


def rule_label(ratio: float) -> str:
    return ("meets the pre-specified criterion (RMSE ratio below 1)" if ratio < 1
            else "does not meet the pre-specified criterion (RMSE ratio not below 1)")


def change_sentence(old: dict | None, new: dict, ref: str) -> str:
    """The generated 'effect of the data update' sentence; it never claims that the model is better."""
    if not old:
        return f"Effect of the data update: UNKNOWN (the version at git tag {ref} could not be read)."
    text = (f"Effect of the data update (OLD = git tag {ref}, NEW = current files): usable decisions "
            f"{old['usable_n']} → {new['usable_n']}; estimation sample {old['estimation_n']} → {new['estimation_n']} "
            f"decisions (ending {old['estimation_end']} → {new['estimation_end']}); holdout {old['holdout_n']} → "
            f"{new['holdout_n']} decisions ({old['holdout_start']}–{old['holdout_end']} → {new['holdout_start']}–"
            f"{new['holdout_end']}). The holdout RMSE ratio changed from {old['rmse_ratio']:.3f} to "
            f"{new['rmse_ratio']:.3f}")
    if (old["rmse_ratio"] < 1) != (new["rmse_ratio"] < 1):
        text += (f", so the pre-specified rule's label changed from \"{rule_label(old['rmse_ratio'])}\" to "
                 f"\"{rule_label(new['rmse_ratio'])}\".")
    else:
        text += f"; the pre-specified rule's label is unchanged (\"{rule_label(new['rmse_ratio'])}\")."
    bounds = [old.get("rmse_ratio_ci_low"), old.get("rmse_ratio_ci_high"),
              new.get("rmse_ratio_ci_low"), new.get("rmse_ratio_ci_high")]
    if all(isinstance(value, (int, float)) for value in bounds):
        inside = all(lo <= r <= hi for r in (old["rmse_ratio"], new["rmse_ratio"])
                     for lo, hi in ((bounds[0], bounds[1]), (bounds[2], bounds[3])))
        text += (f" 95% bootstrap intervals: OLD {bounds[0]:.3f} to {bounds[1]:.3f}, NEW {bounds[2]:.3f} to "
                 f"{bounds[3]:.3f}" + ("; both ratios lie inside both intervals, so the change does not show that "
                                       "the model forecasts better or worse than before." if inside else "."))
    return text


def _f(value: Any, digits: int = 3) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _pct(probabilities: dict) -> str:
    return " / ".join(f"{name} {probabilities[name] * 100:.1f}%" for name in ("Decrease", "Hold", "Increase"))


def rows(old: dict | None, new: dict) -> list[tuple[str, str, str]]:
    def both(fn) -> tuple[str, str]:
        return (fn(old) if old else "UNKNOWN", fn(new))

    items = [
        ("Usable decisions (dropped)", lambda v: f"{v['usable_n']} ({v['dropped_n']})"),
        ("Estimation sample", lambda v: f"{v['estimation_n']}: {v['estimation_start']} to {v['estimation_end']}"),
        ("Holdout", lambda v: f"{v['holdout_n']}: {v['holdout_start']} to {v['holdout_end']}"),
        ("Latest decision in the data", lambda v: v["latest_decision"]),
        ("Headline score [95% band]", lambda v: f"{v['headline_score']:+.3f} [{v['headline_band_low']:+.3f}, "
                                                f"{v['headline_band_high']:+.3f}]"),
        ("Next-decision probabilities", lambda v: _pct(v["next_probabilities"])),
        ("Holdout RMSE model / Always Hold", lambda v: f"{_f(v['rmse_model'])} / {_f(v['rmse_hold'])}"),
        ("RMSE ratio (pre-specified verdict)", lambda v: f"{_f(v['rmse_ratio'])}: {rule_label(v['rmse_ratio'])}"),
        ("RMSE ratio 95% block-bootstrap interval", lambda v: f"{_f(v['rmse_ratio_ci_low'])} to {_f(v['rmse_ratio_ci_high'])}"),
        ("Diebold–Mariano p (squared error, HLN)", lambda v: _f(v["dm_p"])),
        ("RPS model / Always Hold / class frequencies / persistence (supplementary)",
         lambda v: " / ".join(_f(v["rps"][k]) for k in ("model", "always_hold", "class_frequency", "persistence"))),
        ("Joint LR test p (six slopes)", lambda v: _f(v["joint_lr_p"])),
        ("Slopes significant after Holm (5%)", lambda v: ", ".join(v["holm_significant_slopes"]) or "none"),
        ("Parameter stability LR", lambda v: f"p {_f(v['stability_p'])} ({v['stability_result']})"),
        ("Comparable robustness checks with RMSE ratio below 1",
         lambda v: f"{v['robustness_ratio_below_one']} of {v['robustness_comparable']} "
                   f"({', '.join(v['robustness_ratio_below_one_ids']) or 'none'})"),
    ]
    return [(label, *both(fn)) for label, fn in items]


def render_markdown(result: dict) -> str:
    lines = ["# OLD vs NEW after the data update", "",
             f"OLD: git tag `{result['old_ref']}` (`model/artifact.json`, `model/robust_eval.json` read with `git show`). "
             "NEW: the current files. Every value is read from these files by `python run.py compare`; nothing is "
             "typed. Robustness counts use the comparable checks only (binary-target checks are left out) in both "
             "versions. RPS is supplementary; the verdict is the pre-specified RMSE-ratio rule.", "",
             "| Item | OLD | NEW |", "|---|---|---|"]
    lines += [f"| {label} | {old} | {new} |" for label, old, new in rows(result["old"], result["new"])]
    lines += ["", result["sentence"], "", "Generated by `python run.py compare` (src/compare.py).", ""]
    return "\n".join(lines)


def run(artifact_path: Path = ARTIFACT_PATH, robust_path: Path = ROBUST_PATH, json_path: Path = JSON_PATH,
        md_path: Path = MD_PATH, ref: str = COMPARE_TAG) -> dict[str, Any]:
    new = summarize(json.loads(Path(artifact_path).read_text(encoding="utf-8")),
                    json.loads(Path(robust_path).read_text(encoding="utf-8")) if Path(robust_path).is_file() else None)
    old_artifact = _git_show(ref, "model/artifact.json")
    if old_artifact is not None:
        old = summarize(old_artifact, _git_show(ref, "model/robust_eval.json"))
        source = "git"
    elif JSON_PATH.is_file():
        old = json.loads(JSON_PATH.read_text(encoding="utf-8")).get("old")
        source = "committed model/version_comparison.json (git not available)"
    else:
        old, source = None, "unavailable"
    result = {"generated_by": "python run.py compare", "old_ref": ref, "old_source": source,
              "old": old, "new": new, "sentence": change_sentence(old, new, ref)}
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    Path(md_path).parent.mkdir(parents=True, exist_ok=True)
    Path(md_path).write_text(render_markdown(result), encoding="utf-8", newline="\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", default=COMPARE_TAG, help=f"git ref of the OLD version (default {COMPARE_TAG})")
    args = parser.parse_args(argv)
    result = run(ref=args.ref)
    text = render_markdown(result)
    try:
        print(text)
    except UnicodeEncodeError:  # Windows consoles with a legacy code page
        print(text.encode("ascii", "replace").decode("ascii"))
    print(f"Wrote {MD_PATH.relative_to(ROOT)} and {JSON_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
