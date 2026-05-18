"""
L8 — Longitudinal orchestration.
Calls Gemini via existing llm._call with longitudinal-specific prompt.
Nudge cards from L7 are passed through unchanged (no LLM).
Saves everything to longitudinal_caregiver_concerns.
"""
import json
import logging
from supabase import Client
from services.llm import _call as _llm_call

logger = logging.getLogger("carecircle.longitudinal")

_SYSTEM_PROMPT = """\
You are a presentation layer for a caregiver health platform in India.

Your job is to group new, escalated, resolved, and improved clinical findings into
caregiver-friendly concern cards. Recurring findings are shown separately as nudge cards
— do NOT include them in your output.

CRITICAL RULES:
1. Every finding in the input must appear in at least one concern card. Never drop a finding.
2. Use brand names first, generic in brackets: "Glycomet (Metformin)".
   Use ONLY the brand_map provided. Never invent brand names.
3. Priority: critical_concern | high_priority | moderate | for_your_awareness.
4. ESCALATED findings: always state the prior severity AND the new severity explicitly.
5. RESOLVED findings: frame positively — "The records now show improvement in [X]."
6. Medication changes: always surface explicitly in what_was_found.
7. Tone: calm, advisory. Never say "stop", "discontinue", "do not take".
   Say "discuss with doctor before the next dose."
8. Return only valid JSON.\
"""

_USER_TEMPLATE = """\
Brand name map (use these for ALL medication references):
{brand_map_json}

Guardian-confirmed medication changes this upload:
{medication_transitions_json}

Findings to orchestrate (new, escalated, resolved, improved only — no recurring):
{findings_json}

Each finding has: finding_id, classification, finding_type, severity, title,
clinical_evidence, related_entities.

Group into caregiver concern cards. Return JSON:
{{
  "concerns": [
    {{
      "concern_category": "new | escalated | resolved | improved",
      "priority": "critical_concern | high_priority | moderate | for_your_awareness",
      "title": "max 10 words, plain language",
      "summary": "1-2 sentences",
      "what_was_found": "specific details — brand name (generic), values, source, date",
      "why_it_matters": "why this applies to THIS patient specifically",
      "what_to_do": "specific action — what to bring, ask, or show doctor",
      "evidence": [{{"entity": "exact value", "source": "specific doc", "date": "ISO or empty"}}],
      "source_documents": ["document name list"],
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
    """L8: save nudge cards pass-through, orchestrate non-recurring findings via LLM.
    Returns total number of concern rows saved."""
    logger.info(
        f"L8 orchestration — {len(finding_ids_to_orchestrate)} findings, "
        f"{len(nudge_cards)} nudges"
    )
    saved = 0

    # Save nudge cards first (no LLM)
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

    # Load finding rows
    findings = (db.table("clinical_findings").select("*")
                .in_("id", finding_ids_to_orchestrate).execute()).data

    # Load classifications from longitudinal_findings
    lf_rows = (db.table("longitudinal_findings")
               .select("clinical_finding_id,classification")
               .eq("run_id", run_id).execute()).data
    classification_map = {r["clinical_finding_id"]: r["classification"] for r in lf_rows}

    finding_inputs = [
        {
            "finding_id": str(f["id"]),
            "classification": classification_map.get(f["id"], "new"),
            "finding_type": f.get("finding_type", ""),
            "severity": f.get("severity", "informational"),
            "title": f.get("title", ""),
            "clinical_evidence": _parse_json(f.get("clinical_evidence")),
            "related_entities": _parse_json(f.get("related_entities")),
        }
        for f in findings
    ]

    brand_map = _build_brand_map(db, patient_id, findings)

    clean_transitions = [
        {
            "drug_name_brand": t.get("drug_name_brand"),
            "drug_name_generic": t.get("drug_name_generic"),
            "transition_type": t.get("transition_type"),
            "prior_dose_mg": t.get("prior_dose_mg"),
            "new_dose_mg": t.get("new_dose_mg"),
        }
        for t in medication_transitions
    ]

    try:
        result = await _llm_call(
            _SYSTEM_PROMPT,
            _USER_TEMPLATE.format(
                brand_map_json=json.dumps(brand_map, ensure_ascii=False, indent=2),
                medication_transitions_json=json.dumps(clean_transitions, ensure_ascii=False, indent=2),
                findings_json=json.dumps(finding_inputs, ensure_ascii=False, indent=2),
            ),
            timeout=180,
        )
        concerns = result.get("concerns") or []
        if not isinstance(concerns, list):
            raise ValueError(f"LLM returned non-list: {type(concerns)}")
    except Exception as e:
        logger.warning(f"L8 LLM failed: {e} — using fallback (one card per finding)")
        concerns = [_independent_concern(fi) for fi in finding_inputs]

    # Ensure all finding_ids are covered
    covered: set[str] = set()
    for c in concerns:
        covered.update(str(fid) for fid in (c.get("contributing_finding_ids") or []))
    for fi in finding_inputs:
        if fi["finding_id"] not in covered:
            concerns.append(_independent_concern(fi))

    # Save concern cards in display order
    for order_idx, c in enumerate(concerns, start=1):
        cat = c.get("concern_category", "new")
        if cat not in ("new", "escalated", "resolved", "improved", "nudge"):
            cat = "new"
        try:
            db.table("longitudinal_caregiver_concerns").insert({
                "patient_id": patient_id,
                "run_id": run_id,
                "upload_event_id": upload_event_id,
                "concern_type": "grouped",
                "concern_category": cat,
                "priority": _valid_priority(c.get("priority")),
                "title": (c.get("title") or "Finding")[:500],
                "summary": c.get("summary") or "",
                "what_was_found": c.get("what_was_found") or "",
                "why_it_matters": c.get("why_it_matters") or "",
                "what_to_do": c.get("what_to_do") or "",
                "evidence": c.get("evidence") or [],
                "source_documents": c.get("source_documents") or [],
                "is_nudge": False,
                "display_order": order_idx,
            }).execute()
            saved += 1
        except Exception as e:
            logger.warning(f"L8: could not save concern: {e}")

    logger.info(f"L8 complete — {saved} concern rows saved")
    return saved


def _build_brand_map(db: Client, patient_id: str, findings: list[dict]) -> dict:
    all_generics: set[str] = set()
    for f in findings:
        entities = _parse_json(f.get("related_entities"))
        for m in (entities.get("medications") or []):
            if m:
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


def _independent_concern(fi: dict) -> dict:
    category = fi.get("classification", "new")
    sev = fi.get("severity", "informational")
    priority_map = {
        "critical": "critical_concern", "high": "high_priority",
        "moderate": "moderate", "low": "for_your_awareness",
        "informational": "for_your_awareness",
    }
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


def _save_no_changes_concern(
    db: Client, patient_id: str, run_id: str, upload_event_id: str
) -> None:
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
