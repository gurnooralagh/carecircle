"""
Phase 6.6 — Intelligent Action Summary.

Reads full patient context (meds, labs, directives, monitoring, concerns).
Calls Gemini to reason about what the caregiver actually needs to do.
Saves three action lists to patient_action_summaries.
Does NOT change onboarding_status timing (findings_ready already set by Phase 6.5).
"""
import json
from datetime import date
from supabase import Client
from config.logging import get_logger
from services.llm import generate_action_summary

logger = get_logger("ACTION_SUMMARIZER")


async def run_action_summary(db: Client, patient_id: str) -> dict:
    """Phase 6.6: builds action context, calls LLM, saves to patient_action_summaries.

    Returns the saved action summary dict (do_now, follow_up, ongoing_monitoring).
    """
    logger.info(f"Phase 6.6: action summary starting — patient {patient_id}")

    try:
        context = _build_action_context(db, patient_id)
        patient_name = context["patient"].get("name") or "the patient"

        try:
            result = await generate_action_summary(context, patient_name)
        except Exception as e:
            logger.warning(f"Action summary LLM failed: {e}")
            result = {"do_now": [], "follow_up": [], "ongoing_monitoring": []}

        do_now = result.get("do_now") or []
        follow_up = result.get("follow_up") or []
        ongoing = result.get("ongoing_monitoring") or []

        # Personalization validation — retry once if any item fails
        if do_now or follow_up or ongoing:
            all_items = do_now + follow_up + ongoing
            if not _passes_personalization_check(all_items, patient_name):
                logger.warning("Action summary failed personalization check — retrying with explicit instruction")
                try:
                    result = await generate_action_summary(
                        {**context, "_retry_instruction": f"Be more specific. Use {patient_name}'s actual name, actual medication names, actual test values, actual dates, and actual document names. Do not use generic language."},
                        patient_name,
                    )
                    do_now = result.get("do_now") or do_now
                    follow_up = result.get("follow_up") or follow_up
                    ongoing = result.get("ongoing_monitoring") or ongoing
                except Exception:
                    pass

        reasoning_run_id = _get_latest_run_id(db, patient_id)
        _save_action_summary(db, patient_id, reasoning_run_id, do_now, follow_up, ongoing)
        logger.info(f"Phase 6.6 complete — {len(do_now)} do_now, {len(follow_up)} follow_up, {len(ongoing)} monitoring")
        return {"do_now": do_now, "follow_up": follow_up, "ongoing_monitoring": ongoing}

    except Exception as e:
        logger.error(f"Phase 6.6 failed: {e}", exc_info=True)
        return {"do_now": [], "follow_up": [], "ongoing_monitoring": []}


# ── Context builder ───────────────────────────────────────────────────────────

