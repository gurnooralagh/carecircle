"""
Extraction pipeline v3.0 — 9 phases.
Phase 2: Document OCR + full clinical entity extraction
Phase 3.1: Batch normalization (brand → generic)
Phase 3.2: Deduplication
Phase 3.3: Cross-reference verification
Phase 3.4: Set medication_verification_needed
Phases 5-8 run after guardian confirms medications (triggered from router).
"""
import asyncio
import json
from datetime import date, datetime, timezone
from supabase import Client
from config.logging import get_logger
from services import storage, ocr, pdf_extractor, llm
from services.resolver import resolve_drug_name
from services.deduplicator import (
    deduplicate_medications,
    deduplicate_conditions,
    deduplicate_allergies,
)
from services.reasoning_engine import run_reasoning_engine
from services.flag_generator import generate_flags_for_patient
from services.orchestrator import run_orchestration
from services.action_summarizer import run_action_summary

logger = get_logger("PIPELINE")
OCR_CONFIDENCE_THRESHOLD = 0.40  # below this: skip LLM extraction
OCR_PENALTY_THRESHOLD = 0.65      # below this: apply confidence penalty


async def run_extraction_pipeline(patient_id: str, db: Client) -> None:
    """Phases 2 → 3.4: background extraction + normalization + dedup → set medication_verification_needed."""
    logger.info(f"=== Phase 2-3 pipeline starting for patient {patient_id} ===")

    docs_result = (
        db.table("documents")
        .select("*")
        .eq("patient_id", patient_id)
        .eq("extraction_status", "pending")
        .eq("is_deleted", False)
        .execute()
    )
    documents = docs_result.data
    logger.info(f"Found {len(documents)} documents to process")

    succeeded = 0
    failed = 0
    for doc in documents:
        ok = await _process_document(doc, patient_id, db)
        if ok:
            succeeded += 1
        else:
            failed += 1

    # Phase 3.1 — Batch normalize all extracted medication names
    await _batch_normalize_medications(patient_id, db)

    # Phase 3.2 — Deduplicate
    await deduplicate_medications(db, patient_id)
    await deduplicate_conditions(db, patient_id)
    await deduplicate_allergies(db, patient_id)

    # Phase 3.3 — Cross-reference verification
    await _cross_reference_verification(patient_id, db)

    # Flag if multiple docs failed
    if failed >= 3:
        _create_flag(db, patient_id, "FOR_YOUR_AWARENESS",
                     f"{failed} of {len(documents)} documents had processing issues",
                     "Re-upload clearer versions or ask doctor to review all medications together.",
                     "processing_error")
    elif failed > 0:
        logger.warning(f"{failed} document(s) failed processing for patient {patient_id}")

    # Phase 3.4 — Set status
    db.table("patients").update({
        "onboarding_status": "medication_verification_needed"
    }).eq("id", patient_id).execute()
    logger.info(f"Pipeline phases 2-3 complete — status: medication_verification_needed")


async def run_analysis_pipeline(patient_id: str, db: Client) -> None:
    """Phases 5-8: reasoning engine + flag generation + orchestration + silent summary → findings_ready."""
    logger.info(f"=== Phases 5-8 analysis starting for patient {patient_id} ===")

    # Phase 5 — Reasoning engine
    findings = await run_reasoning_engine(db, patient_id)

    # Phase 6 — Flag generation
    flags_count = await generate_flags_for_patient(db, patient_id)

    # Phase 6.5 — Presentation orchestration (sets findings_ready on completion)
    concerns_count = await run_orchestration(db, patient_id)

    # Phase 6.6 — Intelligent action summary (silent, never blocks)
    await run_action_summary(db, patient_id)

    # Phase 7 — Silent patient summary
    await _generate_silent_summary(patient_id, db, findings)

    logger.info(f"Analysis complete — {len(findings)} findings, {flags_count} flags, {concerns_count} concerns")


