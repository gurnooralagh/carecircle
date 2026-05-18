"""
Longitudinal pipeline router — 7 endpoints under /api/longitudinal/.
All require bearer token auth.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from supabase import Client
from db.client import get_db
from dependencies import get_current_user
from services.storage import upload_file
from services.longitudinal_pipeline import run_pre_gate_pipeline, run_post_gate_pipeline
from config.logging import get_logger

logger = get_logger("LONGITUDINAL")
router = APIRouter(prefix="/api/longitudinal", tags=["longitudinal"])


@router.post("/upload/{patient_id}")
async def upload_documents(
    patient_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    file_types: str = Form("[]"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Upload new post-onboarding documents. Starts L1→L3 background pipeline."""
    patient = (db.table("patients").select("onboarding_status")
               .eq("id", patient_id).execute()).data
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient[0].get("onboarding_status") != "complete":
        raise HTTPException(
            status_code=400,
            detail="Patient onboarding must be complete before uploading new documents",
        )

    try:
        file_types_list = json.loads(file_types) if file_types else []
    except json.JSONDecodeError:
        file_types_list = []

    # Create upload event record
    event_result = db.table("document_upload_events").insert({
        "patient_id": patient_id,
        "processing_status": "pending",
        "uploaded_files": [f.filename for f in files],
    }).execute()
    if not event_result.data:
        raise HTTPException(status_code=500, detail="Could not create upload event")
    upload_event_id = event_result.data[0]["id"]

    # Upload files to storage and create document records tagged post_onboarding
    for i, uploaded_file in enumerate(files):
        file_bytes = await uploaded_file.read()
        _raw_type = file_types_list[i] if i < len(file_types_list) else "other"
        _type_map = {
            "Prescription": "prescription",
            "Lab Report": "lab_report",
            "Discharge Summary": "discharge_summary",
            "Other": "other",
        }
        doc_type = _type_map.get(_raw_type, _raw_type.lower().replace(" ", "_"))
        storage_path = upload_file(
            db=db,
            patient_id=patient_id,
            document_type=doc_type,
            filename=uploaded_file.filename,
            file_bytes=file_bytes,
            mime_type=uploaded_file.content_type or "application/octet-stream",
        )
        mime = uploaded_file.content_type or "application/octet-stream"
        db.table("documents").insert({
            "patient_id": patient_id,
            "document_type": doc_type,
            "original_filename": uploaded_file.filename,
            "storage_path": storage_path,
            "mime_type": mime,
            "file_type": mime,
            "extraction_status": "pending",
            "upload_context": "post_onboarding",
            "is_deleted": False,
        }).execute()
        logger.info(f"Document uploaded: {uploaded_file.filename} ({doc_type})")

    db.table("patients").update({"longitudinal_status": "processing"}).eq("id", patient_id).execute()

    background_tasks.add_task(
        run_pre_gate_pipeline,
        patient_id=patient_id,
        upload_event_id=upload_event_id,
        db=db,
    )
    logger.info(f"Pre-gate pipeline scheduled for patient {patient_id}, event {upload_event_id}")

    return {"upload_event_id": upload_event_id, "status": "extracting"}


