import pytest
from services.flags import create_flag, resolve_flag, get_pending_questions


def test_create_drug_interaction_flag(db, test_patient):
    flag_id = create_flag(
        db=db,
        patient_id=test_patient,
        flag_type="drug_interaction",
        severity="moderate",
        title="Possible interaction: Amlodipine + Metformin",
        description="Amlodipine may affect blood sugar levels in patients on Metformin.",
        plain_language_alert="Your father's blood pressure medication may interact with his diabetes medication. Mention this to his doctor at the next visit.",
    )
    assert flag_id is not None
    print(f"\nCreated flag: {flag_id}")

    # Verify in DB
    result = db.table("open_flags").select("*").eq("id", flag_id).execute()
    assert len(result.data) == 1
    flag = result.data[0]
    assert flag["flag_type"] == "drug_interaction"
    assert flag["status"] == "open"
    assert flag["severity"] == "moderate"


def test_create_flag_deduplication(db, test_patient):
    """Creating same flag twice returns existing flag_id, not a duplicate."""
    flag_id_1 = create_flag(
        db=db,
        patient_id=test_patient,
        flag_type="lab_anomaly",
        severity="high",
        title="High HbA1c",
        description="HbA1c 7.8% above target range",
    )
    flag_id_2 = create_flag(
        db=db,
        patient_id=test_patient,
        flag_type="lab_anomaly",
        severity="high",
        title="High HbA1c",
        description="HbA1c 7.8% above target range",
    )
    assert flag_id_1 == flag_id_2


def test_resolve_flag(db, test_patient):
    flag_id = create_flag(
        db=db,
        patient_id=test_patient,
        flag_type="unconfirmed_diagnosis",
        severity="moderate",
        title="Unconfirmed: Hypertension",
        description="Hypertension was mentioned in discharge summary but not in stated conditions.",
    )
    resolve_flag(
        flag_id=flag_id,
        answer="yes",
        answer_detail="Yes, he was diagnosed with hypertension 3 years ago.",
        db=db,
    )
    result = db.table("open_flags").select("*").eq("id", flag_id).execute()
    assert result.data[0]["status"] == "resolved"
    assert result.data[0]["meera_answer"] == "yes"


def test_get_pending_questions(db, test_patient):
    create_flag(
        db=db,
        patient_id=test_patient,
        flag_type="stale_report",
        severity="low",
        title="Lab report over 3 months old",
        description="The lab report is dated more than 90 days ago.",
    )
    questions = get_pending_questions(db=db, patient_id=test_patient, max_questions=3)
    assert isinstance(questions, list)
    assert len(questions) >= 1
    q = questions[0]
    assert "flag_id" in q
    assert "question_text" in q
    assert "severity" in q
