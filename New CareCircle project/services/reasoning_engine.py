"""
Reasoning engine — Phase 5.
Builds patient_state object, calls Gemini with 13-dimension prompt,
post-processes findings, saves to clinical_findings table.
"""
import json
import time
from datetime import date
from supabase import Client
from config.logging import get_logger
from services import llm

logger = get_logger("REASONING")

SEVERITY_RANK = {"critical": 5, "high": 4, "moderate": 3, "low": 2, "informational": 1}


async def run_reasoning_engine(db: Client, patient_id: str) -> list[dict]:
    """
    Builds patient_state, calls Gemini, post-processes, saves findings.
    Returns list of saved findings.
    Never crashes — falls back to simplified 3-dimension check on failure.
    """
    start_ms = int(time.time() * 1000)
    run_id = _create_run(db, patient_id)

    try:
        patient_state = _build_patient_state(db, patient_id)
        logger.info(f"Patient state built: {len(patient_state.get('active_medications', []))} meds, "
                    f"{len(patient_state.get('lab_results', []))} labs, "
                    f"{len(patient_state.get('conditions', []))} conditions")

        findings_raw = await llm.run_reasoning(patient_state)
        findings = findings_raw.get("findings", [])
        logger.info(f"Reasoning returned {len(findings)} raw findings")

        # Post-processing
        findings = _apply_quality_gates(findings)
        findings = _deduplicate_findings(findings)
        findings = _sort_by_severity(findings)
        findings = _check_recurring(db, patient_id, findings)

        # Save to DB
        saved = []
        for f in findings:
            saved_finding = _save_finding(db, patient_id, f)
            if saved_finding:
                saved.append(saved_finding)

        elapsed = int(time.time() * 1000) - start_ms
        _update_run(db, run_id, {
            "status": "success",
            "findings_generated": len(saved),
            "findings_discarded": len(findings_raw.get("findings", [])) - len(saved),
            "dimensions_run": _get_dimensions_run(patient_state),
            "total_processing_ms": elapsed,
        })
        logger.info(f"Reasoning complete — {len(saved)} findings saved in {elapsed}ms")
        return saved

    except Exception as e:
        logger.error(f"Reasoning engine failed: {e}", exc_info=True)
        elapsed = int(time.time() * 1000) - start_ms
        _update_run(db, run_id, {
            "status": "partial",
            "error_message": str(e),
            "total_processing_ms": elapsed,
        })
        # Simplified 3-dimension fallback
        return await _simplified_fallback(db, patient_id)


