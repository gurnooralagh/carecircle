# Longitudinal Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a post-onboarding longitudinal pipeline that runs every time new documents are uploaded, compares against the patient baseline, and surfaces only what changed.

**Architecture:** Two asyncio background tasks split by a human gate: `run_pre_gate_pipeline` (L1→L3) and `run_post_gate_pipeline` (L5→L10). Seven new API endpoints under `/api/longitudinal/`. Deterministic classification always overrides LLM classification.

**Tech Stack:** FastAPI + Supabase Python SDK + asyncio background tasks + Gemini 2.5 Flash via OpenRouter (same as onboarding)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `migrations/v3_7_longitudinal.sql` | Create | 6 new tables + ALTER TABLE on `clinical_findings` and `patients` |
| `services/longitudinal_comparison.py` | Create | L3: baseline load, entity comparison, delta detection |
| `services/longitudinal_classification.py` | Create | L6: deterministic classification + L7: nudge generation |
| `services/longitudinal_orchestration.py` | Create | L8: orchestration LLM call → `longitudinal_caregiver_concerns` |
| `services/longitudinal_pipeline.py` | Create | `log_event()`, `run_pre_gate_pipeline()`, `run_post_gate_pipeline()`, reasoning build |
| `routers/longitudinal.py` | Create | All 7 API endpoints |
| `main.py` | Edit | Add import + `app.include_router(longitudinal.router)` |
| `tests/test_longitudinal.py` | Create | Full L1→L10 integration test |
| `test_ui/index.html` | Edit | Longitudinal screens appended after Screen 6 |

---

## Task 1: Migration SQL

**Files:**
- Create: `migrations/v3_7_longitudinal.sql`

- [ ] **Step 1: Write the migration**

```sql
-- migrations/v3_7_longitudinal.sql
-- Run ONCE in Supabase SQL editor.

-- TABLE 1: longitudinal_runs (no circular FK yet)
CREATE TABLE IF NOT EXISTS longitudinal_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    baseline_patient_state JSONB,
    new_medications INT DEFAULT 0,
    changed_medications INT DEFAULT 0,
    new_lab_results INT DEFAULT 0,
    new_diagnoses INT DEFAULT 0,
    new_directives INT DEFAULT 0,
    findings_new INT DEFAULT 0,
    findings_recurring INT DEFAULT 0,
    findings_escalated INT DEFAULT 0,
    findings_resolved INT DEFAULT 0,
    findings_suppressed INT DEFAULT 0,
    status TEXT DEFAULT 'success' CHECK (status IN ('success', 'partial', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 2: document_upload_events
CREATE TABLE IF NOT EXISTS document_upload_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    longitudinal_run_id UUID REFERENCES longitudinal_runs(id),
    processing_status TEXT DEFAULT 'pending'
        CHECK (processing_status IN ('pending','extracting','reconciling','reasoning','orchestrating','ready','failed')),
    uploaded_files JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add reverse FK from longitudinal_runs → document_upload_events (circular, safe because nullable)
ALTER TABLE longitudinal_runs ADD COLUMN IF NOT EXISTS upload_event_id UUID REFERENCES document_upload_events(id);

-- TABLE 3: medication_state_transitions
CREATE TABLE IF NOT EXISTS medication_state_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES longitudinal_runs(id),
    upload_event_id UUID REFERENCES document_upload_events(id),
    medication_id UUID REFERENCES medications(id),
    drug_name_brand TEXT,
    drug_name_generic TEXT,
    transition_type TEXT NOT NULL
        CHECK (transition_type IN ('added','removed','continued','dose_changed','frequency_changed','status_changed','restarted')),
    prior_dose_mg NUMERIC,
    new_dose_mg NUMERIC,
    prior_frequency TEXT,
    new_frequency TEXT,
    source_document TEXT,
    guardian_confirmed BOOLEAN DEFAULT FALSE,
    guardian_action TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 4: longitudinal_findings
CREATE TABLE IF NOT EXISTS longitudinal_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES longitudinal_runs(id),
    clinical_finding_id UUID REFERENCES clinical_findings(id),
    prior_clinical_finding_id UUID REFERENCES clinical_findings(id),
    classification TEXT NOT NULL
        CHECK (classification IN ('new','recurring','escalated','resolved','improved')),
    is_suppressed_from_caregiver BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 5: longitudinal_caregiver_concerns
CREATE TABLE IF NOT EXISTS longitudinal_caregiver_concerns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES longitudinal_runs(id),
    upload_event_id UUID REFERENCES document_upload_events(id),
    concern_type TEXT,
    concern_category TEXT
        CHECK (concern_category IN ('new','escalated','resolved','improved','nudge')),
    priority TEXT,
    title TEXT,
    summary TEXT,
    what_was_found TEXT,
    why_it_matters TEXT,
    what_to_do TEXT,
    evidence JSONB,
    source_documents JSONB,
    is_nudge BOOLEAN DEFAULT FALSE,
    nudge_original_finding_date TIMESTAMPTZ,
    display_order INT DEFAULT 0,
    is_acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 6: longitudinal_pipeline_logs
CREATE TABLE IF NOT EXISTS longitudinal_pipeline_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES longitudinal_runs(id),
    upload_event_id UUID REFERENCES document_upload_events(id),
    phase TEXT,
    event TEXT,
    level TEXT DEFAULT 'INFO',
    detail JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_long_logs_run_id ON longitudinal_pipeline_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_long_logs_level ON longitudinal_pipeline_logs(level);
CREATE INDEX IF NOT EXISTS idx_long_logs_phase ON longitudinal_pipeline_logs(phase);

-- ALTER existing tables (ADD COLUMN only — never drops)
ALTER TABLE clinical_findings ADD COLUMN IF NOT EXISTS last_seen_run_id UUID REFERENCES longitudinal_runs(id);
ALTER TABLE clinical_findings ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;
ALTER TABLE clinical_findings ADD COLUMN IF NOT EXISTS times_seen INT DEFAULT 1;

ALTER TABLE patients ADD COLUMN IF NOT EXISTS post_onboarding_upload_count INT DEFAULT 0;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS last_document_upload_at TIMESTAMPTZ;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS longitudinal_status TEXT DEFAULT 'idle'
    CHECK (longitudinal_status IN ('idle','processing','ready','failed'));
```

- [ ] **Step 2: Run in Supabase SQL editor**

Paste the entire file into the Supabase dashboard → SQL editor → Run. Verify no errors.

- [ ] **Step 3: Verify tables exist**

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN (
  'document_upload_events','longitudinal_runs','medication_state_transitions',
  'longitudinal_findings','longitudinal_caregiver_concerns','longitudinal_pipeline_logs'
);
```

Expected: 6 rows returned.

- [ ] **Step 4: Commit**

```bash
git add migrations/v3_7_longitudinal.sql
git commit -m "feat: add longitudinal pipeline migration (6 tables + alter clinical_findings/patients)"
```

---

## Task 2: Entity Comparison Service

**Files:**
- Create: `services/longitudinal_comparison.py`

- [ ] **Step 1: Write the service**

```python
"""
L3 — Baseline load + entity comparison.
Loads patient baseline before any writes, saves snapshot, compares new extractions.
Creates medication_state_transitions. Updates longitudinal_runs delta counts.
"""
import json
import logging
from datetime import datetime, timezone
from supabase import Client

logger = logging.getLogger("carecircle.longitudinal")

_SEVERITY_RANK = {"critical": 4, "high": 3, "moderate": 2, "low": 1, "informational": 0}


def load_and_save_baseline(db: Client, patient_id: str, run_id: str) -> dict:
    """Load full patient state from DB and save snapshot to longitudinal_runs. Returns baseline dict."""
    meds = (db.table("medications").select("*")
            .eq("patient_id", patient_id).eq("is_deleted", False).execute()).data
    labs = (db.table("lab_results").select("*")
            .eq("patient_id", patient_id).order("report_date", desc=True).execute()).data
    diagnoses = (db.table("diagnoses").select("*")
                 .eq("patient_id", patient_id).execute()).data
    directives = (db.table("clinical_directives").select("*")
                  .eq("patient_id", patient_id).eq("is_active", True).execute()).data
    monitoring = (db.table("monitoring_instructions").select("*")
                  .eq("patient_id", patient_id).execute()).data
    findings = (db.table("clinical_findings").select("*")
                .eq("patient_id", patient_id)
                .in_("status", ["open", "monitoring", "recurring"]).execute()).data

    baseline = {
        "medications": meds,
        "lab_results": labs,
        "diagnoses": diagnoses,
        "directives": directives,
        "monitoring": monitoring,
        "prior_findings": findings,
    }
    db.table("longitudinal_runs").update({
        "baseline_patient_state": json.dumps(baseline, default=str)
    }).eq("id", run_id).execute()
    logger.info(f"L3 baseline saved — {len(meds)} meds, {len(labs)} labs, {len(findings)} findings")
    return baseline


def compare_entities(
    db: Client,
    patient_id: str,
    run_id: str,
    upload_event_id: str,
    baseline: dict,
) -> dict:
    """Compare newly extracted entities against baseline. Creates transition records. Returns delta counts."""
    # Load newly extracted docs (post_onboarding)
    new_docs = (db.table("documents").select("id,document_type,original_filename")
                .eq("patient_id", patient_id)
                .eq("upload_context", "post_onboarding").execute()).data
    new_doc_ids = [d["id"] for d in new_docs]

    if not new_doc_ids:
        logger.warning("L3: no post_onboarding documents found")
        return {"new_medications": 0, "changed_medications": 0, "new_lab_results": 0,
                "new_diagnoses": 0, "new_directives": 0}

    # New medications from these docs
    new_meds = (db.table("medications").select("*")
                .eq("patient_id", patient_id)
                .in_("source_document_id", new_doc_ids).execute()).data

    delta = {"new_medications": 0, "changed_medications": 0,
             "new_lab_results": 0, "new_diagnoses": 0, "new_directives": 0}

    # Build baseline medication index: generic → row
    baseline_meds_by_generic: dict[str, dict] = {}
    baseline_meds_by_brand: dict[str, dict] = {}
    for m in baseline["medications"]:
        g = (m.get("drug_name_generic") or "").lower().strip()
        b = (m.get("drug_name_brand") or "").lower().strip()
        if g:
            baseline_meds_by_generic[g] = m
        if b:
            baseline_meds_by_brand[b] = m

    for nm in new_meds:
        ng = (nm.get("drug_name_generic") or "").lower().strip()
        nb = (nm.get("drug_name_brand") or "").lower().strip()
        baseline_match = baseline_meds_by_generic.get(ng) or baseline_meds_by_brand.get(nb)

        if baseline_match is None:
            _create_transition(db, patient_id, run_id, upload_event_id, nm, "added", baseline_match)
            delta["new_medications"] += 1
        else:
            transition_type = _detect_medication_transition(baseline_match, nm)
            _create_transition(db, patient_id, run_id, upload_event_id, nm, transition_type, baseline_match)
            if transition_type != "continued":
                delta["changed_medications"] += 1

    # New lab results
    new_labs = (db.table("lab_results").select("*")
                .eq("patient_id", patient_id)
                .in_("source_document_id", new_doc_ids).execute()).data
    delta["new_lab_results"] = len(new_labs)

    # New diagnoses
    new_diags = (db.table("diagnoses").select("*")
                 .eq("patient_id", patient_id)
                 .in_("source_document_id", new_doc_ids).execute()).data
    delta["new_diagnoses"] = len(new_diags)

    # New directives
    new_dirs = (db.table("clinical_directives").select("*")
                .eq("patient_id", patient_id)
                .in_("source_document_id", new_doc_ids).execute()).data
    delta["new_directives"] = len(new_dirs)

    db.table("longitudinal_runs").update(delta).eq("id", run_id).execute()
    logger.info(f"L3 comparison complete — delta: {delta}")
    return delta


