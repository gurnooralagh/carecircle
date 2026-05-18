# CareCircle — Post-Onboarding Longitudinal Pipeline Design
# Date: 2026-05-16
# Status: Approved by Gurnoor

---

## Goal

Build a completely separate post-onboarding pipeline that runs every time new documents are uploaded after onboarding is complete. It compares new information against the established patient baseline, classifies findings as new/recurring/escalated/resolved/improved, and surfaces only what changed — not a repeat of onboarding.

## Architecture

**Non-negotiable file rules (from longitudinal PRD):**
- Existing `services/` files: read-only — import from them, never edit them
- Existing `routers/onboarding.py`: zero changes
- Existing migrations: never alter or re-run
- New service files call existing functions via import

**Background task pattern (mirrors onboarding):**
- Upload triggers asyncio background task: L1 → L2 → L3 → set status='reconciling' → task ends
- Human L4 gate: synchronous router endpoints (no background work)
- Confirm reconciliation triggers second asyncio background task: L5 → L6 → L7 → L8 → L9 → L10 → set status='ready' → task ends

## Tech Stack

- FastAPI + Supabase (Python SDK) + asyncio background tasks
- LLM: Gemini 2.5 Flash via OpenRouter (same as onboarding)
- Auth: same `get_current_user` bearer token dependency
- Logging: `logging.getLogger('carecircle.longitudinal')` + DB writes to `longitudinal_pipeline_logs`

---

## File Structure

### New files (create only)

| File | Responsibility |
|---|---|
| `routers/longitudinal.py` | All 7 API endpoints + background task triggers |
| `services/longitudinal_pipeline.py` | Phase orchestrator (L1→L3 pre-gate, L5→L10 post-gate) + `log_event()` utility |
| `services/longitudinal_comparison.py` | L3: baseline load, entity comparison, delta detection, deduplication, transition records |
| `services/longitudinal_classification.py` | L6: deterministic finding classification + L7: nudge generation |
| `services/longitudinal_orchestration.py` | L8: orchestration LLM call → `longitudinal_caregiver_concerns` |
| `migrations/v3_7_longitudinal.sql` | 6 new tables + ALTER TABLE on `clinical_findings` and `patients` |
| `tests/test_longitudinal.py` | Pytest integration test: full L1→L10 pipeline |

### Edited files (minimal additions only)

| File | Change |
|---|---|
| `main.py` | One import + one `app.include_router(longitudinal.router)` |
| `test_ui/index.html` | Longitudinal test screens appended after Screen 6 (onboarding complete) |

---

## Database Design

### 6 new tables

**`document_upload_events`** — tracks each upload event
- `processing_status` CHECK: `pending | extracting | reconciling | reasoning | orchestrating | ready | failed`
- Links to `longitudinal_runs` via `longitudinal_run_id`

**`longitudinal_runs`** — audit + stats per run
- `baseline_patient_state` JSONB snapshot (saved before any writes)
- Counts: `new_medications`, `changed_medications`, `new_lab_results`, `new_diagnoses`, `new_directives`
- Finding counts: `findings_new`, `findings_recurring`, `findings_escalated`, `findings_resolved`, `findings_suppressed`
- `status` CHECK: `success | partial | failed`

**`medication_state_transitions`** — per-medication delta
- `transition_type` CHECK: `added | removed | continued | dose_changed | frequency_changed | status_changed | restarted`
- `guardian_confirmed` BOOLEAN — false until L4 submit

**`longitudinal_findings`** — finding lifecycle record
- `classification` CHECK: `new | recurring | escalated | resolved | improved`
- `prior_clinical_finding_id` for comparison
- `is_suppressed_from_caregiver` for recurring findings

**`longitudinal_caregiver_concerns`** — L8 output
- Same structure as `caregiver_concerns` + `concern_category` CHECK: `new | escalated | resolved | improved | nudge`
- `is_nudge` BOOLEAN + `nudge_original_finding_date` for nudge cards

**`longitudinal_pipeline_logs`** — structured phase logs
- Indexed on `run_id`, `level`, `phase`
- Queryable via `GET /api/longitudinal/logs/{run_id}`

