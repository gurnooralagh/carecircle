"""
Onboarding router — v3.0 API.

Active endpoints:
  POST /api/onboarding/submit
  GET  /api/onboarding/status/{patient_id}
  GET  /api/onboarding/extracted_medications/{patient_id}
  POST /api/onboarding/confirm_medications/{patient_id}
  GET  /api/onboarding/findings/{patient_id}
  POST /api/onboarding/confirm/{patient_id}

Removed in v3.0:
  GET  /api/onboarding/questions (no questions asked)
  POST /api/onboarding/answer
  GET  /api/onboarding/drug_safety_results
  GET  /api/onboarding/results
  POST /api/onboarding/corrections
"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, status
from supabase import Client
from db.client import get_db
from dependencies import get_current_user
from models.requests import ConfirmMedicationsRequest, MedicationInput
from models.responses import (
    SubmitResponse, StatusResponse,
    ExtractedMedicationsResponse, MedicationItem,
    ConfirmMedicationsResponse, FlagItem, FindingsResponse,
    ConcernItem, ConcernSummary, EvidenceItem, BrandNameUsed,
    ConfirmResponse, ActionItem, ActionSummary,
)
from services.storage import upload_file
from services.extraction_pipeline import run_extraction_pipeline, run_analysis_pipeline, _normalize_frequency
from config.logging import get_logger

logger = get_logger("ONBOARDING")
router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.post("/submit", response_model=SubmitResponse)
async def submit_onboarding(
    background_tasks: BackgroundTasks,
    full_name: str = Form(...),
    date_of_birth: str = Form(...),
    gender: str = Form(...),
    blood_group: str = Form(None),
    weight_kg: float = Form(None),
    height_cm: float = Form(None),
    city: str = Form(None),
    state: str = Form(None),
    primary_language: str = Form("hindi"),
    conditions: str = Form("[]"),
    medications: str = Form("[]"),
    allergies: str = Form("[]"),
    doctors: str = Form("[]"),
    files: list[UploadFile] = File(default=[]),
    file_types: str = Form("[]"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    logger.info(f"Onboarding submit — user: {current_user['id']}, patient: {full_name}")

    try:
        conditions_list = json.loads(conditions)
        medications_list = json.loads(medications)
        allergies_list = json.loads(allergies)
        doctors_list = json.loads(doctors)
        file_types_list = json.loads(file_types) if file_types else []
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON in form field: {e}")

    # 1. Create patient record
    patient_result = db.table("patients").insert({
        "full_name": full_name,
        "date_of_birth": date_of_birth,
        "gender": gender,
        "weight_kg": weight_kg,
        "height_cm": height_cm,
        "city": city or "Unknown",
        "state": state,
        "primary_language": primary_language,
        "onboarding_status": "processing",
    }).execute()
    if not patient_result.data:
        raise HTTPException(status_code=500, detail="Failed to create patient record")
    patient_id = patient_result.data[0]["id"]
    logger.info(f"Patient created: {patient_id}")

    # 2. Link guardian
    profile_result = db.table("user_profiles").select("id").eq("auth_user_id", current_user["id"]).execute()
    if not profile_result.data:
        raise HTTPException(status_code=400, detail="Call /api/auth/set-role first")
    profile_id = profile_result.data[0]["id"]
    db.table("patient_guardians").insert({
        "patient_id": patient_id,
        "user_profile_id": profile_id,
        "is_primary_guardian": True,
    }).execute()

    # 3. Insert stated conditions
    for condition_name in conditions_list:
        if condition_name:
            db.table("diagnoses").insert({
                "patient_id": patient_id,
                "condition_name": condition_name,
                "source": "guardian_stated",
                "confirmation_status": "confirmed",
                "confirmed_by_guardian": True,
            }).execute()

    # 4. Insert stated medications (Phase 1 inline brand resolution happens in background)
    for med in medications_list:
        drug_name = med.get("drug_name") or med.get("name") or ""
        if drug_name:
            dose = med.get("dose_text") or med.get("dosage")
            db.table("medications").insert({
                "patient_id": patient_id,
                "drug_name_brand": drug_name,
                "drug_name_normalized": drug_name,  # backward compat
                "drug_name_original_ocr": drug_name,
                "dose_text": dose,
                "dosage": dose,  # backward compat
                "frequency": med.get("frequency"),
                "timing": med.get("timing"),
                "source": "guardian_stated",
                "confirmed_by_guardian": True,
                "is_otc": med.get("is_otc", False),
                "is_supplement": med.get("is_supplement", False),
                "status": "active",
                "is_current": True,
            }).execute()

    # 5. Insert allergies
    for allergy in allergies_list:
        allergen = allergy.get("allergen") or allergy.get("name") or ""
        if allergen:
            db.table("allergies").insert({
                "patient_id": patient_id,
                "allergen": allergen,
                "reaction_type": allergy.get("reaction") or allergy.get("reaction_type"),
                "severity": allergy.get("severity", "unknown"),
                "source": "guardian_stated",
            }).execute()

    # 6. Insert doctors
    for doctor in doctors_list:
        doc_name = doctor.get("name") or doctor.get("full_name") or ""
        if doc_name:
            db.table("doctors").insert({
                "patient_id": patient_id,
                "name": doc_name,
                "full_name": doc_name,
                "specialty": doctor.get("specialty"),
                "hospital_name": doctor.get("hospital"),
                "hospital": doctor.get("hospital"),
                "phone": doctor.get("phone"),
                "source": "guardian_stated",
                "is_primary": doctor.get("is_primary", False),
                "is_primary_physician": doctor.get("is_primary", False),
            }).execute()

    # 7. Upload files
    for i, uploaded_file in enumerate(files):
        file_bytes = await uploaded_file.read()
        doc_type = file_types_list[i] if i < len(file_types_list) else "other"
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
            "uploaded_by": profile_id,
            "document_type": doc_type,
            "original_filename": uploaded_file.filename,
            "storage_path": storage_path,
            "mime_type": mime,
            "file_type": mime,
            "extraction_status": "pending",
            "is_deleted": False,
        }).execute()
        logger.info(f"Document uploaded: {uploaded_file.filename} ({doc_type})")

    # 8. Start background pipeline (phases 2-3.4)
    background_tasks.add_task(run_extraction_pipeline, patient_id=patient_id, db=db)
    logger.info(f"Background extraction scheduled for patient {patient_id}")

    return SubmitResponse(patient_id=patient_id, status="processing")


@router.get("/status/{patient_id}", response_model=StatusResponse)
async def get_status(
    patient_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    patient = db.table("patients").select("id,onboarding_status,completeness_score").eq("id", patient_id).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail="Patient not found")
    p = patient.data[0]
    return StatusResponse(
        patient_id=patient_id,
        status=p["onboarding_status"],
        completeness_score=p.get("completeness_score") or 0,
    )


@router.get("/extracted_medications/{patient_id}", response_model=ExtractedMedicationsResponse)
async def get_extracted_medications(
    patient_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Returns deduplicated medication list with brand names as primary display.
    Includes dose/status conflict details for Screen 4.
    """
    meds_result = (
        db.table("medications").select("*")
        .eq("patient_id", patient_id)
        .eq("is_deleted", False)
        .execute()
    )
    conditions_result = (
        db.table("diagnoses").select("condition_name")
        .eq("patient_id", patient_id)
        .execute()
    )

    # Get dedup conflicts from clinical_findings
    conflicts = (
        db.table("clinical_findings").select("*")
        .eq("patient_id", patient_id)
        .in_("finding_type", ["medication_dose_conflict", "stopped_medication_still_prescribed", "same_medication_multiple_prescribers"])
        .execute()
    ).data

    conflict_map: dict[str, dict] = {}
    for c in conflicts:
        related = c.get("related_entities") or {}
        if isinstance(related, str):
            try:
                related = json.loads(related)
            except Exception:
                related = {}
        for med_name in related.get("medications") or []:
            conflict_map[med_name.lower()] = c

    medications = []
    for m in meds_result.data:
        brand = m.get("drug_name_brand") or m.get("drug_name_normalized") or ""
        generic = m.get("drug_name_generic")
        display_conf = m.get("normalization_confidence") or m.get("extraction_confidence") or m.get("confidence")

        # Determine dedup_status
        dedup_status = "unique"
        conflict_detail = None
        med_key = (generic or brand).lower()
        if med_key in conflict_map:
            conflict_finding = conflict_map[med_key]
            if conflict_finding["finding_type"] == "medication_dose_conflict":
                dedup_status = "dose_conflict"
            elif conflict_finding["finding_type"] == "stopped_medication_still_prescribed":
                dedup_status = "status_conflict"
            elif conflict_finding["finding_type"] == "same_medication_multiple_prescribers":
                dedup_status = "merged"

        # Confidence-based verification flag
        conf = float(display_conf or 0.8)
        needs_verification = conf < 0.75 or not generic

        source_refs = m.get("source_references") or []
        if isinstance(source_refs, str):
            try:
                source_refs = json.loads(source_refs)
            except Exception:
                source_refs = []

        medications.append(MedicationItem(
            medication_id=m["id"],
            drug_name_brand=brand,
            drug_name_generic=generic,
            drug_class=m.get("drug_class"),
            dose_text=m.get("dose_text") or m.get("dosage"),
            frequency=m.get("frequency"),
            timing=m.get("timing"),
            source=m.get("source", "unknown"),
            source_references=source_refs if isinstance(source_refs, list) else [],
            cross_reference_status=m.get("cross_reference_status", "document_only"),
            confidence=display_conf,
            normalization_confidence=m.get("normalization_confidence"),
            needs_verification=needs_verification,
            confirmed_by_guardian=m.get("confirmed_by_guardian", False),
            dedup_status=dedup_status,
            # Legacy fields
            drug_name=brand,
            dosage=m.get("dose_text") or m.get("dosage"),
            safety_check_status=m.get("safety_check_status", "pending"),
            candidates=m.get("candidates") or [],
        ))

    conditions = [r["condition_name"] for r in conditions_result.data]
    logger.info(f"Returning {len(medications)} medications for patient {patient_id}")
    return ExtractedMedicationsResponse(medications=medications, extracted_conditions=conditions)


