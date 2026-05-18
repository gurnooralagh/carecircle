"""
L3 — Baseline load + entity comparison.
Loads patient baseline BEFORE any new writes, saves snapshot to longitudinal_runs.
Compares newly extracted medications against baseline, creates medication_state_transitions.
"""
import json
import re
import logging
from datetime import datetime, timezone
from supabase import Client

logger = logging.getLogger("carecircle.longitudinal")


def load_and_save_baseline(db: Client, patient_id: str, run_id: str) -> dict:
    """Load full patient state from DB and save snapshot. Must be called BEFORE any new entity writes."""
    meds = (db.table("medications").select("*")
            .eq("patient_id", patient_id).eq("is_deleted", False).execute()).data
    labs = (db.table("lab_results").select("*")
            .eq("patient_id", patient_id).order("report_date", desc=True).execute()).data
    diagnoses = (db.table("diagnoses").select("*").eq("patient_id", patient_id).execute()).data
    directives = (db.table("clinical_directives").select("*")
                  .eq("patient_id", patient_id).eq("is_active", True).execute()).data
    monitoring = (db.table("monitoring_instructions").select("*")
                  .eq("patient_id", patient_id).execute()).data
    findings = (db.table("clinical_findings").select("*")
                .eq("patient_id", patient_id)
                .in_("status", ["open", "monitoring", "recurring"]).execute()).data

    baseline = {
        "medications": meds,
        "lab_results": labs,
        "diagnoses": diagnoses,
        "directives": directives,
        "monitoring": monitoring,
        "prior_findings": findings,
    }
    try:
        db.table("longitudinal_runs").update({
            "baseline_patient_state": json.dumps(baseline, default=str)
        }).eq("id", run_id).execute()
    except Exception as e:
        logger.warning(f"L3: could not save baseline snapshot: {e}")

    logger.info(
        f"L3 baseline saved — {len(meds)} meds, {len(labs)} labs, "
        f"{len(diagnoses)} diagnoses, {len(findings)} prior findings"
    )
    return baseline


def compare_entities(
    db: Client,
    patient_id: str,
    run_id: str,
    upload_event_id: str,
    baseline: dict,
) -> dict:
    """
    Compare newly extracted entities against baseline.
    Creates medication_state_transitions records.
    Updates longitudinal_runs with delta counts.
    Returns delta counts dict.
    """
    # Find documents tagged as post_onboarding for this upload event
    new_docs = (db.table("documents").select("id,document_type,original_filename")
                .eq("patient_id", patient_id)
                .eq("upload_context", "post_onboarding").execute()).data

    if not new_docs:
        logger.warning("L3: no post_onboarding documents found for comparison")
        return {"new_medications": 0, "changed_medications": 0,
                "new_lab_results": 0, "new_diagnoses": 0, "new_directives": 0}

    new_doc_ids = [d["id"] for d in new_docs]

    delta = {"new_medications": 0, "changed_medications": 0,
             "new_lab_results": 0, "new_diagnoses": 0, "new_directives": 0}

    # Build baseline medication lookup by generic + brand
    baseline_by_generic: dict[str, dict] = {}
    baseline_by_brand: dict[str, dict] = {}
    for m in baseline["medications"]:
        g = (m.get("drug_name_generic") or "").lower().strip()
        b = (m.get("drug_name_brand") or "").lower().strip()
        if g:
            baseline_by_generic[g] = m
        if b:
            baseline_by_brand[b] = m

    # New medications from these docs
    new_meds = (db.table("medications").select("*")
                .eq("patient_id", patient_id)
                .in_("source_document_id", new_doc_ids).execute()).data

    for nm in new_meds:
        ng = (nm.get("drug_name_generic") or "").lower().strip()
        nb = (nm.get("drug_name_brand") or "").lower().strip()
        prior = baseline_by_generic.get(ng) or baseline_by_brand.get(nb)

        if prior is None:
            _create_transition(db, patient_id, run_id, upload_event_id, nm, "added", None)
            delta["new_medications"] += 1
        else:
            tt = _detect_transition(prior, nm)
            _create_transition(db, patient_id, run_id, upload_event_id, nm, tt, prior)
            if tt != "continued":
                delta["changed_medications"] += 1

    # Count other entity types
    new_labs = (db.table("lab_results").select("id")
                .eq("patient_id", patient_id)
                .in_("source_document_id", new_doc_ids).execute()).data
    delta["new_lab_results"] = len(new_labs)

    new_diags = (db.table("diagnoses").select("id")
                 .eq("patient_id", patient_id)
                 .in_("source_document_id", new_doc_ids).execute()).data
    delta["new_diagnoses"] = len(new_diags)

    new_dirs = (db.table("clinical_directives").select("id")
                .eq("patient_id", patient_id)
                .in_("source_document_id", new_doc_ids).execute()).data
    delta["new_directives"] = len(new_dirs)

    try:
        db.table("longitudinal_runs").update(delta).eq("id", run_id).execute()
    except Exception as e:
        logger.warning(f"L3: could not update run delta counts: {e}")

    logger.info(f"L3 entity comparison complete — delta: {delta}")
    return delta


def _detect_transition(prior: dict, new: dict) -> str:
    prior_dose = _extract_dose_mg(prior)
    new_dose = _extract_dose_mg(new)
    if prior_dose is not None and new_dose is not None and abs(prior_dose - new_dose) > 0.01:
        return "dose_changed"

    prior_freq = (prior.get("frequency") or "").lower().strip()
    new_freq = (new.get("frequency") or "").lower().strip()
    if prior_freq and new_freq and prior_freq != new_freq:
        return "frequency_changed"

    prior_status = (prior.get("status") or "active").lower()
    new_status = (new.get("status") or "active").lower()
    if prior_status != new_status:
        return "status_changed"

    return "continued"


def _extract_dose_mg(med: dict) -> float | None:
    if med.get("dose_mg"):
        try:
            return float(med["dose_mg"])
        except (ValueError, TypeError):
            pass
    dose_text = med.get("dose_text") or med.get("dosage") or ""
    m = re.search(r"(\d+\.?\d*)\s*mg", str(dose_text), re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _create_transition(
    db: Client,
    patient_id: str,
    run_id: str,
    upload_event_id: str,
    new_med: dict,
    transition_type: str,
    prior_med: dict | None,
) -> None:
    try:
        db.table("medication_state_transitions").insert({
            "patient_id": patient_id,
            "run_id": run_id,
            "upload_event_id": upload_event_id,
            "medication_id": new_med.get("id"),
            "drug_name_brand": new_med.get("drug_name_brand"),
            "drug_name_generic": new_med.get("drug_name_generic"),
            "transition_type": transition_type,
            "prior_dose_mg": _extract_dose_mg(prior_med) if prior_med else None,
            "new_dose_mg": _extract_dose_mg(new_med),
            "prior_frequency": prior_med.get("frequency") if prior_med else None,
            "new_frequency": new_med.get("frequency"),
            "source_document": new_med.get("source_document_id"),
            "guardian_confirmed": False,
        }).execute()
    except Exception as e:
        logger.warning(
            f"L3: could not save transition for {new_med.get('drug_name_brand')}: {e}"
        )