### ALTER TABLE on existing tables (ADD COLUMN only)

```sql
-- clinical_findings
ADD COLUMN last_seen_run_id UUID REFERENCES longitudinal_runs(id);
ADD COLUMN last_seen_at TIMESTAMPTZ;
ADD COLUMN times_seen INT DEFAULT 1;

-- patients
ADD COLUMN post_onboarding_upload_count INT DEFAULT 0;
ADD COLUMN last_document_upload_at TIMESTAMPTZ;
ADD COLUMN longitudinal_status TEXT DEFAULT 'idle'
  CHECK (longitudinal_status IN ('idle', 'processing', 'ready', 'failed'));
```

---

## API Contract

All endpoints in `routers/longitudinal.py` under `/api/longitudinal/`. All require bearer token auth.

| Method | Path | Trigger | Returns |
|---|---|---|---|
| `POST` | `/upload/{patient_id}` | Starts L1→L3 background | `{ upload_event_id, status: "extracting" }` |
| `GET` | `/status/{patient_id}/{upload_event_id}` | Poll every 3s | `{ processing_status, stage }` |
| `GET` | `/medication_reconciliation/{patient_id}/{upload_event_id}` | When `status='reconciling'` | `{ existing_medications, newly_extracted_medications }` |
| `POST` | `/confirm_reconciliation/{patient_id}/{upload_event_id}` | Starts L5→L10 background | `{ status: "reasoning_running" }` |
| `GET` | `/findings/{patient_id}/{upload_event_id}` | When `status='ready'` | Full findings + action summary |
| `POST` | `/confirm_findings/{patient_id}/{upload_event_id}` | Marks run acknowledged | `{ status: "complete", concerns_acknowledged: N }` |
| `GET` | `/logs/{run_id}` | Debug/testing only | Full phase log |

**State machine:**
```
pending → extracting → reconciling → reasoning → orchestrating → ready
                    ↘ failed (at any phase)
```

**GET /findings response shape:**
```json
{
  "status": "running | ready",
  "run_summary": { "findings_new": N, "findings_escalated": N, "findings_resolved": N, "findings_improved": N, "findings_recurring_suppressed": N },
  "medication_changes": [ { "drug_name_brand", "drug_name_generic", "transition_type", "prior_dose_mg", "new_dose_mg", "prior_frequency", "new_frequency", "source_document" } ],
  "concerns": [ { "concern_id", "concern_type", "concern_category", "priority", "title", "summary", "what_was_found", "why_it_matters", "what_to_do", "evidence", "source_documents", "is_nudge", "nudge_original_finding_date", "display_order" } ],
  "concern_summary": { "new": N, "escalated": N, "resolved": N, "improved": N, "nudge_items": N },
  "action_summary": { "do_now": [...], "follow_up": [...], "ongoing_monitoring": [...], "resolved_since_last_upload": [...] }
}
```

---

## Phase Logic

### L1 — Document Extraction
- `_process_document()` in `extraction_pipeline.py` is private — cannot be called externally
- `longitudinal_pipeline.py` implements `_process_document_longitudinal()` using the same underlying imports: `storage`, `ocr`, `pdf_extractor`, `llm` (same libraries, different file)
- Saves docs with `upload_context='post_onboarding'`
- Sets `processing_status='extracting'`

### L2 — Normalization
- Calls `_batch_normalize_medications()` via direct import from `extraction_pipeline` (private but importable within the package) OR reimplements using `services.resolver.resolve_drug_name` directly
- Calls public deduplicator functions: `deduplicate_medications`, `deduplicate_conditions`, `deduplicate_allergies`
- No new logic beyond what onboarding does

### L3 — Entity Comparison (`longitudinal_comparison.py`)
- Load baseline patient state from DB, snapshot to `longitudinal_runs.baseline_patient_state` BEFORE any writes
- Compare medications: exact match → `continued`; same generic, different dose → `dose_changed`; new → `added`
- Compare labs: worsened/improved/stable/critical_change based on direction from normal range
- Compare diagnoses: new only → insert with `confirmation_status='suspected'`
- Compare directives: same doctor newer date → supersede; different doctor conflict → `contradicted`
- Compare monitoring: check if new doc IS the completion of a pending test
- Create `medication_state_transitions` records
- Update `longitudinal_runs` delta counts
- Set `processing_status='reconciling'`