def _detect_medication_transition(prior: dict, new: dict) -> str:
    prior_dose = _extract_dose_mg(prior)
    new_dose = _extract_dose_mg(new)
    if prior_dose and new_dose and abs(prior_dose - new_dose) > 0.01:
        return "dose_changed"
    prior_freq = (prior.get("frequency") or "").lower().strip()
    new_freq = (new.get("frequency") or "").lower().strip()
    if prior_freq and new_freq and prior_freq != new_freq:
        return "frequency_changed"
    prior_status = (prior.get("status") or "active").lower()
    new_status = (new.get("status") or "active").lower()
    if prior_status != new_status:
        return "status_changed"
    return "continued"


def _extract_dose_mg(med: dict) -> float | None:
    if med.get("dose_mg"):
        try:
            return float(med["dose_mg"])
        except (ValueError, TypeError):
            pass
    dose_text = med.get("dose_text") or med.get("dosage") or ""
    import re
    m = re.search(r"(\d+\.?\d*)\s*mg", dose_text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _create_transition(
    db: Client,
    patient_id: str,
    run_id: str,
    upload_event_id: str,
    new_med: dict,
    transition_type: str,
    prior_med: dict | None,
) -> None:
    try:
        db.table("medication_state_transitions").insert({
            "patient_id": patient_id,
            "run_id": run_id,
            "upload_event_id": upload_event_id,
            "medication_id": new_med.get("id"),
            "drug_name_brand": new_med.get("drug_name_brand"),
            "drug_name_generic": new_med.get("drug_name_generic"),
            "transition_type": transition_type,
            "prior_dose_mg": _extract_dose_mg(prior_med) if prior_med else None,
            "new_dose_mg": _extract_dose_mg(new_med),
            "prior_frequency": prior_med.get("frequency") if prior_med else None,
            "new_frequency": new_med.get("frequency"),
            "source_document": new_med.get("source_document_id"),
            "guardian_confirmed": False,
        }).execute()
    except Exception as e:
        logger.warning(f"L3: could not save transition for {new_med.get('drug_name_brand')}: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add services/longitudinal_comparison.py
git commit -m "feat: add longitudinal entity comparison service (L3)"
```

---

## Task 3: Classification + Nudge Service

**Files:**
- Create: `services/longitudinal_classification.py`

- [ ] **Step 1: Write the service**

```python
"""
L6 — Deterministic finding classification (new/recurring/escalated/resolved/improved).
L7 — Nudge card generation for recurring findings (max 4, one per severity tier).
Deterministic classification is law — LLM suggestions are ignored.
"""
import json
import logging
from datetime import datetime, timezone
from supabase import Client

logger = logging.getLogger("carecircle.longitudinal")

_SEVERITY_RANK = {"critical": 4, "high": 3, "moderate": 2, "low": 1, "informational": 0}
_SEVERITY_TIERS = ["critical", "high", "moderate", "low"]


def classify_findings(
    db: Client,
    patient_id: str,
    run_id: str,
    new_finding_ids: list[str],
    prior_findings: list[dict],
) -> tuple[list[str], list[str]]:
    """
    Classify each new finding against prior findings.
    Returns (unsuppressed_ids, suppressed_recurring_ids).
    """
    unsuppressed: list[str] = []
    suppressed: list[str] = []

    counts = {"new": 0, "recurring": 0, "escalated": 0, "resolved": 0, "improved": 0}

    for fid in new_finding_ids:
        row = (db.table("clinical_findings").select("*")
               .eq("id", fid).limit(1).execute()).data
        if not row:
            continue
        finding = row[0]

        classification, prior_match = _deterministic_classify(finding, prior_findings)
        counts[classification] += 1

        is_suppressed = classification == "recurring"
        db.table("longitudinal_findings").insert({
            "patient_id": patient_id,
            "run_id": run_id,
            "clinical_finding_id": fid,
            "prior_clinical_finding_id": prior_match["id"] if prior_match else None,
            "classification": classification,
            "is_suppressed_from_caregiver": is_suppressed,
        }).execute()

        if prior_match:
            _update_prior_finding(db, prior_match, fid, run_id, classification)

        if is_suppressed:
            suppressed.append(fid)
        else:
            unsuppressed.append(fid)

    db.table("longitudinal_runs").update({
        "findings_new": counts["new"],
        "findings_recurring": counts["recurring"],
        "findings_escalated": counts["escalated"],
        "findings_resolved": counts["resolved"],
        "findings_suppressed": counts["recurring"],
    }).eq("id", run_id).execute()

    logger.info(f"L6 classification: {counts}")
    return unsuppressed, suppressed


def _deterministic_classify(
    finding: dict,
    prior_findings: list[dict],
) -> tuple[str, dict | None]:
    """Match by finding_type + related_entities overlap. Compare severity for escalated/improved."""
    finding_type = finding.get("finding_type", "")
    new_entities = _parse_json(finding.get("related_entities"))
    new_meds = {m.lower() for m in (new_entities.get("medications") or [])}
    new_labs = {l.lower() for l in (new_entities.get("labs") or [])}
    new_conditions = {c.lower() for c in (new_entities.get("conditions") or [])}

    best_match: dict | None = None
    best_overlap = 0

    for pf in prior_findings:
        if pf.get("finding_type") != finding_type:
            continue
        prior_entities = _parse_json(pf.get("related_entities"))
        prior_meds = {m.lower() for m in (prior_entities.get("medications") or [])}
        prior_labs = {l.lower() for l in (prior_entities.get("labs") or [])}
        prior_conds = {c.lower() for c in (prior_entities.get("conditions") or [])}

        overlap = (
            len(new_meds & prior_meds) +
            len(new_labs & prior_labs) +
            len(new_conditions & prior_conds)
        )
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = pf

    if best_match is None or best_overlap == 0:
        return "new", None

    new_rank = _SEVERITY_RANK.get(finding.get("severity", "informational"), 0)
    prior_rank = _SEVERITY_RANK.get(best_match.get("severity", "informational"), 0)

    if new_rank > prior_rank:
        return "escalated", best_match
    if new_rank < prior_rank:
        return "improved", best_match
    return "recurring", best_match


def _update_prior_finding(
    db: Client,
    prior: dict,
    new_finding_id: str,
    run_id: str,
    classification: str,
) -> None:
    times_seen = (prior.get("times_seen") or 1) + 1
    updates: dict = {
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
        "last_seen_run_id": run_id,
        "times_seen": times_seen,
    }
    if classification == "escalated":
        updates["status"] = "escalated"
    elif classification in ("resolved", "improved"):
        updates["status"] = "resolved"
    try:
        db.table("clinical_findings").update(updates).eq("id", prior["id"]).execute()
    except Exception as e:
        logger.warning(f"L6: could not update prior finding {prior['id']}: {e}")


def generate_nudge_cards(
    db: Client,
    patient_id: str,
    run_id: str,
    upload_event_id: str,
    suppressed_finding_ids: list[str],
) -> list[dict]:
    """
    L7: Group recurring findings by severity tier. Max 4 nudge cards (one per tier).
    Returns list of nudge card dicts (not yet saved — caller saves them).
    """
    if not suppressed_finding_ids:
        return []

    # Load the suppressed findings
    rows = (db.table("clinical_findings").select("*")
            .in_("id", suppressed_finding_ids).execute()).data

    by_tier: dict[str, list[dict]] = {t: [] for t in _SEVERITY_TIERS}
    for row in rows:
        sev = row.get("severity", "low")
        tier = sev if sev in by_tier else "low"
        by_tier[tier].append(row)

    nudge_cards: list[dict] = []
    display_order = 1000  # nudges always at the bottom

    for tier in _SEVERITY_TIERS:
        findings_in_tier = by_tier[tier]
        if not findings_in_tier:
            continue

        titles = [f.get("title", "") for f in findings_in_tier[:3]]
        title_text = titles[0] if len(titles) == 1 else f"{len(findings_in_tier)} recurring findings"

        # Find earliest original finding date
        oldest_date = None
        for f in findings_in_tier:
            ca = f.get("created_at")
            if ca and (oldest_date is None or ca < oldest_date):
                oldest_date = ca

        card = {
            "patient_id": patient_id,
            "run_id": run_id,
            "upload_event_id": upload_event_id,
            "concern_type": "nudge",
            "concern_category": "nudge",
            "priority": "for_your_awareness",
            "title": f"Still monitoring: {title_text}",
            "summary": (
                f"{len(findings_in_tier)} previously flagged finding(s) at {tier} severity "
                "remain unchanged in the new documents."
            ),
            "what_was_found": "; ".join(f.get("title", "") for f in findings_in_tier),
            "why_it_matters": "These findings have been tracked across visits. No new changes detected.",
            "what_to_do": "Continue current management. Mention at next doctor visit.",
            "evidence": [],
            "source_documents": [],
            "is_nudge": True,
            "nudge_original_finding_date": oldest_date,
            "display_order": display_order,
        }
        nudge_cards.append(card)
        display_order += 1

        if len(nudge_cards) >= 4:
            break

    logger.info(f"L7: generated {len(nudge_cards)} nudge cards")
    return nudge_cards


def _parse_json(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}
    return {}
```

- [ ] **Step 2: Commit**

```bash
git add services/longitudinal_classification.py
git commit -m "feat: add longitudinal classification (L6) and nudge generation (L7)"
```

---

## Task 4: Orchestration Service

**Files:**
- Create: `services/longitudinal_orchestration.py`

- [ ] **Step 1: Write the service**

```python
"""
L8 — Longitudinal orchestration.
Calls Gemini via existing llm._call. Input: new/escalated/resolved/improved findings only.
Nudge cards from L7 passed through unchanged.
Saves to longitudinal_caregiver_concerns.
"""
import json
import logging
from supabase import Client
from services.llm import _call as _llm_call

logger = logging.getLogger("carecircle.longitudinal")

_SYSTEM_PROMPT = """\
You are a presentation layer for a caregiver health platform in India.

Your job is to group new/escalated/resolved/improved clinical findings into caregiver-friendly concern cards.
Recurring findings will be shown separately as nudge cards — do NOT include them.

CRITICAL RULES:
1. Every finding must appear in at least one concern card. Do not drop any finding.
2. Use brand names first, generic in brackets: "Glycomet (Metformin)".
   Use only the brand_map provided. Never invent brand names.
3. Priority labels: critical_concern, high_priority, moderate, for_your_awareness.
4. ESCALATED findings: always state the prior severity AND the new severity explicitly.
5. RESOLVED findings: frame positively — "The records now show improvement in [X]."
6. Medication changes: always surface explicitly in what_was_found.
7. Tone: calm, advisory. Never say "stop", "discontinue", "do not take".
   Say "discuss with doctor before the next dose."
8. Return only valid JSON.\
"""

_USER_TEMPLATE = """\
Brand name map:
{brand_map_json}

Medication changes confirmed by guardian:
{medication_transitions_json}

Findings to orchestrate (new, escalated, resolved, improved only):
{findings_json}

Each finding includes: finding_id, classification, finding_type, severity, title,
clinical_evidence, related_entities.

Group into caregiver concern cards. Return JSON:
{{
  "concerns": [
    {{
      "concern_category": "new | escalated | resolved | improved",
      "priority": "critical_concern | high_priority | moderate | for_your_awareness",
      "title": "max 10 words, plain language",
      "summary": "1-2 sentences",
      "what_was_found": "specific details, brand name (generic), values, source, date",
      "why_it_matters": "why this applies to THIS patient",
      "what_to_do": "specific action — what to bring, ask, or show doctor",
      "evidence": [{{"entity": "value", "source": "doc", "date": "ISO or empty"}}],
      "source_documents": ["doc name list"],
      "contributing_finding_ids": ["uuid list"]
    }}
  ]
}}\
"""


async def run_longitudinal_orchestration(
    db: Client,
    patient_id: str,
    run_id: str,
    upload_event_id: str,
    finding_ids_to_orchestrate: list[str],
    nudge_cards: list[dict],
    medication_transitions: list[dict],
) -> int:
    """L8: orchestrate non-recurring findings into concern cards. Save nudge cards unchanged.
    Returns total number of concern rows saved."""
    logger.info(f"L8 orchestration — {len(finding_ids_to_orchestrate)} findings, {len(nudge_cards)} nudges")

    saved = 0

    # Save nudge cards first (pass-through, no LLM)
    for card in nudge_cards:
        try:
            db.table("longitudinal_caregiver_concerns").insert(card).execute()
            saved += 1
        except Exception as e:
            logger.warning(f"L8: could not save nudge card: {e}")

    if not finding_ids_to_orchestrate:
        if saved == 0:
            _save_no_changes_concern(db, patient_id, run_id, upload_event_id)
            saved = 1
        return saved

    # Load full finding rows
    findings = (db.table("clinical_findings").select("*")
                .in_("id", finding_ids_to_orchestrate).execute()).data

    # Load longitudinal_findings for classifications
    lf_rows = (db.table("longitudinal_findings").select("clinical_finding_id,classification")
               .eq("run_id", run_id).execute()).data
    classification_map = {r["clinical_finding_id"]: r["classification"] for r in lf_rows}

    finding_inputs = []
    for f in findings:
        finding_inputs.append({
            "finding_id": str(f["id"]),
            "classification": classification_map.get(f["id"], "new"),
            "finding_type": f.get("finding_type", ""),
            "severity": f.get("severity", "informational"),
            "title": f.get("title", ""),
            "clinical_evidence": _parse_json(f.get("clinical_evidence")),
            "related_entities": _parse_json(f.get("related_entities")),
        })

    brand_map = _build_brand_map(db, patient_id, findings)

    try:
        result = await _llm_call(
            _SYSTEM_PROMPT,
            _USER_TEMPLATE.format(
                brand_map_json=json.dumps(brand_map, ensure_ascii=False, indent=2),
                medication_transitions_json=json.dumps(medication_transitions, ensure_ascii=False, indent=2),
                findings_json=json.dumps(finding_inputs, ensure_ascii=False, indent=2),
            ),
            timeout=180,
        )
        concerns = result.get("concerns") or []
        if not isinstance(concerns, list):
            raise ValueError("LLM returned non-list concerns")
    except Exception as e:
        logger.warning(f"L8 LLM failed: {e} — using fallback")
        concerns = _fallback_concerns(finding_inputs)

    # Ensure all findings are covered
    covered_ids = set()
    for c in concerns:
        covered_ids.update(c.get("contributing_finding_ids") or [])
    for fi in finding_inputs:
        if fi["finding_id"] not in covered_ids:
            concerns.append(_independent_concern(fi))

    start_order = 1
    for c in concerns:
        category = c.get("concern_category", "new")
        if category not in ("new", "escalated", "resolved", "improved", "nudge"):
            category = "new"
        try:
            db.table("longitudinal_caregiver_concerns").insert({
                "patient_id": patient_id,
                "run_id": run_id,
                "upload_event_id": upload_event_id,
                "concern_type": "grouped",
                "concern_category": category,
                "priority": _valid_priority(c.get("priority")),
                "title": (c.get("title") or "Finding")[:500],
                "summary": c.get("summary") or "",
                "what_was_found": c.get("what_was_found") or "",
                "why_it_matters": c.get("why_it_matters") or "",
                "what_to_do": c.get("what_to_do") or "",
                "evidence": c.get("evidence") or [],
                "source_documents": c.get("source_documents") or [],
                "is_nudge": False,
                "display_order": start_order,
            }).execute()
            saved += 1
            start_order += 1
        except Exception as e:
            logger.warning(f"L8: could not save concern: {e}")

    logger.info(f"L8 complete — {saved} concern rows saved")
    return saved


def _build_brand_map(db: Client, patient_id: str, findings: list[dict]) -> dict:
    all_generics: set[str] = set()
    for f in findings:
        entities = _parse_json(f.get("related_entities"))
        for m in (entities.get("medications") or []):
            all_generics.add(m.lower())
    if not all_generics:
        return {}
    meds = (db.table("medications").select("drug_name_generic,drug_name_brand")
            .eq("patient_id", patient_id).eq("is_deleted", False).execute()).data
    brand_map: dict[str, str] = {}
    for m in meds:
        g = (m.get("drug_name_generic") or "").strip()
        b = (m.get("drug_name_brand") or "").strip()
        if g and b:
            brand_map[g] = b
    return brand_map


def _fallback_concerns(finding_inputs: list[dict]) -> list[dict]:
    return [_independent_concern(fi) for fi in finding_inputs]


def _independent_concern(fi: dict) -> dict:
    category = fi.get("classification", "new")
    sev = fi.get("severity", "informational")
    priority_map = {"critical": "critical_concern", "high": "high_priority",
                    "moderate": "moderate", "low": "for_your_awareness",
                    "informational": "for_your_awareness"}
    return {
        "concern_category": category,
        "priority": priority_map.get(sev, "for_your_awareness"),
        "title": fi.get("title") or "Clinical finding",
        "summary": fi.get("title") or "",
        "what_was_found": fi.get("title") or "",
        "why_it_matters": "This finding was identified in the new documents.",
        "what_to_do": "Discuss with the doctor at the next visit.",
        "evidence": [],
        "source_documents": [],
        "contributing_finding_ids": [fi["finding_id"]],
    }


def _save_no_changes_concern(db: Client, patient_id: str, run_id: str, upload_event_id: str) -> None:
    try:
        db.table("longitudinal_caregiver_concerns").insert({
            "patient_id": patient_id,
            "run_id": run_id,
            "upload_event_id": upload_event_id,
            "concern_type": "independent",
            "concern_category": "new",
            "priority": "for_your_awareness",
            "title": "No new findings in the uploaded documents",
            "summary": "We reviewed the new documents. No new or changed findings were identified.",
            "what_was_found": "All records reviewed. No new clinical concerns found.",
            "why_it_matters": "The new documents appear consistent with the current treatment plan.",
            "what_to_do": "Continue all medications as prescribed. Attend scheduled follow-ups.",
            "evidence": [],
            "source_documents": [],
            "is_nudge": False,
            "display_order": 1,
        }).execute()
    except Exception as e:
        logger.warning(f"L8: could not save no-changes concern: {e}")


def _parse_json(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}
    return {}


_VALID_PRIORITIES = {"critical_concern", "high_priority", "moderate", "for_your_awareness"}


def _valid_priority(val: str | None) -> str:
    return val if val in _VALID_PRIORITIES else "for_your_awareness"
```

- [ ] **Step 2: Commit**

```bash
git add services/longitudinal_orchestration.py
git commit -m "feat: add longitudinal orchestration service (L8)"
```

---

## Task 5: Pipeline Orchestrator

**Files:**
- Create: `services/longitudinal_pipeline.py`

- [ ] **Step 1: Write the service**

```python
"""
Longitudinal pipeline orchestrator.
log_event() — structured logging to DB + Python logger.
run_pre_gate_pipeline() — L1→L3, sets status='reconciling'.
run_post_gate_pipeline() — L5→L10, sets status='ready'.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from supabase import Client
from services import storage, ocr, pdf_extractor, llm
from services.resolver import resolve_drug_name
from services.deduplicator import deduplicate_medications, deduplicate_conditions, deduplicate_allergies
from services.longitudinal_comparison import load_and_save_baseline, compare_entities
from services.longitudinal_classification import classify_findings, generate_nudge_cards
from services.longitudinal_orchestration import run_longitudinal_orchestration

logger = logging.getLogger("carecircle.longitudinal")

OCR_CONFIDENCE_THRESHOLD = 0.40
OCR_PENALTY_THRESHOLD = 0.65


# ── Structured logger ─────────────────────────────────────────────────────────

def log_event(
    db: Client,
    run_id: str | None,
    upload_event_id: str | None,
    phase: str,
    event: str,
    detail: dict | None = None,
    level: str = "INFO",
) -> None:
    msg = f"[{phase}] {event}"
    if detail:
        msg += f" — {json.dumps(detail, default=str)}"
    if level == "ERROR":
        logger.error(msg)
    elif level == "WARNING":
        logger.warning(msg)
    else:
        logger.info(msg)
    try:
        db.table("longitudinal_pipeline_logs").insert({
            "run_id": run_id,
            "upload_event_id": upload_event_id,
            "phase": phase,
            "event": event,
            "level": level,
            "detail": detail or {},
        }).execute()
    except Exception as e:
        logger.warning(f"Could not write pipeline log: {e}")


# ── Pre-gate pipeline (L1 → L3) ───────────────────────────────────────────────

async def run_pre_gate_pipeline(
    patient_id: str,
    upload_event_id: str,
    db: Client,
) -> None:
    """L1→L3: extract, normalize, compare against baseline. Sets status='reconciling'."""
    run_id = None
    try:
        # Create longitudinal_run record
        run_result = db.table("longitudinal_runs").insert({
            "patient_id": patient_id,
            "upload_event_id": upload_event_id,
            "status": "success",
        }).execute()
        run_id = run_result.data[0]["id"]
        db.table("document_upload_events").update({
            "longitudinal_run_id": run_id
        }).eq("id", upload_event_id).execute()

        log_event(db, run_id, upload_event_id, "L1", "extraction_started")
        _set_upload_status(db, upload_event_id, "extracting")

        # L1: Process documents
        docs = (db.table("documents").select("*")
                .eq("patient_id", patient_id)
                .eq("upload_context", "post_onboarding")
                .eq("extraction_status", "pending")
                .eq("is_deleted", False).execute()).data

        if not docs:
            log_event(db, run_id, upload_event_id, "L1", "no_documents_found", level="ERROR")
            _set_upload_status(db, upload_event_id, "failed",
                               error="No pending documents found for this upload event")
            return

        succeeded = 0
        failed = 0
        for doc in docs:
            ok = await _process_document_longitudinal(doc, patient_id, db)
            if ok:
                succeeded += 1
            else:
                failed += 1

        log_event(db, run_id, upload_event_id, "L1", "extraction_complete",
                  {"succeeded": succeeded, "failed": failed})

        if succeeded == 0:
            _set_upload_status(db, upload_event_id, "failed",
                               error=f"All {failed} documents failed extraction")
            db.table("longitudinal_runs").update({"status": "failed"}).eq("id", run_id).execute()
            return

        if failed > 0:
            log_event(db, run_id, upload_event_id, "L1", "partial_failure",
                      {"failed_count": failed}, level="WARNING")

        # L2: Normalize + deduplicate
        log_event(db, run_id, upload_event_id, "L2", "normalization_started")
        await _batch_normalize_medications_longitudinal(patient_id, db)
        await deduplicate_medications(db, patient_id)
        await deduplicate_conditions(db, patient_id)
        await deduplicate_allergies(db, patient_id)
        log_event(db, run_id, upload_event_id, "L2", "normalization_complete")

        # L3: Baseline load + entity comparison
        log_event(db, run_id, upload_event_id, "L3", "comparison_started")
        try:
            baseline = load_and_save_baseline(db, patient_id, run_id)
        except Exception as e:
            log_event(db, run_id, upload_event_id, "L3", "baseline_load_failed",
                      {"error": str(e)}, level="ERROR")
            _set_upload_status(db, upload_event_id, "failed", error=f"L3 baseline load failed: {e}")
            db.table("longitudinal_runs").update({"status": "failed"}).eq("id", run_id).execute()
            return

        try:
            compare_entities(db, patient_id, run_id, upload_event_id, baseline)
        except Exception as e:
            log_event(db, run_id, upload_event_id, "L3", "comparison_partial_failure",
                      {"error": str(e)}, level="WARNING")

        log_event(db, run_id, upload_event_id, "L3", "comparison_complete")
        _set_upload_status(db, upload_event_id, "reconciling")
        db.table("patients").update({"longitudinal_status": "processing"}).eq("id", patient_id).execute()

    except Exception as e:
        log_event(db, run_id, upload_event_id, "L1-L3", "pipeline_failed",
                  {"error": str(e)}, level="ERROR")
        _set_upload_status(db, upload_event_id, "failed", error=str(e))
        if run_id:
            db.table("longitudinal_runs").update({"status": "failed"}).eq("id", run_id).execute()


# ── Post-gate pipeline (L5 → L10) ────────────────────────────────────────────

async def run_post_gate_pipeline(
    patient_id: str,
    upload_event_id: str,
    db: Client,
) -> None:
    """L5→L10: reasoning, classification, orchestration, action summary, state update."""
    run_row = (db.table("document_upload_events").select("longitudinal_run_id")
               .eq("id", upload_event_id).limit(1).execute()).data
    run_id = run_row[0]["longitudinal_run_id"] if run_row else None

    try:
        _set_upload_status(db, upload_event_id, "reasoning")

        # L5: Reasoning
        log_event(db, run_id, upload_event_id, "L5", "reasoning_started")
        prior_findings = (db.table("clinical_findings").select("*")
                          .eq("patient_id", patient_id)
                          .in_("status", ["open", "monitoring", "recurring"]).execute()).data

        patient_state = _build_longitudinal_patient_state(db, patient_id, upload_event_id, run_id)
        new_finding_ids = await _run_longitudinal_reasoning(db, patient_id, patient_state, run_id)
        log_event(db, run_id, upload_event_id, "L5", "reasoning_complete",
                  {"findings_saved": len(new_finding_ids)})

        # L6: Classification
        log_event(db, run_id, upload_event_id, "L6", "classification_started")
        unsuppressed_ids, suppressed_ids = classify_findings(
            db, patient_id, run_id, new_finding_ids, prior_findings
        )
        log_event(db, run_id, upload_event_id, "L6", "classification_complete",
                  {"unsuppressed": len(unsuppressed_ids), "suppressed": len(suppressed_ids)})

        # L7: Nudge generation
        log_event(db, run_id, upload_event_id, "L7", "nudge_generation_started")
        nudge_cards = generate_nudge_cards(
            db, patient_id, run_id, upload_event_id, suppressed_ids
        )
        log_event(db, run_id, upload_event_id, "L7", "nudge_generation_complete",
                  {"nudge_count": len(nudge_cards)})

        # L8: Orchestration
        log_event(db, run_id, upload_event_id, "L8", "orchestration_started")
        _set_upload_status(db, upload_event_id, "orchestrating")
        medication_transitions = (db.table("medication_state_transitions").select("*")
                                  .eq("run_id", run_id)
                                  .eq("guardian_confirmed", True).execute()).data

        await run_longitudinal_orchestration(
            db, patient_id, run_id, upload_event_id,
            unsuppressed_ids, nudge_cards, medication_transitions
        )
        log_event(db, run_id, upload_event_id, "L8", "orchestration_complete")

        # L9: Action summary
        log_event(db, run_id, upload_event_id, "L9", "action_summary_started")
        try:
            await _run_action_summary_longitudinal(db, patient_id, run_id)
            log_event(db, run_id, upload_event_id, "L9", "action_summary_complete")
        except Exception as e:
            log_event(db, run_id, upload_event_id, "L9", "action_summary_failed",
                      {"error": str(e)}, level="WARNING")

        # L10: State update (retry 3x)
        log_event(db, run_id, upload_event_id, "L10", "state_update_started")
        await _run_state_update_with_retry(db, patient_id, run_id, upload_event_id)

        _set_upload_status(db, upload_event_id, "ready")
        if run_id:
            db.table("longitudinal_runs").update({"status": "success"}).eq("id", run_id).execute()
        log_event(db, run_id, upload_event_id, "L10", "pipeline_complete")

    except Exception as e:
        log_event(db, run_id, upload_event_id, "L5-L10", "pipeline_failed",
                  {"error": str(e)}, level="ERROR")
        _set_upload_status(db, upload_event_id, "failed", error=str(e))
        if run_id:
            db.table("longitudinal_runs").update({"status": "failed"}).eq("id", run_id).execute()
        db.table("patients").update({"longitudinal_status": "failed"}).eq("id", patient_id).execute()


# ── L5 helpers ────────────────────────────────────────────────────────────────

def _build_longitudinal_patient_state(
    db: Client,
    patient_id: str,
    upload_event_id: str,
    run_id: str | None,
) -> dict:
    """Build enriched patient state for reasoning — includes transition_type on meds, prior findings with times_seen."""
    patient = (db.table("patients").select("*").eq("id", patient_id).execute()).data
    patient_row = patient[0] if patient else {}

    meds = (db.table("medications").select("*")
            .eq("patient_id", patient_id).eq("is_deleted", False).execute()).data

    # Attach transition_type from this run
    transitions = {}
    if run_id:
        trans_rows = (db.table("medication_state_transitions").select("*")
                      .eq("run_id", run_id).execute()).data
        for t in trans_rows:
            med_id = t.get("medication_id")
            if med_id:
                transitions[med_id] = t.get("transition_type", "continued")

    enriched_meds = []
    for m in meds:
        enriched_meds.append({
            **m,
            "transition_type": transitions.get(m["id"], "continued"),
        })

    labs = (db.table("lab_results").select("*")
            .eq("patient_id", patient_id)
            .order("report_date", desc=True).limit(30).execute()).data

    diagnoses = (db.table("diagnoses").select("*").eq("patient_id", patient_id).execute()).data
    directives = (db.table("clinical_directives").select("*")
                  .eq("patient_id", patient_id).eq("is_active", True).execute()).data
    monitoring = (db.table("monitoring_instructions").select("*")
                  .eq("patient_id", patient_id).execute()).data
    allergies = (db.table("allergies").select("*").eq("patient_id", patient_id).execute()).data
    doctors = (db.table("doctors").select("*").eq("patient_id", patient_id).execute()).data

    # Prior findings with full clinical_evidence + related_entities + times_seen
    prior_findings = (db.table("clinical_findings").select("*")
                      .eq("patient_id", patient_id)
                      .in_("status", ["open", "monitoring", "recurring"]).execute()).data

    # Brand map
    brand_map: dict[str, str] = {}
    for m in meds:
        g = (m.get("drug_name_generic") or "").lower()
        b = m.get("drug_name_brand") or ""
        if g and b:
            brand_map[g] = b

    return {
        "patient": {
            "id": patient_id,
            "name": patient_row.get("full_name", ""),
            "date_of_birth": str(patient_row.get("date_of_birth") or ""),
            "gender": patient_row.get("gender"),
            "city": patient_row.get("city"),
            "post_onboarding_upload_count": patient_row.get("post_onboarding_upload_count", 0),
        },
        "medications": enriched_meds,
        "lab_results": labs,
        "diagnoses": diagnoses,
        "clinical_directives": directives,
        "monitoring_instructions": monitoring,
        "allergies": allergies,
        "doctors": doctors,
        "prior_findings": prior_findings,
        "brand_map": brand_map,
        "context": {
            "pipeline": "longitudinal",
            "upload_event_id": upload_event_id,
            "run_id": run_id,
        },
    }


async def _run_longitudinal_reasoning(
    db: Client,
    patient_id: str,
    patient_state: dict,
    run_id: str | None,
) -> list[str]:
    """Call llm.run_reasoning, apply quality gates, save findings. Returns list of saved finding IDs."""
    try:
        result = await llm.run_reasoning(patient_state)
    except Exception as e:
        logger.warning(f"L5 reasoning LLM failed: {e}")
        return []

    findings = result.get("findings") or result.get("items") or []
    if not isinstance(findings, list):
        logger.warning(f"L5: unexpected reasoning output shape: {type(findings)}")
        return []

    saved_ids: list[str] = []
    for f in findings:
        # Quality gates
        if float(f.get("confidence") or 0) < 0.05:
            continue
        evidence = f.get("clinical_evidence")
        if not evidence:
            continue

        try:
            row = db.table("clinical_findings").insert({
                "patient_id": patient_id,
                "finding_type": f.get("finding_type", "unknown"),
                "dimension": f.get("dimension"),
                "severity": f.get("severity", "informational"),
                "title": (f.get("title") or "")[:200],
                "clinical_evidence": json.dumps(f.get("clinical_evidence") or []),
                "source_documents": None,
                "related_entities": json.dumps(f.get("related_entities") or {}),
                "is_patient_specific": True,
                "patient_context": f.get("patient_specific_reasoning"),
                "confidence": f.get("confidence"),
                "status": "open",
                "last_seen_run_id": run_id,
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "times_seen": 1,
            }).execute()
            if row.data:
                saved_ids.append(row.data[0]["id"])
        except Exception as e:
            logger.warning(f"L5: could not save finding: {e}")

    return saved_ids


# ── L9 ────────────────────────────────────────────────────────────────────────

async def _run_action_summary_longitudinal(
    db: Client,
    patient_id: str,
    run_id: str | None,
) -> None:
    """L9: Build action summary from longitudinal concerns. Saves to patient_action_summaries."""
    concerns = (db.table("longitudinal_caregiver_concerns").select("*")
                .eq("patient_id", patient_id)
                .eq("run_id", run_id).execute()).data if run_id else []

    do_now = []
    follow_up = []
    ongoing = []
    resolved_since = []

    for c in concerns:
        cat = c.get("concern_category", "new")
        pri = c.get("priority", "for_your_awareness")
        item = {"action": c.get("what_to_do") or "", "source": c.get("title") or ""}

        if cat in ("new", "escalated") and pri in ("critical_concern", "high_priority"):
            do_now.append(item)
        elif cat == "resolved":
            resolved_since.append(item)
        elif pri in ("moderate",):
            follow_up.append(item)
        else:
            ongoing.append(item)

    db.table("patient_action_summaries").update({"is_current": False}).eq("patient_id", patient_id).execute()
    db.table("patient_action_summaries").insert({
        "patient_id": patient_id,
        "do_now": do_now,
        "follow_up": follow_up,
        "ongoing_monitoring": ongoing,
        "resolved_since_last_upload": resolved_since,
        "is_current": True,
    }).execute()


# ── L10 ───────────────────────────────────────────────────────────────────────

async def _run_state_update_with_retry(
    db: Client,
    patient_id: str,
    run_id: str | None,
    upload_event_id: str,
    max_retries: int = 3,
) -> None:
    """L10: apply confirmed medication transitions, update patient counters. Retries 3x."""
    for attempt in range(max_retries):
        try:
            if run_id:
                transitions = (db.table("medication_state_transitions").select("*")
                               .eq("run_id", run_id)
                               .eq("guardian_confirmed", True).execute()).data
                for t in transitions:
                    med_id = t.get("medication_id")
                    if not med_id:
                        continue
                    tt = t.get("transition_type")
                    updates: dict = {}
                    if tt == "dose_changed" and t.get("new_dose_mg"):
                        updates["dose_mg"] = t["new_dose_mg"]
                    if tt == "frequency_changed" and t.get("new_frequency"):
                        updates["frequency"] = t["new_frequency"]
                    if tt in ("removed", "status_changed") and t.get("guardian_action") == "stopped":
                        updates["status"] = "stopped"
                        updates["is_current"] = False
                    if updates:
                        db.table("medications").update(updates).eq("id", med_id).execute()

            db.table("patients").update({
                "post_onboarding_upload_count": db.rpc(
                    "increment_upload_count", {"p_patient_id": patient_id}
                ),
                "last_document_upload_at": datetime.now(timezone.utc).isoformat(),
                "longitudinal_status": "idle",
            }).eq("id", patient_id).execute()
            return

        except Exception as e:
            logger.warning(f"L10 attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.critical(f"L10 all retries failed for patient {patient_id}: {e}")
                db.table("patients").update({"longitudinal_status": "failed"}).eq("id", patient_id).execute()
                raise


# ── L1 document processing ────────────────────────────────────────────────────

async def _process_document_longitudinal(doc: dict, patient_id: str, db: Client) -> bool:
    doc_id = doc["id"]
    mime = doc.get("mime_type") or doc.get("file_type") or "application/octet-stream"
    logger.info(f"L1 processing: {doc['original_filename']} ({mime})")

    db.table("documents").update({"extraction_status": "processing"}).eq("id", doc_id).execute()

    try:
        file_bytes = db.storage.from_("documents").download(doc["storage_path"])

        if mime.startswith("image/"):
            raw_text, confidence = await ocr.extract_text_from_image(file_bytes, mime)
        else:
            raw_text = pdf_extractor.extract_text_from_pdf(file_bytes)
            confidence = 1.0
            if len(raw_text.strip()) < 50:
                page_images = pdf_extractor.render_pdf_to_images(file_bytes)
                page_texts, confidences = [], []
                for img_bytes in page_images:
                    pt, pc = await ocr.extract_text_from_image(img_bytes, "image/png")
                    page_texts.append(pt)
                    confidences.append(pc)
                raw_text = "\n".join(page_texts)
                confidence = sum(confidences) / len(confidences) if confidences else 0.0

        if confidence < OCR_CONFIDENCE_THRESHOLD:
            db.table("documents").update({"extraction_status": "needs_review"}).eq("id", doc_id).execute()
            return False

        penalty = 0.85 if confidence < OCR_PENALTY_THRESHOLD else 1.0

        doc_type = doc["document_type"]
        extracted = {}
        try:
            if doc_type == "prescription":
                extracted = await llm.extract_prescription(raw_text)
            elif doc_type == "lab_report":
                extracted = await llm.extract_lab_report(raw_text)
            elif doc_type == "discharge_summary":
                extracted = await llm.extract_discharge_summary(raw_text)
        except Exception as e:
            logger.error(f"L1 LLM extraction failed for {doc_id}: {e}")
            db.table("documents").update({"extraction_status": "failed"}).eq("id", doc_id).execute()
            return False

        extraction_id_result = db.table("document_extractions").insert({
            "document_id": doc_id,
            "patient_id": patient_id,
            "raw_ocr_text": raw_text,
            "ocr_confidence": round(confidence, 3),
            "extracted_data": extracted,
            "extraction_model": "google/gemini-2.5-flash",
            "overall_confidence": round(confidence * penalty, 3),
        }).execute()
        extraction_id = extraction_id_result.data[0]["id"] if extraction_id_result.data else None

        # Use same merge logic as onboarding (import the private function)
        from services.extraction_pipeline import _merge_to_layer3
        await _merge_to_layer3(
            doc_id, extraction_id, patient_id, doc_type, extracted,
            confidence * penalty, db
        )

        db.table("documents").update({"extraction_status": "completed"}).eq("id", doc_id).execute()
        return True

    except Exception as e:
        logger.error(f"L1 document processing failed {doc_id}: {e}", exc_info=True)
        db.table("documents").update({"extraction_status": "failed"}).eq("id", doc_id).execute()
        return False


async def _batch_normalize_medications_longitudinal(patient_id: str, db: Client) -> None:
    from services.extraction_pipeline import _batch_normalize_medications
    await _batch_normalize_medications(patient_id, db)


# ── Utility ───────────────────────────────────────────────────────────────────

def _set_upload_status(db: Client, upload_event_id: str, status: str, error: str | None = None) -> None:
    updates: dict = {"processing_status": status}
    if error:
        updates["error_message"] = error[:500]
    try:
        db.table("document_upload_events").update(updates).eq("id", upload_event_id).execute()
    except Exception as e:
        logger.warning(f"Could not set upload status: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add services/longitudinal_pipeline.py
git commit -m "feat: add longitudinal pipeline orchestrator (L1-L10)"
```

---

## Task 6: Router

**Files:**
- Create: `routers/longitudinal.py`

- [ ] **Step 1: Write the router**

```python
"""
Longitudinal pipeline router — 7 endpoints.
All under /api/longitudinal/. All require bearer token auth.
"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from supabase import Client
from db.client import get_db
from dependencies import get_current_user
from services.storage import upload_file
from services.longitudinal_pipeline import run_pre_gate_pipeline, run_post_gate_pipeline, log_event
from config.logging import get_logger

logger = get_logger("LONGITUDINAL")
router = APIRouter(prefix="/api/longitudinal", tags=["longitudinal"])


@router.post("/upload/{patient_id}")
async def upload_documents(
    patient_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    file_types: str = Form("[]"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Upload new post-onboarding documents. Starts L1→L3 background pipeline."""
    patient = db.table("patients").select("onboarding_status,longitudinal_status").eq("id", patient_id).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail="Patient not found")

    onboarding_status = patient.data[0].get("onboarding_status")
    if onboarding_status != "complete":
        raise HTTPException(status_code=400, detail="Patient onboarding must be complete before uploading new documents")

    file_types_list = json.loads(file_types) if file_types else []

    # Create upload event
    event_result = db.table("document_upload_events").insert({
        "patient_id": patient_id,
        "processing_status": "pending",
        "uploaded_files": [f.filename for f in files],
    }).execute()
    if not event_result.data:
        raise HTTPException(status_code=500, detail="Could not create upload event")
    upload_event_id = event_result.data[0]["id"]

    # Upload files to storage and create document records
    for i, uploaded_file in enumerate(files):
        file_bytes = await uploaded_file.read()
        doc_type = file_types_list[i] if i < len(file_types_list) else "other"
        storage_path = upload_file(
            db=db, patient_id=patient_id, document_type=doc_type,
            filename=uploaded_file.filename, file_bytes=file_bytes,
            mime_type=uploaded_file.content_type or "application/octet-stream",
        )
        mime = uploaded_file.content_type or "application/octet-stream"
        db.table("documents").insert({
            "patient_id": patient_id,
            "document_type": doc_type,
            "original_filename": uploaded_file.filename,
            "storage_path": storage_path,
            "mime_type": mime,
            "file_type": mime,
            "extraction_status": "pending",
            "upload_context": "post_onboarding",
            "is_deleted": False,
        }).execute()

    db.table("patients").update({"longitudinal_status": "processing"}).eq("id", patient_id).execute()

    background_tasks.add_task(run_pre_gate_pipeline, patient_id=patient_id,
                              upload_event_id=upload_event_id, db=db)

    return {"upload_event_id": upload_event_id, "status": "extracting"}


@router.get("/status/{patient_id}/{upload_event_id}")
async def get_upload_status(
    patient_id: str,
    upload_event_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Poll every 3s for processing_status."""
    row = (db.table("document_upload_events").select("processing_status,error_message")
           .eq("id", upload_event_id).eq("patient_id", patient_id).execute()).data
    if not row:
        raise HTTPException(status_code=404, detail="Upload event not found")
    ev = row[0]
    return {
        "upload_event_id": upload_event_id,
        "processing_status": ev["processing_status"],
        "error_message": ev.get("error_message"),
    }


@router.get("/medication_reconciliation/{patient_id}/{upload_event_id}")
async def get_medication_reconciliation(
    patient_id: str,
    upload_event_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Returns existing medications and newly extracted ones for L4 guardian review."""
    ev = (db.table("document_upload_events").select("processing_status,longitudinal_run_id")
          .eq("id", upload_event_id).execute()).data
    if not ev:
        raise HTTPException(status_code=404, detail="Upload event not found")
    if ev[0]["processing_status"] != "reconciling":
        raise HTTPException(status_code=400, detail=f"Upload not in reconciling state (current: {ev[0]['processing_status']})")

    run_id = ev[0].get("longitudinal_run_id")

    # Existing medications (pre-this-upload, guardian-confirmed, active)
    existing_meds = (db.table("medications").select("*")
                     .eq("patient_id", patient_id)
                     .eq("is_deleted", False)
                     .eq("is_current", True).execute()).data

    # New medications from this upload (via transition records)
    transitions = []
    if run_id:
        transitions = (db.table("medication_state_transitions").select("*")
                       .eq("run_id", run_id).execute()).data

    # Separate added vs changed vs continued
    added = [t for t in transitions if t["transition_type"] == "added"]
    changed = [t for t in transitions if t["transition_type"] not in ("added", "continued")]
    continued = [t for t in transitions if t["transition_type"] == "continued"]

    return {
        "existing_medications": [
            {
                "medication_id": m["id"],
                "drug_name_brand": m.get("drug_name_brand"),
                "drug_name_generic": m.get("drug_name_generic"),
                "dose_text": m.get("dose_text") or m.get("dosage"),
                "frequency": m.get("frequency"),
                "status": m.get("status"),
            }
            for m in existing_meds
        ],
        "newly_extracted_medications": [
            {
                "transition_id": t["id"],
                "transition_type": t["transition_type"],
                "drug_name_brand": t.get("drug_name_brand"),
                "drug_name_generic": t.get("drug_name_generic"),
                "prior_dose_mg": t.get("prior_dose_mg"),
                "new_dose_mg": t.get("new_dose_mg"),
                "prior_frequency": t.get("prior_frequency"),
                "new_frequency": t.get("new_frequency"),
                "source_document": t.get("source_document"),
            }
            for t in (added + changed)
        ],
        "continued_medications": len(continued),
    }


@router.post("/confirm_reconciliation/{patient_id}/{upload_event_id}")
async def confirm_reconciliation(
    patient_id: str,
    upload_event_id: str,
    body: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Guardian confirms each medication. body: {"confirmations": [{"transition_id": ..., "action": "confirm|edit|remove", "guardian_action": "still_taking|stopped|held|not_sure"}]}
    Marks transitions guardian_confirmed=True, then triggers L5→L10.
    """
    ev = (db.table("document_upload_events").select("processing_status,longitudinal_run_id")
          .eq("id", upload_event_id).execute()).data
    if not ev:
        raise HTTPException(status_code=404, detail="Upload event not found")
    if ev[0]["processing_status"] != "reconciling":
        raise HTTPException(status_code=400, detail="Upload is not in reconciling state")

    confirmations = body.get("confirmations") or []
    for conf in confirmations:
        tid = conf.get("transition_id")
        if not tid:
            continue
        action = conf.get("action", "confirm")
        guardian_action = conf.get("guardian_action", "still_taking")

        updates: dict = {
            "guardian_confirmed": True,
            "guardian_action": guardian_action,
        }
        if action == "edit":
            if conf.get("new_dose_mg"):
                updates["new_dose_mg"] = conf["new_dose_mg"]
            if conf.get("new_frequency"):
                updates["new_frequency"] = conf["new_frequency"]

        if action != "remove":
            try:
                db.table("medication_state_transitions").update(updates).eq("id", tid).execute()
            except Exception as e:
                logger.warning(f"Could not update transition {tid}: {e}")

    db.table("document_upload_events").update({"processing_status": "reasoning"}).eq("id", upload_event_id).execute()
    background_tasks.add_task(run_post_gate_pipeline, patient_id=patient_id,
                              upload_event_id=upload_event_id, db=db)

    return {"status": "reasoning_running", "upload_event_id": upload_event_id}


@router.get("/findings/{patient_id}/{upload_event_id}")
async def get_findings(
    patient_id: str,
    upload_event_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Returns full longitudinal findings when processing_status='ready'."""
    ev = (db.table("document_upload_events").select("processing_status,longitudinal_run_id")
          .eq("id", upload_event_id).execute()).data
    if not ev:
        raise HTTPException(status_code=404, detail="Upload event not found")

    status = ev[0]["processing_status"]
    if status not in ("ready", "failed"):
        return {"status": "running", "processing_status": status}

    run_id = ev[0].get("longitudinal_run_id")

    # Run summary
    run_summary = {}
    if run_id:
        run_row = (db.table("longitudinal_runs").select("*").eq("id", run_id).execute()).data
        if run_row:
            r = run_row[0]
            run_summary = {
                "findings_new": r.get("findings_new", 0),
                "findings_escalated": r.get("findings_escalated", 0),
                "findings_resolved": r.get("findings_resolved", 0),
                "findings_improved": r.get("findings_improved", 0),
                "findings_recurring_suppressed": r.get("findings_suppressed", 0),
            }

    # Medication changes
    medication_changes = []
    if run_id:
        trans = (db.table("medication_state_transitions").select("*")
                 .eq("run_id", run_id)
                 .neq("transition_type", "continued").execute()).data
        medication_changes = [
            {
                "drug_name_brand": t.get("drug_name_brand"),
                "drug_name_generic": t.get("drug_name_generic"),
                "transition_type": t.get("transition_type"),
                "prior_dose_mg": t.get("prior_dose_mg"),
                "new_dose_mg": t.get("new_dose_mg"),
                "prior_frequency": t.get("prior_frequency"),
                "new_frequency": t.get("new_frequency"),
                "source_document": t.get("source_document"),
            }
            for t in trans
        ]

    # Concerns
    concerns = []
    concern_summary = {"new": 0, "escalated": 0, "resolved": 0, "improved": 0, "nudge_items": 0}
    if run_id:
        concern_rows = (db.table("longitudinal_caregiver_concerns").select("*")
                        .eq("run_id", run_id)
                        .order("display_order").execute()).data
        for c in concern_rows:
            cat = c.get("concern_category", "new")
            if cat in concern_summary:
                concern_summary[cat] += 1
            elif c.get("is_nudge"):
                concern_summary["nudge_items"] += 1

            concerns.append({
                "concern_id": str(c["id"]),
                "concern_type": c.get("concern_type"),
                "concern_category": cat,
                "priority": c.get("priority"),
                "title": c.get("title"),
                "summary": c.get("summary"),
                "what_was_found": c.get("what_was_found"),
                "why_it_matters": c.get("why_it_matters"),
                "what_to_do": c.get("what_to_do"),
                "evidence": c.get("evidence") or [],
                "source_documents": c.get("source_documents") or [],
                "is_nudge": c.get("is_nudge", False),
                "nudge_original_finding_date": str(c.get("nudge_original_finding_date") or ""),
                "display_order": c.get("display_order", 0),
            })

    # Action summary
    action_summary_row = (db.table("patient_action_summaries").select("*")
                          .eq("patient_id", patient_id)
                          .eq("is_current", True).limit(1).execute()).data
    action_summary = None
    if action_summary_row:
        a = action_summary_row[0]
        action_summary = {
            "do_now": a.get("do_now") or [],
            "follow_up": a.get("follow_up") or [],
            "ongoing_monitoring": a.get("ongoing_monitoring") or [],
            "resolved_since_last_upload": a.get("resolved_since_last_upload") or [],
        }

    return {
        "status": status,
        "run_summary": run_summary,
        "medication_changes": medication_changes,
        "concerns": concerns,
        "concern_summary": concern_summary,
        "action_summary": action_summary,
    }


@router.post("/confirm_findings/{patient_id}/{upload_event_id}")
async def confirm_findings(
    patient_id: str,
    upload_event_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Guardian acknowledges findings. Marks concerns acknowledged."""
    ev = (db.table("document_upload_events").select("longitudinal_run_id")
          .eq("id", upload_event_id).execute()).data
    if not ev:
        raise HTTPException(status_code=404, detail="Upload event not found")

    run_id = ev[0].get("longitudinal_run_id")
    acknowledged = 0
    if run_id:
        result = (db.table("longitudinal_caregiver_concerns").update({"is_acknowledged": True})
                  .eq("run_id", run_id).execute())
        acknowledged = len(result.data) if result.data else 0

    return {"status": "complete", "concerns_acknowledged": acknowledged}


@router.get("/logs/{run_id}")
async def get_logs(
    run_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Debug endpoint: returns all pipeline logs for a run."""
    logs = (db.table("longitudinal_pipeline_logs").select("*")
            .eq("run_id", run_id)
            .order("created_at").execute()).data
    return {"run_id": run_id, "log_count": len(logs), "logs": logs}
```

- [ ] **Step 2: Commit**

```bash
git add routers/longitudinal.py
git commit -m "feat: add longitudinal router (7 endpoints)"
```

---

## Task 7: Wire main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Read current main.py**

```bash
cat main.py
```

- [ ] **Step 2: Add the import and router registration**

Add to `main.py` (after the existing router imports and include_router calls):

```python
from routers import longitudinal          # ADD THIS LINE

# ... existing includes ...
app.include_router(longitudinal.router)   # ADD THIS LINE
```

The full imports section becomes:
```python
from routers import auth, onboarding, documents, longitudinal
```

And the router registrations become:
```python
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(documents.router)
app.include_router(longitudinal.router)
```

- [ ] **Step 3: Verify app starts**

```bash
uvicorn main:app --reload --port 8000
```

Expected: no import errors, server starts.

- [ ] **Step 4: Check route is registered**

```bash
curl http://localhost:8000/openapi.json | python3 -c "import json,sys; paths=json.load(sys.stdin)['paths']; print([p for p in paths if 'longitudinal' in p])"
```

Expected: 7 paths listed.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: register longitudinal router in main.py"
```

---

## Task 8: Integration Test

**Files:**
- Create: `tests/test_longitudinal.py`

- [ ] **Step 1: Write the test**

```python
"""
Full longitudinal pipeline integration test.
Runs real DB, real LLM, real OCR.
Prerequisites: onboarding complete for the test patient.

Run with: pytest tests/test_longitudinal.py -v -s
"""
import pytest
import time
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
POLL_INTERVAL = 3
MAX_POLLS = 60


def poll_upload(upload_event_id: str, target_statuses: list[str], token: str, patient_id: str) -> str:
    for _ in range(MAX_POLLS):
        resp = client.get(
            f"/api/longitudinal/status/{patient_id}/{upload_event_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        status = resp.json()["processing_status"]
        print(f"  polling... status={status}")
        if status in target_statuses:
            return status
        if status == "failed":
            raise RuntimeError(f"Upload event failed: {resp.json().get('error_message')}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Did not reach {target_statuses} in time")


@pytest.mark.asyncio
async def test_full_longitudinal_flow(db, test_user_token, sample_prescription_bytes, sample_lab_pdf_bytes):
    headers = {"Authorization": f"Bearer {test_user_token}"}

    # ── Step 0: Complete onboarding first ──────────────────────────────────────
    print("\n[0] Setting role...")
    role_resp = client.post("/api/auth/set-role", headers=headers, json={
        "role": "guardian", "full_name": "Longitudinal Test Guardian", "relationship": "daughter",
    })
    assert role_resp.status_code == 200, role_resp.text

    print("[1] Submitting onboarding...")
    submit_resp = client.post(
        "/api/onboarding/submit",
        headers=headers,
        data={
            "full_name": "Longitudinal Test Patient",
            "date_of_birth": "1960-05-01",
            "gender": "male",
            "city": "Delhi",
            "state": "Delhi",
            "conditions": '["Type 2 Diabetes", "Hypertension"]',
            "medications": '[{"drug_name": "Metformin", "dosage": "500mg", "frequency": "twice daily"}]',
            "allergies": '[]',
            "doctors": '[{"name": "Dr. Test", "specialty": "General", "is_primary": true}]',
            "file_types": '["prescription", "lab_report"]',
        },
        files=[
            ("files", ("prescription.jpg", sample_prescription_bytes, "image/jpeg")),
            ("files", ("lab_report.pdf", sample_lab_pdf_bytes, "application/pdf")),
        ],
    )
    assert submit_resp.status_code == 200, submit_resp.text
    patient_id = submit_resp.json()["patient_id"]
    print(f"    patient_id: {patient_id}")

    # Poll for medication_verification_needed
    print("[2] Waiting for medication_verification_needed...")
    for _ in range(MAX_POLLS):
        s = client.get(f"/api/onboarding/status/{patient_id}", headers=headers).json()["status"]
        print(f"  onboarding status={s}")
        if s == "medication_verification_needed":
            break
        if s in ("failed",):
            pytest.fail(f"Onboarding failed: {s}")
        time.sleep(POLL_INTERVAL)

    meds_resp = client.get(f"/api/onboarding/extracted_medications/{patient_id}", headers=headers)
    assert meds_resp.status_code == 200
    meds_data = meds_resp.json()
    confirmed = [{"medication_id": m["medication_id"], "action": "confirm"} for m in meds_data["medications"]]
    confirm_resp = client.post(
        f"/api/onboarding/confirm_medications/{patient_id}",
        headers=headers,
        json={"confirmed_medications": confirmed, "added_medications": []},
    )
    assert confirm_resp.status_code == 200

    print("[3] Waiting for onboarding findings_ready...")
    for _ in range(MAX_POLLS):
        s = client.get(f"/api/onboarding/status/{patient_id}", headers=headers).json()["status"]
        print(f"  onboarding status={s}")
        if s in ("findings_ready", "complete"):
            break
        time.sleep(POLL_INTERVAL)

    confirm_ob = client.post(f"/api/onboarding/confirm/{patient_id}", headers=headers)
    assert confirm_ob.status_code == 200
    assert confirm_ob.json()["status"] == "complete"
    print(f"[4] Onboarding complete — patient {patient_id}")

    # ── Step 1: Upload new post-onboarding documents ───────────────────────────
    print("\n[LONGITUDINAL] Uploading new documents...")
    upload_resp = client.post(
        f"/api/longitudinal/upload/{patient_id}",
        headers=headers,
        data={"file_types": '["prescription", "lab_report"]'},
        files=[
            ("files", ("new_prescription.jpg", sample_prescription_bytes, "image/jpeg")),
            ("files", ("new_lab_report.pdf", sample_lab_pdf_bytes, "application/pdf")),
        ],
    )
    assert upload_resp.status_code == 200, upload_resp.text
    upload_event_id = upload_resp.json()["upload_event_id"]
    print(f"    upload_event_id: {upload_event_id}")

    # ── Step 2: Poll until reconciling ────────────────────────────────────────
    print("[L2] Polling for reconciling...")
    status = poll_upload(upload_event_id, ["reconciling"], test_user_token, patient_id)
    print(f"    Reached: {status}")

    # ── Step 3: GET medication reconciliation ─────────────────────────────────
    print("[L3] Getting medication reconciliation...")
    recon_resp = client.get(
        f"/api/longitudinal/medication_reconciliation/{patient_id}/{upload_event_id}",
        headers=headers,
    )
    assert recon_resp.status_code == 200, recon_resp.text
    recon_data = recon_resp.json()
    print(f"    existing_medications: {len(recon_data['existing_medications'])}")
    print(f"    newly_extracted: {len(recon_data['newly_extracted_medications'])}")
    assert len(recon_data["existing_medications"]) > 0, "Should have at least one existing medication"

    # ── Step 4: POST confirm reconciliation ───────────────────────────────────
    print("[L4] Confirming reconciliation...")
    confirmations = []
    for t in recon_data["newly_extracted_medications"]:
        confirmations.append({
            "transition_id": t["transition_id"],
            "action": "confirm",
            "guardian_action": "still_taking",
        })
    confirm_recon_resp = client.post(
        f"/api/longitudinal/confirm_reconciliation/{patient_id}/{upload_event_id}",
        headers=headers,
        json={"confirmations": confirmations},
    )
    assert confirm_recon_resp.status_code == 200, confirm_recon_resp.text
    assert confirm_recon_resp.json()["status"] == "reasoning_running"

    # ── Step 5: Poll until ready ───────────────────────────────────────────────
    print("[L5] Polling for ready...")
    status = poll_upload(upload_event_id, ["ready"], test_user_token, patient_id)
    print(f"    Reached: {status}")

    # ── Step 6: GET findings ──────────────────────────────────────────────────
    print("[L6] Getting findings...")
    findings_resp = client.get(
        f"/api/longitudinal/findings/{patient_id}/{upload_event_id}",
        headers=headers,
    )
    assert findings_resp.status_code == 200, findings_resp.text
    findings_data = findings_resp.json()
    print(f"    status: {findings_data['status']}")
    print(f"    run_summary: {findings_data['run_summary']}")
    print(f"    concerns: {len(findings_data['concerns'])}")
    assert findings_data["status"] == "ready"
    assert len(findings_data["concerns"]) > 0, "Should have at least one concern card"
    assert findings_data["run_summary"] is not None
    assert findings_data["action_summary"] is not None

    # ── Step 7: GET logs ───────────────────────────────────────────────────────
    print("[L7] Getting pipeline logs...")
    run_resp = db.table("document_upload_events").select("longitudinal_run_id").eq("id", upload_event_id).execute()
    run_id = run_resp.data[0]["longitudinal_run_id"] if run_resp.data else None
    if run_id:
        logs_resp = client.get(f"/api/longitudinal/logs/{run_id}", headers=headers)
        assert logs_resp.status_code == 200
        logs_data = logs_resp.json()
        print(f"    log count: {logs_data['log_count']}")
        phases_logged = {log["phase"] for log in logs_data["logs"]}
        print(f"    phases logged: {phases_logged}")
        critical_errors = [l for l in logs_data["logs"] if l["level"] == "ERROR"]
        assert len(critical_errors) == 0, f"Pipeline had ERROR logs: {critical_errors}"

    # ── Step 8: POST confirm findings ─────────────────────────────────────────
    print("[L8] Confirming findings...")
    confirm_resp = client.post(
        f"/api/longitudinal/confirm_findings/{patient_id}/{upload_event_id}",
        headers=headers,
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "complete"
    print(f"    acknowledged: {confirm_resp.json()['concerns_acknowledged']}")

    # ── Cleanup ────────────────────────────────────────────────────────────────
    print("\n[CLEANUP] Cleaning up test data...")
    for table in [
        "longitudinal_pipeline_logs",
        "longitudinal_caregiver_concerns",
        "longitudinal_findings",
        "medication_state_transitions",
    ]:
        try:
            db.table(table).delete().eq("patient_id", patient_id).execute()
        except Exception:
            pass

    if run_id:
        try:
            db.table("longitudinal_runs").delete().eq("id", run_id).execute()
        except Exception:
            pass

    try:
        db.table("document_upload_events").delete().eq("patient_id", patient_id).execute()
    except Exception:
        pass

    # Onboarding cleanup
    for table in ["patient_action_summaries", "caregiver_concerns",
                  "temporal_logic_evaluations", "reasoning_runs",
                  "clinical_findings", "open_flags", "culture_findings", "restrictions",
                  "monitoring_instructions", "clinical_directives", "patient_summaries",
                  "drug_safety_checks", "lab_results", "allergies", "diagnoses", "medications",
                  "doctors", "document_extractions", "documents", "patient_guardians"]:
        try:
            db.table(table).delete().eq("patient_id", patient_id).execute()
        except Exception:
            pass

    db.table("patients").delete().eq("id", patient_id).execute()
    print("[DONE] Test complete.")
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/test_longitudinal.py -v -s
```

Expected: all assertions pass, cleanup completes without errors.

- [ ] **Step 3: Commit**

```bash
git add tests/test_longitudinal.py
git commit -m "test: add longitudinal pipeline integration test (L1-L10)"
```

---

## Task 9: Test UI

**Files:**
- Modify: `test_ui/index.html`

- [ ] **Step 1: Read the tail of index.html to find where Screen 6 ends**

```bash
tail -80 test_ui/index.html
```

- [ ] **Step 2: Append longitudinal screens before the closing `</body></script>` tags**

Append the following block immediately before the closing `</body>` tag in `test_ui/index.html`:

```html
<!-- ═══════════════════════════════════════════════════════════════
     LONGITUDINAL PIPELINE — Screens L1-L5 (post-onboarding)
     Run AFTER completing onboarding (Screen 6).
     ═══════════════════════════════════════════════════════════════ -->

<h2 style="margin-top:48px">Longitudinal Pipeline</h2>
<p style="color:#6b7280;margin-bottom:24px">Upload new documents after onboarding is complete. Use the patient_id from Screen 6.</p>

<!-- Screen L1: Upload new documents -->
<div class="step active" id="screen-l1">
  <h3>Screen L1 — Upload New Documents</h3>
  <label>Patient ID (from Screen 6)</label>
  <input id="l-patient-id" placeholder="paste patient_id here" />
  <label>Authorization Token</label>
  <input id="l-token" placeholder="paste Bearer token here" />
  <label>Document Type (file 1)</label>
  <select id="l-doc-type-1">
    <option value="prescription">Prescription</option>
    <option value="lab_report">Lab Report</option>
    <option value="discharge_summary">Discharge Summary</option>
  </select>
  <label>File 1</label>
  <input type="file" id="l-file-1" />
  <label>Document Type (file 2, optional)</label>
  <select id="l-doc-type-2">
    <option value="">-- none --</option>
    <option value="prescription">Prescription</option>
    <option value="lab_report">Lab Report</option>
    <option value="discharge_summary">Discharge Summary</option>
  </select>
  <label>File 2 (optional)</label>
  <input type="file" id="l-file-2" />
  <button onclick="lUpload()">Upload &amp; Start Pipeline</button>
  <pre id="l-upload-result"></pre>
</div>

<!-- Screen L2: Status polling (extracting → reconciling) -->
<div class="step" id="screen-l2">
  <h3>Screen L2 — Polling Status (extracting → reconciling)</h3>
  <p>Auto-polls every 3s after upload. Waiting for <code>reconciling</code> status.</p>
  <pre id="l-status-result">Waiting for upload...</pre>
  <button onclick="lPollStatus(['reconciling'], 'l-status-result', lShowRecon)">Poll Now</button>
</div>

<!-- Screen L3: Medication reconciliation -->
<div class="step" id="screen-l3">
  <h3>Screen L3 — Medication Reconciliation</h3>
  <button onclick="lGetRecon()">Load Medication Reconciliation</button>
  <div id="l-recon-area"></div>
  <button class="success" onclick="lConfirmRecon()">Confirm All &amp; Start Analysis</button>
  <pre id="l-recon-result"></pre>
</div>

<!-- Screen L4: Status polling (reasoning → orchestrating → ready) -->
<div class="step" id="screen-l4">
  <h3>Screen L4 — Polling Status (reasoning → orchestrating → ready)</h3>
  <p>Auto-polls every 3s after reconciliation confirmed. Waiting for <code>ready</code> status.</p>
  <pre id="l-reasoning-result">Waiting for reconciliation confirm...</pre>
  <button onclick="lPollStatus(['ready'], 'l-reasoning-result', lShowFindings)">Poll Now</button>
</div>

<!-- Screen L5: Longitudinal findings -->
<div class="step" id="screen-l5">
  <h3>Screen L5 — Longitudinal Findings</h3>
  <button onclick="lGetFindings()">Load Findings</button>
  <div id="l-run-summary" style="margin:12px 0"></div>
  <div id="l-med-changes" style="margin:12px 0"></div>
  <div id="l-concerns-area"></div>
  <div id="l-action-summary" style="margin:16px 0"></div>
  <button class="success" onclick="lConfirmFindings()">Acknowledge Findings</button>
  <pre id="l-findings-result"></pre>

  <!-- Log viewer -->
  <h4 style="margin-top:24px">Pipeline Log Viewer</h4>
  <button onclick="lGetLogs()">Load Pipeline Logs</button>
  <pre id="l-logs-result" style="max-height:400px;overflow-y:auto"></pre>
</div>

<script>
// ── Longitudinal state ────────────────────────────────────────────────────────
let _lUploadEventId = null;
let _lRunId = null;
let _lPollTimer = null;
let _lReconData = null;

function lHeaders() {
  return { "Authorization": "Bearer " + document.getElementById("l-token").value.trim() };
}
function lPatientId() { return document.getElementById("l-patient-id").value.trim(); }
function lBase() { return "http://localhost:8000"; }

async function lUpload() {
  const pid = lPatientId();
  const file1 = document.getElementById("l-file-1").files[0];
  if (!pid || !file1) { alert("Patient ID and at least one file required"); return; }

  const fd = new FormData();
  const types = [document.getElementById("l-doc-type-1").value];
  fd.append("files", file1, file1.name);

  const file2 = document.getElementById("l-file-2").files[0];
  const type2 = document.getElementById("l-doc-type-2").value;
  if (file2 && type2) {
    fd.append("files", file2, file2.name);
    types.push(type2);
  }
  fd.append("file_types", JSON.stringify(types));

  document.getElementById("l-upload-result").textContent = "Uploading...";
  try {
    const r = await fetch(`${lBase()}/api/longitudinal/upload/${pid}`, {
      method: "POST", headers: lHeaders(), body: fd
    });
    const data = await r.json();
    document.getElementById("l-upload-result").textContent = JSON.stringify(data, null, 2);
    if (data.upload_event_id) {
      _lUploadEventId = data.upload_event_id;
      document.getElementById("l-status-result").textContent = "upload_event_id: " + _lUploadEventId + "\nPolling...";
      lPollStatus(["reconciling"], "l-status-result", lShowRecon);
    }
  } catch(e) {
    document.getElementById("l-upload-result").textContent = "Error: " + e;
  }
}

async function lPollStatus(targetStatuses, outputId, onReached) {
  if (!_lUploadEventId) { alert("No upload event ID. Upload first."); return; }
  if (_lPollTimer) clearInterval(_lPollTimer);
  const el = document.getElementById(outputId);
  _lPollTimer = setInterval(async () => {
    try {
      const r = await fetch(
        `${lBase()}/api/longitudinal/status/${lPatientId()}/${_lUploadEventId}`,
        { headers: lHeaders() }
      );
      const data = await r.json();
      el.textContent = JSON.stringify(data, null, 2);
      if (targetStatuses.includes(data.processing_status)) {
        clearInterval(_lPollTimer);
        if (onReached) onReached(data);
      }
      if (data.processing_status === "failed") {
        clearInterval(_lPollTimer);
        el.textContent = "FAILED: " + JSON.stringify(data, null, 2);
      }
    } catch(e) { el.textContent = "Poll error: " + e; }
  }, 3000);
}

function lShowRecon(data) {
  document.getElementById("l-status-result").textContent += "\n✅ Reached reconciling — see Screen L3";
}

async function lGetRecon() {
  if (!_lUploadEventId) { alert("No upload event ID."); return; }
  try {
    const r = await fetch(
      `${lBase()}/api/longitudinal/medication_reconciliation/${lPatientId()}/${_lUploadEventId}`,
      { headers: lHeaders() }
    );
    _lReconData = await r.json();
    const area = document.getElementById("l-recon-area");
    area.innerHTML = `<p><b>Existing medications:</b> ${_lReconData.existing_medications.length}</p>
      <p><b>Newly extracted / changed:</b> ${_lReconData.newly_extracted_medications.length}</p>
      <p><b>Continued unchanged:</b> ${_lReconData.continued_medications}</p>`;
    _lReconData.newly_extracted_medications.forEach(t => {
      area.innerHTML += `<div class="med-card">
        <b>${t.drug_name_brand || t.drug_name_generic}</b> — <em>${t.transition_type}</em><br>
        Prior dose: ${t.prior_dose_mg || "—"} → New dose: ${t.new_dose_mg || "—"}<br>
        Prior freq: ${t.prior_frequency || "—"} → New freq: ${t.new_frequency || "—"}
      </div>`;
    });
    document.getElementById("l-recon-result").textContent = JSON.stringify(_lReconData, null, 2);
  } catch(e) {
    document.getElementById("l-recon-result").textContent = "Error: " + e;
  }
}

async function lConfirmRecon() {
  if (!_lReconData || !_lUploadEventId) { alert("Load reconciliation first."); return; }
  const confirmations = _lReconData.newly_extracted_medications.map(t => ({
    transition_id: t.transition_id,
    action: "confirm",
    guardian_action: "still_taking"
  }));
  try {
    const r = await fetch(
      `${lBase()}/api/longitudinal/confirm_reconciliation/${lPatientId()}/${_lUploadEventId}`,
      { method: "POST", headers: { ...lHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ confirmations }) }
    );
    const data = await r.json();
    document.getElementById("l-recon-result").textContent = JSON.stringify(data, null, 2);
    if (data.status === "reasoning_running") {
      document.getElementById("l-reasoning-result").textContent = "Reasoning started...\nPolling...";
      lPollStatus(["ready"], "l-reasoning-result", lShowFindings);
    }
  } catch(e) {
    document.getElementById("l-recon-result").textContent = "Error: " + e;
  }
}

function lShowFindings(data) {
  document.getElementById("l-reasoning-result").textContent += "\n✅ Ready — see Screen L5";
}

async function lGetFindings() {
  if (!_lUploadEventId) { alert("No upload event ID."); return; }
  try {
    const r = await fetch(
      `${lBase()}/api/longitudinal/findings/${lPatientId()}/${_lUploadEventId}`,
      { headers: lHeaders() }
    );
    const data = await r.json();
    document.getElementById("l-findings-result").textContent = JSON.stringify(data, null, 2);

    // Run summary pills
    const rs = data.run_summary || {};
    document.getElementById("l-run-summary").innerHTML =
      `<b>Run Summary:</b> ` +
      `<span class="summary-pill pill-red">New: ${rs.findings_new||0}</span>` +
      `<span class="summary-pill pill-amber">Escalated: ${rs.findings_escalated||0}</span>` +
      `<span class="summary-pill pill-blue">Resolved: ${rs.findings_resolved||0}</span>` +
      `<span class="summary-pill pill-gray">Recurring: ${rs.findings_recurring_suppressed||0}</span>`;

    // Med changes
    const mc = data.medication_changes || [];
    let mcHtml = `<b>Medication Changes (${mc.length}):</b><br>`;
    mc.forEach(m => {
      mcHtml += `<span class="summary-pill pill-blue">${m.drug_name_brand||m.drug_name_generic}: ${m.transition_type}</span>`;
    });
    document.getElementById("l-med-changes").innerHTML = mcHtml;

    // Concerns
    const ca = document.getElementById("l-concerns-area");
    ca.innerHTML = "";
    (data.concerns || []).forEach(c => {
      const isNudge = c.is_nudge;
      const cat = c.concern_category || "new";
      const pri = c.priority || "for_your_awareness";
      ca.innerHTML += `
        <div class="concern-card ${pri}" style="${isNudge ? 'border-left-color:#888780;opacity:0.85;' : ''}">
          ${isNudge ? '<span class="concern-badge badge-for_your_awareness">NUDGE</span>' : ''}
          <span class="concern-badge badge-${pri}">${cat.toUpperCase()}</span>
          <b>${c.title}</b>
          <p>${c.summary}</p>
          <p><b>Found:</b> ${c.what_was_found}</p>
          <p><b>Why it matters:</b> ${c.why_it_matters}</p>
          <p><b>What to do:</b> ${c.what_to_do}</p>
        </div>`;
    });

    // Action summary
    const as_ = data.action_summary || {};
    document.getElementById("l-action-summary").innerHTML =
      `<b>Action Summary:</b><br>
       Do Now (${(as_.do_now||[]).length}): ${(as_.do_now||[]).map(a=>a.action).join("; ") || "none"}<br>
       Follow Up (${(as_.follow_up||[]).length}): ${(as_.follow_up||[]).map(a=>a.action).join("; ") || "none"}<br>
       Resolved Since Last Upload (${(as_.resolved_since_last_upload||[]).length})`;

    // Store run_id for logs
    const evRow = data;
    if (!_lRunId) {
      // Try to extract from log endpoint later
    }
  } catch(e) {
    document.getElementById("l-findings-result").textContent = "Error: " + e;
  }
}

async function lConfirmFindings() {
  if (!_lUploadEventId) { alert("No upload event ID."); return; }
  try {
    const r = await fetch(
      `${lBase()}/api/longitudinal/confirm_findings/${lPatientId()}/${_lUploadEventId}`,
      { method: "POST", headers: lHeaders() }
    );
    const data = await r.json();
    document.getElementById("l-findings-result").textContent = "CONFIRMED:\n" + JSON.stringify(data, null, 2);
  } catch(e) {
    document.getElementById("l-findings-result").textContent = "Error: " + e;
  }
}

async function lGetLogs() {
  // Get run_id from upload event
  try {
    const r = await fetch(
      `${lBase()}/api/longitudinal/status/${lPatientId()}/${_lUploadEventId}`,
      { headers: lHeaders() }
    );
    // We need run_id — fetch findings to get it from response or use a direct DB approach
    // For now, ask user to paste run_id
    const runId = prompt("Paste the run_id (from findings response or DB):");
    if (!runId) return;
    _lRunId = runId;
    const lr = await fetch(`${lBase()}/api/longitudinal/logs/${runId}`, { headers: lHeaders() });
    const logs = await lr.json();
    document.getElementById("l-logs-result").textContent = JSON.stringify(logs, null, 2);
  } catch(e) {
    document.getElementById("l-logs-result").textContent = "Error: " + e;
  }
}
</script>
```

- [ ] **Step 3: Verify the HTML is valid (no syntax errors)**

Open `test_ui/index.html` in a browser. Confirm the longitudinal section renders without JS errors in the console.

- [ ] **Step 4: Commit**

```bash
git add test_ui/index.html
git commit -m "feat: add longitudinal test UI screens (L1-L5)"
```

---

## Self-Review Checklist

### Spec Coverage
- [x] L1 (document extraction) — `_process_document_longitudinal` in `longitudinal_pipeline.py`
- [x] L2 (normalization) — delegates to `_batch_normalize_medications` import
- [x] L3 (entity comparison) — `longitudinal_comparison.py`: `load_and_save_baseline`, `compare_entities`
- [x] L4 (reconciliation gate) — router: `GET /medication_reconciliation`, `POST /confirm_reconciliation`
- [x] L5 (reasoning) — `_build_longitudinal_patient_state`, `_run_longitudinal_reasoning` in pipeline
- [x] L6 (classification) — `longitudinal_classification.py`: deterministic classify, updates prior findings
- [x] L7 (nudge generation) — `generate_nudge_cards`: max 4 per tier, always `for_your_awareness`
- [x] L8 (orchestration) — `longitudinal_orchestration.py`: LLM call, fallback, coverage check
- [x] L9 (action summary) — `_run_action_summary_longitudinal`: deterministic from concern categories
- [x] L10 (state update) — `_run_state_update_with_retry`: 3 retries + exponential backoff
- [x] 6 new DB tables — migration SQL
- [x] ALTER TABLE on `clinical_findings` + `patients` — migration SQL
- [x] 7 API endpoints — router
- [x] `log_event()` — writes to Python logger + `longitudinal_pipeline_logs` table
- [x] Baseline snapshot before any writes — `load_and_save_baseline` called before `compare_entities`
- [x] Deterministic classification overrides LLM — `_deterministic_classify` is the only classification path
- [x] Recurring findings suppressed from caregiver (shown as nudge only) — `is_suppressed_from_caregiver=True`
- [x] Nudge cards always at bottom (display_order 1000+) — nudge generation sets high display_order
- [x] L4 gate required before L5 — `confirm_reconciliation` endpoint triggers `run_post_gate_pipeline`
- [x] Caregiver never sees blank screen — `_save_no_changes_concern` fallback in orchestration
- [x] Integration test full L1→L10 — `tests/test_longitudinal.py`
- [x] Test UI longitudinal screens — `test_ui/index.html`

### L10 Note
`increment_upload_count` is a Supabase RPC function. If it doesn't exist, replace with a read-then-write pattern:
```python
current = (db.table("patients").select("post_onboarding_upload_count").eq("id", patient_id).execute()).data
count = (current[0].get("post_onboarding_upload_count") or 0) + 1 if current else 1
db.table("patients").update({
    "post_onboarding_upload_count": count,
    "last_document_upload_at": datetime.now(timezone.utc).isoformat(),
    "longitudinal_status": "idle",
}).eq("id", patient_id).execute()
```
