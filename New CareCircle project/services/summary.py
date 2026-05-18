from datetime import date
from supabase import Client
from config.logging import get_logger
from services import llm

logger = get_logger("SUMMARY")


def build_snapshot(patient_id: str, db: Client) -> dict:
    logger.info(f"Building snapshot for patient {patient_id}")

    patient = db.table("patients").select("*").eq("id", patient_id).execute().data[0]
    dob = date.fromisoformat(str(patient["date_of_birth"]))
    age = int((date.today() - dob).days / 365.25)

    conditions = [
        r["condition_name"] for r in
        db.table("diagnoses").select("condition_name")
        .eq("patient_id", patient_id).eq("confirmation_status", "confirmed").execute().data
    ]

    medications = [
        {"drug_name": r["drug_name_normalized"], "dosage": r.get("dosage"), "frequency": r.get("frequency")}
        for r in db.table("medications").select("drug_name_normalized,dosage,frequency")
        .eq("patient_id", patient_id).eq("confirmed_by_guardian", True)
        .eq("safety_check_status", "clear").execute().data
    ]

    allergies = [
        r["allergen"] for r in
        db.table("allergies").select("allergen").eq("patient_id", patient_id).execute().data
    ]

    doctors = [
        {"name": r["name"], "specialty": r.get("specialty")}
        for r in db.table("doctors").select("name,specialty").eq("patient_id", patient_id).execute().data
    ]

    open_flags_count = (
        db.table("open_flags").select("id", count="exact")
        .eq("patient_id", patient_id).eq("status", "open").execute().count or 0
    )

    snapshot = {
        "patient": {
            "name": patient["full_name"],
            "age": age,
            "gender": patient.get("gender"),
            "city": patient.get("city"),
        },
        "conditions": conditions,
        "medications": medications,
        "allergies": allergies,
        "doctors": doctors,
        "open_flags_count": open_flags_count,
    }
    logger.info(f"Snapshot: {len(conditions)} conditions, {len(medications)} meds, {open_flags_count} open flags")
    return snapshot


async def generate_and_save(patient_id: str, db: Client) -> str:
    snapshot = build_snapshot(patient_id=patient_id, db=db)
    logger.info(f"Calling LLM to generate summary ({len(str(snapshot))} chars snapshot)")

    result = await llm.generate_patient_summary(snapshot)

    db.table("patient_summaries").update({"is_current": False}).eq("patient_id", patient_id).execute()

    versions = (
        db.table("patient_summaries").select("version")
        .eq("patient_id", patient_id).order("version", desc=True).limit(1).execute()
    )
    version = (versions.data[0]["version"] + 1) if versions.data else 1

    summary_result = db.table("patient_summaries").insert({
        "patient_id": patient_id,
        "summary_text": result.get("summary_text", ""),
        "sections": result.get("sections", {}),
        "version": version,
        "is_current": True,
    }).execute()
    summary_id = summary_result.data[0]["id"]

    db.table("patients").update({"onboarding_status": "ready_for_review"}).eq("id", patient_id).execute()
    logger.info(f"Summary saved (v{version}) — {len(result.get('summary_text', ''))} chars")
    return summary_id