### L4 — Medication Reconciliation Gate (synchronous, router only)
- GET endpoint returns existing + newly extracted medications
- POST endpoint: guardian confirms each medication status, inline dose/frequency edits normalized
- Guardian actions: `still_taking | stopped | held | not_sure` for existing; `confirm | edit | remove` for new
- Saves `medication_state_transitions` with `guardian_confirmed=True`
- Sets `processing_status='reasoning'` → triggers L5→L10 background task

### L5 — Reasoning Engine (`longitudinal_pipeline.py`)
- Cannot call `run_reasoning_engine(db, patient_id)` directly — it builds its own patient state internally via private `_build_patient_state()` and does not accept longitudinal enrichments
- Instead: `longitudinal_pipeline.py` builds the enriched longitudinal patient state directly from DB (reads meds with `transition_type`, labs with `delta_type`/`prior_value_numeric`, prior_findings with full `clinical_evidence` + `related_entities` + `times_seen`)
- Calls `llm.run_reasoning(longitudinal_patient_state)` directly (public function) with longitudinal context block appended to user prompt
- Applies simplified quality gates inline (confidence > 0.05, non-empty clinical_evidence)
- Saves findings to `clinical_findings` table — same schema as onboarding

### L6 — Classification (`longitudinal_classification.py`)
- Deterministic matching per PRD Part 15:
  1. Find candidates by `finding_type` match in prior findings
  2. Match by `related_entities` overlap (medications/labs/conditions)
  3. Compare severity → recurring/escalated/improved
- If LLM classification disagrees with deterministic result: **deterministic wins**
- Creates `longitudinal_findings` record per finding
- Updates matched prior `clinical_findings`: `last_seen_at`, `times_seen += 1`, `status` (escalated/resolved)
- Recurring findings: `is_suppressed_from_caregiver=True`

### L7 — Nudge Generation (`longitudinal_classification.py`)
- Groups recurring findings by severity tier (critical/high/moderate/low_informational)
- Max 4 nudge cards (one per tier with recurring findings)
- Pure Python construction — no LLM call
- Nudge priority is always `for_your_awareness` regardless of original severity

### L8 — Orchestration (`longitudinal_orchestration.py`)
- Calls Gemini via existing `llm.py` functions
- Input: new/escalated/resolved/improved findings only (not recurring) + brand_map + medication_state_transitions
- Output: `longitudinal_caregiver_concerns`
- Longitudinal-specific prompt additions: escalated must state prior→new severity; resolved framed positively; medication changes always surfaced explicitly
- Nudge cards from L7 passed through unchanged — not re-orchestrated
- Fallback: one independent concern per finding if LLM fails
- Sets `processing_status='orchestrating'`

### L9 — Action Summary Update (`longitudinal_pipeline.py`)
- Calls existing `generate_action_summary()` from `llm.py` with longitudinal context
- `do_now`: concerns with `concern_category='new'|'escalated'` at critical/high priority
- `follow_up`: pending monitoring_instructions + resolved concerns needing doctor confirmation
- `ongoing_monitoring`: moderate/for_your_awareness concerns + stable monitoring
- `resolved_since_last_upload`: directly from concerns with `concern_category='resolved'` — no LLM needed
- Saves to `patient_action_summaries` with `is_current=True`, sets prior `is_current=False`

### L10 — Patient State Update (`longitudinal_pipeline.py`)
- Applies guardian-confirmed `medication_state_transitions` to `medications` table
- Updates `patients.post_onboarding_upload_count += 1`, `last_document_upload_at`, `longitudinal_status='idle'`
- Generates new `patient_summaries` record (calls existing summary logic)
- Retry up to 3× with exponential backoff — this is the ONLY phase with retry logic
- On all retries failed: set `longitudinal_status='failed'`, log CRITICAL
- Sets `processing_status='ready'`