async def _process_document(doc: dict, patient_id: str, db: Client) -> bool:
    doc_id = doc["id"]
    mime = doc.get("mime_type") or doc.get("file_type") or "application/octet-stream"
    logger.info(f"Processing: {doc['original_filename']} ({mime})")

    db.table("documents").update({"extraction_status": "processing"}).eq("id", doc_id).execute()

    try:
        file_bytes = db.storage.from_("documents").download(doc["storage_path"])

        # OCR / text extraction
        if mime.startswith("image/"):
            raw_text, confidence = await ocr.extract_text_from_image(file_bytes, mime)
            logger.info(f"OCR confidence: {confidence:.2f}")
        else:
            raw_text = pdf_extractor.extract_text_from_pdf(file_bytes)
            confidence = 1.0

            if len(raw_text.strip()) < 50:
                # Scanned PDF — render to images and OCR
                logger.info("PDF text too short — rendering pages for OCR")
                page_images = pdf_extractor.render_pdf_to_images(file_bytes)
                page_texts = []
                confidences = []
                for i, img_bytes in enumerate(page_images):
                    page_text, page_conf = await ocr.extract_text_from_image(img_bytes, "image/png")
                    page_texts.append(page_text)
                    confidences.append(page_conf)
                raw_text = "\n".join(page_texts)
                confidence = sum(confidences) / len(confidences) if confidences else 0.0
                logger.info(f"PDF OCR: {len(page_images)} pages, avg conf: {confidence:.2f}")

        # Apply confidence penalties
        extraction_confidence_multiplier = 1.0
        if confidence < OCR_CONFIDENCE_THRESHOLD:
            logger.warning(f"OCR confidence {confidence:.2f} below threshold — skipping LLM extraction")
            _save_raw_extraction(db, doc_id, patient_id, raw_text, confidence, None)
            db.table("documents").update({"extraction_status": "needs_review"}).eq("id", doc_id).execute()
            _create_flag(db, patient_id, "FOR_YOUR_AWARENESS",
                         f"Photo quality too low to read: {doc['original_filename']}",
                         "Please retake the photo in better lighting or upload a clearer scan.",
                         "ocr_low_confidence", doc_id)
            return False

        if confidence < OCR_PENALTY_THRESHOLD:
            extraction_confidence_multiplier = 0.85
            logger.info(f"OCR conf {confidence:.2f} — applying 0.85 penalty to all fields")

        # LLM extraction
        doc_type = doc["document_type"]
        extracted = {}
        try:
            if doc_type == "prescription":
                extracted = await llm.extract_prescription(raw_text)
            elif doc_type == "lab_report":
                extracted = await llm.extract_lab_report(raw_text)
            elif doc_type == "discharge_summary":
                extracted = await llm.extract_discharge_summary(raw_text)
            else:
                extracted = {}
            logger.info(f"LLM extraction complete for {doc_type}")
        except Exception as e:
            logger.error(f"LLM extraction failed for {doc_id}: {e}")
            _save_raw_extraction(db, doc_id, patient_id, raw_text, confidence, None)
            db.table("documents").update({"extraction_status": "needs_review"}).eq("id", doc_id).execute()
            _create_flag(db, patient_id, "VERIFY_WITH_DOCTOR",
                         f"Could not read document: {doc['original_filename']}",
                         "The document could not be analyzed automatically. Please review with your doctor.",
                         "llm_extraction_failed", doc_id)
            return False

        # Apply hallucination check to medications
        if doc_type == "prescription":
            extracted = _check_medication_hallucinations(extracted, raw_text, extraction_confidence_multiplier)

        # Save extraction
        extraction_id = _save_raw_extraction(db, doc_id, patient_id, raw_text, confidence, extracted)

        # Save to Layer 3 tables
        await _merge_to_layer3(doc_id, extraction_id, patient_id, doc_type, extracted,
                               confidence * extraction_confidence_multiplier, db)

        db.table("documents").update({"extraction_status": "completed"}).eq("id", doc_id).execute()
        return True

    except Exception as exc:
        logger.error(f"Pipeline failed for document {doc_id}: {exc}", exc_info=True)
        db.table("documents").update({"extraction_status": "failed", "extraction_error": str(exc)}).eq("id", doc_id).execute()
        return False