@router.post("/confirm_medications/{patient_id}", response_model=ConfirmMedicationsResponse)
async def confirm_medications(
    patient_id: str,
    body: ConfirmMedicationsRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Screen 4 guardian confirmation. Handles:
    - confirm: mark confirmed
    - edit: update fields
    - remove: soft delete
    - dose_conflict resolution
    - status_conflict resolution
    Then triggers phases 5-8 analysis in background.
    """
    logger.info(f"Medication confirmation for patient {patient_id} — {len(body.confirmed_medications)} items")
    confirmed_count = 0

    for item in body.confirmed_medications:
        if item.action == "remove" and item.medication_id:
            db.table("medications").update({
                "is_deleted": True,
                "deleted_reason": "guardian_removed",
            }).eq("id", item.medication_id).execute()

        elif item.action in ("confirm", "edit") and item.medication_id:
            update: dict = {
                "confirmed_by_guardian": True,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            }

            if item.action == "edit" and item.updated_fields:
                if item.updated_fields.get("drug_name_brand"):
                    update["drug_name_brand"] = item.updated_fields["drug_name_brand"]
                    update["drug_name_normalized"] = item.updated_fields["drug_name_brand"]
                if item.updated_fields.get("dose_text"):
                    update["dose_text"] = item.updated_fields["dose_text"]
                    update["dosage"] = item.updated_fields["dose_text"]
                if item.updated_fields.get("frequency"):
                    update["frequency"] = item.updated_fields["frequency"]

            # Handle conflict resolution
            if item.conflict_resolution:
                res = item.conflict_resolution
                if res.chosen_dose_text:
                    update["dose_text"] = res.chosen_dose_text
                    update["dosage"] = res.chosen_dose_text
                if res.chosen_dose_mg is not None:
                    update["dose_mg"] = res.chosen_dose_mg
                if res.is_currently_taking is False:
                    update["status"] = "stopped"
                    update["is_current"] = False
                elif res.is_currently_taking is True:
                    update["status"] = "active"
                    update["is_current"] = True

            # Legacy: handle old drug_name field
            if not item.updated_fields and item.drug_name:
                update["drug_name_brand"] = item.drug_name
                update["drug_name_normalized"] = item.drug_name

            # Fix 1C: guardian taking status and confirmed dose/frequency
            if item.guardian_taking_status:
                update["guardian_taking_status"] = item.guardian_taking_status
                update["guardian_taking_confirmed_at"] = datetime.now(timezone.utc).isoformat()
                if item.guardian_taking_status == "no_stopped":
                    update["is_current"] = False
                    update["status"] = "stopped"
            if item.guardian_confirmed_dose_text:
                update["dose_text"] = item.guardian_confirmed_dose_text
                update["dosage"] = item.guardian_confirmed_dose_text
            if item.guardian_confirmed_frequency:
                update["frequency"] = _normalize_frequency(item.guardian_confirmed_frequency)

            db.table("medications").update(update).eq("id", item.medication_id).execute()
            confirmed_count += 1

    # Add new medications from guardian
    for added in body.added_medications:
        drug_name = added.drug_name or ""
        if not drug_name:
            continue
        dose = added.dose_text or added.dosage
        db.table("medications").insert({
            "patient_id": patient_id,
            "drug_name_brand": drug_name,
            "drug_name_normalized": drug_name,
            "drug_name_original_ocr": drug_name,
            "dose_text": dose,
            "dosage": dose,
            "frequency": added.frequency,
            "timing": added.timing,
            "source": "guardian_stated",
            "confirmed_by_guardian": True,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "is_current": True,
        }).execute()
        confirmed_count += 1

    # Confirmed conditions (legacy compat)
    for condition_name in body.confirmed_conditions:
        existing = db.table("diagnoses").select("id").eq("patient_id", patient_id).eq("condition_name", condition_name).execute()
        if not existing.data:
            db.table("diagnoses").insert({
                "patient_id": patient_id,
                "condition_name": condition_name,
                "source": "guardian_stated",
                "confirmation_status": "confirmed",
                "confirmed_by_guardian": True,
            }).execute()

    # Set status → analysis_running, then kick off phases 5-8
    db.table("patients").update({"onboarding_status": "analysis_running"}).eq("id", patient_id).execute()
    background_tasks.add_task(run_analysis_pipeline, patient_id=patient_id, db=db)
    logger.info(f"Analysis pipeline scheduled for patient {patient_id}")

    return ConfirmMedicationsResponse(
        status="analysis_running",
        medications_confirmed=confirmed_count,
        analysis_started=True,
        drug_check_started=True,
    )


@router.get("/findings/{patient_id}", response_model=FindingsResponse)
async def get_findings(
    patient_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Screen 5: return caregiver_concerns produced by Phase 6.5 orchestration."""
    patient = db.table("patients").select("onboarding_status").eq("id", patient_id).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail="Patient not found")

    current_status = patient.data[0]["onboarding_status"]
    if current_status not in ("findings_ready", "complete"):
        return FindingsResponse(status="running")

    # Load concerns ordered for display
    rows = (
        db.table("caregiver_concerns").select("*")
        .eq("patient_id", patient_id)
        .eq("status", "active")
        .order("display_order")
        .execute()
    ).data

    # Count raw flags (for informational note only)
    raw_flags_count = (
        db.table("open_flags").select("id", count="exact")
        .eq("patient_id", patient_id)
        .eq("status", "open")
        .execute()
    ).count or 0

    concerns: list[ConcernItem] = []
    summary = ConcernSummary()

    for row in rows:
        priority = row.get("priority") or "for_your_awareness"

        # Build evidence list
        raw_evidence = row.get("evidence") or []
        if isinstance(raw_evidence, str):
            try:
                raw_evidence = json.loads(raw_evidence)
            except Exception:
                raw_evidence = []
        evidence_items = [
            EvidenceItem(
                entity=e.get("entity", "") if isinstance(e, dict) else str(e),
                source=e.get("source", "") if isinstance(e, dict) else "",
                date=e.get("date", "") if isinstance(e, dict) else "",
            )
            for e in (raw_evidence if isinstance(raw_evidence, list) else [])
        ]

        # Build brand_names_used
        raw_brands = row.get("brand_names_used") or []
        if isinstance(raw_brands, str):
            try:
                raw_brands = json.loads(raw_brands)
            except Exception:
                raw_brands = []
        brand_items = [
            BrandNameUsed(
                brand=b.get("brand", "") if isinstance(b, dict) else "",
                generic=b.get("generic", "") if isinstance(b, dict) else "",
            )
            for b in (raw_brands if isinstance(raw_brands, list) else [])
        ]

        concerns.append(ConcernItem(
            concern_id=str(row["id"]),
            concern_type=row.get("concern_type") or "independent",
            priority=priority,
            title=row.get("title") or "",
            summary=row.get("summary") or "",
            what_was_found=row.get("what_was_found") or "",
            why_it_matters=row.get("why_it_matters") or "",
            what_to_do=row.get("what_to_do") or "",
            evidence=evidence_items,
            source_documents=row.get("source_documents") or [],
            is_partial_match=bool(row.get("is_partial_match")),
            partial_match_group_id=str(row["partial_match_group_id"]) if row.get("partial_match_group_id") else None,
            brand_names_used=brand_items,
            display_order=row.get("display_order") or 0,
        ))

        # Tally summary counts
        if priority == "critical_concern":
            summary.critical_concern += 1
        elif priority == "high_priority":
            summary.high_priority += 1
        elif priority == "moderate":
            summary.moderate += 1
        else:
            summary.for_your_awareness += 1

    summary.total = len(concerns)

    # Load action summary (Phase 6.6)
    action_summary_row = (
        db.table("patient_action_summaries").select("do_now, follow_up, ongoing_monitoring")
        .eq("patient_id", patient_id)
        .eq("is_current", True)
        .limit(1)
        .execute()
    ).data

    action_summary = None
    if action_summary_row:
        raw = action_summary_row[0]

        def _parse_items(data) -> list[ActionItem]:
            if not data:
                return []
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    return []
            return [
                ActionItem(
                    action=item.get("action", "") if isinstance(item, dict) else str(item),
                    reason=item.get("reason") if isinstance(item, dict) else None,
                    source=item.get("source") if isinstance(item, dict) else None,
                )
                for item in (data if isinstance(data, list) else [])
            ]

        action_summary = ActionSummary(
            do_now=_parse_items(raw.get("do_now")),
            follow_up=_parse_items(raw.get("follow_up")),
            ongoing_monitoring=_parse_items(raw.get("ongoing_monitoring")),
        )

    return FindingsResponse(
        status="ready",
        concerns=concerns,
        concern_summary=summary,
        raw_flags_count=raw_flags_count,
        action_summary=action_summary,
        # Legacy fields so old polling code doesn't break
        total_flags=raw_flags_count,
        critical_count=summary.critical_concern,
        high_count=summary.high_priority,
    )


