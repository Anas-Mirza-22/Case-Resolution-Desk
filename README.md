# Case Resolution Desk

A small full-stack app that lets a SkillBridge coordinator enter learner facts,
retrieve current policy with version awareness, get a **code-computed**
recommendation explained by an LLM, and persist the case with a review status.

> **Golden rule:** code decides, the LLM explains. The LLM can never change an
> outcome, status, threshold, or approval.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Stack](#stack)
3. [Setup](#setup)
4. [Run](#run)
5. [Environment variables](#environment-variables)
6. [Project structure](#project-structure)
7. [API routes](#api-routes)
8. [How the pipeline works](#how-the-pipeline-works)
9. [Retrieval approach](#retrieval-approach)
10. [Rules approach](#rules-approach)
11. [Tests](#tests)
12. [Manual results (Nadia and Sara)](#manual-results-nadia-and-sara)
13. [Acceptance cases A–D](#acceptance-cases-ad)
14. [LLM failure path](#llm-failure-path)
15. [Decisions that require human approval](#decisions-that-require-human-approval)
16. [Assumptions](#assumptions)
17. [Limitations](#limitations)
18. [Demo walkthrough (3–5 minutes)](#demo-walkthrough-35-minutes)

---

## What it does

A coordinator opens one page, enters case facts (unknowns allowed), asks a
natural-language question, and clicks **Analyze**. The backend:

1. validates the input,
2. retrieves the relevant current policy sections (version-aware),
3. evaluates thresholds and approval states in deterministic Python,
4. asks an LLM only to explain the code-computed outcome with source-grounded wording,
5. persists the case and its review status.

The UI shows:

- **Verdict** badges — `eligible` / `ineligible` / `pending`, plus a submission
  hold (`none` / `secret_found` / `missing_readme` / …).
- **Next step** badge — who has to act (`Next: Mentor`, `Next: Learner`,
  `Next: Reviewer`, `Next: Coordinator`, `Done`).
- An LLM-written explanation of the code outcome.
- Sources with IDs and versions (`KB-02 v3`), with a `SUPERSEDED` tag on KB-05.
- Missing facts, one primary next action, and all other blockers.
- A code-generated case note (never LLM-authored) for the audit trail.

Cases are reopenable from the History list.

---

## Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, stdlib `sqlite3`.
- **Retrieval:** scikit-learn TF-IDF over policy chunks (no embeddings, no vector DB).
- **LLM:** Groq (free tier) via `httpx`, called from the server only.
- **Frontend:** plain HTML/JS/CSS served from the same origin by FastAPI.
- **Tests:** pytest.
- **No paid services, no auth, no deployment, no agent framework.**

---

## Setup

```bash
cd case-resolution-desk

# 1. Virtual environment
python3.12 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate

# 2. Dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 3. Environment file
cp .env.example .env                # then edit .env and set GROQ_API_KEY

# 4. Policy files
# Copy the five KB files unchanged into backend/policies/:
#   backend/policies/KB-01.md
#   backend/policies/KB-02.md
#   backend/policies/KB-03.md
#   backend/policies/KB-04.md
#   backend/policies/KB-05.md
```

**Note:** run tests with `python -m pytest` (not the bare `pytest` command)
so they always execute under the active virtual environment's interpreter.

---

## Run

```bash
uvicorn backend.app:app --reload --port 8000
# open http://localhost:8000
```

Startup log should show:

```
INFO ... Loaded 45 policy chunks from /.../backend/policies
```

Quick health check:

```bash
curl -s http://localhost:8000/api/health
# {"status":"ok","llm_configured":true,"policies_loaded":45,"detail":{}}
```

The app runs without an LLM key. In that case, the code-computed result is
still shown and a readable `llm_error` appears beside it; the case is still
saved.

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | *(empty)* | Server-side LLM key. Never sent to the frontend. |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Model ID. **Override this** if your account does not have the default model. |
| `GROQ_TIMEOUT_SECONDS` | `20` | LLM request timeout. |
| `POLICIES_DIR` | `backend/policies` | Policy corpus location. |
| `DB_PATH` | `backend/data/cases.db` | SQLite file. |

**Model note:** `llama-3.1-8b-instant` was not available on the demo account
used for this build. We verified the account's available models via
`GET https://api.groq.com/openai/v1/models` and set `GROQ_MODEL` to a model
that supports `response_format: json_object` (for example `openai/gpt-oss-20b`).
Verify your own account before starting.

**Key note:** an empty `GROQ_API_KEY` (or a value that is only the `gsk_`
prefix) is treated as **not configured**; the app falls back to the readable
`llm_error` path instead of sending a bad key to the provider.

---

## Project structure

```
case-resolution-desk/
├── backend/
│   ├── __init__.py
│   ├── app.py            # FastAPI app, routes, static mount, error handlers
│   ├── config.py         # env-based settings (single place for env access)
│   ├── constants.py      # thresholds, enums, statuses, timezone, paths
│   ├── models.py         # Pydantic v2 request/response models + validation
│   ├── rules.py          # pure functions: tri-state checks, extension, outcome, status
│   ├── retrieval.py      # load/parse policies, chunk by "## ", TF-IDF, version filter
│   ├── llm.py            # Groq client, prompt build, JSON parse, safe errors
│   ├── service.py        # orchestration: validate → retrieve → evaluate → explain → persist
│   ├── db.py             # SQLite access (parameterized SQL only)
│   ├── policies/         # KB-01.md … KB-05.md (copy unchanged)
│   ├── data/             # runtime SQLite file (git-ignored)
│   └── tests/
│       ├── test_thresholds.py   # 3 tests: 79.9 vs 80, 69 vs 70, 2 vs 3 sessions
│       └── test_approval.py     # 5 tests: unknowns, request ≠ approval, secret hold
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## API routes

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/cases` | Create + analyze a case (201). |
| `GET` | `/api/cases` | List cases, newest first. |
| `GET` | `/api/cases/{id}` | Full case detail (404 if missing). |
| `GET` | `/api/health` | Health + LLM-configured + policy count. |
| `GET` | `/` | Serves the frontend. |
| `/static/*` | — | Frontend assets. |

### Example request

```json
POST /api/cases
{
  "learner_name": "Nadia",
  "question": "Can I still receive a certificate, and can I submit my capstone one day late?",
  "assessed_on": "2026-10-07",
  "attendance_pct": 76,
  "live_sessions": 2,
  "capstone_score": null,
  "submission_state": "unknown",
  "extension_state": "requested_pending",
  "extension_requested_at": "2026-10-07T11:00:00+05:00",
  "medical_note": "offered_unverified",
  "makeup_state": "none",
  "missed_session_date": null,
  "learner_notes": "A colleague sent an older policy saying 60 is enough to pass."
}
```

### Example response (abridged)

```json
{
  "id": 1,
  "outcome": {
    "eligibility": "ineligible",
    "submission_hold": "unknown",
    "requirement_results": [
      {"name": "attendance", "met": false, "detail": "Recorded attendance 76% is below the 80% threshold."},
      {"name": "live_sessions", "met": false, "detail": "2 completed live session(s) are below the minimum of 3."},
      {"name": "capstone", "met": null, "detail": "Capstone score is unknown; certification remains pending."}
    ],
    "extension": {"state": "requested_pending", "timely": true, "due_date": "2026-10-09T17:00:00+05:00"},
    "due_date": "2026-10-09T17:00:00+05:00"
  },
  "status": "Waiting for Mentor",
  "next_action": "Route the timely extension request to the mentor for a recorded decision; the standard due date remains in force until approval.",
  "citations": [
    {"doc_id": "KB-01", "version": "v2"},
    {"doc_id": "KB-02", "version": "v3"},
    {"doc_id": "KB-05", "version": "v1", "superseded": true}
  ],
  "llm_error": null
}
```

All errors use the same shape:

```json
{ "error": { "code": "not_found", "message": "Case 42 not found." } }
```

Validation errors return a 422 with field-level readable messages.

---

## How the pipeline works

```
Case entry (unknowns allowed)
   ↓
Validate  ── impossible number (attendance 140, score 110) ──► 422, nothing saved
   ↓
Retrieve  ── version-aware chunks effective on the case date
   ↓
Evaluate  ── code computes tri-state results (no guessing)
   ↓
Explain   ── LLM writes a grounded explanation of the code outcome
   │          └─ provider failure → readable llm_error, answer empty, continue
   ↓
Persist   ── always save: outcome, status, next action, citations, case note
   ↓
Review    ── UI shows everything; if llm_error, show it beside the result
```

The LLM step happens **after** the verdict is fixed. Structurally, the model
cannot change the outcome — it only receives a pre-computed result to explain.

---

## Retrieval approach

- Each `KB-*.md` file is parsed for `Document ID`, `Version`, `Effective date`,
  and `Status`, then split on `## ` headings. Every chunk carries that metadata.
- A TF-IDF index (scikit-learn, unigrams + bigrams) ranks chunks for the query.
- **Version-aware:** only documents whose `effective_date <= assessed_on` are
  eligible for decisions. A case dated before 1 Oct 2026 would not see KB-02 v3.
- **Superseded handling:** KB-05 chunks are only included when the question or
  notes reference the old policy (keywords: "60", "old policy", "colleague",
  "superseded", "18:00"). They are always labelled `SUPERSEDED` in the UI.
- **Mandatory sources:** the retriever adds rule-driven sources by keyword
  (attendance/sessions/makeup/medical → KB-01; capstone/extension/deadline →
  KB-02; submission/secret/README → KB-03; workflow → KB-04) so grounding never
  depends on TF-IDF ranking alone.
- **Citation validation:** after the LLM responds, any citation whose
  `(doc_id, version)` isn't in the retrieved excerpts is dropped.

---

## Rules approach

`backend/rules.py` is pure: no I/O, no clock calls, no LLM, no DB. Inputs in,
structured results out.

**Thresholds (KB-01, KB-02 v3):**
- Attendance ≥ 80, no rounding. `79.9` fails, `80` passes.
- Live sessions ≥ 3. `2` fails, `3` passes.
- Capstone ≥ 70. `69` fails, `70` passes.

**Unknowns:** values are `None`. They are never converted to 0 or assumed
sufficient. An unknown capstone keeps certification pending.

**Eligibility precedence:**
1. Submission has a secret → **ineligible**, no pass decision.
2. Any confirmed unmet requirement → **ineligible**.
3. Missing facts or pending submission issue → **pending**.
4. All met + submission safe → **eligible** (human review; never a certificate).

**Extension (KB-02 v3):**
- Request must be strictly before the deadline (9 Oct 2026, 17:00 PKT).
- Mentor approval must be recorded. A request alone keeps the standard due date.
- Approved extension ends Monday 12 Oct 2026, 17:00 PKT (business days Mon–Fri).
- A request at or after the deadline gets no automatic extension; the case is
  routed for human review without promising acceptance.
- A naive timestamp is treated as indeterminate; the standard due date remains.

**Makeup (KB-01):**
- Requires mentor approval and the missed-session date.
- A request is not a completed session; the session count does not change until
  a completed makeup is recorded.

**Status priority (KB-04):**
- Mentor blocker (extension or makeup pending) → `Waiting for Mentor`.
- Else learner blocker (missing facts, submission hold, medical unverified) →
  `Waiting for Learner`.
- Else eligible → `Ready for Review`.
- Else → `Open`.
- `Closed` is never set automatically.

**Verdict vs status:** the *verdict* answers "what do the current facts say?"
The *status* answers "whose turn is it to act?" They are separate concepts and
are shown as separate badges. The same status can apply to two different
verdicts (e.g. an eligible and an ineligible case may both be waiting on the
mentor for an extension decision).

---

## Tests

```bash
python -m pytest backend/tests/test_thresholds.py -v
python -m pytest backend/tests/test_approval.py -v
```

Expected:

- `test_thresholds.py` → **3 passed**
  - `test_attendance_no_rounding` — 79.9 vs 80
  - `test_capstone_threshold` — 69 vs 70
  - `test_live_sessions_threshold` — 2 vs 3
- `test_approval.py` → **5 passed**
  - `test_unknown_values_are_pending_not_zero`
  - `test_extension_request_is_not_approval` (aware timestamp, pending approval)
  - `test_extension_request_with_naive_timestamp_is_indeterminate`
  - `test_approved_extension_ends_monday`
  - `test_secret_hold_blocks_pass`

Both suites are deterministic and network-free.

---

## Manual results (Nadia and Sara)

Verified in the running app.

- **Nadia** — 76%, 2 sessions, capstone unknown, medical note offered but
  unverified, extension requested at 11:00 PKT on 7 Oct but not approved.
  - Verdict: **ineligible** on the current record.
  - Submission hold: **none** (submission state unknown).
  - Next step: **Next: Mentor** (extension approval is outstanding).
  - Due date: **Fri 9 Oct 2026, 17:00 PKT** (standard, since the extension is
    not approved).
  - Citations: **KB-01 v2**, **KB-02 v3**, **KB-05 v1 (SUPERSEDED)**.

- **Sara** — 85%, 3 sessions, capstone 65, claims the old 60-point rule.
  - Verdict: **ineligible** (65 < 70 under KB-02 v3).
  - Next step: **Next: Coordinator** — no approval pending; the case is ready
    for human handling of the dispute.
  - Citations: **KB-02 v3**, **KB-05 v1 (SUPERSEDED)**.
  - The explanation states the old 60-point rule is superseded and cannot
    justify a pass; the current deadline (9 Oct 17:00 PKT) is shown.

---

## Acceptance cases A–D

| Case | Eligibility | Hold | Status | Citations |
|---|---|---|---|---|
| **A · Nadia** | ineligible | none | Waiting for Mentor | KB-01 v2, KB-02 v3, KB-05 v1 (SUPERSEDED) |
| **B · Hamza** | ineligible | secret_found | Waiting for Learner | KB-03 v2, KB-01 v2 |
| **C · Sara** | ineligible | none | Ready for Review | KB-02 v3, KB-05 v1 (SUPERSEDED) |
| **D · Missing data** | pending | unknown | Waiting for Learner | KB-01 v2, KB-02 v3, KB-03 v2 |

**B (Hamza):** 82%, 3 sessions, score 78, submission safe except a Groq key is
present in the ZIP. The secret hold blocks the pass decision regardless of the
numbers. The assistant asks for key rotation, removal (including repo history),
and a clean replacement. The key is never echoed.

**D (Missing data):** "Am I eligible?" with attendance, sessions, and score all
unknown. The app asks for each missing fact and stores a pending case. It does
not fabricate numbers or grant eligibility.

---

## LLM failure path

Two ways to demonstrate:

1. **Missing key** — start the server with `GROQ_API_KEY=` (empty) in the
   environment. `curl /api/health` shows `llm_configured: false`. Submitting a
   case still produces the code-computed result, full citations, missing facts,
   and next action. The answer area shows:

   > *LLM is not configured (GROQ_API_KEY missing). The code-computed result is shown.*

2. **Provider error** — set `GROQ_MODEL=does-not-exist` and restart. The
   provider returns a non-200 status. The UI shows:

   > *The explanation service is temporarily unavailable (provider status 404).
   > The saved case and code-computed result remain available.*

In both cases:
- No stack trace, no key, no internal path is exposed.
- The case is still persisted and appears in History.
- The Review card shows the code-computed badges, citations, and next action.

---

## Decisions that require human approval

The assistant never grants, waives, or closes. These are human actions:

- Mentor approval of a one-business-day extension.
- Mentor approval of a makeup session.
- Coordinator verification of attendance or medical evidence before correcting
  the attendance record.
- Coordinator confirmation that a clean submission has replaced a leaked one.
- Final certificate decision — the assistant at most reports "meets
  requirements, ready for human review".
- Closing a case (`Closed` is never set automatically).

---

## Assumptions

The following are design choices, not source requirements:

- **Model fallback.** `llama-3.1-8b-instant` was not available on the demo
  account; `GROQ_MODEL` was set to a currently available model that supports
  JSON output.
- **Status vs verdict labels.** Backend status strings (`Waiting for Mentor`,
  etc.) are rendered in the UI as `Next: Mentor`, `Next: Learner`,
  `Next: Reviewer`, `Next: Coordinator`, `Done`, to make clear that status
  answers "whose turn?" rather than "what is the verdict?".
- **Additional input fields.** `makeup_state`, `missed_session_date`, and
  `learner_notes` were added to model the KB-01/KB-03 scenarios. They do not
  change any threshold.
- **Secret redaction.** Learner text is scanned for key-shaped strings
  (`gsk_…`, `sk-…`, `AIza…`) before storage and before being sent to the LLM.
- **Citation validation.** LLM citations that do not match a retrieved chunk
  are dropped.
- **`extra="forbid"`** on request bodies; unknown fields return 422.
- **`/api/health`** returns `llm_configured` and `policies_loaded`.
- **Example-case chips** in the frontend prefill the four acceptance cases.

---

## Limitations

- Single-user, no auth, no deployment.
- SQLite only; cases are not editable or re-analyzable in the UI.
- No document upload — the five seeded policies are the authoritative corpus.
- The LLM explanation depends on provider availability; the deterministic
  result does not.
- The LLM key must be on the server; there is no per-user or per-tenant key
  management.
- The app has been exercised on macOS with Python 3.12. Other Python 3.11+
  versions should work but have not been verified.

---

## Demo walkthrough (3–5 minutes)

1. **Nadia — verdict, citations, status.**
   Load Nadia → Analyze. Show `ineligible` + `hold: none` + `Next: Mentor`.
   Point out KB-01 v2, KB-02 v3, and KB-05 v1 **SUPERSEDED**.
   Read the next action: route the extension to the mentor; standard due date
   remains Fri 9 Oct 17:00 PKT.

2. **Reopen from History.**
   Click any Nadia row in History. The Review card re-renders from
   `GET /api/cases/{id}`, showing the same verdict, citations, and case note.

3. **Sara — version conflict.**
   Load Sara → Analyze. Show `ineligible` + `hold: none` + `Next: Coordinator`.
   Point out KB-02 v3 (70) vs KB-05 v1 SUPERSEDED (60). The explanation states
   that the 60-point rule cannot be used for a case assessed on or after
   1 Oct 2026.

4. **Optional — Hamza (secret hold).**
   Load Hamza → Analyze. Show `ineligible` + `hold: secret_found` +
   `Next: Learner`. The next action asks the learner to rotate the key and
   supply a clean package. The key itself never appears.

5. **Failure path.**
   Stop uvicorn, restart with `GROQ_API_KEY=` (empty). `curl /api/health` shows
   `llm_configured: false`. Re-analyze Nadia: the verdict, citations, and next
   action still render; the answer area shows the readable `llm_error`; the
   case is saved. Restore the key and restart.

6. **Close.**
   Remind the audience that the tool never grants a certificate. It produces a
   verdict, a set of cited sources, and a next action for a human.