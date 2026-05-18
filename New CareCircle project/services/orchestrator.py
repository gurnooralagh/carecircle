"""
Phase 6.5 — Presentation Orchestration Layer.

Reads open_flags + clinical_findings for a patient.
Groups related findings into caregiver concern cards via Gemini.
Writes ONLY to caregiver_concerns table.
Sets onboarding_status = 'findings_ready' after successful completion.
"""
import json
import uuid
from supabase import Client
from config.logging import get_logger
from services.llm import _call as _llm_call

logger = get_logger("ORCHESTRATOR")

_PRIORITY_ORDER = {
    "critical_concern": 0,
    "high_priority": 1,
    "moderate": 2,
    "for_your_awareness": 3,
}
_TYPE_ORDER = {"grouped": 0, "independent": 1, "partial_match_source": 2}
_SEVERITY_TO_PRIORITY = {
    "critical": "critical_concern",
    "high": "high_priority",
    "moderate": "moderate",
    "low": "for_your_awareness",
    "informational": "for_your_awareness",
}

_SYSTEM_PROMPT = """\
You are a presentation orchestration system for a caregiver health platform in India.

Your job is to group related clinical findings into caregiver-friendly concern cards.

YOU ARE NOT modifying clinical data.
YOU ARE NOT changing what was found.
YOU ARE deciding how to present findings to reduce duplication and overload.

CRITICAL RULES:
1. Every finding must appear in at least one concern. You may NOT drop any finding.
2. Priority is grouping to reduce duplication. But if grouping would lose any evidence,
   show the full original finding as a separate independent card alongside the group.
3. Use brand names first, generic in brackets for ALL medication references.
   Use ONLY the brand_map provided. Never invent a brand name not in the map.
4. Priority labels: critical_concern, high_priority, moderate, for_your_awareness.
   Never use "stop immediately." Never say "stop this medication" unless the evidence
   contains an explicit doctor-written STOP instruction. Otherwise say:
   "contact the doctor urgently to review this medication before the next dose."
5. Each concern must have: title, summary, what_was_found, why_it_matters,
   what_to_do, evidence array, source_documents array.
6. Produce 3-8 concern cards where possible. Never exceed 15.
7. Return only valid JSON.

TONE RULES (non-negotiable):
- This system is advisory only. Never give direct medical instructions.
- Never use: stop, discontinue, do not take, do not give, restart, reduce dose, increase dose, you must, you should not.
- Always frame as: "we noticed," "the records show," "it may be worth discussing," "we recommend confirming with the doctor."
- Even when a doctor's document says stop a medication, say: "The records contain an instruction to hold or stop [medication]. We recommend confirming with the doctor whether this is still current."
- Tone must be calm, informative, and cautious. Never panic-inducing. Never dismissive.\
"""

_USER_TEMPLATE = """\
Brand name map (use these for ALL medication references — never invent):
{brand_map_json}

All clinical flags and their evidence:
{flags_json}
Each item includes: flag_id, finding_id, directive_type, severity, title,
what_was_found, why_it_matters, what_to_do, source_reference,
clinical_evidence, related_entities (medications, labs, conditions, directives)

Group these into caregiver concerns following these rules:

GROUPING RULES:
1. Group findings that share the same medication, OR the same lab value,
   OR the same clinical condition, OR the same directive.
2. If multiple findings share the same core clinical topic (e.g. hyperkalemia risk),
   group them into one concern even if the specific medications differ.
3. Assign priority = highest severity among all findings in the group.
4. Write one harmonized what_to_do for the group — not a list of separate actions.
5. Aggregate all evidence from all findings into one evidence array.

PARTIAL MATCH RULE (most important):
If a finding partially matches a group (shares one entity but not the core topic):
- Include it in the group (add its evidence to the group card)
- ALSO output it as a SEPARATE concern with concern_type = "partial_match_source"
- The separate card shows the FULL original finding text and evidence UNCHANGED
- Do NOT trim or summarize the partial_match_source card
- Set partial_match_group_id to the same UUID on both cards
- A slight duplication is acceptable. Lost information is not.

INDEPENDENT RULE:
If a finding does not match any group at all:
- Output it as concern_type = "independent"
- Use the original flag text (what_was_found, why_it_matters, what_to_do) UNCHANGED

WORDING SAFETY:
- ONLY say "do not give [medication]" if the evidence contains an explicit
  doctor-written STOP instruction. Otherwise: "contact the doctor urgently
  to review this medication before the next dose."

Return exactly this JSON shape:
{{
  "concerns": [
    {{
      "concern_type": "grouped | independent | partial_match_source",
      "priority": "critical_concern | high_priority | moderate | for_your_awareness",
      "title": "max 10 words, plain language, brand name first if medication involved",
      "summary": "1-2 sentences, plain language overview",
      "what_was_found": "specific details with brand name (generic), value, source, date",
      "why_it_matters": "why this applies to THIS patient with their specific data",
      "what_to_do": "specific action — what to bring, ask, or show doctor",
      "evidence": [{{"entity": "exact value", "source": "specific doc", "date": "ISO or empty"}}],
      "source_documents": ["document name list"],
      "contributing_flag_ids": ["uuid list"],
      "contributing_finding_ids": ["uuid list"],
      "is_partial_match": false,
      "partial_match_group_id": null,
      "brand_names_used": [{{"brand": "Glycomet", "generic": "Metformin"}}]
    }}
  ]
}}\
"""