def _save_raw_extraction(db: Client, doc_id: str, patient_id: str,
                          raw_text: str, confidence: float, extracted: dict | None) -> str:
    result = db.table("document_extractions").insert({
        "document_id": doc_id,
        "patient_id": patient_id,
        "raw_ocr_text": raw_text,
        "ocr_confidence": round(confidence, 3),
        "extracted_data": extracted,
        "extraction_model": "google/gemini-2.5-flash",
        "overall_confidence": round(confidence, 3) if extracted is None else (extracted.get("overall_confidence") or confidence),
    }).execute()
    return result.data[0]["id"] if result.data else None


def _check_medication_hallucinations(extracted: dict, raw_text: str, multiplier: float) -> dict:
    """Flag medications whose names don't appear in raw OCR text."""
    raw_lower = raw_text.lower()
    meds = extracted.get("medications") or []
    validated = []
    for med in meds:
        brand = (med.get("drug_name_brand") or "").lower()
        if brand and len(brand) >= 3:
            # Check if first 4 chars appear in raw text (handles OCR variation)
            prefix = brand[:4]
            if prefix not in raw_lower:
                med["confidence"] = 0.20
                med["_possibly_hallucinated"] = True
                logger.warning(f"Possible hallucination: {brand!r} not found in OCR text")
        validated.append(med)
    extracted["medications"] = validated
    return extracted