@router.post("/rerun_analysis/{patient_id}")
async def rerun_analysis(
    patient_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Clears previous analysis output and re-runs the analysis pipeline
    using already-uploaded documents. Safe to call if findings are missing,
    incomplete, or the pipeline previously crashed.
    """
    logger.info(f"Re-run analysis requested for patient {patient_id}")

    # Verify patient exists
    patient = db.table("patients").select("id, onboarding_status").eq("id", patient_id).execute()
    if not patient.data:
        raise HTTPException(status_code=404, detail="Patient not found")

    current_status = patient.data[0]["onboarding_status"]
    # Block re-run if still mid-extraction (documents not yet processed)
    if current_status in ("pending", "processing"):
        raise HTTPException(
            status_code=400,
            detail="Documents are still being extracted. Wait for medication verification before re-running analysis."
        )

    # Clear previous analysis output
    db.table("caregiver_concerns").delete().eq("patient_id", patient_id).execute()
    db.table("patient_action_summaries").delete().eq("patient_id", patient_id).execute()
    db.table("open_flags").delete().eq("patient_id", patient_id).execute()

    # Reset status so polling screen shows correctly
    db.table("patients").update({"onboarding_status": "analysis_running"}).eq("id", patient_id).execute()

    # Re-queue analysis pipeline
    background_tasks.add_task(run_analysis_pipeline, patient_id=patient_id, db=db)
    logger.info(f"Analysis pipeline re-queued for patient {patient_id}")

    return {"status": "analysis_running", "patient_id": patient_id}


@router.post("/confirm/{patient_id}", response_model=ConfirmResponse)
async def confirm_onboarding(
    patient_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Screen 6: guardian reviewed findings → mark onboarding complete."""
    logger.info(f"Onboarding confirmed for patient {patient_id}")

    checks = {
        "has_conditions": bool(db.table("diagnoses").select("id", count="exact").eq("patient_id", patient_id).execute().count),
        "has_medications": bool(db.table("medications").select("id", count="exact").eq("patient_id", patient_id).eq("confirmed_by_guardian", True).execute().count),
        "has_allergies": bool(db.table("allergies").select("id", count="exact").eq("patient_id", patient_id).execute().count),
        "has_doctors": bool(db.table("doctors").select("id", count="exact").eq("patient_id", patient_id).execute().count),
        "has_documents": bool(db.table("documents").select("id", count="exact").eq("patient_id", patient_id).execute().count),
        "has_summary": bool(db.table("patient_summaries").select("id", count="exact").eq("patient_id", patient_id).eq("is_current", True).execute().count),
    }
    score = int((sum(checks.values()) / len(checks)) * 100)

    flags_count = (
        db.table("open_flags").select("id", count="exact")
        .eq("patient_id", patient_id).eq("status", "open").execute()
    ).count or 0

    db.table("patients").update({
        "onboarding_status": "complete",
        "onboarding_completed_at": datetime.now(timezone.utc).isoformat(),
        "completeness_score": score,
    }).eq("id", patient_id).execute()

    logger.info(f"Onboarding complete — patient {patient_id}, score: {score}%")
    return ConfirmResponse(
        status="complete",
        completeness_score=score,
        patient_id=patient_id,
        flags_saved=flags_count,
    )