@router.get("/status/{patient_id}/{upload_event_id}")
async def get_upload_status(
    patient_id: str,
    upload_event_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Poll every 3s. Returns processing_status and error_message if failed."""
    row = (db.table("document_upload_events")
           .select("processing_status,error_message")
           .eq("id", upload_event_id)
           .eq("patient_id", patient_id).execute()).data
    if not row:
        raise HTTPException(status_code=404, detail="Upload event not found")
    return {
        "upload_event_id": upload_event_id,
        "processing_status": row[0]["processing_status"],
        "error_message": row[0].get("error_message"),
    }


@router.get("/medication_reconciliation/{patient_id}/{upload_event_id}")
async def get_medication_reconciliation(
    patient_id: str,
    upload_event_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """L4 gate: returns existing medications + newly extracted/changed ones for guardian review."""
    ev = (db.table("document_upload_events")
          .select("processing_status,longitudinal_run_id")
          .eq("id", upload_event_id).execute()).data
    if not ev:
        raise HTTPException(status_code=404, detail="Upload event not found")

    current_status = ev[0]["processing_status"]
    if current_status != "reconciling":
        raise HTTPException(
            status_code=400,
            detail=f"Upload is not in reconciling state (current: {current_status})",
        )

    run_id = ev[0].get("longitudinal_run_id")

    # Existing active medications (baseline)
    existing = (db.table("medications").select("*")
                .eq("patient_id", patient_id)
                .eq("is_deleted", False)
                .eq("is_current", True).execute()).data

    # Transition records for this run
    transitions = []
    if run_id:
        transitions = (db.table("medication_state_transitions").select("*")
                       .eq("run_id", run_id).execute()).data

    added_or_changed = [t for t in transitions if t["transition_type"] not in ("continued",)]
    continued_count = sum(1 for t in transitions if t["transition_type"] == "continued")

    return {
        "existing_medications": [
            {
                "medication_id": m["id"],
                "drug_name_brand": m.get("drug_name_brand"),
                "drug_name_generic": m.get("drug_name_generic"),
                "dose_text": m.get("dose_text") or m.get("dosage"),
                "frequency": m.get("frequency"),
                "status": m.get("status"),
            }
            for m in existing
        ],
        "newly_extracted_medications": [
            {
                "transition_id": t["id"],
                "transition_type": t["transition_type"],
                "drug_name_brand": t.get("drug_name_brand"),
                "drug_name_generic": t.get("drug_name_generic"),
                "prior_dose_mg": t.get("prior_dose_mg"),
                "new_dose_mg": t.get("new_dose_mg"),
                "prior_frequency": t.get("prior_frequency"),
                "new_frequency": t.get("new_frequency"),
                "source_document": t.get("source_document"),
            }
            for t in added_or_changed
        ],
        "continued_medications": continued_count,
    }


@router.post("/confirm_reconciliation/{patient_id}/{upload_event_id}")
async def confirm_reconciliation(
    patient_id: str,
    upload_event_id: str,
    body: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Guardian confirms medication reconciliation. Triggers L5→L10.
    body: {
      "confirmations": [
        {"transition_id": "...", "action": "confirm|edit|remove",
         "guardian_action": "still_taking|stopped|held|not_sure",
         "new_dose_mg": null, "new_frequency": null}
      ]
    }
    """
    ev = (db.table("document_upload_events")
          .select("processing_status,longitudinal_run_id")
          .eq("id", upload_event_id).execute()).data
    if not ev:
        raise HTTPException(status_code=404, detail="Upload event not found")
    if ev[0]["processing_status"] != "reconciling":
        raise HTTPException(status_code=400, detail="Upload is not in reconciling state")

    confirmations = body.get("confirmations") or []
    for conf in confirmations:
        tid = conf.get("transition_id")
        if not tid:
            continue
        action = conf.get("action", "confirm")
        guardian_action = conf.get("guardian_action", "still_taking")

        if action == "remove":
            continue  # guardian rejected this transition — leave it unconfirmed

        updates: dict = {
            "guardian_confirmed": True,
            "guardian_action": guardian_action,
        }
        if action == "edit":
            if conf.get("new_dose_mg") is not None:
                updates["new_dose_mg"] = conf["new_dose_mg"]
            if conf.get("new_frequency"):
                updates["new_frequency"] = conf["new_frequency"]

        try:
            db.table("medication_state_transitions").update(updates).eq("id", tid).execute()
        except Exception as e:
            logger.warning(f"Could not update transition {tid}: {e}")

    db.table("document_upload_events").update({
        "processing_status": "reasoning"
    }).eq("id", upload_event_id).execute()

    background_tasks.add_task(
        run_post_gate_pipeline,
        patient_id=patient_id,
        upload_event_id=upload_event_id,
        db=db,
    )
    logger.info(f"Post-gate pipeline scheduled for patient {patient_id}, event {upload_event_id}")

    return {"status": "reasoning_running", "upload_event_id": upload_event_id}


@router.get("/findings/{patient_id}/{upload_event_id}")
async def get_findings(
    patient_id: str,
    upload_event_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Returns full longitudinal findings when processing_status='ready'."""
    ev = (db.table("document_upload_events")
          .select("processing_status,longitudinal_run_id")
          .eq("id", upload_event_id).execute()).data
    if not ev:
        raise HTTPException(status_code=404, detail="Upload event not found")

    status = ev[0]["processing_status"]
    if status not in ("ready", "failed"):
        return {"status": "running", "processing_status": status}

    run_id = ev[0].get("longitudinal_run_id")

    # Run summary
    run_summary = {}
    if run_id:
        run_rows = (db.table("longitudinal_runs").select("*").eq("id", run_id).execute()).data
        if run_rows:
            r = run_rows[0]
            run_summary = {
                "findings_new": r.get("findings_new", 0),
                "findings_escalated": r.get("findings_escalated", 0),
                "findings_resolved": r.get("findings_resolved", 0),
                "findings_improved": r.get("findings_improved", 0),
                "findings_recurring_suppressed": r.get("findings_suppressed", 0),
            }

    # Medication changes (non-continued)
    medication_changes = []
    if run_id:
        trans = (db.table("medication_state_transitions").select("*")
                 .eq("run_id", run_id)
                 .neq("transition_type", "continued").execute()).data
        medication_changes = [
            {
                "drug_name_brand": t.get("drug_name_brand"),
                "drug_name_generic": t.get("drug_name_generic"),
                "transition_type": t.get("transition_type"),
                "prior_dose_mg": t.get("prior_dose_mg"),
                "new_dose_mg": t.get("new_dose_mg"),
                "prior_frequency": t.get("prior_frequency"),
                "new_frequency": t.get("new_frequency"),
                "source_document": t.get("source_document"),
            }
            for t in trans
        ]

    # Concerns ordered by display_order
    concerns = []
    concern_summary = {"new": 0, "escalated": 0, "resolved": 0, "improved": 0, "nudge_items": 0}
    if run_id:
        concern_rows = (db.table("longitudinal_caregiver_concerns").select("*")
                        .eq("run_id", run_id)
                        .order("display_order").execute()).data
        for c in concern_rows:
            cat = c.get("concern_category", "new")
            if cat == "nudge" or c.get("is_nudge"):
                concern_summary["nudge_items"] += 1
            elif cat in concern_summary:
                concern_summary[cat] += 1

            concerns.append({
                "concern_id": str(c["id"]),
                "concern_type": c.get("concern_type"),
                "concern_category": cat,
                "priority": c.get("priority"),
                "title": c.get("title"),
                "summary": c.get("summary"),
                "what_was_found": c.get("what_was_found"),
                "why_it_matters": c.get("why_it_matters"),
                "what_to_do": c.get("what_to_do"),
                "evidence": c.get("evidence") or [],
                "source_documents": c.get("source_documents") or [],
                "is_nudge": c.get("is_nudge", False),
                "nudge_original_finding_date": str(c.get("nudge_original_finding_date") or ""),
                "display_order": c.get("display_order", 0),
            })

    # Action summary
    action_summary = None
    as_rows = (db.table("patient_action_summaries").select("*")
               .eq("patient_id", patient_id)
               .eq("is_current", True).limit(1).execute()).data
    if as_rows:
        a = as_rows[0]
        action_summary = {
            "do_now": a.get("do_now") or [],
            "follow_up": a.get("follow_up") or [],
            "ongoing_monitoring": a.get("ongoing_monitoring") or [],
            "resolved_since_last_upload": a.get("resolved_since_last_upload") or [],
        }

    return {
        "status": status,
        "run_id": run_id,
        "run_summary": run_summary,
        "medication_changes": medication_changes,
        "concerns": concerns,
        "concern_summary": concern_summary,
        "action_summary": action_summary,
    }


@router.post("/confirm_findings/{patient_id}/{upload_event_id}")
async def confirm_findings(
    patient_id: str,
    upload_event_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Guardian acknowledges longitudinal findings. Marks concerns acknowledged."""
    ev = (db.table("document_upload_events").select("longitudinal_run_id")
          .eq("id", upload_event_id).execute()).data
    if not ev:
        raise HTTPException(status_code=404, detail="Upload event not found")

    run_id = ev[0].get("longitudinal_run_id")
    acknowledged = 0
    if run_id:
        result = (db.table("longitudinal_caregiver_concerns")
                  .update({"is_acknowledged": True})
                  .eq("run_id", run_id).execute())
        acknowledged = len(result.data) if result.data else 0

    return {"status": "complete", "concerns_acknowledged": acknowledged}


@router.get("/logs/{run_id}")
async def get_logs(
    run_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Debug: returns all pipeline logs for a run in chronological order."""
    logs = (db.table("longitudinal_pipeline_logs").select("*")
            .eq("run_id", run_id)
            .order("created_at").execute()).data
    return {"run_id": run_id, "log_count": len(logs), "logs": logs}
