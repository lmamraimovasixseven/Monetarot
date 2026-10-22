# AI use disclosure

## Summary

We used AI tools to build this project. Below we list every tool, what it did and when we used it. We chose the topic, the data and the methods, and we are responsible for the result. The AI tools wrote most of the code and drafted most of the documents in `docs/`. We checked the sources and the references ourselves, and we wrote the technical note ourselves.

| Tool | What it did | When | Notes |
|---|---|---|---|
| Codex | First stage: reorganised the data folders, wrote the data cleaning code, and built the first version of the model and the website from our prompts. | UNKNOWN | Version UNKNOWN |
| GitHub Copilot, agent mode | Second stage, after Codex reached its usage limit: added more robustness checks (including the differenced-factors check RB09). | 2026-10-16 to 2026-10-17 | Version UNKNOWN |
| Claude Code in VS Code | Third stage: wrote the one-command start (`run.py`), the acceptance tests, the replication check (`src/check.py`), the reports and figures, the form for source facts, the README and the documents in `docs/`. | 2026-10-17 to 2026-10-19 | Version UNKNOWN |
| Claude, chat interface | Wrote and reviewed the prompts we sent to the coding assistants, explained the assignment, compared the project with the grading rubric, and helped organise the provenance and the documents. It suggested the wording of the mechanisms in `docs/model_spec.md`, the "new element" sentence, the planned claims for the references and additions to the demo questions, and it looked up the abstracts of the five references on RePEc (it did not read the full texts). In the chat session it also unpacked a copy of the project in its own sandbox, installed the requirements and ran the checks and the website there to verify them; it did not change the repository. | 2026-10-16 to 2026-10-19 | Version UNKNOWN |
Persons responsible for checking AI output: Linara Mamraimova and Darina Baikazakova

## What we did ourselves

- We chose the topic: NBK base-rate decisions. The course instructor suggested this idea at a lecture on 2026-10-07; there is no written proof of this suggestion.
- We chose the data series and extracted the CSV files in `data/raw/` by hand from the downloaded Excel files.
- We found the sources and wrote down their titles, links, publication dates, units and download dates (`docs/facts_to_fill.csv`).
- We decided which tests and which regression to use, guided by our literature review, which we wrote ourselves.
- We accepted option 1 (direction flag) as the decision rule after the chat assistant compared the three options.
- We read and reviewed the results.
- We supplied the five references (`docs/references.md`) from our literature review and checked that they exist and that their DOIs work. We also confirm, by opening the papers, the abstract checks recorded in `docs/references.md`.
- We wrote the technical note (Word file) ourselves.

## What the AI did

- The coding assistants wrote the code: data pipeline, model and diagnostics, the website, tests and checks. We asked for it step by step with prompts.
- The chat assistant helped us write those prompts, read the assignment, audit the project against the rubric, and draft some wording (see the table above).
- The assistants drafted most of the documents in `docs/`, and we reviewed and edited them. The facts we typed into `docs/facts_to_fill.md` and `docs/facts_to_fill.csv` are ours; the technical note is ours; the literature review is ours. All other documents in `docs/` were drafted by the assistants.

## The main prompts

The full text of every prompt and answer is in the chat export attached to this project. In short, the main prompts were:

1. Project rules (`AGENTS.md`): never invent numbers or sources, never edit raw data, keep estimation and the website separate, record all random seeds, report failures honestly.
2. Reorganise the repository and rebuild the processed data from the raw files by code only.
3. Build the model and write all results into `model/artifact.json`; build the website so it only reads that file.
4. Add falsification verdicts and robustness checks, and report the ones that fail.
5. Automate the ten acceptance checks, add a one-command start, an offline mode and a replication check.
6. Generate every table and figure for the note by code into `outputs/`, and rewrite the README.
7. Record the sources, dates, units and references in the repository.
8. Fill the decision rule, the release-lag limitation, the mechanisms, the new-element sentence and the reference checks in the project forms, and verify every claim against the repository first.

## Suggestions we rejected or changed

- We did not like the first design of the website and asked for a clearer one: probabilities in percent, the verdict on top, no large "DECREASE" label.
- The first multiple-testing correction covered the whole run and made a joint test look failed. We asked for it to be redefined for separate groups of tests.
- The first version showed "source unreachable" without making a real request. We asked for a real attempt with a short time limit, or a clear message when no source is configured.
- The "Always Hold" log score was shown as infinity. We replaced it with "undefined" and a note.
- A wrong download link for the consumption series and a wrong claim that it was an annual series were corrected after we checked the source page.
- We kept the main model as it was and did not replace it with the differenced version, because that version looked better on the holdout. It stays as a robustness check.
- The chat assistant first gave possible explanations for the negative signs of imports, corporate lending and consumption. We removed them, because those coefficients are not significant and we do not interpret them.
- The chat assistant first called the household lending result "borderline under a stricter correction" without running any such check. We removed this and wrote that no correction beyond Holm was run.
- The chat assistant's first "new element" sentence (a decision-rule panel and automated checks) did not match the assignment's definition, and its second version credited ordered-outcome models to papers we had not yet checked. We replaced it after the abstracts were looked up.

## How we checked the work

Checks by people:
- We opened the source pages and wrote down titles, publication dates, units and download dates.
- We opened the five references and checked that they exist. The assistant looked up their abstracts; we confirm them by opening the papers.
- We read the results on the website and in the tables.

Automated checks (these run code against code and data; they do not replace a human review):

| Check | What it does |
|---|---|
| `python run.py test` | Unit, integration and acceptance tests; the run fails if any test changes repository files. |
| `python -m src.check` | Re-runs the data and model steps in a temporary folder and compares every number, figure and generated file with the committed ones, within the tolerance stored in `model/artifact.json`. |
| `python scripts/clean_install_check.py` | Creates a fresh virtual environment from the README steps, installs the requirements and starts the site. |
| `python scripts/scan_secrets.py` | Scans the repository and its history for secrets and personal data. |

## Where AI-written code lives

| Location | What it contains |
|---|---|
| `src/` | Data pipeline (`ingest.py`), model (`model.py`), website (`app.py`), reports and README (`report.py`, `readme.py`), source facts (`facts.py`), replication check (`check.py`), and the older classifier modules. |
| `tests/` | The pytest suite and the acceptance checks. |
| `scripts/` | The clean-install check and the secret scan. |
| `run.py`, `Makefile` | The single entry point and the targets that call it. |
| `docs/templates/`, `docs/README.template.md` | Templates used to generate documents. |

Which assistant wrote which file: Codex wrote the first data code, model and website files (`src/ingest.py`, `src/hashing.py`, `src/model.py`, `model/artifact.json`, `src/app.py`); Copilot added robustness checks in `src/model.py` and `outputs/robustness_table.md`; Claude Code wrote the rest. This is our reading of the chat history; the commit history (`git log`) shows the details.

## Responsibility for numbers and references

- Every number in the technical note comes from `outputs/numbers_for_note.json`, where each number records its source in `model/artifact.json`.
- We are responsible for checking every number and every reference in the note. The automated checks do not replace that.

## Statement

We confirm that the topic, the choice of data, the methods and the interpretation of the results are our own decisions, that the AI tools listed above wrote most of the code, drafted most of the documents and helped with prompts, that all use of AI is listed in this file, and that we are responsible for everything in this repository.

Linara Mamraimova, SixSeven, 2026-10-19
Darina Baikazakova: SixSeven, 2026-10-19

Клянусь всем чем можно сами все писали ничего не придумывали, поверьте плиз мы очень старались
