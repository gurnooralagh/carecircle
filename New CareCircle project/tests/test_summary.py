import pytest
from services.summary import build_snapshot, generate_and_save


@pytest.mark.asyncio
async def test_generate_summary(db, test_patient):
    db.table("patients").update({
        "date_of_birth": "1959-03-15", "gender": "male",
        "city": "Lucknow", "onboarding_status": "drug_check_complete",
    }).eq("id", test_patient).execute()

    db.table("diagnoses").insert([
        {"patient_id": test_patient, "condition_name": "Type 2 Diabetes",
         "source": "guardian_stated", "confirmation_status": "confirmed"},
    ]).execute()

    db.table("medications").insert({
        "patient_id": test_patient, "drug_name_normalized": "Metformin",
        "dosage": "500mg", "frequency": "twice daily",
        "confirmed_by_guardian": True, "source": "guardian_stated",
        "safety_check_status": "clear",
    }).execute()

    snapshot = build_snapshot(patient_id=test_patient, db=db)
    print(f"\nSnapshot:\n{snapshot}")
    assert "patient" in snapshot
    assert "conditions" in snapshot
    assert "medications" in snapshot

    summary_id = await generate_and_save(patient_id=test_patient, db=db)
    assert summary_id is not None

    summary = db.table("patient_summaries").select("*").eq("id", summary_id).execute()
    assert len(summary.data) == 1
    assert summary.data[0]["is_current"] is True
    assert len(summary.data[0]["summary_text"]) > 50
    print(f"\nSummary text:\n{summary.data[0]['summary_text'][:400]}")

    patient = db.table("patients").select("onboarding_status").eq("id", test_patient).execute()
    assert patient.data[0]["onboarding_status"] == "ready_for_review"