async def run_orchestration(db: Client, patient_id: str) -> int:
    """Phase 6.5: groups open_flags into caregiver_concerns, sets findings_ready.

    Returns number of concern rows saved.
    """
    logger.info(f"Phase 6.5: orchestration starting — patient {patient_id}")

    reasoning_run_id = _get_latest_run_id(db, patient_id)
    if reasoning_run_id:
        _update_run(db, reasoning_run_id, {"orchestration_status": "running"})

    try:
        flags = (
            db.table("open_flags").select("*")
            .eq("patient_id", patient_id)
            .eq("status", "open")
            .execute()
        ).data

        if not flags:
            logger.info(f"No open flags — saving empty-state concern for patient {patient_id}")
            _save_empty_state_concern(db, patient_id, reasoning_run_id)
            _set_findings_ready(db, patient_id)
            if reasoning_run_id:
                _update_run(db, reasoning_run_id, {"orchestration_status": "done", "concerns_generated": 0})
            return 0

        findings_by_id = _load_findings(db, patient_id)
        flag_inputs = _build_flag_inputs(flags, findings_by_id)
        brand_map = _build_brand_map(db, patient_id, flag_inputs)

        # Call orchestration LLM
        try:
            concerns = await _call_orchestration_llm(flag_inputs, brand_map)
        except Exception as e:
            logger.warning(f"Orchestration LLM failed: {e} — using fallback")
            concerns = _fallback_concerns(flag_inputs)
            saved = _save_concerns(db, patient_id, reasoning_run_id, concerns)
            _set_findings_ready(db, patient_id)
            if reasoning_run_id:
                _update_run(db, reasoning_run_id, {
                    "orchestration_status": "fallback",
                    "orchestration_error": str(e)[:500],
                    "concerns_generated": saved,
                })
            logger.info(f"Phase 6.5 fallback complete — {saved} concerns")
            return saved

        # Validate output
        all_flag_ids = {inp["flag_id"] for inp in flag_inputs}
        concerns, used_fallback = _validate_and_fix(concerns, flag_inputs, all_flag_ids)

        concerns = _assign_display_order(concerns)
        saved = _save_concerns(db, patient_id, reasoning_run_id, concerns)

        orch_status = "fallback" if used_fallback else "done"
        _set_findings_ready(db, patient_id)
        if reasoning_run_id:
            _update_run(db, reasoning_run_id, {
                "orchestration_status": orch_status,
                "concerns_generated": saved,
            })
        logger.info(f"Phase 6.5 complete — {saved} concerns, status={orch_status}")
        return saved

    except Exception as e:
        logger.error(f"Phase 6.5 critical failure: {e}", exc_info=True)
        # Save a single system-error concern so caregiver isn't stuck
        _save_error_fallback_concern(db, patient_id, reasoning_run_id)
        _set_findings_ready(db, patient_id)
        if reasoning_run_id:
            _update_run(db, reasoning_run_id, {
                "orchestration_status": "failed",
                "orchestration_error": str(e)[:500],
                "concerns_generated": 1,
            })
        return 1


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_latest_run_id(db: Client, patient_id: str) -> str | None:
    result = (
        db.table("reasoning_runs").select("id")
        .eq("patient_id", patient_id)
        .eq("status", "success")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0]["id"] if result.data else None