async def _merge_to_layer3(
    doc_id: str, extraction_id: str | None, patient_id: str,
    doc_type: str, extracted: dict, ocr_confidence: float, db: Client
) -> None:
    """Save all extracted entities to Layer 3 tables."""

    if doc_type == "prescription":
        # Medications
        for med in extracted.get("medications") or []:
            if not med.get("drug_name_brand") and not med.get("drug_name_generic"):
                continue
            conf = float(med.get("confidence") or 0.7) * ocr_confidence
            db.table("medications").insert({
                "patient_id": patient_id,
                "source_document_id": doc_id,
                "source_extraction_id": extraction_id,
                "drug_name_original_ocr": med.get("drug_name_brand") or med.get("drug_name_generic"),
                "drug_name_brand": med.get("drug_name_brand") or med.get("drug_name_generic"),
                "drug_name_generic": med.get("drug_name_generic"),
                "drug_name_normalized": med.get("drug_name_brand") or med.get("drug_name_generic") or "unknown",
                "drug_class": med.get("drug_class"),
                "dose_text": med.get("dose_text"),
                "dosage": med.get("dose_text"),  # backward compat
                "frequency": _normalize_frequency(med.get("frequency")),
                "timing": med.get("timing"),
                "duration_days": med.get("duration_days"),
                "duration_text": med.get("duration_text"),
                "is_prn": med.get("is_prn", False),
                "is_sos": med.get("is_sos", False),
                "source": "document_extracted",
                "confirmed_by_guardian": False,
                "extraction_confidence": round(conf, 3),
                "status": "active",
                "is_current": True,
            }).execute()
            logger.info(f"Layer 3: medication saved — {med.get('drug_name_brand')}")

        # Diagnoses from prescription
        for diag in extracted.get("diagnoses_mentioned") or []:
            if not diag.get("condition_name"):
                continue
            # Don't overwrite confirmed guardian-stated conditions
            existing = db.table("diagnoses").select("id,source").eq("patient_id", patient_id).eq("condition_name", diag["condition_name"]).execute()
            if not existing.data:
                db.table("diagnoses").insert({
                    "patient_id": patient_id,
                    "condition_name": diag["condition_name"],
                    "source": "document_extracted",
                    "source_document_id": doc_id,
                    "confirmation_status": "unconfirmed",
                    "chronic_or_acute": diag.get("chronic_or_acute"),
                    "severity_stage": diag.get("severity_stage"),
                }).execute()

        # Clinical directives
        for directive in extracted.get("clinical_directives") or []:
            if not directive.get("target_entity") or not directive.get("instruction_text"):
                continue
            if extraction_id:
                db.table("clinical_directives").insert({
                    "patient_id": patient_id,
                    "source_document_id": doc_id,
                    "source_extraction_id": extraction_id,
                    "directive_type": directive.get("directive_type", "other"),
                    "target_entity": directive["target_entity"],
                    "target_entity_type": directive.get("target_entity_type") if directive.get("target_entity_type") in ("medication","drug_class","food","activity","lab_test","other") else "other",
                    "instruction_text": directive["instruction_text"],
                    "condition_for_execution": directive.get("condition_for_execution"),
                    "condition_type": directive.get("condition_type"),
                    "extraction_confidence": round(float(directive.get("confidence") or 0.7) * ocr_confidence, 3),
                    "directive_date": extracted.get("prescription_date"),
                }).execute()

        # Restrictions
        for restriction in extracted.get("restrictions") or []:
            if not restriction.get("target") or not restriction.get("instruction_text"):
                continue
            db.table("restrictions").insert({
                "patient_id": patient_id,
                "source_document_id": doc_id,
                "restriction_type": restriction.get("restriction_type", "other"),
                "target": restriction["target"],
                "reason": restriction.get("reason"),
                "instruction_text": restriction["instruction_text"],
                "extraction_confidence": round(float(restriction.get("confidence") or 0.7) * ocr_confidence, 3),
            }).execute()

        # Monitoring instructions
        for monitor in extracted.get("monitoring_instructions") or []:
            if not monitor.get("test_or_vital"):
                continue
            db.table("monitoring_instructions").insert({
                "patient_id": patient_id,
                "source_document_id": doc_id,
                "test_or_vital": monitor["test_or_vital"],
                "monitoring_category": monitor.get("monitoring_category", "lab_test"),
                "frequency_text": monitor.get("frequency_text"),
                "timing_text": monitor.get("timing_text"),
                "urgency": monitor.get("urgency", "routine"),
                "ordered_by": extracted.get("prescribing_doctor", {}).get("name"),
                "extraction_confidence": round(float(monitor.get("confidence") or 0.7) * ocr_confidence, 3),
            }).execute()

        # Allergies from prescription
        for allergy in extracted.get("allergies_mentioned") or []:
            if not allergy.get("allergen"):
                continue
            existing = db.table("allergies").select("id").eq("patient_id", patient_id).eq("allergen", allergy["allergen"]).execute()
            if not existing.data:
                db.table("allergies").insert({
                    "patient_id": patient_id,
                    "allergen": allergy["allergen"],
                    "reaction_type": allergy.get("reaction_type"),
                    "severity": allergy.get("severity", "unknown"),
                    "source": "document_extracted",
                    "source_document_id": doc_id,
                }).execute()

        # Doctor from prescription
        doctor_data = extracted.get("prescribing_doctor") or {}
        if doctor_data.get("name"):
            db.table("doctors").insert({
                "patient_id": patient_id,
                "name": doctor_data["name"],
                "full_name": doctor_data["name"],
                "specialty": doctor_data.get("specialty"),
                "hospital_name": doctor_data.get("hospital"),
                "hospital": doctor_data.get("hospital"),
                "phone": doctor_data.get("phone"),
                "source": "document_extracted",
                "source_document_id": doc_id,
            }).execute()

    elif doc_type == "lab_report":
        report_date = extracted.get("report_date")
        lab_name = extracted.get("lab_name")

        for test in extracted.get("tests") or []:
            if not test.get("test_name"):
                continue
            value_numeric = None
            try:
                v = test.get("value_numeric")
                if v is not None:
                    value_numeric = float(v)
                elif test.get("value_text"):
                    import re
                    m = re.search(r"(\d+\.?\d*)", str(test["value_text"]))
                    if m:
                        value_numeric = float(m.group(1))
            except (ValueError, TypeError):
                pass

            lab_result = db.table("lab_results").insert({
                "patient_id": patient_id,
                "source_document_id": doc_id,
                "source_extraction_id": extraction_id,
                "test_name": test["test_name"],
                "test_name_normalized": test.get("test_name_normalized") or test["test_name"],
                "test_category": test.get("test_category"),
                "value_numeric": value_numeric,
                "value_text": test.get("value_text") or test.get("value"),
                "unit": test.get("unit"),
                "reference_low": test.get("reference_low"),
                "reference_high": test.get("reference_high"),
                "is_flagged_by_lab": test.get("is_flagged_by_lab", False),
                "flag_direction": test.get("flag_direction"),
                "report_date": report_date,
                "lab_name": lab_name,
                "fasting_status": extracted.get("patient_fasting_status"),
                "extraction_confidence": round(float(test.get("confidence") or 0.7) * ocr_confidence, 3),
            }).execute()

            if test.get("is_flagged_by_lab"):
                logger.info(f"Flagged lab result: {test['test_name']} = {test.get('value_text')}")

        # Culture findings from lab report
        for culture in extracted.get("culture_findings") or []:
            if not culture.get("organism") and not culture.get("organism_normalized"):
                continue
            db.table("culture_findings").insert({
                "patient_id": patient_id,
                "source_document_id": doc_id,
                "organism_name": culture.get("organism"),
                "organism_normalized": culture.get("organism_normalized"),
                "specimen_type": culture.get("specimen_type"),
                "collection_date": culture.get("collection_date"),
                "resistant_to": culture.get("resistant_to") or [],
                "sensitive_to": culture.get("sensitive_to") or [],
                "intermediate_to": culture.get("intermediate_to") or [],
                "extraction_confidence": round(0.7 * ocr_confidence, 3),
            }).execute()

    elif doc_type == "discharge_summary":
        # Medications at discharge
        for med in extracted.get("medications_at_discharge") or []:
            if not med.get("drug_name_brand"):
                continue
            db.table("medications").insert({
                "patient_id": patient_id,
                "source_document_id": doc_id,
                "source_extraction_id": extraction_id,
                "drug_name_original_ocr": med.get("drug_name_brand"),
                "drug_name_brand": med.get("drug_name_brand"),
                "drug_name_normalized": med.get("drug_name_brand") or med.get("drug_name_generic") or "unknown",
                "dose_text": med.get("dose_text"),
                "dosage": med.get("dose_text"),  # backward compat
                "frequency": _normalize_frequency(med.get("frequency")),
                "source": "document_extracted",
                "confirmed_by_guardian": False,
                "extraction_confidence": round(0.85 * ocr_confidence, 3),
                "status": "active",
                "is_current": True,
            }).execute()

        # Stopped medications from discharge
        for med in extracted.get("medications_stopped") or []:
            if not med.get("drug_name_brand"):
                continue
            db.table("medications").insert({
                "patient_id": patient_id,
                "source_document_id": doc_id,
                "source_extraction_id": extraction_id,
                "drug_name_original_ocr": med.get("drug_name_brand"),
                "drug_name_brand": med.get("drug_name_brand"),
                "drug_name_normalized": med.get("drug_name_brand"),
                "source": "document_extracted",
                "confirmed_by_guardian": False,
                "extraction_confidence": round(0.85 * ocr_confidence, 3),
                "status": "stopped",
                "is_current": False,
            }).execute()

        # Diagnoses from discharge
        for diag_name in [extracted.get("primary_diagnosis")] + (extracted.get("secondary_diagnoses") or []):
            if not diag_name:
                continue
            existing = db.table("diagnoses").select("id").eq("patient_id", patient_id).eq("condition_name", diag_name).execute()
            if not existing.data:
                db.table("diagnoses").insert({
                    "patient_id": patient_id,
                    "condition_name": diag_name,
                    "source": "document_extracted",
                    "source_document_id": doc_id,
                    "confirmation_status": "unconfirmed",
                }).execute()

        # Discharge directives
        for directive in extracted.get("discharge_directives") or []:
            if not directive.get("target_entity") or not directive.get("instruction_text"):
                continue
            if extraction_id:
                db.table("clinical_directives").insert({
                    "patient_id": patient_id,
                    "source_document_id": doc_id,
                    "source_extraction_id": extraction_id,
                    "directive_type": directive.get("directive_type", "other"),
                    "target_entity": directive["target_entity"],
                    "target_entity_type": directive.get("target_entity_type") if directive.get("target_entity_type") in ("medication","drug_class","food","activity","lab_test","other") else "other",
                    "instruction_text": directive["instruction_text"],
                    "condition_for_execution": directive.get("condition_for_execution"),
                    "condition_type": directive.get("condition_type"),
                    "extraction_confidence": round(float(directive.get("confidence") or 0.85) * ocr_confidence, 3),
                    "directive_date": extracted.get("discharge_date"),
                }).execute()

        # Discharge restrictions
        for restriction in extracted.get("discharge_restrictions") or []:
            if not restriction.get("target") or not restriction.get("instruction_text"):
                continue
            db.table("restrictions").insert({
                "patient_id": patient_id,
                "source_document_id": doc_id,
                "restriction_type": restriction.get("restriction_type", "other"),
                "target": restriction["target"],
                "reason": restriction.get("reason"),
                "instruction_text": restriction["instruction_text"],
                "extraction_confidence": round(float(restriction.get("confidence") or 0.85) * ocr_confidence, 3),
            }).execute()

        # Monitoring instructions from discharge
        for monitor in extracted.get("monitoring_required") or []:
            if not monitor.get("test_or_vital"):
                continue
            db.table("monitoring_instructions").insert({
                "patient_id": patient_id,
                "source_document_id": doc_id,
                "test_or_vital": monitor["test_or_vital"],
                "monitoring_category": monitor.get("monitoring_category", "lab_test"),
                "frequency_text": monitor.get("frequency_text"),
                "timing_text": monitor.get("timing_text"),
                "urgency": monitor.get("urgency", "routine"),
                "ordered_by": extracted.get("treating_doctor"),
                "extraction_confidence": round(float(monitor.get("confidence") or 0.85) * ocr_confidence, 3),
            }).execute()

        # Culture findings from discharge
        for culture in extracted.get("culture_findings") or []:
            if not culture.get("organism") and not culture.get("organism_normalized"):
                continue
            db.table("culture_findings").insert({
                "patient_id": patient_id,
                "source_document_id": doc_id,
                "organism_name": culture.get("organism"),
                "organism_normalized": culture.get("organism_normalized"),
                "specimen_type": culture.get("specimen_type"),
                "collection_date": culture.get("collection_date"),
                "resistant_to": culture.get("resistant_to") or [],
                "sensitive_to": culture.get("sensitive_to") or [],
                "intermediate_to": culture.get("intermediate_to") or [],
                "extraction_confidence": round(0.85 * ocr_confidence, 3),
            }).execute()

        # Treating doctor
        if extracted.get("treating_doctor"):
            db.table("doctors").insert({
                "patient_id": patient_id,
                "name": extracted["treating_doctor"],
                "full_name": extracted["treating_doctor"],
                "hospital_name": extracted.get("hospital_name"),
                "hospital": extracted.get("hospital_name"),
                "source": "document_extracted",
                "source_document_id": doc_id,
            }).execute()


