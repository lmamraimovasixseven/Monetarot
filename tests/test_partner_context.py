"""D59: partner rates as context on corridor.html. Descriptive counts and spreads from stored files; nothing estimated.

Every assertion is a relation computed from the data, the extension files and the artifact (AGENTS.md rule 10).
"""

from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path

import pandas as pd
import pytest
from _tolerance import same_within_float_tolerance

from src import external_data, partner_context as pc, site_build, site_partners

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
STORED = json.loads((ROOT / "model" / "extensions" / "partner_context.json").read_text(encoding="utf-8"))
OVB = json.loads((ROOT / "model" / "extensions" / "ovb_check.json").read_text(encoding="utf-8"))
ARTIFACT = json.loads((ROOT / "model" / "artifact.json").read_text(encoding="utf-8"))
PAGE = (SITE / "corridor.html").read_text(encoding="utf-8")


def _text(fragment: str) -> str:
    plain = re.sub(r'<span class="gloss-tip"[^>]*>.*?</span>', "", fragment, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", plain))).strip()


def _leaves(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, f"{path}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{path}/{index}")
    else:
        yield path, value


# ----------------------------------------------------------------------------- the extension file

def test_committed_context_equals_a_fresh_build():
    assert same_within_float_tolerance(STORED, json.loads(json.dumps(pc.build())))


def test_context_is_kept_outside_the_artifact():
    assert "partner_context" not in ARTIFACT and not any(key.startswith("partner") for key in ARTIFACT)


def test_every_number_has_a_ledger_row():
    with (ROOT / "ledger" / "evidence_ledger.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["id"]: row for row in csv.DictReader(handle)}
    for path, value in _leaves(STORED):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            key = f"partners:{path.lstrip('/')}"
            assert key in rows, key
            assert float(rows[key]["value"]) == pytest.approx(float(value)), key
    assert "external:kz_export_shares_2025.csv" in rows


def _independent_groups(name: str) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """A second, loop-based implementation of the definitions in pc.DEFINITIONS."""
    raw = external_data.read_raw(name)
    value = raw.columns[1]
    stored = raw.dropna(subset=[value]).assign(date=lambda f: pd.to_datetime(f["date"])).sort_values("date")
    dates, values = list(stored["date"]), list(stored[value].astype(float))
    changes = [(dates[i], "rise" if values[i] > values[i - 1] else "cut") for i in range(1, len(values)) if values[i] != values[i - 1]]
    decisions = pd.read_csv(ROOT / "data" / "processed" / "nbk_decisions_clean.csv", parse_dates=["decision_date"]).sort_values("decision_date")
    window = pd.Timedelta(days=STORED["window_days"])
    days = list(decisions["decision_date"])
    matched: dict[pd.Timestamp, set[str]] = {}
    for when, direction in changes:
        after = [d for d in days if d > when]
        if after and after[0] - when <= window:
            matched.setdefault(after[0], set()).add(direction)
    sample = decisions[(decisions["decision_date"] - window >= dates[0]) & (decisions["decision_date"] <= dates[-1])]
    groups: dict[str, list[str]] = {g: [] for g in pc.GROUPS}
    for row in sample.itertuples():
        if row.decision_date in matched:
            directions = matched[row.decision_date]
            group = next(iter(directions)) if len(directions) == 1 else "mixed"
        elif any(row.decision_date - window <= when < row.decision_date for when, _ in changes):
            group = "change_matched_to_an_earlier_decision"
        else:
            group = "no_change_in_window"
        groups[group].append(row.decision)
    return sample, groups


@pytest.mark.parametrize("name", list(pc.PARTNERS))
def test_event_counts_follow_from_the_raw_files(name):
    entry = STORED["events"][name]
    sample, groups = _independent_groups(name)
    assert entry["sample"]["n"] == len(sample)
    assert sum(entry[group]["n"] for group in pc.GROUPS) == entry["sample"]["n"]  # the groups partition the sample
    for group, outcomes in groups.items():
        row = entry[group]
        assert row["n"] == len(outcomes)
        for cls, key in pc.OUTCOMES.items():
            assert row[key] == outcomes.count(cls), (name, group, key)
        assert row["increase"] + row["hold"] + row["decrease"] == row["n"]
        assert row["small_n"] == int(row["n"] < STORED["small_n_threshold"])
    assert entry["partner_changes_in_period"] == entry["partner_rises_in_period"] + entry["partner_cuts_in_period"]


def test_overall_outcome_distribution_is_every_nbk_decision():
    decisions = pd.read_csv(ROOT / "data" / "processed" / "nbk_decisions_clean.csv")
    overall = STORED["events"]["all_nbk_decisions"]
    assert overall["n"] == len(decisions)
    for cls, key in pc.OUTCOMES.items():
        assert overall[key] == int((decisions["decision"] == cls).sum())


def test_latest_values_are_the_last_stored_rows_and_the_corridor_real_rates():
    real = ARTIFACT["carry_corridor"]["partner_real_rates"]
    for name, (_, _, real_key) in pc.PARTNERS.items():
        raw = external_data.read_raw(name).dropna()
        assert STORED["latest"][name]["date"] == str(raw.iloc[-1, 0]) and STORED["latest"][name]["nominal"] == float(raw.iloc[-1, 1])
        if real_key:
            assert STORED["latest"][name]["real"] == pytest.approx(real[real_key])
        else:
            assert "real" not in STORED["latest"][name]  # no euro-area inflation is stored: nominal only
    decisions = pd.read_csv(ROOT / "data" / "processed" / "nbk_decisions_clean.csv").sort_values("decision_date")
    assert STORED["latest"]["nbk"]["rate"] == float(decisions["base_rate_after"].iloc[-1])


def test_spreads_are_nbk_minus_partner_in_the_stated_month():
    hist = pc.history()
    for name, entry in STORED["spreads"].items():
        i = hist["months"].index(entry["nominal_month"])
        assert entry["nominal"] == pytest.approx(hist["nbk"][i] - hist[name][i], abs=1e-6)
        if "real" in entry:
            j = hist["months"].index(entry["real_month"])
            assert entry["real"] == pytest.approx(hist["nbk_real"][j] - hist[f"{name}_real"][j], abs=1e-6)


def test_trade_shares_are_the_stored_file_and_the_sums_are_arithmetic():
    frame = pd.read_csv(ROOT / "data" / "raw" / "external" / "kz_export_shares_2025.csv")
    shares = {r.item.lower(): float(r.value) for r in frame.itertuples() if r.unit == "percent of exports"}
    trade = STORED["trade"]
    assert trade["shares_pct"] == shares and trade["named_partners"] == len(shares)
    assert trade["total_exports_mln_usd"] == float(frame.loc[frame["item"] == "Total exports", "value"].iloc[0])
    assert trade["sums_pct"]["russia_and_china"] == round(shares["russia"] + shares["china"], 1)
    assert trade["sums_pct"]["named_euro_area_partners"] == round(sum(shares[c.lower()] for c in pc.EURO_AREA_NAMED), 1)
    source = json.loads((ROOT / "config" / "external_sources.json").read_text(encoding="utf-8"))["context"]["kz_export_shares_2025"]
    assert source["url"].startswith("https://stat.gov.kz/") and source["retrieved"] and "primary source" in source["publisher"]


# ----------------------------------------------------------------------------- the page

def test_page_leads_with_the_model_check_in_the_existing_wording():
    lead = re.search(r'<p class="p-lead" id="partners-finding">(.*?)</p>', PAGE, re.S)
    assert lead and PAGE.index('id="partners-finding"') < PAGE.index("<h2")
    headline = _text(site_build.ovb_headline(site_build.Ledger()))
    assert _text(lead.group(1)).endswith(headline)
    assert html.escape(OVB["label"]) in PAGE


def test_menu_order_and_the_home_link():
    labels = [label for _, label in site_build.PAGES]
    hrefs = [href for href, _ in site_build.PAGES]
    assert hrefs[:5] == ["index.html", "forecasts.html", "corridor.html", "evidence.html", "methods.html"]
    assert labels[2] == "Russia, China, ECB"
    home = (SITE / "index.html").read_text(encoding="utf-8")
    link = re.search(r'<a class="r-link" href="corridor.html">.*?</a>', home, re.S)
    assert link and html.escape(site_build.DESCRIPTIONS["corridor.html"]) in link.group(0)
    nav = re.search(r'<nav aria-label="Site sections">(.*?)</nav>', PAGE, re.S).group(1)
    assert re.findall(r'href="([^"]+)"', nav) == hrefs


def test_sections_are_anchored_and_listed_on_the_page():
    ids = ["partners-trade", "partners-rates", "partners-spreads", "partners-mechanism", "corridor-history", "corridor-tool",
           "partners-model", "partners-events", "partners-limits"]
    positions = [PAGE.index(f'<h2 id="{i}"') for i in ids]
    assert positions == sorted(positions)
    onpage = re.search(r'<nav class="onpage".*?</nav>', PAGE, re.S).group(0)
    assert all(f'href="#{i}"' in onpage for i in ids)


def test_no_causal_wording_and_no_eighty_percent_claim():
    text = _text(PAGE).lower()
    assert not re.search(r"\b(controls?|determines?|drives?)\b", text)
    assert not re.search(r"80\s*%", text)


def test_controls_are_hidden_without_javascript_and_fallback_tables_are_present():
    for fig in ("px", "sx"):
        figure = PAGE.split(f'<figure id="{fig}"', 1)[1].split("</figure>", 1)[0]
        tools = re.findall(r'<div class="chart-tools"[^>]*>', figure)
        assert tools and all(t.endswith(" hidden>") for t in tools)
        assert '<details class="ptable">' in figure and figure.count("<tr>") - 1 == len(pc.history()["months"])
    assert '<div id="wi-picker" hidden>' in PAGE and 'id="wi-table"' in PAGE
    assert '<div class="chart-tools" id="ev-picker" role="group" aria-label="Partner shown" hidden>' in PAGE
    assert PAGE.count('class="ev-partner"') == len(pc.PARTNERS)


def test_chart_data_are_the_stored_series():
    hist = pc.history()
    data = json.loads(re.search(r'<figure id="px".*?<script type="application/json" class="pdata">(.*?)</script>', PAGE, re.S).group(1))
    assert data["months"] == hist["months"] and data["geom"] == site_partners.GEOM
    for key in ("nbk", *pc.PARTNERS):
        assert data["modes"]["nominal"][key] == [None if v is None else round(v, 3) for v in hist[key]]
    assert set(data["modes"]["real"]) == {"nbk", *(k for k in pc.PARTNERS if f"{k}_real" in hist)}


def test_ecb_slider_drives_only_its_readout_and_not_the_corridor():
    label = re.search(r"<label>ECB deposit rate[^<]*.*?</label>", PAGE, re.S).group(0)
    assert "not part of the corridor definition" in label and 'id="c-ecb"' in label
    app = (ROOT / "src" / "site_assets" / "app.js").read_text(encoding="utf-8")
    call = re.search(r"var res = corridor\((.*?)\);", app).group(1)
    assert "ecb" not in call.lower()
    assert 'byId("c-ecb")' in (ROOT / "src" / "site_assets" / "partners.js").read_text(encoding="utf-8")
    assert "c-ecb" not in app
    value = float(re.search(r'id="c-ecb"[^>]*value="([^"]+)"', PAGE).group(1))
    assert value == STORED["latest"]["ecb_deposit_rate"]["nominal"]


def test_what_if_rows_state_in_words_whether_the_interval_includes_zero():
    rows = re.findall(r"<tr><th>[^<]*point</th><td>[^<]*</td><td>(.*?)</td></tr>", PAGE.split('id="wi-table"', 1)[1], re.S)
    flags = [m["interval_includes_zero"] for e in OVB["partner_what_if"]["specifications"].values()
             for mv in e["moves"].values() for m in mv.values() if isinstance(m, dict)]
    assert len(rows) == len(flags)
    assert sum("the interval includes zero" in r for r in rows) == sum(flags)
    assert sum("the interval excludes zero" in r for r in rows) == len(flags) - sum(flags)
    section = PAGE.split('id="partners-what-if"', 1)[1].split("<h2", 1)[0]
    assert "exploratory, not used for the forecast" in section


def test_credit_constraint_statement_follows_the_artifact():
    identified = ARTIFACT["carry_corridor"]["credit_constraint"]["identified"]
    tool = PAGE.split('<h2 id="corridor-tool"', 1)[1].split("<form", 1)[0]
    assert "What-if on stated assumptions, not a model estimate" in tool
    assert ("credit constraint is not identified" in tool) == (not identified)


def test_partner_assets_load_only_on_the_corridor_page():
    for page in dict(site_build.PAGES):
        text = (SITE / page).read_text(encoding="utf-8")
        assert ("assets/partners.css" in text) == (page == "corridor.html"), page
        assert ("assets/partners.js" in text) == (page == "corridor.html"), page
