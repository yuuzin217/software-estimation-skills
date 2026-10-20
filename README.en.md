# software-estimation-skills

**Language:** [日本語](README.md) | **English**

Agent Skills for estimating software development **effort, cost, and schedule** from requirements. You can create a traceable estimate with a work breakdown structure (WBS) and explicit assumptions even without past project data. When comparable historical data becomes available, the same workflow can use it as the primary estimation method.

An LLM helps decompose requirements and propose optimistic, most-likely, and pessimistic effort values. A Python standard-library calculator validates inputs and performs the arithmetic using decimal numbers.

## Goals

Make it possible to trace:

- Which requirement and WBS task contributed to an estimate
- How the three-point inputs produced the PERT expected effort
- Whether each value is backed by a source, historical evidence, an assumption, or an AI estimate
- Whether cost or duration was calculated, or withheld because necessary inputs were missing

## Why this exists

Unfounded “standard effort” values and arbitrary risk multipliers can make estimates misleading. Likewise, published statistics are not automatically representative of a different project. This repository preserves uncertainties and unestimated work, and does not silently substitute unrelated external benchmarks for calculated effort.

## Skills

| Skill | Purpose |
| --- | --- |
| `software-estimation` | Entry point: selects the estimation approach and presents the result |
| `cold-start-estimation` | WBS and bottom-up three-point estimates when suitable historical data is unavailable |
| `historical-estimation` | Validates CSV/JSON history and scales effort using comparable projects |

The authoritative skill definitions live in `.agents/skills/`; copies are not maintained in `.cursor/skills/` or `.codex/skills/`. Cursor and Codex can discover this layout as described by their respective documentation.

A skill's instructions can be read independently, but **calculations require the repository-level `estimator` Python package**. Copying a skill directory alone is insufficient.

## Estimation workflow

1. Classify requirements into features, non-functional requirements, exclusions, unknowns, and assumptions.
2. Build a WBS for the applicable phases; not every phase is mandatory.
3. For each task, supply optimistic (O), most-likely (M), and pessimistic (P) effort.
4. Calculate the PERT expected value: `E = (O + 4M + P) / 6`. This is **not** a guarantee or a confidence interval.
5. Without usable history, use `cold-start` as the primary method.
6. If at least three historical projects are comparable in scope, phases, size metric, and other required conditions, `historical` can become the primary method. Do **not** add historical and WBS totals together.
7. Otherwise, retain `cold-start`; qualifying history may be auxiliary evidence, but dissimilar records must not be adjusted into eligibility without justification.
8. Use published statistics only for cross-checks when development type, units, phases, and population match. They never replace or add to the planned effort.

The thresholds of **three records**, **0.60 similarity**, **0.50 phase overlap**, and **2× maximum size ratio per historical record** are **this project's policies**, not IPA or CoBRA standards. For details, see [estimation methods](docs/method.md) (Japanese) and [calculation rules](.agents/skills/software-estimation/references/calculation-rules.md) (Japanese).

## Installation

Python **3.11+** is required. No additional runtime packages or network services are needed.

```bash
git clone https://github.com/yuuzin217/software-estimation-skills.git
cd software-estimation-skills
python -m estimator --help
```

## Estimate directly from a documentation folder (recommended)

Put your requirements, screen specifications, architecture diagrams, API specifications, and other project documentation in one folder. **Give the folder path to Codex or Cursor** to request an estimate—there is no need to prepare the calculator's JSON input yourself.

For example, open this repository in Codex and ask:

```text
Use the software-estimation skill to estimate development effort from
/Users/me/work/project-docs/.
Do not modify the source documents. Provide the estimate and a source inventory.
```

To try this workflow without your own documents, use the fictional folder `examples/folder-input-demo/`:

```text
Use software-estimation to estimate examples/folder-input-demo/.
```

The agent inventories readable files recursively, identifies requirements and uncertainty, and prepares `request.json`. **Python remains responsible for the calculations.** By default, generated artifacts go into this repository (not into the supplied documentation folder):

```text
.estimates/<source-folder-name>/
├── request.json     # Structured input drafted by the agent
├── sources.md       # Document inventory, citations, conflicts, unread sources
├── estimate.json    # Canonical estimate result
├── estimate.md      # Human-readable estimate report
└── wbs.csv          # WBS details
```

`.estimates/` is excluded from Git. Existing outputs are preserved unless the user requests an overwrite. The source folder is treated as read-only; sensitive data must not be copied into generated artifacts.

**Requirements and limitations:** The agent must have access to the source folder and this repository's `estimator` package. Reading PDFs, Word/Excel files, scans, and diagrams depends on what the agent environment can actually read. Inaccessible or unsupported files must be disclosed rather than treated as reviewed. Uncertain requirements stay explicit; estimates are not guaranteed.