### Logging — `log_event()` in `longitudinal_pipeline.py`
- Every phase emits structured JSON log: `{ timestamp, run_id, phase, event, detail }`
- Writes to both Python logger (`carecircle.longitudinal`) and `longitudinal_pipeline_logs` table
- Imported by all other longitudinal service files

---

## Error Handling

| Phase | Failure | Action |
|---|---|---|
| L1/L2 — all docs fail | Set `status='failed'`, stop pipeline | Error returned to frontend |
| L1/L2 — partial failure | Continue with succeeded docs, add FOR_YOUR_AWARENESS concern | |
| L3 — baseline cannot load | Set `status='failed'`, stop pipeline | |
| L3 — partial entity comparison | Skip failed entity type, log, continue | |
| L4 — reconciliation load fails | Set `status='failed'`, return retry option | |
| L4 — save fails mid-way | Roll back all transitions atomically | |
| L5 — timeout >45s | Save partial findings, run 3-dimension fallback, set `status='partial'` | |
| L5 — empty findings | Retry once, then proceed empty | |
| L6 — classification fails | Default all to `classification='new'`, no nudge | |
| L8 — orchestration fails | One independent concern per finding (no grouping) | |
| L9 — action summary fails | Save empty arrays, don't block findings display | |
| L10 — state update fails | Retry 3×, log CRITICAL, set `longitudinal_status='failed'` | |
| Any — caregiver never sees blank screen | Always show at least one FOR_YOUR_AWARENESS concern | |

---

## Testing

**`tests/test_longitudinal.py`** — full integration test, real DB, real LLM, real OCR:

1. Complete onboarding (reuses fixtures from `conftest.py`)
2. Upload new prescription + lab report via `POST /upload`
3. Poll until `status='reconciling'`
4. GET medication reconciliation — assert non-empty existing_medications
5. POST confirm reconciliation — confirm all
6. Poll until `status='ready'`
7. GET findings — assert non-empty concerns, non-empty run_summary, action_summary present
8. GET logs — assert all 10 phases present, no critical-level errors
9. POST confirm findings
10. Cleanup in FK-safe order: `longitudinal_pipeline_logs → longitudinal_caregiver_concerns → longitudinal_findings → medication_state_transitions → longitudinal_runs → document_upload_events → [existing onboarding cleanup] → patients`

**HTML UI (`test_ui/index.html`)** — longitudinal screens added after Screen 6:
- Screen L1: Upload new documents (file picker + document type selection)
- Screen L2: Status polling (extracting → reconciling)
- Screen L3: Medication reconciliation (existing + newly extracted, inline edit)
- Screen L4: Status polling (reasoning → orchestrating → ready)
- Screen L5: Longitudinal findings (medication change pills + new/escalated/resolved/improved cards + nudge cards + action summary)
- Log viewer: shows `GET /logs/{run_id}` output inline

---

## Hard Rules (from PRD, enforced in code)

1. Never re-run onboarding pipeline on post-onboarding documents — separate code paths
2. Never auto-remove a medication because it is absent from a new document — always confirm with guardian
3. Never mark a finding as resolved without specific evidence from a new document
4. Recurring findings are never shown as new concern cards — always nudges
5. Nudge cards are always at the bottom, always `for_your_awareness`
6. Escalated findings always state prior severity and new severity explicitly
7. Lab results are never deduplicated across dates — all dates are trend data
8. Baseline snapshot must be saved BEFORE any new entity writes — baseline is rollback reference
9. L4 gate is not optional — L5 must not run until guardian confirms
10. All 13 reasoning dimensions run on full patient state (old + new combined), never on delta only
11. Deterministic classification overrides LLM classification — deterministic is law
12. `patient_action_summaries.is_current=True` on exactly one record per patient at all times
13. Nudge must always be generated if there are recurring findings — never suppress entirely
14. Caregiver never sees blank screen — always at least one concern even on failure
15. Uploaded files are never lost regardless of pipeline failure — docs saved in L1 before processing
