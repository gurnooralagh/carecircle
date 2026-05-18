from supabase import Client
from config.logging import get_logger
from datetime import datetime, timezone

logger = get_logger("FLAGS")

QUESTION_FLAG_TYPES = {
    "lab_anomaly", "stale_report", "conflict_unresolved",
    "unconfirmed_diagnosis", "missing_doctor_info", "currency_uncertain",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "moderate": 2, "low": 3}


def create_flag(
    db: Client,
    patient_id: str,
    flag_type: str,
    severity: str,
    title: str,
    description: str = None,
    plain_language_alert: str = None,
    linked_medication_id: str = None,
    linked_document_id: str = None,
    linked_diagnosis_id: str = None,
    linked_lab_result_id: str = None,
) -> str:
    existing = (
        db.table("open_flags")
        .select("id")
        .eq("patient_id", patient_id)
        .eq("flag_type", flag_type)
        .eq("title", title)
        .eq("status", "open")
        .eq("is_deleted", False)
        .execute()
    )
    if existing.data:
        logger.info(f"Dedup: flag already exists for '{title}' — returning existing id")
        return existing.data[0]["id"]

    row = {
        "patient_id": patient_id,
        "flag_type": flag_type,
        "severity": severity,
        "title": title,
        "status": "open",
    }
    if description:
        row["description"] = description
    if plain_language_alert:
        row["plain_language_alert"] = plain_language_alert
    if linked_medication_id:
        row["linked_medication_id"] = linked_medication_id
    if linked_document_id:
        row["linked_document_id"] = linked_document_id
    if linked_diagnosis_id:
        row["linked_diagnosis_id"] = linked_diagnosis_id
    if linked_lab_result_id:
        row["linked_lab_result_id"] = linked_lab_result_id

    result = db.table("open_flags").insert(row).execute()
    flag_id = result.data[0]["id"]
    logger.info(f"Flag created: {flag_type} [{severity}] — {title} (id: {flag_id})")
    return flag_id


def resolve_flag(flag_id: str, answer: str, answer_detail: str, db: Client) -> None:
    db.table("open_flags").update({
        "status": "resolved",
        "meera_answer": answer,
        "meera_answer_detail": answer_detail,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", flag_id).execute()
    logger.info(f"Flag resolved: {flag_id} — answer: {answer}")


def get_pending_questions(db: Client, patient_id: str, max_questions: int = 3) -> list[dict]:
    result = (
        db.table("open_flags")
        .select("id,flag_type,severity,title,description,plain_language_alert,linked_medication_id,linked_lab_result_id,linked_diagnosis_id")
        .eq("patient_id", patient_id)
        .eq("status", "open")
        .eq("is_deleted", False)
        .in_("flag_type", list(QUESTION_FLAG_TYPES))
        .execute()
    )
    flags = result.data
    flags.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 99))
    flags = flags[:max_questions]

    questions = []
    for flag in flags:
        questions.append({
            "flag_id": flag["id"],
            "flag_type": flag["flag_type"],
            "severity": flag["severity"],
            "question_text": flag["title"],
            "context": flag.get("description"),
            "plain_language_alert": flag.get("plain_language_alert"),
        })
    logger.info(f"Returning {len(questions)} pending questions for patient {patient_id}")
    return questions