def _load_findings(db: Client, patient_id: str) -> dict:
    findings_data = (
        db.table("clinical_findings").select("*")
        .eq("patient_id", patient_id)
        .execute()
    ).data
    return {f["id"]: f for f in findings_data}


def _build_flag_inputs(flags: list[dict], findings_by_id: dict) -> list[dict]:
    inputs = []
    for flag in flags:
        finding = findings_by_id.get(flag.get("finding_id"))
        clinical_evidence: dict = {}
        related_entities: dict = {}
        if finding:
            clinical_evidence = _safe_json(finding.get("clinical_evidence"))
            related_entities = _safe_json(finding.get("related_entities"))

        inputs.append({
            "flag_id": str(flag["id"]),
            "finding_id": str(flag.get("finding_id") or ""),
            "directive_type": flag.get("directive_type") or "FOR_YOUR_AWARENESS",
            "severity": flag.get("severity") or "informational",
            "title": flag.get("title") or "",
            "what_was_found": flag.get("what_was_found") or flag.get("description") or "",
            "why_it_matters": flag.get("why_it_matters") or "",
            "what_to_do": flag.get("what_to_do") or "",
            "source_reference": flag.get("source_reference") or "",
            "clinical_evidence": clinical_evidence,
            "related_entities": related_entities,
        })
    return inputs


def _build_brand_map(db: Client, patient_id: str, flag_inputs: list[dict]) -> dict:
    all_generics: set[str] = set()
    for inp in flag_inputs:
        meds = (inp.get("related_entities") or {}).get("medications") or []
        for med in meds:
            if med:
                all_generics.add(med.lower())

    brand_map: dict[str, str] = {}
    if not all_generics:
        return brand_map

    meds = (
        db.table("medications").select("drug_name_generic,drug_name_brand")
        .eq("patient_id", patient_id)
        .eq("is_current", True)
        .eq("is_deleted", False)
        .execute()
    ).data
    for med in meds:
        generic = (med.get("drug_name_generic") or "").strip()
        brand = (med.get("drug_name_brand") or "").strip()
        if generic and brand:
            brand_map[generic] = brand
            brand_map[generic.lower()] = brand

    return brand_map


async def _call_orchestration_llm(flag_inputs: list[dict], brand_map: dict) -> list[dict]:
    user_prompt = _USER_TEMPLATE.format(
        brand_map_json=json.dumps(brand_map, ensure_ascii=False, indent=2),
        flags_json=json.dumps(flag_inputs, ensure_ascii=False, indent=2),
    )
    result = await _llm_call(_SYSTEM_PROMPT, user_prompt, timeout=180)
    concerns = result.get("concerns") or result.get("items") or []
    if not isinstance(concerns, list):
        raise ValueError(f"LLM returned unexpected concerns shape: {type(concerns)}")
    return concerns


def _validate_and_fix(
    concerns: list[dict],
    flag_inputs: list[dict],
    all_flag_ids: set[str],
) -> tuple[list[dict], bool]:
    """Ensure no flag is dropped, no empty evidence, cap at 15. Returns (concerns, used_fallback)."""
    used_fallback = False

    # Remove concerns with empty evidence
    concerns = [c for c in concerns if c.get("evidence")]

    if not concerns:
        logger.warning("All concerns had empty evidence — falling back")
        return _fallback_concerns(flag_inputs), True

    # Find any flag_id not covered
    covered: set[str] = set()
    for c in concerns:
        for fid in (c.get("contributing_flag_ids") or []):
            covered.add(str(fid))

    missing = all_flag_ids - covered
    if missing:
        logger.warning(f"{len(missing)} flag(s) not covered by orchestration — adding as independent")
        flag_by_id = {inp["flag_id"]: inp for inp in flag_inputs}
        for fid in missing:
            inp = flag_by_id.get(fid)
            if inp:
                concerns.append(_independent_concern_from_flag(inp))
        used_fallback = True

    # Cap at 15 — only merge for_your_awareness if over limit
    if len(concerns) > 15:
        concerns = _cap_concerns(concerns)

    # Ensure at least 1
    if not concerns:
        return _fallback_concerns(flag_inputs), True

    return concerns, used_fallback