**Note:** `python -m estimator calculate --input /path/to/folder` is **not** supported. Folder discovery and extraction are done by the agent, which passes the generated `request.json` to the existing Python CLI. See the [folder input workflow](.agents/skills/software-estimation/references/folder-input.md) (Japanese) for the detailed procedure.

## Using the skills in Cursor

The repository places each `SKILL.md` under `.agents/skills/`, following [Cursor's Agent Skills documentation](https://cursor.com/docs/skills). In Cursor, ask the agent to estimate a Markdown/text requirement specification or select the skill from the `/` menu when available.

Example:

```text
Use the software-estimation skill to estimate the input in
examples/case-e-missing-rate/request.json.
```

The agent prepares the request JSON. Run the calculator from the repository root:

```bash
python -m estimator calculate \
  --input request.json \
  --json-output estimate.json \
  --output estimate.md \
  --csv-output wbs.csv
```

Use the result only if the process exits with code 0. `estimate.json` is the structured source of truth; the Markdown and CSV render the **same calculated result**.

For PDF or Word input, rely on the agent's document-reading capability to extract text; this repository does not ship a document parser.

**Verification limit:** Frontmatter validation and CLI calculations have been exercised, but interactive skill discovery and invocation in Cursor have not been independently verified here.

## Using the skills in Codex

The skill layout under `.agents/skills/` also follows Codex's documented repository skill discovery. The calculation command is the same as for Cursor. Running the calculator does not require a network connection or non-standard runtime packages. Interactive invocation in Codex has not been verified here.

## Inputs and examples

The minimal schema example is at `.agents/skills/software-estimation/assets/request.minimal.json`. Seven end-to-end scenarios are in `examples/`:

| Directory | Scenario |
| --- | --- |
| `examples/case-a-new-web` | New web application without history; incompatible statistics are not applied |
| `examples/case-b-similar-history` | Three similar fictional records; historical estimation becomes primary |
| `examples/case-c-ambiguous` | Ambiguous requirements; unestimated tasks remain explicit and the estimate is partial |
| `examples/case-d-dissimilar-history` | Historical records exist but project types are too different to scale |
| `examples/case-e-missing-rate` | No labor rate or team size; effort only |
| `examples/case-f-non-functional` | Non-functional tasks and contingency are explicitly separated |
| `examples/case-g-enhancement` | Enhancement of an existing system, including impact analysis and regression tests |

Each directory includes a `scenario.md` describing expected behavior. Example history CSV/JSON files in `.agents/skills/historical-estimation/assets/` are **fictional**; do not use them to justify production estimates.

Example input fragment (see the complete case E request for all required fields):

```json
{
  "meta": {
    "system_name": "Add a field to an existing API",
    "effort_unit": "person_day"
  },
  "wbs": [
    {
      "id": "WBS-001",
      "optimistic": "1",
      "most_likely": "2",
      "pessimistic": "4",
      "basis": {
        "kind": "AI_ESTIMATE",
        "explanation": "Provisional values based on an analogous field addition"
      }
    }
  ]
}
```

Effort inputs must be integers or decimal **strings**; JSON floating-point numbers are rejected.

## Example outputs

Case E produces **2.17 person-days** of planned effort. Cost and duration are not calculated because labor rate and staffing information are missing. See [case E report](examples/case-e-missing-rate/estimate.md).

Case A produces **27.17 person-days** of planned effort and **JPY 2,173,333.33** using the explicitly provided JPY 80,000/person-day rate. The indicative lower bound on elapsed time is **22.64 days** using a team of two at 60% utilization, **not** a committed delivery date. Cost is derived from unrounded planned effort, not the displayed 27.17. The three-point values are provisional AI estimates, not IPA or industry standard productivity. See the [case A report](examples/case-a-new-web/estimate.md).

### Output files

| File | Contents |
| --- | --- |
| `estimate.json` | **Canonical structured result**, including scope, assumptions, requirements, WBS, O/M/P, PERT, coverage, risks, provenance, effort, cost, schedule, and historical selection decisions. `*_exact` values are unrounded. |
| `estimate.md` | Human-readable report with summary, assumptions, WBS, coverage, effort, cost, schedule, risks, exclusions, and re-estimation conditions |
| `wbs.csv` | Excel-friendly WBS details: IDs, phases, descriptions, three-point values, expected effort, units, status, provenance, uncertainty, adoption/cross-check role, and reasons for unestimated tasks |

The CSV column headers are Japanese, matching the current implementation:

| CSV columns | Meaning |
| --- | --- |
| `WBS ID`, `要件ID` | WBS and requirement IDs |
| `工程`, `作業名`, `作業内容` | Phase, task name, task description |
| `楽観工数`, `最頻工数`, `悲観工数`, `期待工数` | O/M/P and PERT display values, consistent with JSON |
| `工数単位`, `算定状態` | `person_day` / `person_hour`; estimated/unestimated |
| `根拠区分`, `算定根拠`, `不確実性` | Evidence category, explanation, uncertainty (`low` / `medium` / `high`) |
| `採用区分`, `未算定理由` | Used for the plan vs. cross-check only; why a task is not estimated |

CSV output is UTF-8 with a BOM to aid direct opening in Excel. CSV quoting preserves commas, quotes, and line breaks; it does **not**, by itself, prevent formula execution. Text fields whose first non-whitespace/control character is `=`, `+`, `-`, or `@` are prefixed with an apostrophe to reduce CSV formula-injection risk.

The CLI rejects output paths pointing to the input request JSON or its referenced `history.path` file, including relative and symlink aliases.

For `cold-start`, an estimate is considered complete only when functional and non-functional requirements map to estimable WBS tasks and no unestimated WBS tasks remain. Otherwise, the result is labeled **partial**, and total project cost and duration are withheld. When `historical` is primary, its project-wide estimate is separate from any cross-check-only WBS.

A historical record is accepted for scaling only if `project_scope` and the other comparability conditions match and its size is **within a factor of two of the target size**. Each record is checked individually. With fewer than three eligible records, `cold-start` remains primary. The factor-of-two rule is a project policy, **not** an IPA standard.

## Evidence and provenance

| Category | Meaning |
| --- | --- |
| `SOURCE` | Verifiable external source |
| `HISTORICAL` | Supplied development history |
| `ASSUMPTION` | Explicit assumption |
| `AI_ESTIMATE` | Provisional AI estimate; not a verified actual |

The calculator does not invent labor rates or assume 8 hours/person-day or 160 hours/person-month for conversions. If the required rate is missing, it does not produce a cost.

The productivity figures from IPA's *Software Development Data Analysis 2022* are available for conditional cross-checking only when measurement units, five development phases, type, size band, and data population are comparable. They do not affect planned effort, and IPA regression equations are not implemented. See [references](docs/references.md) (Japanese) and `estimator/data/benchmarks.json`.

## Limitations and safety

- Requirements decomposition and three-point ranges are supplied by the agent/user; the Python code validates and aggregates them but does not infer effort directly from arbitrary natural language.
- PERT expectations and optimistic/pessimistic ranges are not statistical prediction intervals.
- Historical estimates from fewer than 10 records remain provisional; fewer than 3 eligible records cannot become the primary method.
- Fictional history is for demonstrations; `allow_fictional` is not intended to justify real estimates.
- Never commit client secrets, personal data, or confidential project history to this repository.
- IPA's underlying enterprise-oriented data mainly covers fiscal years 2016–2021 and must not automatically be treated as representative of small cloud-native or AI-assisted projects.
- The repository is MIT-licensed. IPA and JISA retain copyright in their own materials; their PDFs are not bundled.
- Excel `.xlsx` and PDF generation, a dedicated natural-language parser, and critical-path analysis are out of scope.

## References

- [IPA Software Development Data Analysis 2022](https://www.ipa.go.jp/digital/software-survey/metrics/metrics2022.html)
- [IPA Software Development Estimation Guidebook](https://www.ipa.go.jp/archive/publish/secbooks20060425.html) (bibliographic reference; no reproduction)
- [IPA Software Improvement/Enhancement Estimation Guidebook](https://www.ipa.go.jp/archive/publish/secbooks20071025.html) (bibliographic reference only)
- [IPA CoBRA-Based Estimation Tool](https://www.ipa.go.jp/archive/digital/tools/cobra.html) (CoBRA itself is not implemented)
- [Agent Skills Specification](https://agentskills.io/specification)
- [Cursor Agent Skills](https://cursor.com/docs/skills)

The citation rationale, population restrictions, and reasons for not reproducing source materials are documented in [docs/references.md](docs/references.md) (Japanese).

## Development and tests

Run from the repository root:

```bash
python -m unittest discover -s tests -v
python -m estimator validate-skills
```

`validate-skills` checks skill frontmatter, the 500-line limit, and referenced files. It also runs the official validator if `skills-ref` is installed; otherwise that official check is skipped.

```bash
python -m pip install skills-ref==0.1.1
python -m estimator validate-skills
```

The latest PR test run reports **62 unit tests passed**, along with successful GitHub Actions validation including `skills-ref`. This does not verify live invocation in Cursor/Codex. The checked-in `estimate.md` and `estimate.json` examples are compared against freshly calculated results by tests; manually changing calculated values would cause those tests to fail.
