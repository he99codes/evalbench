# EvalBench — Project Overview

**What it is:** an AI response evaluation workbench. You submit a prompt and two candidate
responses (A and B). EvalBench extracts what the prompt actually requires, scores each
response independently against a shared rubric with quoted evidence, then produces a
pairwise preference, one concrete improvement suggestion, and a reward-mismatch check.

**Why it exists:** comparing AI outputs is mostly done by vibes. EvalBench mirrors the
methodology of real evaluation pipelines — understand the request first, judge both
answers against the *same* criteria, ground every judgment in evidence you can point at,
and double-check whether an apparent win actually satisfies the task.

---

## The philosophy

Every architectural choice follows from five principles:

### 1. Understand before you judge
The prompt is parsed into explicit requirements (requests vs. constraints) *before* any
scoring. An evaluator that doesn't know "under 120 words" or "never promise a timeline"
were required can't catch when a polished answer quietly ignores them.

### 2. Judge in isolation, compare after
Responses A and B are scored **independently** — each per-criterion call sees exactly one
response and never knows the other exists. Only after both are fully scored does a
separate pairwise stage compare them. This reduces contamination bias, where seeing a
stronger/weaker rival first skews the per-criterion scores.

### 3. Evidence or it didn't happen
Every criterion score must carry at least one quote that is a **verbatim substring** of
the response being judged. The backend locates each quote in the response text and stores
its character span. If an LLM returns a score with no verifiable evidence, the call is
rejected and retried — and if it never produces one, the whole run fails rather than
store an ungrounded number. A score without evidence is never persisted.

### 4. Never trust the LLM's math
The LLM proposes; code disposes. Overall scores are computed **deterministically** from
stored per-criterion scores and weights (`utils/scoring.py`):

```
overall = round( Σ normalize(score, scale_min, scale_max) × weight_share × 100 , 2 )
```

An LLM-reported aggregate or winner is never trusted. The stored rubric rows are always
visible — the percentage is never the only output.

### 5. Every run is reproducible
Each `evaluation_runs` row records: evaluator model, provider, a hash of the exact rubric
used (`rubric_version`), the prompt-template version, the randomized candidate order,
per-call raw outputs, token counts, and latency. Any past run can be audited or diffed
against another — that's what powers run history and evaluator agreement.

---

## The pipeline (5 stages, separate LLM calls — never combined)

```
                 prompt
                   │
        ┌──────────▼──────────┐
        │ 1. Requirement       │   Extract requests, constraints, format rules,
        │    extraction        │   and ambiguities from the prompt itself.
        └──────────┬──────────┘
                   │ requirements feed everything below
        ┌──────────▼──────────┐
        │ 2. Independent       │   One call per criterion per response.
        │    evaluation        │   8 criteria → 16 calls. A never sees B.
        │    (A ∥ B)           │   Each call: score + passed + reasoning + evidence
        └──────────┬──────────┘
                   │ (overall A / overall B computed in code here)
        ┌──────────▼──────────┐
        │ 3. Pairwise          │   Candidate order randomized (AB or BA) to
        │    comparison        │   control position bias; result mapped back to A/B.
        └──────────┬──────────┘
        ┌──────────▼──────────┐
        │ 4. Improvement       │   One specific, actionable edit for one response.
        └──────────┬──────────┘
        ┌──────────▼──────────┐
        │ 5. Compliance +      │   Each mandatory requirement checked per response;
        │    reward mismatch   │   mismatch flag computed deterministically.
        └─────────────────────┘
```

