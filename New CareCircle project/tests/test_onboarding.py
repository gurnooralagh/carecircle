"""
Full onboarding flow v3.0:
  submit → poll for medication_verification_needed → get extracted_medications
  → confirm_medications → poll for findings_ready → get findings → confirm

Run with: pytest tests/test_onboarding.py -v -s
"""
import pytest
import time
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

POLL_INTERVAL = 3
MAX_POLLS = 40


def poll_until(patient_id: str, target_statuses: list[str], token: str) -> str:
    for _ in range(MAX_POLLS):
        resp = client.get(
            f"/api/onboarding/status/{patient_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        status = resp.json()["status"]
        print(f"  polling... status={status}")
        if status in target_statuses:
            return status
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Patient {patient_id} did not reach {target_statuses} in time")


@pytest.mark.asyncio
async def test_full_onboarding_flow(db, test_user_token, sample_prescription_bytes, sample_lab_pdf_bytes):
    headers = {"Authorization": f"Bearer {test_user_token}"}

    # Step 0: Set role
    role_resp = client.post("/api/auth/set-role", headers=headers, json={
        "role": "guardian", "full_name": "Meera E2E Test v3", "relationship": "daughter",
    })
    assert role_resp.status_code == 200, role_resp.text
    print(f"\n[1] Role set: {role_resp.json()}")

    # Step 1: Submit onboarding form
    submit_resp = client.post(
        "/api/onboarding/submit",
        headers=headers,
        data={
            "full_name": "Rajesh E2E Test",
            "date_of_birth": "1959-03-15",
            "gender": "male",
            "city": "Lucknow",
            "state": "Uttar Pradesh",
            "conditions": '["Type 2 Diabetes", "Hypertension"]',
            "medications": '[{"drug_name": "Metformin", "dosage": "500mg", "frequency": "twice daily"}]',
            "allergies": '[{"allergen": "Penicillin", "severity": "severe"}]',
            "doctors": '[{"name": "Dr. Sharma", "specialty": "Endocrinologist", "is_primary": true}]',
            "file_types": '["prescription", "lab_report"]',
        },
        files=[
            ("files", ("prescription.jpg", sample_prescription_bytes, "image/jpeg")),
            ("files", ("lab_report.pdf", sample_lab_pdf_bytes, "application/pdf")),
        ],
    )
    assert submit_resp.status_code == 200, submit_resp.text
    patient_id = submit_resp.json()["patient_id"]
    print(f"\n[2] Submitted — patient_id: {patient_id}")

    # Step 2: Poll for medication_verification_needed
    print("\n[3] Polling for medication_verification_needed...")
    status = poll_until(patient_id, ["medication_verification_needed"], test_user_token)
    print(f"    Reached: {status}")

    # Step 3: Get extracted medications (deduplicated, brand names as primary)
    meds_resp = client.get(f"/api/onboarding/extracted_medications/{patient_id}", headers=headers)
    assert meds_resp.status_code == 200, meds_resp.text
    meds_data = meds_resp.json()
    print(f"\n[4] Extracted medications: {len(meds_data['medications'])} meds")
    for m in meds_data["medications"]:
        brand = m.get("drug_name_brand") or m.get("drug_name") or ""
        generic = m.get("drug_name_generic")
        dedup = m.get("dedup_status", "unique")
        conf = m.get("confidence") or 0
        print(f"    - {brand} ({generic}) [{m['source']}] conf={conf:.2f} dedup={dedup}")

    # Step 4: Confirm medications — confirm all, no edits in this test
    confirmed = [
        {
            "medication_id": m["medication_id"],
            "action": "confirm",
        }
        for m in meds_data["medications"]
    ]
    confirm_meds_resp = client.post(
        f"/api/onboarding/confirm_medications/{patient_id}",
        headers=headers,
        json={
            "confirmed_medications": confirmed,
            "added_medications": [],
        },
    )
    assert confirm_meds_resp.status_code == 200, confirm_meds_resp.text
    confirm_data = confirm_meds_resp.json()
    print(f"\n[5] Medications confirmed: {confirm_data}")
    assert confirm_data["status"] == "analysis_running"

    # Step 5: Poll for findings_ready
    print("\n[6] Polling for findings_ready...")
    status = poll_until(patient_id, ["findings_ready", "complete"], test_user_token)
    print(f"    Reached: {status}")

    # Step 6: Get findings (Screen 5)
    findings_resp = client.get(f"/api/onboarding/findings/{patient_id}", headers=headers)
    assert findings_resp.status_code == 200, findings_resp.text
    findings_data = findings_resp.json()
    print(f"\n[7] Findings: status={findings_data['status']}, total={findings_data['total_flags']}")
    print(f"    critical={findings_data['critical_count']}, high={findings_data['high_count']}")
    for directive_type, flags in findings_data.get("flags_by_directive", {}).items():
        print(f"    [{directive_type}]: {len(flags)} flags")
        for flag in flags[:2]:
            print(f"      - {flag['title']}")

    # Step 7: Confirm onboarding complete (Screen 6)
    final_resp = client.post(f"/api/onboarding/confirm/{patient_id}", headers=headers)
    assert final_resp.status_code == 200, final_resp.text
    final_data = final_resp.json()
    print(f"\n[8] COMPLETE — status: {final_data['status']}, score: {final_data['completeness_score']}%")
    print(f"    flags_saved: {final_data['flags_saved']}")

    assert final_data["status"] == "complete"
    assert final_data["completeness_score"] > 0

    # Cleanup
    for table in ["patient_action_summaries", "caregiver_concerns",
                  "temporal_logic_evaluations", "reasoning_runs",
                  "clinical_findings", "open_flags", "culture_findings", "restrictions",
                  "monitoring_instructions", "clinical_directives", "patient_summaries",
                  "drug_safety_checks", "lab_results", "allergies", "diagnoses", "medications",
                  "doctors", "document_extractions", "documents", "patient_guardians"]:
        try:
            db.table(table).delete().eq("patient_id", patient_id).execute()
        except Exception:
            pass
    db.table("patients").delete().eq("id", patient_id).execute()