def _cap_concerns(concerns: list[dict]) -> list[dict]:
    """Merge excess for_your_awareness concerns to stay under 15."""
    non_fya = [c for c in concerns if c.get("priority") != "for_your_awareness"]
    fya = [c for c in concerns if c.get("priority") == "for_your_awareness"]

    slots = 15 - len(non_fya)
    if slots <= 0:
        return non_fya[:15]
    if len(fya) <= slots:
        return non_fya + fya

    # Merge excess fya into one
    keep_fya = fya[:slots - 1]
    merged_items = fya[slots - 1:]
    all_what = "; ".join(c.get("what_was_found", "") for c in merged_items)
    all_evidence = []
    all_flag_ids = []
    for c in merged_items:
        all_evidence.extend(c.get("evidence") or [])
        all_flag_ids.extend(c.get("contributing_flag_ids") or [])

    merged = {
        "concern_type": "grouped",
        "priority": "for_your_awareness",
        "title": "Additional awareness items",
        "summary": f"{len(merged_items)} additional items for your awareness.",
        "what_was_found": all_what,
        "why_it_matters": "These items may be worth mentioning to your doctor.",
        "what_to_do": "Review these items with the doctor at the next visit.",
        "evidence": all_evidence,
        "source_documents": [],
        "contributing_flag_ids": all_flag_ids,
        "contributing_finding_ids": [],
        "is_partial_match": False,
        "partial_match_group_id": None,
        "brand_names_used": [],
    }
    return non_fya + keep_fya + [merged]


def _assign_display_order(concerns: list[dict]) -> list[dict]:
    """Sort: priority ASC, then type ASC, then higher severity first."""
    def sort_key(c: dict) -> tuple:
        p = _PRIORITY_ORDER.get(c.get("priority", "for_your_awareness"), 3)
        t = _TYPE_ORDER.get(c.get("concern_type", "independent"), 1)
        return (p, t)

    sorted_concerns = sorted(concerns, key=sort_key)
    for i, c in enumerate(sorted_concerns):
        c["display_order"] = i + 1
    return sorted_concerns


def _save_concerns(
    db: Client,
    patient_id: str,
    reasoning_run_id: str | None,
    concerns: list[dict],
) -> int:
    saved = 0
    for c in concerns:
        # Coerce UUID arrays — LLM may return strings or empty
        flag_ids = _coerce_uuid_list(c.get("contributing_flag_ids"))
        finding_ids = _coerce_uuid_list(c.get("contributing_finding_ids"))

        try:
            db.table("caregiver_concerns").insert({
                "patient_id": patient_id,
                "reasoning_run_id": reasoning_run_id,
                "concern_type": _valid_concern_type(c.get("concern_type")),
                "priority": _valid_priority(c.get("priority")),
                "title": (c.get("title") or "Clinical finding")[:500],
                "summary": c.get("summary") or "",
                "what_was_found": c.get("what_was_found") or "",
                "why_it_matters": c.get("why_it_matters") or "",
                "what_to_do": c.get("what_to_do") or "",
                "evidence": c.get("evidence") or [],
                "source_documents": c.get("source_documents") or [],
                "contributing_flag_ids": flag_ids or None,
                "contributing_finding_ids": finding_ids or None,
                "is_partial_match": bool(c.get("is_partial_match")),
                "partial_match_group_id": c.get("partial_match_group_id"),
                "brand_names_used": c.get("brand_names_used"),
                "display_order": c.get("display_order", saved + 1),
                "status": "active",
            }).execute()
            saved += 1
        except Exception as e:
            logger.warning(f"Failed to save concern: {e}")

    return saved


def _fallback_concerns(flag_inputs: list[dict]) -> list[dict]:
    """One independent concern per flag. Used when LLM orchestration fails."""
    concerns = []
    for i, inp in enumerate(flag_inputs):
        concerns.append({
            **_independent_concern_from_flag(inp),
            "display_order": i + 1,
        })
    return concerns