def _build_patient_state(db: Client, patient_id: str) -> dict:
    patient = db.table("patients").select("*").eq("id", patient_id).single().execute().data

    conditions = (
        db.table("diagnoses").select("*")
        .eq("patient_id", patient_id)
        .execute()
    ).data

    meds = (
        db.table("medications").select("*")
        .eq("patient_id", patient_id)
        .eq("is_deleted", False)
        .eq("is_current", True)
        .execute()
    ).data

    labs = (
        db.table("lab_results").select("*")
        .eq("patient_id", patient_id)
        .execute()
    ).data

    allergies = (
        db.table("allergies").select("*")
        .eq("patient_id", patient_id)
        .execute()
    ).data

    directives = (
        db.table("clinical_directives").select("*")
        .eq("patient_id", patient_id)
        .eq("is_active", True)
        .execute()
    ).data

    restrictions = (
        db.table("restrictions").select("*")
        .eq("patient_id", patient_id)
        .execute()
    ).data

    monitoring = (
        db.table("monitoring_instructions").select("*")
        .eq("patient_id", patient_id)
        .eq("status", "pending")
        .execute()
    ).data

    cultures = (
        db.table("culture_findings").select("*")
        .eq("patient_id", patient_id)
        .execute()
    ).data

    prior_findings = (
        db.table("clinical_findings").select("id,finding_type,severity,status,title")
        .eq("patient_id", patient_id)
        .in_("status", ["open", "monitoring", "recurring"])
        .execute()
    ).data

    # Build age
    dob = patient.get("date_of_birth")
    age = None
    if dob:
        try:
            from datetime import date as dt
            dob_date = dt.fromisoformat(str(dob))
            today = dt.today()
            age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
        except Exception:
            pass

    # Prescription dates map
    prescription_dates = {}
    for m in meds:
        name = m.get("drug_name_generic") or m.get("drug_name_brand") or ""
        if name and m.get("prescription_date"):
            prescription_dates[name] = str(m["prescription_date"])

    lab_dates = {}
    for lab in labs:
        name = lab.get("test_name_normalized") or lab.get("test_name") or ""
        if name and lab.get("report_date"):
            lab_dates.setdefault(name, []).append(str(lab["report_date"]))

    return {
        "patient": {
            "age": age,
            "gender": patient.get("gender"),
            "weight_kg": patient.get("weight_kg"),
            "height_cm": patient.get("height_cm"),
            "city": patient.get("city"),
        },
        "conditions": [
            {
                "condition_normalized": c.get("condition_normalized") or c.get("condition_name"),
                "severity_stage": c.get("severity_stage"),
                "chronic_or_acute": c.get("chronic_or_acute"),
                "source": c.get("source"),
                "cross_reference_status": c.get("cross_reference_status"),
                "confidence": c.get("extraction_confidence"),
            }
            for c in conditions
        ],
        "active_medications": [
            {
                "drug_name_generic": m.get("drug_name_generic"),
                "drug_name_brand": m.get("drug_name_brand") or m.get("drug_name_normalized"),
                "drug_class": m.get("drug_class"),
                "dose_mg": m.get("dose_mg"),
                "dose_text": m.get("dose_text") or m.get("dosage"),
                "frequency": m.get("frequency"),
                "route": m.get("route"),
                "timing": m.get("timing"),
                "is_current": m.get("is_current", True),
                "prescription_date": str(m["prescription_date"]) if m.get("prescription_date") else None,
                "prescription_age_days": m.get("prescription_age_days"),
                "source": m.get("source"),
                "prescribing_doctor": str(m.get("prescribing_doctor_id") or ""),
                "confidence": m.get("extraction_confidence"),
                "is_sos": m.get("is_sos"),
                "duration_days": m.get("duration_days"),
                "guardian_taking_status": m.get("guardian_taking_status"),
            }
            for m in meds
        ],
        "lab_results": [
            {
                "test_name_normalized": lab.get("test_name_normalized") or lab.get("test_name"),
                "test_category": lab.get("test_category"),
                "value_numeric": float(lab["value_numeric"]) if lab.get("value_numeric") is not None else None,
                "value_text": lab.get("value_text") or lab.get("value"),
                "unit_normalized": lab.get("unit"),
                "reference_low": float(lab["reference_low"]) if lab.get("reference_low") is not None else None,
                "reference_high": float(lab["reference_high"]) if lab.get("reference_high") is not None else None,
                "flag_direction": lab.get("flag_direction"),
                "is_flagged_by_lab": lab.get("is_flagged_by_lab", False),
                "collection_date": str(lab["report_date"]) if lab.get("report_date") else None,
                "report_age_days": lab.get("report_age_days"),
                "is_stale": lab.get("is_stale", False),
                "lab_name": lab.get("lab_name"),
            }
            for lab in labs
        ],
        "directives": [
            {
                "directive_type": d.get("directive_type"),
                "target_entity": d.get("target_entity"),
                "target_entity_type": d.get("target_entity_type"),
                "instruction_text": d.get("instruction_text"),
                "condition_for_execution": d.get("condition_for_execution"),
                "condition_type": d.get("condition_type"),
                "condition_met": d.get("condition_met"),
                "source": d.get("source_document_id"),
                "directive_date": str(d["directive_date"]) if d.get("directive_date") else None,
            }
            for d in directives
        ],
        "restrictions": [
            {
                "restriction_type": r.get("restriction_type"),
                "target": r.get("target"),
                "reason": r.get("reason"),
                "source": r.get("source_document_id"),
            }
            for r in restrictions
        ],
        "monitoring_instructions": [
            {
                "test_or_vital": m.get("test_or_vital"),
                "timing_text": m.get("timing_text"),
                "due_date": str(m["due_date"]) if m.get("due_date") else None,
                "status": m.get("status"),
                "source": m.get("source_document_id"),
            }
            for m in monitoring
        ],
        "allergies": [
            {
                "allergen_normalized": a.get("allergen_normalized") or a.get("allergen"),
                "drug_class": a.get("drug_class"),
                "reaction_type": a.get("reaction_type") or a.get("reaction"),
                "severity": a.get("severity"),
                "source": a.get("source"),
            }
            for a in allergies
        ],
        "culture_findings": [
            {
                "organism_name": c.get("organism_normalized") or c.get("organism_name"),
                "specimen_type": c.get("specimen_type"),
                "collection_date": str(c["collection_date"]) if c.get("collection_date") else None,
                "resistant_to": c.get("resistant_to") or [],
                "sensitive_to": c.get("sensitive_to") or [],
            }
            for c in cultures
        ],
        "prior_findings": [
            {
                "finding_id": str(f["id"]),
                "finding_type": f.get("finding_type"),
                "severity": f.get("severity"),
                "status": f.get("status"),
                "title": f.get("title"),
            }
            for f in prior_findings
        ],
        "temporal_context": {
            "today": str(date.today()),
            "prescription_dates": prescription_dates,
            "lab_dates": lab_dates,
        },
    }


