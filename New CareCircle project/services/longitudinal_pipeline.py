"""
Longitudinal pipeline orchestrator.
log_event()             — structured logging to both Python logger and longitudinal_pipeline_logs.
run_pre_gate_pipeline() — L1→L3, ends with processing_status='reconciling'.
run_post_gate_pipeline()— L5→L10, ends with processing_status='ready'.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from supabase import Client

from services import storage, ocr, pdf_extractor, llm
from services.deduplicator import (
    deduplicate_medications,
    deduplicate_conditions,
    deduplicate_allergies,
)
from services.longitudinal_comparison import load_and_save_baseline, compare_entities
from services.longitudinal_classification import classify_findings, generate_nudge_cards
from services.longitudinal_orchestration import run_longitudinal_orchestration

logger = logging.getLogger("carecircle.longitudinal")

OCR_CONFIDENCE_THRESHOLD = 0.40
OCR_PENALTY_THRESHOLD = 0.65


# ── Structured event logger ───────────────────────────────────────────────────

def log_event(
    db: Client,
    run_id: str | None,
    upload_event_id: str | None,
    phase: str,
    event: str,
    detail: dict | None = None,
    level: str = "INFO",
) -> None:
    msg = f"[{phase}] {event}"
    if detail:
        msg += f" — {json.dumps(detail, default=str)}"
    if level == "ERROR":
        logger.error(msg)
    elif level == "WARNING":
        logger.warning(msg)
    else:
        logger.info(msg)
    try:
        db.table("longitudinal_pipeline_logs").insert({
            "run_id": run_id,
            "upload_event_id": upload_event_id,
            "phase": phase,
            "event": event,
            "level": level,
            "detail": detail or {},
        }).execute()
    except Exception as e:
        logger.warning(f"Could not write pipeline log: {e}")


# ── Pre-gate pipeline: L1 → L3 ───────────────────────────────────────────────

async def run_pre_gate_pipeline(
    patient_id: str,
    upload_event_id: str,
    db: Client,
) -> None:
    """L1→L3: extract, normalize, compare. Sets status='reconciling' on success."""
    run_id = None
    try:
        # Create longitudinal_run record
        run_result = db.table("longitudinal_runs").insert({
            "patient_id": patient_id,
            "upload_event_id": upload_event_id,
            "status": "success",
        }).execute()
        if not run_result.data:
            _set_upload_status(db, upload_event_id, "failed", error="Could not create longitudinal_run")
            return
        run_id = run_result.data[0]["id"]

        # Link run to upload event
        db.table("document_upload_events").update({
            "longitudinal_run_id": run_id
        }).eq("id", upload_event_id).execute()

        # ── L1: Document extraction ────────────────────────────────────────────
        log_event(db, run_id, upload_event_id, "L1", "extraction_started")
        _set_upload_status(db, upload_event_id, "extracting")

        docs = (db.table("documents").select("*")
                .eq("patient_id", patient_id)
                .eq("upload_context", "post_onboarding")
                .eq("extraction_status", "pending")
                .eq("is_deleted", False).execute()).data

        if not docs:
            log_event(db, run_id, upload_event_id, "L1", "no_documents_found",
                      level="ERROR")
            _set_upload_status(db, upload_event_id, "failed", error="No pending post-onboarding documents found")
            db.table("longitudinal_runs").update({"status": "failed"}).eq("id", run_id).execute()
            return

        succeeded, failed_count = 0, 0
        for doc in docs:
            ok = await _process_document_longitudinal(doc, patient_id, db)
            if ok:
                succeeded += 1
            else:
                failed_count += 1

        log_event(db, run_id, upload_event_id, "L1", "extraction_complete",
                  {"succeeded": succeeded, "failed": failed_count})

        if succeeded == 0:
            _set_upload_status(db, upload_event_id, "failed",
                               error=f"All {failed_count} documents failed extraction")
            db.table("longitudinal_runs").update({"status": "failed"}).eq("id", run_id).execute()
            return

        # ── L2: Normalize + deduplicate ────────────────────────────────────────
        log_event(db, run_id, upload_event_id, "L2", "normalization_started")
        try:
            from services.extraction_pipeline import _batch_normalize_medications
            await _batch_normalize_medications(patient_id, db)
        except Exception as e:
            log_event(db, run_id, upload_event_id, "L2", "normalization_warning",
                      {"error": str(e)}, level="WARNING")

        try:
            await deduplicate_medications(db, patient_id)
            await deduplicate_conditions(db, patient_id)
            await deduplicate_allergies(db, patient_id)
        except Exception as e:
            log_event(db, run_id, upload_event_id, "L2", "dedup_warning",
                      {"error": str(e)}, level="WARNING")
        log_event(db, run_id, upload_event_id, "L2", "normalization_complete")

        # ── L3: Baseline snapshot + entity comparison ──────────────────────────
        log_event(db, run_id, upload_event_id, "L3", "comparison_started")
        try:
            baseline = load_and_save_baseline(db, patient_id, run_id)
        except Exception as e:
            log_event(db, run_id, upload_event_id, "L3", "baseline_load_failed",
                      {"error": str(e)}, level="ERROR")
            _set_upload_status(db, upload_event_id, "failed",
                               error=f"Baseline load failed: {e}")
            db.table("longitudinal_runs").update({"status": "failed"}).eq("id", run_id).execute()
            return

        try:
            compare_entities(db, patient_id, run_id, upload_event_id, baseline)
        except Exception as e:
            log_event(db, run_id, upload_event_id, "L3", "comparison_partial_failure",
                      {"error": str(e)}, level="WARNING")

        log_event(db, run_id, upload_event_id, "L3", "comparison_complete")
        _set_upload_status(db, upload_event_id, "reconciling")
        db.table("patients").update({"longitudinal_status": "processing"}).eq("id", patient_id).execute()

    except Exception as e:
        log_event(db, run_id, upload_event_id, "L1-L3", "pipeline_error",
                  {"error": str(e)}, level="ERROR")
        _set_upload_status(db, upload_event_id, "failed", error=str(e))
        if run_id:
            db.table("longitudinal_runs").update({"status": "failed"}).eq("id", run_id).execute()


# ── Post-gate pipeline: L5 → L10 ─────────────────────────────────────────────

async def run_post_gate_pipeline(
    patient_id: str,
    upload_event_id: str,
    db: Client,
) -> None:
    """L5→L10: reasoning, classification, orchestration, action summary, state update."""
    ev_row = (db.table("document_upload_events").select("longitudinal_run_id")
              .eq("id", upload_event_id).limit(1).execute()).data
    run_id = ev_row[0]["longitudinal_run_id"] if ev_row else None

    try:
        _set_upload_status(db, upload_event_id, "reasoning")

        # ── L5: Reasoning ──────────────────────────────────────────────────────
        log_event(db, run_id, upload_event_id, "L5", "reasoning_started")
        prior_findings = (db.table("clinical_findings").select("*")
                          .eq("patient_id", patient_id)
                          .in_("status", ["open", "monitoring", "recurring"]).execute()).data

        patient_state = _build_longitudinal_patient_state(db, patient_id, upload_event_id, run_id)
        # Strip prior_findings before passing to reasoning — the LLM would suppress
        # already-known findings. Classification (L6) handles new vs recurring separately.
        reasoning_state = {k: v for k, v in patient_state.items() if k != "prior_findings"}
        new_finding_ids = await _run_longitudinal_reasoning(db, patient_id, reasoning_state, run_id)
        log_event(db, run_id, upload_event_id, "L5", "reasoning_complete",
                  {"new_findings": len(new_finding_ids)})

        # ── L6: Classification ─────────────────────────────────────────────────
        log_event(db, run_id, upload_event_id, "L6", "classification_started")
        unsuppressed_ids, suppressed_ids = classify_findings(
            db, patient_id, run_id, new_finding_ids, prior_findings
        )
        log_event(db, run_id, upload_event_id, "L6", "classification_complete",
                  {"unsuppressed": len(unsuppressed_ids), "suppressed": len(suppressed_ids)})

        # ── L7: Nudge generation ───────────────────────────────────────────────
        log_event(db, run_id, upload_event_id, "L7", "nudge_started")
        nudge_cards = generate_nudge_cards(
            db, patient_id, run_id, upload_event_id, suppressed_ids
        )
        log_event(db, run_id, upload_event_id, "L7", "nudge_complete",
                  {"nudge_cards": len(nudge_cards)})

        # ── L8: Orchestration ──────────────────────────────────────────────────
        log_event(db, run_id, upload_event_id, "L8", "orchestration_started")
        _set_upload_status(db, upload_event_id, "orchestrating")

        medication_transitions = []
        if run_id:
            medication_transitions = (db.table("medication_state_transitions").select("*")
                                      .eq("run_id", run_id)
                                      .eq("guardian_confirmed", True).execute()).data

        await run_longitudinal_orchestration(
            db, patient_id, run_id, upload_event_id,
            unsuppressed_ids, nudge_cards, medication_transitions,
        )
        log_event(db, run_id, upload_event_id, "L8", "orchestration_complete")

        # ── L9: Action summary ────────────────────────────────────────────────
        log_event(db, run_id, upload_event_id, "L9", "action_summary_started")
        try:
            await _run_action_summary_longitudinal(db, patient_id, run_id)
            log_event(db, run_id, upload_event_id, "L9", "action_summary_complete")
        except Exception as e:
            log_event(db, run_id, upload_event_id, "L9", "action_summary_failed",
                      {"error": str(e)}, level="WARNING")

        # ── L10: State update (retry 3×) ──────────────────────────────────────
        log_event(db, run_id, upload_event_id, "L10", "state_update_started")
        await _run_state_update_with_retry(db, patient_id, run_id, upload_event_id)

        _set_upload_status(db, upload_event_id, "ready")
        if run_id:
            db.table("longitudinal_runs").update({"status": "success"}).eq("id", run_id).execute()
        log_event(db, run_id, upload_event_id, "L10", "pipeline_complete")

    except Exception as e:
        log_event(db, run_id, upload_event_id, "L5-L10", "pipeline_error",
                  {"error": str(e)}, level="ERROR")
        _set_upload_status(db, upload_event_id, "failed", error=str(e))
        if run_id:
            db.table("longitudinal_runs").update({"status": "failed"}).eq("id", run_id).execute()
        db.table("patients").update({"longitudinal_status": "failed"}).eq("id", patient_id).execute()


# ── L5 helpers ────────────────────────────────────────────────────────────────

def _build_longitudinal_patient_state(
    db: Client,
    patient_id: str,
    upload_event_id: str,
    run_id: str | None,
) -> dict:
    """Build enriched patient state for L5 reasoning. Includes transition_type on meds."""
    patient_rows = (db.table("patients").select("*").eq("id", patient_id).execute()).data
    patient_row = patient_rows[0] if patient_rows else {}

    meds = (db.table("medications").select("*")
            .eq("patient_id", patient_id).eq("is_deleted", False).execute()).data

    # Attach transition_type from this run
    transitions: dict[str, str] = {}
    if run_id:
        trans_rows = (db.table("medication_state_transitions").select("medication_id,transition_type")
                      .eq("run_id", run_id).execute()).data
        for t in trans_rows:
            if t.get("medication_id"):
                transitions[t["medication_id"]] = t.get("transition_type", "continued")

    enriched_meds = [{**m, "transition_type": transitions.get(m["id"], "continued")} for m in meds]

    labs = (db.table("lab_results").select("*")
            .eq("patient_id", patient_id).order("report_date", desc=True).limit(30).execute()).data
    diagnoses = (db.table("diagnoses").select("*").eq("patient_id", patient_id).execute()).data
    directives = (db.table("clinical_directives").select("*")
                  .eq("patient_id", patient_id).eq("is_active", True).execute()).data
    monitoring = (db.table("monitoring_instructions").select("*")
                  .eq("patient_id", patient_id).execute()).data
    allergies = (db.table("allergies").select("*").eq("patient_id", patient_id).execute()).data
    doctors = (db.table("doctors").select("*").eq("patient_id", patient_id).execute()).data

    # Prior findings with full detail (clinical_evidence + related_entities + times_seen)
    prior_findings = (db.table("clinical_findings").select("*")
                      .eq("patient_id", patient_id)
                      .in_("status", ["open", "monitoring", "recurring"]).execute()).data

    brand_map: dict[str, str] = {}
    for m in meds:
        g = (m.get("drug_name_generic") or "").lower()
        b = m.get("drug_name_brand") or ""
        if g and b:
            brand_map[g] = b

    return {
        "patient": {
            "id": patient_id,
            "name": patient_row.get("full_name", ""),
            "date_of_birth": str(patient_row.get("date_of_birth") or ""),
            "gender": patient_row.get("gender"),
            "city": patient_row.get("city"),
            "post_onboarding_upload_count": patient_row.get("post_onboarding_upload_count", 0),
        },
        "medications": enriched_meds,
        "lab_results": labs,
        "diagnoses": diagnoses,
        "clinical_directives": directives,
        "monitoring_instructions": monitoring,
        "allergies": allergies,
        "doctors": doctors,
        "prior_findings": prior_findings,
        "brand_map": brand_map,
        "context": {
            "pipeline": "longitudinal",
            "upload_event_id": upload_event_id,
            "run_id": run_id,
        },
    }


async def _run_longitudinal_reasoning(
    db: Client,
    patient_id: str,
    patient_state: dict,
    run_id: str | None,
) -> list[str]:
    """Call llm.run_reasoning, apply quality gates, save to clinical_findings. Returns saved IDs."""
    try:
        result = await llm.run_reasoning(patient_state)
    except Exception as e:
        logger.warning(f"L5 reasoning LLM failed: {e}")
        return []

    findings = result.get("findings") or result.get("items") or []
    if not isinstance(findings, list):
        logger.warning(f"L5: unexpected reasoning output: {type(findings)}")
        return []

    saved_ids: list[str] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for f in findings:
        # Quality gates: confidence > 0.05, non-empty clinical_evidence
        if float(f.get("confidence") or 0) < 0.05:
            continue
        if not f.get("clinical_evidence"):
            continue

        try:
            row = db.table("clinical_findings").insert({
                "patient_id": patient_id,
                "finding_type": f.get("finding_type", "unknown"),
                "dimension": f.get("dimension"),
                "severity": f.get("severity", "informational"),
                "title": (f.get("title") or "")[:200],
                "clinical_evidence": json.dumps(f.get("clinical_evidence") or []),
                "source_documents": None,
                "related_entities": json.dumps(f.get("related_entities") or {}),
                "is_patient_specific": True,
                "patient_context": f.get("patient_specific_reasoning"),
                "confidence": f.get("confidence"),
                "status": "open",
                "last_seen_run_id": run_id,
                "last_seen_at": now_iso,
                "times_seen": 1,
            }).execute()
            if row.data:
                saved_ids.append(row.data[0]["id"])
        except Exception as e:
            logger.warning(f"L5: could not save finding: {e}")

    return saved_ids


# ── L9 ────────────────────────────────────────────────────────────────────────

async def _run_action_summary_longitudinal(
    db: Client,
    patient_id: str,
    run_id: str | None,
) -> None:
    """L9: Build deterministic action summary from longitudinal concern categories."""
    concerns = []
    if run_id:
        concerns = (db.table("longitudinal_caregiver_concerns").select("*")
                    .eq("run_id", run_id).execute()).data

    do_now: list[dict] = []
    follow_up: list[dict] = []
    ongoing: list[dict] = []
    resolved_since: list[dict] = []

    for c in concerns:
        cat = c.get("concern_category", "new")
        pri = c.get("priority", "for_your_awareness")
        item = {"action": c.get("what_to_do") or "", "source": c.get("title") or ""}

        if cat in ("new", "escalated") and pri in ("critical_concern", "high_priority"):
            do_now.append(item)
        elif cat == "resolved":
            resolved_since.append(item)
        elif pri == "moderate":
            follow_up.append(item)
        else:
            ongoing.append(item)

    # Mark previous summary not current
    db.table("patient_action_summaries").update({"is_current": False}).eq("patient_id", patient_id).execute()
    db.table("patient_action_summaries").insert({
        "patient_id": patient_id,
        "do_now": do_now,
        "follow_up": follow_up,
        "ongoing_monitoring": ongoing,
        "resolved_since_last_upload": resolved_since,
        "is_current": True,
    }).execute()


# ── L10 ───────────────────────────────────────────────────────────────────────

async def _run_state_update_with_retry(
    db: Client,
    patient_id: str,
    run_id: str | None,
    upload_event_id: str,
    max_retries: int = 3,
) -> None:
    """L10: Apply confirmed medication transitions, increment upload count. Retries 3× with backoff."""
    for attempt in range(max_retries):
        try:
            # Apply guardian-confirmed medication transitions
            if run_id:
                transitions = (db.table("medication_state_transitions").select("*")
                               .eq("run_id", run_id)
                               .eq("guardian_confirmed", True).execute()).data
                for t in transitions:
                    med_id = t.get("medication_id")
                    if not med_id:
                        continue
                    updates: dict = {}
                    tt = t.get("transition_type", "continued")
                    g_action = t.get("guardian_action", "still_taking")

                    if tt == "dose_changed" and t.get("new_dose_mg"):
                        updates["dose_mg"] = t["new_dose_mg"]
                    if tt == "frequency_changed" and t.get("new_frequency"):
                        updates["frequency"] = t["new_frequency"]
                    if g_action in ("stopped", "no_stopped"):
                        updates["status"] = "stopped"
                        updates["is_current"] = False

                    if updates:
                        db.table("medications").update(updates).eq("id", med_id).execute()

            # Increment upload count (read → write, avoids needing a Supabase RPC)
            current = (db.table("patients").select("post_onboarding_upload_count")
                       .eq("id", patient_id).execute()).data
            count = (current[0].get("post_onboarding_upload_count") or 0) + 1 if current else 1

            db.table("patients").update({
                "post_onboarding_upload_count": count,
                "last_document_upload_at": datetime.now(timezone.utc).isoformat(),
                "longitudinal_status": "idle",
            }).eq("id", patient_id).execute()
            return

        except Exception as e:
            logger.warning(f"L10 attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.critical(f"L10 all retries exhausted for patient {patient_id}: {e}")
                db.table("patients").update({"longitudinal_status": "failed"}).eq("id", patient_id).execute()
                raise


# ── L1: Document processing ───────────────────────────────────────────────────

async def _process_document_longitudinal(doc: dict, patient_id: str, db: Client) -> bool:
    """Extract text + entities from one document. Saves to document_extractions + layer-3 tables."""
    doc_id = doc["id"]
    mime = doc.get("mime_type") or doc.get("file_type") or "application/octet-stream"
    logger.info(f"L1 processing: {doc['original_filename']} ({mime})")

    db.table("documents").update({"extraction_status": "processing"}).eq("id", doc_id).execute()

    try:
        file_bytes = db.storage.from_("documents").download(doc["storage_path"])

        if mime.startswith("image/"):
            raw_text, confidence = await ocr.extract_text_from_image(file_bytes, mime)
        else:
            raw_text = pdf_extractor.extract_text_from_pdf(file_bytes)
            confidence = 1.0
            if len(raw_text.strip()) < 50:
                page_images = pdf_extractor.render_pdf_to_images(file_bytes)
                page_texts, confidences = [], []
                for img_bytes in page_images:
                    pt, pc = await ocr.extract_text_from_image(img_bytes, "image/png")
                    page_texts.append(pt)
                    confidences.append(pc)
                raw_text = "\n".join(page_texts)
                confidence = sum(confidences) / len(confidences) if confidences else 0.0

        if confidence < OCR_CONFIDENCE_THRESHOLD:
            db.table("documents").update({"extraction_status": "needs_review"}).eq("id", doc_id).execute()
            logger.warning(f"L1: OCR confidence {confidence:.2f} too low for {doc['original_filename']}")
            return False

        penalty = 0.85 if confidence < OCR_PENALTY_THRESHOLD else 1.0
        doc_type = doc["document_type"]

        extracted: dict = {}
        try:
            if doc_type == "prescription":
                extracted = await llm.extract_prescription(raw_text)
            elif doc_type == "lab_report":
                extracted = await llm.extract_lab_report(raw_text)
            elif doc_type == "discharge_summary":
                extracted = await llm.extract_discharge_summary(raw_text)
        except Exception as e:
            logger.error(f"L1 LLM extraction failed for {doc_id}: {e}")
            db.table("documents").update({"extraction_status": "failed"}).eq("id", doc_id).execute()
            return False

        # Save raw extraction record
        ext_result = db.table("document_extractions").insert({
            "document_id": doc_id,
            "patient_id": patient_id,
            "raw_ocr_text": raw_text,
            "ocr_confidence": round(confidence, 3),
            "extracted_data": extracted,
            "extraction_model": "google/gemini-2.5-flash",
            "overall_confidence": round(confidence * penalty, 3),
        }).execute()
        extraction_id = ext_result.data[0]["id"] if ext_result.data else None

        # Reuse the onboarding merge logic
        from services.extraction_pipeline import _merge_to_layer3
        await _merge_to_layer3(
            doc_id, extraction_id, patient_id, doc_type, extracted,
            confidence * penalty, db,
        )

        db.table("documents").update({"extraction_status": "completed"}).eq("id", doc_id).execute()
        return True

    except Exception as e:
        logger.error(f"L1 document failed {doc_id}: {e}", exc_info=True)
        db.table("documents").update({"extraction_status": "failed"}).eq("id", doc_id).execute()
        return False


# ── Utility ───────────────────────────────────────────────────────────────────

def _set_upload_status(
    db: Client,
    upload_event_id: str,
    status: str,
    error: str | None = None,
) -> None:
    updates: dict = {"processing_status": status}
    if error:
        updates["error_message"] = error[:500]
    try:
        db.table("document_upload_events").update(updates).eq("id", upload_event_id).execute()
    except Exception as e:
        logger.warning(f"Could not set upload status to {status}: {e}")