def _independent_concern_from_flag(inp: dict) -> dict:
    priority = _SEVERITY_TO_PRIORITY.get(inp.get("severity", "informational"), "for_your_awareness")
    evidence = [{"entity": inp.get("what_was_found", ""), "source": inp.get("source_reference", ""), "date": ""}]
    return {
        "concern_type": "independent",
        "priority": priority,
        "title": inp.get("title") or "Clinical finding",
        "summary": inp.get("what_was_found") or "",
        "what_was_found": inp.get("what_was_found") or "",
        "why_it_matters": inp.get("why_it_matters") or "",
        "what_to_do": inp.get("what_to_do") or "",
        "evidence": evidence,
        "source_documents": [inp.get("source_reference")] if inp.get("source_reference") else [],
        "contributing_flag_ids": [inp["flag_id"]],
        "contributing_finding_ids": [inp["finding_id"]] if inp.get("finding_id") else [],
        "is_partial_match": False,
        "partial_match_group_id": None,
        "brand_names_used": [],
    }


def _save_empty_state_concern(db: Client, patient_id: str, reasoning_run_id: str | None) -> None:
    try:
        db.table("caregiver_concerns").insert({
            "patient_id": patient_id,
            "reasoning_run_id": reasoning_run_id,
            "concern_type": "independent",
            "priority": "for_your_awareness",
            "title": "No concerning findings identified",
            "summary": "We reviewed all records. No concerning findings were identified at this time.",
            "what_was_found": "All records reviewed. No clinical concerns found.",
            "why_it_matters": "Your records appear consistent with the current treatment plan.",
            "what_to_do": "Continue all medications as prescribed. Attend scheduled follow-ups.",
            "evidence": [],
            "display_order": 1,
            "status": "active",
        }).execute()
    except Exception as e:
        logger.warning(f"Could not save empty-state concern: {e}")


def _save_error_fallback_concern(db: Client, patient_id: str, reasoning_run_id: str | None) -> None:
    try:
        db.table("caregiver_concerns").insert({
            "patient_id": patient_id,
            "reasoning_run_id": reasoning_run_id,
            "concern_type": "independent",
            "priority": "for_your_awareness",
            "title": "Findings could not be prepared for display",
            "summary": (
                "Some findings could not be prepared for display. "
                "All raw analysis has been saved."
            ),
            "what_was_found": "Analysis completed but display preparation failed.",
            "why_it_matters": "All clinical findings have been saved and are available for doctor review.",
            "what_to_do": (
                "Please ask the doctor to review the uploaded documents together. "
                "All raw analysis has been saved safely."
            ),
            "evidence": [],
            "display_order": 1,
            "status": "active",
        }).execute()
    except Exception as e:
        logger.warning(f"Could not save error-fallback concern: {e}")


def _set_findings_ready(db: Client, patient_id: str) -> None:
    db.table("patients").update({
        "onboarding_status": "findings_ready"
    }).eq("id", patient_id).execute()
    logger.info(f"onboarding_status → findings_ready for patient {patient_id}")


def _update_run(db: Client, run_id: str, updates: dict) -> None:
    if not run_id:
        return
    try:
        db.table("reasoning_runs").update(updates).eq("id", run_id).execute()
    except Exception as e:
        logger.warning(f"Could not update reasoning_run {run_id}: {e}")


# ── Utility ───────────────────────────────────────────────────────────────────

def _safe_json(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _coerce_uuid_list(value) -> list[str]:
    if not value:
        return []
    result = []
    for item in value:
        s = str(item).strip()
        if s and s != "null" and s != "None":
            result.append(s)
    return result


_VALID_TYPES = {"grouped", "independent", "partial_match_source"}
_VALID_PRIORITIES = {"critical_concern", "high_priority", "moderate", "for_your_awareness"}


def _valid_concern_type(val: str | None) -> str:
    return val if val in _VALID_TYPES else "independent"


def _valid_priority(val: str | None) -> str:
    return val if val in _VALID_PRIORITIES else "for_your_awareness"