async def _batch_normalize_medications(patient_id: str, db: Client) -> None:
    """Phase 3.1 — resolve all document-extracted medication brand names to generics."""
    meds = (
        db.table("medications")
        .select("id,drug_name_brand,drug_name_normalized,normalization_source,source")
        .eq("patient_id", patient_id)
        .is_("normalization_source", "null")
        .execute()
    ).data

    logger.info(f"Phase 3.1: normalizing {len(meds)} medications")
    for med in meds:
        brand = med.get("drug_name_brand") or med.get("drug_name_normalized") or ""
        if not brand:
            continue

        if med.get("source") == "guardian_stated":
            from services.resolver import guardian_stated_result, _extract_drug_name_from_instruction
            clean_brand = _extract_drug_name_from_instruction(brand)
            try:
                result = await resolve_drug_name(db, clean_brand)
                if result["normalization_source"] == "failed":
                    result = guardian_stated_result(clean_brand)
                else:
                    result["drug_name_brand"] = brand  # preserve original guardian text as brand
            except Exception:
                result = guardian_stated_result(clean_brand)
        else:
            try:
                result = await resolve_drug_name(db, brand)
            except Exception as e:
                logger.warning(f"Normalization failed for {brand}: {e}")
                result = {"drug_name_brand": brand, "drug_name_generic": None,
                          "drug_class": "unknown", "normalization_confidence": 0.0,
                          "normalization_source": "failed", "formulation": None}

        db.table("medications").update({
            "drug_name_brand": result["drug_name_brand"],
            "drug_name_generic": result["drug_name_generic"],
            "drug_class": result["drug_class"],
            "normalization_confidence": result["normalization_confidence"],
            "normalization_source": result["normalization_source"],
            "formulation": result["formulation"],
        }).eq("id", med["id"]).execute()