def _build_action_context(db: Client, patient_id: str) -> dict:
    patient_row = (
        db.table("patients").select("*").eq("id", patient_id).execute()
    ).data
    patient = patient_row[0] if patient_row else {}

    # Patient name + caregiver info
    guardian_rows = (
        db.table("patient_guardians")
        .select("user_profile_id, relationship")
        .eq("patient_id", patient_id)
        .eq("is_primary_guardian", True)
        .limit(1)
        .execute()
    ).data
    caregiver_name = None
    caregiver_relationship = None
    if guardian_rows:
        profile = (
            db.table("user_profiles")
            .select("full_name")
            .eq("id", guardian_rows[0]["user_profile_id"])
            .limit(1)
            .execute()
        ).data
        if profile:
            caregiver_name = profile[0].get("full_name")
        caregiver_relationship = guardian_rows[0].get("relationship")

    # Active medications
    meds = (
        db.table("medications").select("*")
        .eq("patient_id", patient_id)
        .eq("is_deleted", False)
        .execute()
    ).data

    # Brand map
    brand_map = {}
    for m in meds:
        g = (m.get("drug_name_generic") or "").lower()
        b = m.get("drug_name_brand") or ""
        if g and b:
            brand_map[g] = b

    # Lab results
    labs = (
        db.table("lab_results").select("*")
        .eq("patient_id", patient_id)
        .order("report_date", desc=True)
        .execute()
    ).data

    # Clinical directives
    directives = (
        db.table("clinical_directives").select("*")
        .eq("patient_id", patient_id)
        .eq("is_active", True)
        .execute()
    ).data

    # Monitoring instructions
    monitoring = (
        db.table("monitoring_instructions").select("*")
        .eq("patient_id", patient_id)
        .execute()
    ).data

    # Caregiver concerns (from Phase 6.5)
    concerns = (
        db.table("caregiver_concerns").select(
            "priority, title, what_to_do, source_documents"
        )
        .eq("patient_id", patient_id)
        .eq("status", "active")
        .execute()
    ).data

    # Doctors for source attribution
    doctors = (
        db.table("doctors").select("name, specialty, hospital_name")
        .eq("patient_id", patient_id)
        .execute()
    ).data

    # Document types for temporal context
    documents = (
        db.table("documents").select("document_type, original_filename")
        .eq("patient_id", patient_id)
        .eq("is_deleted", False)
        .execute()
    ).data

    today = str(date.today())

    return {
        "patient": {
            "name": patient.get("full_name", ""),
            "age": _compute_age(patient.get("date_of_birth")),
            "gender": patient.get("gender"),
            "city": patient.get("city"),
            "caregiver_name": caregiver_name,
            "caregiver_relationship": caregiver_relationship,
            "conditions": [
                r["condition_name"]
                for r in (
                    db.table("diagnoses").select("condition_name")
                    .eq("patient_id", patient_id).execute()
                ).data
            ],
        },
        "medications": [
            {
                "drug_name_brand": m.get("drug_name_brand"),
                "drug_name_generic": m.get("drug_name_generic"),
                "dose_text": m.get("dose_text") or m.get("dosage"),
                "frequency": m.get("frequency"),
                "status": m.get("status"),
                "is_current": m.get("is_current"),
                "guardian_taking_status": m.get("guardian_taking_status"),
                "source": m.get("source"),
            }
            for m in meds
        ],
        "lab_results": [
            {
                "test_name": lab.get("test_name_normalized") or lab.get("test_name"),
                "value": lab.get("value_text") or str(lab.get("value_numeric") or ""),
                "unit": lab.get("unit"),
                "collection_date": str(lab.get("report_date") or ""),
                "is_flagged": lab.get("is_flagged_by_lab", False),
                "flag_direction": lab.get("flag_direction"),
                "reference_range": _fmt_range(lab.get("reference_low"), lab.get("reference_high")),
                "lab_name": lab.get("lab_name"),
            }
            for lab in labs[:20]
        ],
        "directives": [
            {
                "directive_type": d.get("directive_type"),
                "instruction_text": d.get("instruction_text"),
                "target_entity": d.get("target_entity"),
                "condition_for_execution": d.get("condition_for_execution"),
                "directive_date": str(d.get("directive_date") or ""),
                "source_document": d.get("source_document"),
            }
            for d in directives
        ],
        "monitoring_instructions": [
            {
                "test_or_vital": m.get("test_or_vital"),
                "timing_text": m.get("timing_text"),
                "frequency_text": m.get("frequency_text"),
                "urgency": m.get("urgency"),
                "ordered_date": str(m.get("created_at") or "")[:10],
                "ordered_by": m.get("ordered_by"),
            }
            for m in monitoring
        ],
        "caregiver_concerns": [
            {
                "priority": c.get("priority"),
                "title": c.get("title"),
                "what_to_do": c.get("what_to_do"),
                "source_documents": c.get("source_documents") or [],
            }
            for c in concerns
        ],
        "doctors": [
            {"name": d.get("name"), "specialty": d.get("specialty"), "hospital": d.get("hospital_name")}
            for d in doctors
        ],
        "temporal_context": {
            "today": today,
            "documents_uploaded": [
                {"document_type": d.get("document_type", "other"), "filename": d.get("original_filename", "")}
                for d in documents
            ],
        },
        "brand_map": brand_map,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_age(dob: str | None) -> int | None:
    if not dob:
        return None
    try:
        from datetime import date as dt
        dob_date = dt.fromisoformat(str(dob))
        today = dt.today()
        return today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
    except Exception:
        return None


def _fmt_range(low, high) -> str | None:
    if low is not None and high is not None:
        return f"{low}–{high}"
    if low is not None:
        return f">{low}"
    if high is not None:
        return f"<{high}"
    return None


def _passes_personalization_check(items: list[dict], patient_name: str) -> bool:
    """Check that at least half of items reference the patient by name."""
    if not items or not patient_name:
        return True
    first_name = patient_name.split()[0].lower() if patient_name else ""
    if not first_name:
        return True
    passing = sum(1 for item in items if first_name in (item.get("action") or "").lower())
    return passing >= len(items) // 2


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


def _save_action_summary(
    db: Client,
    patient_id: str,
    reasoning_run_id: str | None,
    do_now: list,
    follow_up: list,
    ongoing: list,
) -> None:
    try:
        # Mark previous summaries not current
        db.table("patient_action_summaries").update({"is_current": False}).eq("patient_id", patient_id).execute()
        db.table("patient_action_summaries").insert({
            "patient_id": patient_id,
            "reasoning_run_id": reasoning_run_id,
            "do_now": do_now,
            "follow_up": follow_up,
            "ongoing_monitoring": ongoing,
            "is_current": True,
        }).execute()
    except Exception as e:
        logger.warning(f"Could not save action summary: {e}")
