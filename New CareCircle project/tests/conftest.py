import pytest
import io
from fpdf import FPDF
from supabase import create_client
from config.settings import settings
from db.client import get_db


def make_test_pdf(content: str) -> bytes:
    """Generate a minimal PDF with given text content."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in content.split("\n"):
        pdf.cell(0, 10, line, ln=True)
    return bytes(pdf.output())


@pytest.fixture(scope="session")
def db():
    return get_db()


@pytest.fixture(scope="session")
def test_user_token(db):
    """Create a real Supabase test user and return their JWT access token.
    Uses a separate client so sign_in doesn't corrupt the shared service_role db session."""
    TEST_EMAIL = "pytest_carecircle@test.local"
    TEST_PASSWORD = "CareCircleTest2026!"

    try:
        db.auth.admin.create_user({
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "email_confirm": True,
        })
    except Exception:
        pass  # Already exists from a previous run

    # Use a throwaway client so the shared `db` client keeps service_role headers
    auth_client = create_client(settings.supabase_url, settings.supabase_service_key)
    result = auth_client.auth.sign_in_with_password({
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    })
    return result.session.access_token


@pytest.fixture(scope="session")
def test_user_id(db, test_user_token):
    result = db.auth.get_user(test_user_token)
    return str(result.user.id)


@pytest.fixture
def sample_prescription_bytes():
    with open("tests/fixtures/prescription_sample.jpg", "rb") as f:
        return f.read()


@pytest.fixture
def sample_lab_pdf_bytes():
    content = (
        "LAB REPORT\nPatient: Rajesh Kumar\nDate: 2026-03-10\n"
        "Lab: Apollo Diagnostics, Lucknow\n"
        "HbA1c: 7.8% (Reference: <5.7%)\n"
        "Fasting Blood Sugar: 142 mg/dL (Reference: 70-100 mg/dL) H\n"
        "Serum Creatinine: 1.1 mg/dL (Reference: 0.7-1.2 mg/dL)\n"
        "eGFR: 68 mL/min (Reference: >60)\n"
        "Ordered by: Dr. Sharma, Endocrinologist"
    )
    return make_test_pdf(content)


@pytest.fixture
def sample_discharge_pdf_bytes():
    content = (
        "DISCHARGE SUMMARY\nHospital: Medanta, Lucknow\n"
        "Patient: Rajesh Kumar, 67M\n"
        "Admission: 2026-01-05  Discharge: 2026-01-08\n"
        "Diagnosis: Hypertensive urgency, Type 2 Diabetes Mellitus\n"
        "Medications at Discharge:\n"
        "- Amlodipine 5mg once daily\n"
        "- Metformin 500mg twice daily after meals\n"
        "- Glimepiride 1mg once daily before breakfast\n"
        "Follow-up: Cardiology in 2 weeks\n"
        "Consultant: Dr. Verma, Cardiologist"
    )
    return make_test_pdf(content)


@pytest.fixture
def test_patient(db, test_user_id):
    """Create a test patient, yield their id, then clean up all related rows."""
    # Pre-cleanup: remove any leftover rows from a previous failed test run
    existing = db.table("user_profiles").select("id").eq("auth_user_id", test_user_id).execute()
    for row in existing.data:
        old_profile_id = row["id"]
        old_patients = db.table("patient_guardians").select("patient_id").eq("user_profile_id", old_profile_id).execute()
        for pg in old_patients.data:
            pid = pg["patient_id"]
            for table in [
                "patient_action_summaries", "caregiver_concerns",
                "temporal_logic_evaluations", "reasoning_runs", "clinical_findings",
                "open_flags", "culture_findings", "restrictions",
                "monitoring_instructions", "clinical_directives",
                "patient_summaries", "drug_safety_checks",
                "lab_results", "allergies", "diagnoses", "medications",
                "doctors", "document_extractions", "documents",
                "patient_guardians", "telegram_groups",
            ]:
                db.table(table).delete().eq("patient_id", pid).execute()
            db.table("patients").delete().eq("id", pid).execute()
        db.table("user_profiles").delete().eq("id", old_profile_id).execute()

    # Create user_profile row first
    profile_result = db.table("user_profiles").insert({
        "auth_user_id": test_user_id,
        "role": "guardian",
        "full_name": "Meera Test",
        "email": "pytest_carecircle@test.local",
        "relationship": "daughter",
    }).execute()
    profile_id = profile_result.data[0]["id"]

    # Create patient
    patient_result = db.table("patients").insert({
        "full_name": "Rajesh Kumar Test",
        "date_of_birth": "1959-03-15",
        "gender": "male",
        "city": "Lucknow",
        "state": "Uttar Pradesh",
    }).execute()
    patient_id = patient_result.data[0]["id"]

    # Link guardian
    db.table("patient_guardians").insert({
        "patient_id": patient_id,
        "user_profile_id": profile_id,
        "relationship": "daughter",
        "is_primary_guardian": True,
    }).execute()

    yield patient_id

    # Cleanup — hard delete for tests
    for table in [
        "patient_action_summaries", "caregiver_concerns",
        "temporal_logic_evaluations", "reasoning_runs", "clinical_findings",
        "open_flags", "culture_findings", "restrictions",
        "monitoring_instructions", "clinical_directives",
        "patient_summaries", "drug_safety_checks",
        "lab_results", "allergies", "diagnoses", "medications",
        "doctors", "document_extractions", "documents",
        "patient_guardians", "telegram_groups",
    ]:
        db.table(table).delete().eq("patient_id", patient_id).execute()
    db.table("patients").delete().eq("id", patient_id).execute()
    db.table("user_profiles").delete().eq("id", profile_id).execute()