async def _cross_reference_verification(patient_id: str, db: Client) -> None:
    """Phase 3.3 — cross-reference high-risk entities."""

    # Check directives against active medication list
    directives = (
        db.table("clinical_directives").select("*")
        .eq("patient_id", patient_id)
        .eq("is_active", True)
        .execute()
    ).data

    meds = (
        db.table("medications").select("drug_name_generic,drug_name_brand,drug_class")
        .eq("patient_id", patient_id)
        .eq("is_deleted", False)
        .eq("is_current", True)
        .execute()
    ).data
    active_generics = {(m.get("drug_name_generic") or "").lower() for m in meds}

    for d in directives:
        target = (d.get("target_entity") or "").lower()
        if not target:
            continue
        target_in_active = any(target in g or g in target for g in active_generics if g)

        if d.get("directive_type") == "stop_medication" and target_in_active:
            db.table("clinical_directives").update({
                "cross_reference_status": "contradicted"
            }).eq("id", d["id"]).execute()
        elif target_in_active:
            db.table("clinical_directives").update({
                "cross_reference_status": "cross_verified"
            }).eq("id", d["id"]).execute()
        else:
            db.table("clinical_directives").update({
                "cross_reference_status": "unverifiable"
            }).eq("id", d["id"]).execute()


async def _generate_silent_summary(patient_id: str, db: Client, findings: list[dict]) -> None:
    """Phase 7 — generate clinical summary for system use. Never shown to guardian."""
    try:
        from services.reasoning_engine import _build_patient_state
        patient_state = _build_patient_state(db, patient_id)

        summary_result = await llm.generate_patient_summary(patient_state, findings)

        # Compute flag counts
        flag_counts = {"critical": 0, "high": 0, "moderate": 0, "low": 0, "informational": 0}
        for f in findings:
            sev = f.get("severity", "informational")
            if sev in flag_counts:
                flag_counts[sev] += 1

        # Mark old summaries non-current
        db.table("patient_summaries").update({"is_current": False}).eq("patient_id", patient_id).execute()

        db.table("patient_summaries").insert({
            "patient_id": patient_id,
            "summary_text": summary_result.get("summary_text", ""),
            "snapshot_data": summary_result.get("snapshot_data"),
            "open_flags_count": flag_counts,
            "is_current": True,
            "trigger_event": "onboarding",
        }).execute()
        logger.info(f"Silent summary saved for patient {patient_id}")
    except Exception as e:
        logger.warning(f"Summary generation failed: {e}")


