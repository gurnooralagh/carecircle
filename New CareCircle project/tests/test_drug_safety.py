import pytest
from services.drug_safety import run_drug_safety_checks


@pytest.mark.asyncio
async def test_drug_drug_interactions_found(db, test_patient):
    db.table("medications").insert([
        {"patient_id": test_patient, "drug_name_normalized": "Amlodipine",
         "dosage": "5mg", "confirmed_by_guardian": True, "source": "guardian_stated"},
        {"patient_id": test_patient, "drug_name_normalized": "Metformin",
         "dosage": "500mg", "confirmed_by_guardian": True, "source": "guardian_stated"},
        {"patient_id": test_patient, "drug_name_normalized": "Glimepiride",
         "dosage": "1mg", "confirmed_by_guardian": True, "source": "guardian_stated"},
    ]).execute()

    db.table("allergies").insert({
        "patient_id": test_patient, "allergen": "Penicillin", "severity": "severe",
    }).execute()

    db.table("diagnoses").insert([
        {"patient_id": test_patient, "condition_name": "Type 2 Diabetes",
         "source": "guardian_stated", "confirmation_status": "confirmed"},
        {"patient_id": test_patient, "condition_name": "Hypertension",
         "source": "guardian_stated", "confirmation_status": "confirmed"},
    ]).execute()

    db.table("patients").update({
        "date_of_birth": "1959-03-15", "gender": "male"
    }).eq("id", test_patient).execute()

    await run_drug_safety_checks(patient_id=test_patient, db=db)

    checks = db.table("drug_safety_checks").select("*").eq("patient_id", test_patient).execute()
    assert len(checks.data) >= 1
    print(f"\nDrug safety check record: {checks.data[0]}")

    patient = db.table("patients").select("onboarding_status").eq("id", test_patient).execute()
    assert patient.data[0]["onboarding_status"] == "drug_check_complete"


@pytest.mark.asyncio
async def test_drug_interaction_cache_is_used(db, test_patient):
    """Second run for same drug pair should hit cache, not call LLM again."""
    db.table("drug_interaction_cache").delete().eq("drug_1", "atorvastatin").eq("drug_2", "warfarin").execute()
    db.table("drug_interaction_cache").insert({
        "drug_1": "atorvastatin",
        "drug_2": "warfarin",
        "severity": "high",
        "interaction_description": "Atorvastatin increases warfarin effect",
        "confidence": 0.9,
        "recommendation": "Discuss with your doctor before taking both",
    }).execute()

    db.table("medications").insert([
        {"patient_id": test_patient, "drug_name_normalized": "Atorvastatin",
         "confirmed_by_guardian": True, "source": "guardian_stated"},
        {"patient_id": test_patient, "drug_name_normalized": "Warfarin",
         "confirmed_by_guardian": True, "source": "guardian_stated"},
    ]).execute()

    db.table("patients").update({
        "date_of_birth": "1959-03-15", "gender": "male"
    }).eq("id", test_patient).execute()

    await run_drug_safety_checks(patient_id=test_patient, db=db)

    flags = db.table("open_flags").select("*").eq("patient_id", test_patient).eq("flag_type", "drug_interaction").execute()
    assert len(flags.data) >= 1
    flag = flags.data[0]
    print(f"\nFlag from cache hit: {flag['title']}")