Stage 5 produces the **reward-mismatch** signal: the showcase detection of "reward
hacking" — when a response scores well on the rubric (tone! completeness!) while failing
the actual hard requirements (too long, promised a timeline it wasn't allowed to).
A run flags mismatch when:

- a response's overall score exceeds its mandatory-requirement compliance rate by ≥ 20
  points (`MISMATCH_GAP_THRESHOLD`), or
- the preferred (or higher-scoring) response satisfies *fewer* mandatory requirements
  than the loser.

The seeded demo deliberately shows this: Response A is fluent and warm but 170 words
(limit: 120) and promises "refunded within 3 business days" (explicitly forbidden). It
scores 87.8% on a polish-heavy rubric while satisfying only 66.7% of mandatory
requirements → flagged.

---

## The trust model — what's LLM vs. what's code

| Decision | Made by | Why |
|---|---|---|
| Requirement extraction | LLM | Understanding language is its job |
| Per-criterion score / pass / reasoning | LLM | Judgment call, but evidence-verified |
| Evidence acceptance | **Code** | Quote must exist verbatim in the response, else retry/fail |
| Overall scores | **Code** | Weighted aggregation, `scoring.py` |
| Tie threshold (±0.5 pt) | **Code** | `TIE_MARGIN` |
| Candidate ↔ A/B mapping | **Code** | De-anonymized after the comparison call |
| Compliance rate + mismatch flag | **Code** | From per-requirement checks |
| Run success/failure | **Code** | `FAILED` on unrecoverable error — never a fake success |

Retry semantics are typed, not vibes: timeouts/5xx/connection errors and malformed JSON
are retried (default 3 attempts), HTTP 429 gets its own larger budget (default 6) and
honors `Retry-After`, auth/bad-request errors fail immediately. Every retried error is
recorded on the run's `raw_output.calls[]` — the demo Groq run survived 15 rate-limit
retries this way.

---

## Data model

```
projects ──┬── criteria                (rubric library: name, weight, scale_min/max, enabled)
           └── evaluations ──┬── evaluation_criteria   (criteria + weights chosen FOR THIS eval)
                             ├── prompt_requirements    (extracted requests/constraints)
                             ├── evaluation_runs ──┬── evaluation_results ── evidence_items
                             │   (model, provider,      (per criterion ×     (verbatim quote +
                             │    rubric/prompt          response: score,     char-span location)
                             │    version, raw_output,   passed, reasoning)
                             │    candidate_order,      
                             │    tokens, latency)      
                             └── summary fields: status, preferred_response,
                                 overall_score_a/b, final_reasoning, improvement
```

Two deliberate additions beyond the original spec, approved because later phases can't
work without them: `evaluation_criteria` (a draft must remember which criteria it uses
and at what weights — project criteria are shared) and `evaluation_results.run_id`
(comparing two runs in Phase 9 requires each run's own scores).

Status lifecycle: `DRAFT → READY → RUNNING → COMPLETED/FAILED`. Editing content resets
the verdict (prompt change also drops extracted requirements); past runs are preserved.
Deleting a project cascades; deleting a criterion that's in use returns 409 — disable it
instead.

`raw_output` (JSONB) is the run's audit log: criteria snapshot, per-stage inputs/outputs,
every call's raw text/tokens/retries, progress, and error details. Ambiguities,
compliance checks, and the mismatch flag live here — queryable via Postgres JSONB
operators, no schema bloat.

---

## Running a run

`POST /evaluations/{id}/run` creates a `PENDING` run, marks the evaluation `RUNNING`,
and executes in a FastAPI background task with its own DB session. Progress
(`stage`, `completed_steps/total_steps`) is committed after every step so the UI can
poll. Results are written in **one transaction** at the end — partial results never
surface. On server restart, orphaned `PENDING`/`RUNNING` runs are marked `FAILED`.
Failed runs keep their partial audit trail and can be retried with a new run.

## Providers

`LLMProvider` is a protocol; business logic never touches a vendor SDK or URL:

- **`mock`** — deterministic, offline, zero cost. Parses the tagged prompt sections and
  applies transparent heuristics (length limits, negation detection, politeness markers,
  keyword coverage). Same input → same output, always. This is what tests use.
- **`openai_compatible`** — any OpenAI-compatible chat-completions endpoint (Groq, NVIDIA
  NIM, OpenAI). Strict `json_schema` structured output by default (`json_object`
  fallback). Configured entirely by env: `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`,
  `LLM_API_KEY`. Keys are backend-only — never exposed to the frontend.

## API (`/api/v1`)

| Endpoint | Purpose |
|---|---|
| `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}` | Project CRUD |
| `GET/POST /projects/{id}/criteria`, `PATCH/DELETE /criteria/{id}` | Rubric CRUD |
| `GET/POST /evaluations`, `GET/PATCH/DELETE /evaluations/{id}` | Evaluation CRUD |
| `POST /evaluations/{id}/analyze-prompt` | Stage 1 only (DRAFT → READY) |
| `POST /evaluations/{id}/run` | Start the 5-stage pipeline (async) |
| `GET /evaluations/{id}/runs`, `.../runs/{run_id}` | Run history + progress + raw audit |
| `GET /evaluations/{id}/report` | Full report (latest or `?run_id=`) |
| `GET /evaluations/{id}/agreement?run_1=&run_2=` | Compare two runs |
| `GET /projects/{id}/analytics` | Aggregate stats across the project |
| `GET /evaluations/{id}/export/json` | Download the report as JSON |
| `GET /health` | Liveness + DB connectivity + active provider |

## Frontend map

`/dashboard` — evaluations list + per-project analytics (preference counts, average
quality, compliance rate, reward-mismatch count, criterion pass-rate chart).  
`/evaluations/new` — prompt/A/B editors + criteria checklist with per-evaluation weights.  
`/evaluations/:id` — the report screen: run button with live progress, verdict banner,
mismatch warning, requirements checklist with per-response compliance, score matrix,
evidence panel, improvement card, run history, and run-vs-run agreement.  
`/projects/:id`, `/criteria` — rubric management. `/settings` — project management.

React renders what the API returns; no business logic client-side. TanStack Query polls
`GET /runs/{id}` while a run is active and invalidates on completion.

## Evaluator agreement

Two runs of the same evaluation (e.g. mock vs. Groq, or two rubric versions) can be
diffed: preference agreement, per-criterion score deltas (normalized across scales),
pass/fail agreement %, and an overall agreement figure — all computed from stored
results, nothing estimated. Run numbers are assigned by creation order.

## Testing

137 tests, ~97% coverage, run **inside the backend container** against a real Postgres
`evalbench_test` database (JSONB + native enums don't work on SQLite):

```powershell
docker compose exec backend pytest --cov=app
```

Covers: CRUD + validation rules, scoring edge cases (missing criterion, zero weights,
ties), requirement parsing, the full pipeline against the mock provider, evidence
grounding (duplicates, paraphrases), provider failures (timeout, 429, 5xx, malformed
JSON, auth), retry exhaustion → FAILED, reports, analytics, and agreement.

## Deliberate limitations (V1)

- **In-process background tasks** — no Celery/Redis/queues, per the constraints. A server
  restart marks in-flight runs FAILED rather than resuming them.
- **`sentence-transformers` not installed** — evidence grounding is exact-match +
  whitespace-tolerant regex, not semantic similarity. Deferred dependency.
- **No PDF export** — `export/json` exists; PDF was never specced into a phase.
- **No auth** — single-user workbench; CORS is configured but there's no login layer.
- **Single evaluation target** — pairwise (A vs B) only, not N-way tournaments.

## Config reference (`.env`)

| Var | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | `development` / `test` / `production` |
| `DATABASE_URL` | `postgresql+psycopg://…@localhost:5432/evalbench` | compose overrides host to `postgres` |
| `LLM_PROVIDER` | `mock` | `mock` or `openai_compatible` |
| `LLM_MODEL` | provider default | `openai/gpt-oss-20b` for Groq |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | any OpenAI-compatible endpoint |
| `LLM_API_KEY` | — | required for `openai_compatible`; backend only |
| `LLM_STRUCTURED_MODE` | `json_schema` | `json_object` fallback for weaker models |
| `LLM_TEMPERATURE` | `0` | deterministic evals |
| `LLM_TIMEOUT_SECONDS` | `60` | per-call timeout |
| `LLM_MAX_ATTEMPTS` / `LLM_RATE_LIMIT_MAX_ATTEMPTS` | `3` / `6` | retry budgets |
| `LLM_RETRY_BASE_DELAY_SECONDS` / `..._MAX_DELAY_SECONDS` | `1` / `30` | backoff bounds |
| `CORS_ORIGINS` | `http://localhost:5173` | comma-separated |
| `VITE_API_BASE_URL` | `http://localhost:8000` | the only frontend var; never secrets |

## File map

```
backend/app/
  main.py                    app, CORS, /health, exception handlers, run recovery
  api/v1/                    thin routes: projects, criteria, evaluations, reports
  core/                      config (pydantic-settings), database (engine/Base/mixins), logging
  models/                    SQLAlchemy: the 8 tables above
  schemas/                   Pydantic API contracts — strictly separate from models/
  services/                  project, criterion, evaluation (pipeline orchestration),
                             requirement (stages 1+5), comparison (stages 3+4),
                             evidence (grounding), report (report/analytics/agreement)
  providers/                 base (protocol, errors, retry wrapper), mock,
                             openai_compatible, factory in __init__.py
  utils/                     scoring.py (deterministic math), validation.py (LLM output contracts)
backend/migrations/          Alembic; single initial_schema revision
backend/tests/               137 tests, real Postgres _test DB
data/demo/                   refund_example.json + idempotent seed.py (seeds + runs the demo)
frontend/src/                pages, components (common/layout/evaluation), api/ wrappers,
                             hooks (TanStack Query), types, lib
docs/OVERVIEW.md             this file
docker-compose.yml           postgres:17 + backend (uvicorn --reload) + frontend (vite)
```

## One-line summary

> EvalBench treats LLM judgment like any untrusted oracle: extract the spec first, judge
> each candidate in isolation against a shared rubric, require verifiable evidence for
> every score, compute the verdict in deterministic code, flag when the rubric's reward
> diverges from real compliance, and record enough provenance to audit or reproduce any
> run — while a mock provider makes the whole thing work offline, deterministically,
> for free.