def _normalize_frequency(freq: str | None) -> str | None:
    if not freq:
        return None
    freq_lower = freq.lower().strip()
    mapping = {
        "od": "once_daily", "qd": "once_daily", "once daily": "once_daily",
        "bd": "twice_daily", "bid": "twice_daily", "twice daily": "twice_daily",
        "tds": "three_times_daily", "tid": "three_times_daily",
        "qid": "three_times_daily",
        "qod": "alternate_days", "alternate days": "alternate_days",
        "sos": "as_needed", "prn": "as_needed", "as needed": "as_needed",
    }
    for k, v in mapping.items():
        if k in freq_lower:
            return v
    if freq_lower in ("once_daily", "twice_daily", "three_times_daily", "alternate_days", "as_needed", "sos", "other"):
        return freq_lower
    return "other"


def _create_flag(db: Client, patient_id: str, directive_type: str, title: str,
                  what_to_do: str, flag_type: str, doc_id: str | None = None) -> None:
    try:
        db.table("open_flags").insert({
            "patient_id": patient_id,
            "flag_type": directive_type,
            "directive_type": directive_type,
            "severity": "informational",
            "title": title,
            "what_was_found": title,
            "why_it_matters": "This may affect the completeness of the analysis.",
            "what_to_do": what_to_do,
            "status": "open",
        }).execute()
    except Exception as e:
        logger.warning(f"Could not create flag: {e}")
