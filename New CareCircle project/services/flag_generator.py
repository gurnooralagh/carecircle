"""
Flag generation — Phase 6.
Translates clinical_findings into caregiver-facing open_flags.
Uses Gemini to generate plain-language flags.
"""
import json
from supabase import Client
from config.logging import get_logger
from services import llm

logger = get_logger("FLAGGEN")

SEVERITY_TO_DIRECTIVE = {
    "critical": "STOP_IMMEDIATELY",
    "high": "CONSULT_BEFORE_CONTINUING",
    "moderate": "MONITOR_CLOSELY",
    "low": "VERIFY_WITH_DOCTOR",
    "informational": "FOR_YOUR_AWARENESS",
}

# Special overrides regardless of severity
FINDING_TYPE_OVERRIDES = {
    "stopped_medication_still_active": "STOP_IMMEDIATELY",
    "stopped_medication_still_prescribed": "STOP_IMMEDIATELY",
    "exact_allergen_match": "STOP_IMMEDIATELY",
    "antibiotic_culture_mismatch": "CONSULT_BEFORE_CONTINUING",
    "monitoring_pending": "SCHEDULE_TEST",
    "monitoring_overdue": "SCHEDULE_TEST",
    "held_medication_condition_met_restart_possible": "VERIFY_WITH_DOCTOR",
    "followup_overdue": "SCHEDULE_FOLLOWUP",
}

# Confidence thresholds for flag generation
MIN_CONFIDENCE_FULL_FLAG = 0.50
MIN_CONFIDENCE_AWARENESS = 0.40


async def generate_flags_for_patient(db: Client, patient_id: str) -> int:
    """Generate caregiver flags for all open clinical findings. Returns count generated."""
    findings = (
        db.table("clinical_findings")
        .select("*")
        .eq("patient_id", patient_id)
        .eq("status", "open")
        .execute()
    ).data

    if not findings:
        logger.info(f"No findings to flag for patient {patient_id}")
        return 0

    # Get patient context
    patient = db.table("patients").select("*").eq("id", patient_id).execute().data
    patient_data = patient[0] if patient else {}
    age = patient_data.get("age_years") or "unknown"
    gender = patient_data.get("gender") or "unknown"
    conditions = [
        r["condition_name"]
        for r in db.table("diagnoses").select("condition_name").eq("patient_id", patient_id).execute().data
    ]

    generated = 0
    for finding in findings:
        confidence = float(finding.get("confidence") or 0)
        severity = finding.get("severity", "informational")
        finding_type = finding.get("finding_type", "")

        # Skip low-confidence non-critical findings
        if confidence < MIN_CONFIDENCE_AWARENESS and severity not in ("critical", "high"):
            logger.debug(f"Skipping low-confidence finding: {finding_type} ({confidence:.2f})")
            continue

        directive_type = _determine_directive_type(finding_type, severity, confidence)

        try:
            flag_content = await llm.generate_flag(
                finding=finding,
                patient_age=age,
                patient_gender=gender,
                conditions=conditions,
            )
        except Exception as e:
            logger.warning(f"Flag generation failed for {finding_type}: {e}")
            flag_content = _fallback_flag_content(finding)

        _save_flag(db, patient_id, finding["id"], directive_type, severity, flag_content)
        generated += 1
        logger.info(f"Flag generated: {directive_type} — {finding_type}")

    logger.info(f"Flag generation complete — {generated} flags for patient {patient_id}")
    return generated


def _determine_directive_type(finding_type: str, severity: str, confidence: float) -> str:
    if finding_type in FINDING_TYPE_OVERRIDES:
        return FINDING_TYPE_OVERRIDES[finding_type]

    # Confidence downgrade
    if confidence < MIN_CONFIDENCE_FULL_FLAG:
        return "FOR_YOUR_AWARENESS"

    if "monitoring" in finding_type or "schedule" in finding_type:
        return "SCHEDULE_TEST"

    if "followup" in finding_type:
        return "SCHEDULE_FOLLOWUP"

    if severity == "high" and "lab" in finding_type:
        return "SCHEDULE_TEST"

    return SEVERITY_TO_DIRECTIVE.get(severity, "FOR_YOUR_AWARENESS")


def _save_flag(db: Client, patient_id: str, finding_id: str, directive_type: str, severity: str, content: dict) -> None:
    try:
        db.table("open_flags").insert({
            "patient_id": patient_id,
            "finding_id": finding_id,
            "flag_type": directive_type,
            "directive_type": directive_type,
            "severity": severity,
            "title": content.get("title", "")[:200],
            "what_was_found": content.get("what_was_found", ""),
            "why_it_matters": content.get("why_it_matters", ""),
            "what_to_do": content.get("what_to_do", ""),
            "source_reference": content.get("source_reference"),
            "is_personalized": True,
            "status": "open",
        }).execute()
    except Exception as e:
        logger.warning(f"Could not save flag: {e}")


def _fallback_flag_content(finding: dict) -> dict:
    """Minimal flag content when LLM fails."""
    evidence_list = finding.get("clinical_evidence")
    if isinstance(evidence_list, str):
        try:
            evidence_list = json.loads(evidence_list)
        except Exception:
            evidence_list = []
    first_evidence = (evidence_list or [{}])[0]

    return {
        "title": finding.get("title", "Clinical finding identified"),
        "what_was_found": f"{finding.get('title', 'A clinical finding was identified')}. "
                          f"Evidence: {first_evidence.get('entity', 'See medical records')}.",
        "why_it_matters": "This was identified during analysis of the medical records and may require attention.",
        "what_to_do": "Please discuss this with the treating doctor at the next appointment.",
        "source_reference": first_evidence.get("source", "Medical records"),
    }