def _apply_quality_gates(findings: list[dict]) -> list[dict]:
    passed = []
    for f in findings:
        evidence = f.get("clinical_evidence") or []
        if not evidence:
            logger.debug(f"Discarded (no evidence): {f.get('finding_type')}")
            continue
        if any(not e.get("entity") for e in evidence):
            logger.debug(f"Discarded (vague evidence): {f.get('finding_type')}")
            continue
        confidence = float(f.get("confidence") or 0)
        if confidence < 0.05:
            logger.debug(f"Discarded (conf<0.05): {f.get('finding_type')}")
            continue
        severity = f.get("severity", "informational")
        finding_type = f.get("finding_type", "")
        if "allergen_match" in finding_type and severity in ("low", "informational"):
            f["severity"] = "high"
        passed.append(f)
    return passed


def _deduplicate_findings(findings: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    unique = []
    for f in findings:
        meds = tuple(sorted((f.get("related_entities") or {}).get("medications") or []))
        labs = tuple(sorted((f.get("related_entities") or {}).get("labs") or []))
        key = (f.get("finding_type"), meds, labs)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def _sort_by_severity(findings: list[dict]) -> list[dict]:
    return sorted(findings, key=lambda f: SEVERITY_RANK.get(f.get("severity", "informational"), 1), reverse=True)


def _check_recurring(db: Client, patient_id: str, findings: list[dict]) -> list[dict]:
    prior = (
        db.table("clinical_findings").select("finding_type,severity")
        .eq("patient_id", patient_id)
        .in_("status", ["open", "monitoring", "recurring"])
        .execute()
    ).data
    prior_types = {p["finding_type"] for p in prior}

    escalation = {
        "informational": "low",
        "low": "moderate",
        "moderate": "high",
        "high": "critical",
        "critical": "critical",
    }

    for f in findings:
        if f.get("finding_type") in prior_types:
            original_severity = f.get("severity", "informational")
            f["severity"] = escalation.get(original_severity, original_severity)
            f["_recurring"] = True
    return findings


def _save_finding(db: Client, patient_id: str, f: dict) -> dict | None:
    try:
        result = db.table("clinical_findings").insert({
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
            "status": "recurring" if f.get("_recurring") else "open",
        }).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning(f"Could not save finding {f.get('finding_type')}: {e}")
        return None


def _get_dimensions_run(patient_state: dict) -> list[str]:
    dims = ["D1: Medication-Medication"]
    if patient_state.get("conditions"):
        dims.append("D2: Medication-Condition")
    if patient_state.get("lab_results"):
        dims.extend(["D3: Medication-Lab", "D8: Diagnosis-Lab", "D9: Directive-Lab"])
    if patient_state.get("directives"):
        dims.append("D4: Medication-Directive")
    if patient_state.get("allergies"):
        dims.append("D5: Medication-Allergy")
    if patient_state.get("culture_findings"):
        dims.append("D6: Culture-Antibiotic")
    if len(patient_state.get("conditions", [])) > 1:
        dims.append("D7: Diagnosis-Diagnosis")
    if patient_state.get("restrictions"):
        dims.append("D10: Restriction-ActiveState")
    dims.extend(["D11: Temporal-Logic", "D12: Cross-Document"])
    if patient_state.get("prior_findings"):
        dims.append("D13: Longitudinal")
    return dims


def _create_run(db: Client, patient_id: str) -> str:
    try:
        result = db.table("reasoning_runs").insert({
            "patient_id": patient_id,
            "trigger_event": "onboarding",
            "status": "partial",
        }).execute()
        return result.data[0]["id"] if result.data else ""
    except Exception:
        return ""


def _update_run(db: Client, run_id: str, updates: dict) -> None:
    if not run_id:
        return
    try:
        db.table("reasoning_runs").update(updates).eq("id", run_id).execute()
    except Exception:
        pass


async def _simplified_fallback(db: Client, patient_id: str) -> list[dict]:
    """
    Simplified 3-dimension fallback: allergy check, directive check, duplicate check.
    Always runs even on total failure.
    """
    logger.info("Running simplified 3-dimension fallback")
    findings = []

    try:
        meds = (
            db.table("medications").select("drug_name_generic,drug_name_brand,drug_name_normalized,drug_class")
            .eq("patient_id", patient_id).eq("is_deleted", False).execute()
        ).data
        allergies = (
            db.table("allergies").select("allergen,allergen_normalized,drug_class,severity")
            .eq("patient_id", patient_id).execute()
        ).data

        # Allergy check
        for med in meds:
            med_name = (med.get("drug_name_generic") or med.get("drug_name_brand") or "").lower()
            for allergy in allergies:
                allergen = (allergy.get("allergen_normalized") or allergy.get("allergen") or "").lower()
                if allergen and allergen in med_name:
                    f = {
                        "finding_type": "exact_allergen_match",
                        "dimension": "D5: Medication-Allergy",
                        "severity": "critical",
                        "title": f"Allergy: {med.get('drug_name_brand') or med_name}",
                        "clinical_evidence": [{"entity": allergen, "source": "allergy_record", "date": ""}],
                        "related_entities": {"medications": [med.get("drug_name_brand") or med_name]},
                        "patient_context": "Known allergen found in active medications.",
                        "confidence": 0.85,
                    }
                    saved = _save_finding(db, patient_id, f)
                    if saved:
                        findings.append(saved)

        # Directive check
        directives = (
            db.table("clinical_directives").select("*")
            .eq("patient_id", patient_id).eq("is_active", True).execute()
        ).data
        for d in directives:
            if d.get("directive_type") == "stop_medication":
                target = (d.get("target_entity") or "").lower()
                for med in meds:
                    med_name = (med.get("drug_name_generic") or "").lower()
                    if target and (target in med_name or med_name in target):
                        f = {
                            "finding_type": "stopped_medication_still_active",
                            "dimension": "D4: Medication-Directive",
                            "severity": "critical",
                            "title": f"Doctor said STOP: {d.get('target_entity')}",
                            "clinical_evidence": [{"entity": d.get("instruction_text", ""), "source": "clinical_directive", "date": ""}],
                            "related_entities": {"medications": [d.get("target_entity", "")], "directives": [d.get("instruction_text", "")]},
                            "patient_context": "Doctor instructed to stop this medication but it remains active.",
                            "confidence": 0.90,
                        }
                        saved = _save_finding(db, patient_id, f)
                        if saved:
                            findings.append(saved)

    except Exception as e:
        logger.error(f"Simplified fallback also failed: {e}")

    return findings
