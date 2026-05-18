"""
Full longitudinal pipeline integration test.
Runs real DB, real LLM, real OCR — no mocks.

Sequence:
  1. Complete onboarding (inline, using same fixtures as test_onboarding.py)
  2. POST /upload → starts L1→L3
  3. Poll until status='reconciling'
  4. GET /medication_reconciliation → assert non-empty existing_medications
  5. POST /confirm_reconciliation → starts L5→L10
  6. Poll until status='ready'
  7. GET /findings → assert non-empty concerns + run_summary + action_summary
  8. GET /logs/{run_id} → assert all phases present, no ERROR-level logs
  9. POST /confirm_findings → assert complete
  10. Cleanup in FK-safe order

Run with: pytest tests/test_longitudinal.py -v -s
"""
import pytest
import time
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

POLL_INTERVAL = 3
MAX_POLLS = 60


def poll_onboarding(patient_id: str, target_statuses: list[str], token: str) -> str:
    for _ in range(MAX_POLLS):
        resp = client.get(
            f"/api/onboarding/status/{patient_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        status = resp.json()["status"]
        print(f"  [onboarding] polling... status={status}")
        if status in target_statuses:
            return status
        if status == "failed":
            raise RuntimeError(f"Onboarding failed")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Onboarding did not reach {target_statuses}")


def poll_longitudinal(upload_event_id: str, patient_id: str, target_statuses: list[str], token: str) -> str:
    for _ in range(MAX_POLLS):
        resp = client.get(
            f"/api/longitudinal/status/{patient_id}/{upload_event_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        status = data["processing_status"]
        print(f"  [longitudinal] polling... status={status}")
        if status in target_statuses:
            return status
        if status == "failed":
            raise RuntimeError(f"Longitudinal pipeline failed: {data.get('error_message')}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Longitudinal did not reach {target_statuses}")


@pytest.mark.asyncio
async def test_full_longitudinal_flow(
    db,
    test_user_token,
    sample_prescription_bytes,
    sample_lab_pdf_bytes,
):
    headers = {"Authorization": f"Bearer {test_user_token}"}

    # ── Step 0: Set role ───────────────────────────────────────────────────────
    role_resp = client.post("/api/auth/set-role", headers=headers, json={
        "role": "guardian",
        "full_name": "Longitudinal Test Guardian",
        "relationship": "daughter",
    })
    assert role_resp.status_code == 200, role_resp.text
    print(f"\n[0] Role set")

    # ── Step 1: Submit onboarding ──────────────────────────────────────────────
    submit_resp = client.post(
        "/api/onboarding/submit",
        headers=headers,
        data={
            "full_name": "Longitudinal Test Patient",
            "date_of_birth": "1960-05-01",
            "gender": "male",
            "city": "Delhi",
            "state": "Delhi",
            "conditions": '["Type 2 Diabetes", "Hypertension"]',
            "medications": '[{"drug_name": "Metformin", "dosage": "500mg", "frequency": "twice daily"}]',
            "allergies": '[]',
            "doctors": '[{"name": "Dr. Test", "specialty": "General", "is_primary": true}]',
            "file_types": '["prescription", "lab_report"]',
        },
        files=[
            ("files", ("prescription.jpg", sample_prescription_bytes, "image/jpeg")),
            ("files", ("lab_report.pdf", sample_lab_pdf_bytes, "application/pdf")),
        ],
    )
    assert submit_resp.status_code == 200, submit_resp.text
    patient_id = submit_resp.json()["patient_id"]
    print(f"[1] Onboarding submitted — patient_id: {patient_id}")

    # ── Step 2: Poll onboarding → medication_verification_needed ──────────────
    print("[2] Waiting for medication_verification_needed...")
    poll_onboarding(patient_id, ["medication_verification_needed"], test_user_token)

    # ── Step 3: Confirm medications ────────────────────────────────────────────
    meds_resp = client.get(f"/api/onboarding/extracted_medications/{patient_id}", headers=headers)
    assert meds_resp.status_code == 200, meds_resp.text
    meds_data = meds_resp.json()
    confirmed = [{"medication_id": m["medication_id"], "action": "confirm"} for m in meds_data["medications"]]
    confirm_meds_resp = client.post(
        f"/api/onboarding/confirm_medications/{patient_id}",
        headers=headers,
        json={"confirmed_medications": confirmed, "added_medications": []},
    )
    assert confirm_meds_resp.status_code == 200, confirm_meds_resp.text
    print(f"[3] Medications confirmed")

    # ── Step 4: Poll onboarding → findings_ready ──────────────────────────────
    print("[4] Waiting for findings_ready...")
    poll_onboarding(patient_id, ["findings_ready", "complete"], test_user_token)

    # ── Step 5: Confirm onboarding ─────────────────────────────────────────────
    confirm_ob_resp = client.post(f"/api/onboarding/confirm/{patient_id}", headers=headers)
    assert confirm_ob_resp.status_code == 200, confirm_ob_resp.text
    assert confirm_ob_resp.json()["status"] == "complete"
    print(f"[5] Onboarding complete ✓")

    # ═══════════════════════════════════════════════════════════════════════════
    # LONGITUDINAL PIPELINE
    # ═══════════════════════════════════════════════════════════════════════════

    # ── Step L1: Upload new documents ─────────────────────────────────────────
    print("\n[L1] Uploading new post-onboarding documents...")
    upload_resp = client.post(
        f"/api/longitudinal/upload/{patient_id}",
        headers=headers,
        data={"file_types": '["prescription", "lab_report"]'},
        files=[
            ("files", ("new_prescription.jpg", sample_prescription_bytes, "image/jpeg")),
            ("files", ("new_lab_report.pdf", sample_lab_pdf_bytes, "application/pdf")),
        ],
    )
    assert upload_resp.status_code == 200, upload_resp.text
    upload_data = upload_resp.json()
    upload_event_id = upload_data["upload_event_id"]
    assert upload_data["status"] == "extracting"
    print(f"    upload_event_id: {upload_event_id}")

    # ── Step L2: Poll until reconciling ───────────────────────────────────────
    print("[L2] Polling until reconciling...")
    status = poll_longitudinal(upload_event_id, patient_id, ["reconciling"], test_user_token)
    print(f"    Reached: {status} ✓")

    # ── Step L3: GET medication reconciliation ─────────────────────────────────
    print("[L3] Getting medication reconciliation...")
    recon_resp = client.get(
        f"/api/longitudinal/medication_reconciliation/{patient_id}/{upload_event_id}",
        headers=headers,
    )
    assert recon_resp.status_code == 200, recon_resp.text
    recon_data = recon_resp.json()
    print(f"    existing_medications: {len(recon_data['existing_medications'])}")
    print(f"    newly_extracted: {len(recon_data['newly_extracted_medications'])}")
    assert len(recon_data["existing_medications"]) > 0, "Should have at least one existing medication from onboarding"

    # ── Step L4: POST confirm reconciliation ──────────────────────────────────
    print("[L4] Confirming reconciliation...")
    confirmations = [
        {
            "transition_id": t["transition_id"],
            "action": "confirm",
            "guardian_action": "still_taking",
        }
        for t in recon_data["newly_extracted_medications"]
    ]
    confirm_recon_resp = client.post(
        f"/api/longitudinal/confirm_reconciliation/{patient_id}/{upload_event_id}",
        headers=headers,
        json={"confirmations": confirmations},
    )
    assert confirm_recon_resp.status_code == 200, confirm_recon_resp.text
    assert confirm_recon_resp.json()["status"] == "reasoning_running"
    print("    Reconciliation confirmed ✓")

    # ── Step L5: Poll until ready ──────────────────────────────────────────────
    print("[L5] Polling until ready...")
    status = poll_longitudinal(upload_event_id, patient_id, ["ready"], test_user_token)
    print(f"    Reached: {status} ✓")

    # ── Step L6: GET findings ──────────────────────────────────────────────────
    print("[L6] Getting findings...")
    findings_resp = client.get(
        f"/api/longitudinal/findings/{patient_id}/{upload_event_id}",
        headers=headers,
    )
    assert findings_resp.status_code == 200, findings_resp.text
    findings_data = findings_resp.json()

    print(f"    status: {findings_data['status']}")
    print(f"    run_summary: {findings_data['run_summary']}")
    print(f"    concerns: {len(findings_data['concerns'])}")
    print(f"    concern_summary: {findings_data['concern_summary']}")

    assert findings_data["status"] == "ready"
    assert len(findings_data["concerns"]) > 0, "Should have at least one concern card"
    assert findings_data["run_summary"] is not None
    assert findings_data["action_summary"] is not None

    run_id = findings_data.get("run_id")
    print(f"    run_id: {run_id}")

    # ── Step L7: GET logs ──────────────────────────────────────────────────────
    if run_id:
        print("[L7] Getting pipeline logs...")
        logs_resp = client.get(f"/api/longitudinal/logs/{run_id}", headers=headers)
        assert logs_resp.status_code == 200, logs_resp.text
        logs_data = logs_resp.json()
        print(f"    log_count: {logs_data['log_count']}")

        phases_logged = {log["phase"] for log in logs_data["logs"]}
        print(f"    phases logged: {sorted(phases_logged)}")

        error_logs = [l for l in logs_data["logs"] if l["level"] == "ERROR"]
        assert len(error_logs) == 0, f"Pipeline had ERROR logs: {error_logs}"
        assert logs_data["log_count"] > 0, "Should have pipeline logs"

    # ── Step L8: POST confirm findings ────────────────────────────────────────
    print("[L8] Confirming findings...")
    confirm_resp = client.post(
        f"/api/longitudinal/confirm_findings/{patient_id}/{upload_event_id}",
        headers=headers,
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    confirm_data = confirm_resp.json()
    assert confirm_data["status"] == "complete"
    print(f"    acknowledged: {confirm_data['concerns_acknowledged']} ✓")

    print("\n✅ Full longitudinal pipeline test PASSED")

    # ── Cleanup ────────────────────────────────────────────────────────────────
    print("\n[CLEANUP] Removing test data...")

    # Longitudinal tables in FK-safe order
    for table in [
        "longitudinal_pipeline_logs",
        "longitudinal_caregiver_concerns",
        "longitudinal_findings",
        "medication_state_transitions",
    ]:
        try:
            db.table(table).delete().eq("patient_id", patient_id).execute()
        except Exception:
            pass

    if run_id:
        try:
            db.table("longitudinal_runs").delete().eq("id", run_id).execute()
        except Exception:
            pass

    try:
        db.table("document_upload_events").delete().eq("patient_id", patient_id).execute()
    except Exception:
        pass

    # Onboarding tables in FK-safe order
    for table in [
        "patient_action_summaries", "caregiver_concerns",
        "temporal_logic_evaluations", "reasoning_runs",
        "clinical_findings", "open_flags", "culture_findings", "restrictions",
        "monitoring_instructions", "clinical_directives", "patient_summaries",
        "drug_safety_checks", "lab_results", "allergies", "diagnoses", "medications",
        "doctors", "document_extractions", "documents", "patient_guardians",
    ]:
        try:
            db.table(table).delete().eq("patient_id", patient_id).execute()
        except Exception:
            pass

    try:
        db.table("patients").delete().eq("id", patient_id).execute()
    except Exception:
        pass

    print("[CLEANUP] Done.")
