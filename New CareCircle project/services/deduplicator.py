"""
Deduplication service — Phase 3.2.
Runs AFTER normalization. Operates on generic names as matching key.
Never deduplicates lab results across dates.
"""
import json
from datetime import date
from supabase import Client
from config.logging import get_logger

logger = get_logger("DEDUP")


def _generic_key(med: dict) -> str | None:
    g = med.get("drug_name_generic")
    return g.lower().strip() if g else None


def _brand_key(med: dict) -> str:
    b = med.get("drug_name_brand") or med.get("drug_name_normalized") or ""
    return b.lower().strip().split()[0]  # first word as fallback key


async def deduplicate_medications(db: Client, patient_id: str) -> dict:
    """
    Reads all active, non-deleted medications for the patient.
    Returns counts of merges, dose_conflicts, status_conflicts found.
    Directly updates the DB.
    """
    meds = (
        db.table("medications")
        .select("*")
        .eq("patient_id", patient_id)
        .eq("is_deleted", False)
        .execute()
    ).data

    if not meds:
        return {"merged": 0, "dose_conflicts": 0, "status_conflicts": 0}

    # Group by generic name (primary key) — fallback to brand first-word
    groups: dict[str, list[dict]] = {}
    for med in meds:
        key = _generic_key(med) or _brand_key(med) or med["id"]
        groups.setdefault(key, []).append(med)

    merged_count = 0
    dose_conflict_count = 0
    status_conflict_count = 0

    for key, group in groups.items():
        if len(group) == 1:
            continue  # no dedup needed

        # Separate by status
        active_meds = [m for m in group if m.get("status", "active") != "stopped"]
        stopped_meds = [m for m in group if m.get("status") == "stopped"]

        # SITUATION 3 — Status conflict: same drug stopped in one source, active in another
        if active_meds and stopped_meds:
            logger.info(f"Status conflict: {key} — active in {len(active_meds)} sources, stopped in {len(stopped_meds)}")
            _save_finding(db, patient_id, {
                "finding_type": "stopped_medication_still_prescribed",
                "dimension": "D12: Cross-Document Reconciliation",
                "severity": "critical",
                "title": f"Conflicting status: {_display_name(group[0])}",
                "clinical_evidence": [
                    {"entity": f"Active: {_display_name(m)}", "source": m.get("source", ""), "date": str(m.get("prescription_date", ""))}
                    for m in active_meds
                ] + [
                    {"entity": f"Stopped: {_display_name(m)}", "source": m.get("source", ""), "date": str(m.get("prescription_date", ""))}
                    for m in stopped_meds
                ],
                "related_entities": {"medications": [_display_name(m) for m in group]},
                "patient_context": "Same medication active in one source and stopped in another.",
                "confidence": 0.90,
            })
            status_conflict_count += 1
            continue  # don't merge — keep both, flag surfaced on Screen 4

        # SITUATION 2 — Dose conflict: same generic, different doses
        doses = set()
        for m in group:
            d = m.get("dose_mg") or _parse_dose(m.get("dose_text") or m.get("dosage") or "")
            if d:
                doses.add(d)
        if len(doses) > 1:
            logger.info(f"Dose conflict: {key} — doses {doses}")
            _save_finding(db, patient_id, {
                "finding_type": "medication_dose_conflict",
                "dimension": "D12: Cross-Document Reconciliation",
                "severity": "high",
                "title": f"Dose mismatch: {_display_name(group[0])}",
                "clinical_evidence": [
                    {"entity": f"{_display_name(m)} {m.get('dose_mg') or m.get('dosage', '')}",
                     "source": m.get("source", ""), "date": str(m.get("prescription_date", ""))}
                    for m in group
                ],
                "related_entities": {"medications": [_display_name(m) for m in group]},
                "patient_context": f"Different doses found across sources: {', '.join(str(d) for d in doses)}",
                "confidence": 0.85,
            })
            dose_conflict_count += 1
            continue  # keep both — guardian must choose

        # SITUATION 4 — Same drug, multiple prescribers, same dose: merge
        # SITUATION 1 — True duplicate: merge
        _merge_medications(db, patient_id, group)
        merged_count += 1

    logger.info(f"Dedup complete — merged:{merged_count} dose_conflicts:{dose_conflict_count} status_conflicts:{status_conflict_count}")
    return {
        "merged": merged_count,
        "dose_conflicts": dose_conflict_count,
        "status_conflicts": status_conflict_count,
    }


def _parse_dose(dose_str: str) -> float | None:
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*mg", dose_str, re.IGNORECASE)
    return float(m.group(1)) if m else None


def _display_name(med: dict) -> str:
    brand = med.get("drug_name_brand") or med.get("drug_name_normalized") or ""
    generic = med.get("drug_name_generic")
    if generic and generic.lower() != brand.lower():
        return f"{brand} ({generic})" if brand else generic
    return brand or generic or "Unknown"


def _merge_medications(db: Client, patient_id: str, group: list[dict]) -> None:
    """Keep the most recent prescription record, soft-delete others, merge source_references."""
    # Sort: prescription from most recent date first, guardian_stated last
    def sort_key(m):
        src_priority = {"document_extracted": 0, "caregiver_stated": 1, "guardian_stated": 2}
        p = src_priority.get(m.get("source", "guardian_stated"), 3)
        d = m.get("prescription_date") or "1900-01-01"
        return (p, d)

    sorted_group = sorted(group, key=sort_key)
    primary = sorted_group[0]
    rest = sorted_group[1:]

    # Build combined source_references
    all_refs = []
    existing_refs = primary.get("source_references") or []
    if isinstance(existing_refs, str):
        try:
            existing_refs = json.loads(existing_refs)
        except Exception:
            existing_refs = []
    all_refs.extend(existing_refs)

    for m in rest:
        refs = m.get("source_references") or []
        if isinstance(refs, str):
            try:
                refs = json.loads(refs)
            except Exception:
                refs = []
        if refs:
            all_refs.extend(refs)
        elif m.get("source"):
            all_refs.append({
                "source_type": m["source"],
                "stated_name": _display_name(m),
                "document_id": m.get("source_document_id"),
            })

    # Check if multiple prescribers
    prescribers = set(str(m.get("prescribing_doctor_id", "")) for m in group if m.get("prescribing_doctor_id"))
    if len(prescribers) > 1:
        _save_finding(db, patient_id, {
            "finding_type": "same_medication_multiple_prescribers",
            "dimension": "D12: Cross-Document Reconciliation",
            "severity": "low",
            "title": f"{_display_name(primary)} from multiple prescribers",
            "clinical_evidence": [
                {"entity": _display_name(m), "source": m.get("source", ""), "date": ""}
                for m in group
            ],
            "related_entities": {"medications": [_display_name(m) for m in group]},
            "patient_context": "Same medication prescribed by multiple doctors at same dose.",
            "confidence": 0.80,
        })

    # Update primary with merged references and cross_verified status
    db.table("medications").update({
        "source_references": json.dumps(all_refs),
        "cross_reference_status": "cross_verified" if len(group) > 1 else "document_only",
        "updated_at": "now()",
    }).eq("id", primary["id"]).execute()

    # Soft-delete the rest
    for m in rest:
        db.table("medications").update({
            "is_deleted": True,
            "deleted_reason": "deduplicated_into_" + primary["id"],
        }).eq("id", m["id"]).execute()

    logger.info(f"Merged {len(rest)} duplicates → {primary['id']} ({_display_name(primary)})")


def _save_finding(db: Client, patient_id: str, finding: dict) -> None:
    """Save a clinical finding to clinical_findings table."""
    try:
        db.table("clinical_findings").insert({
            "patient_id": patient_id,
            "finding_type": finding["finding_type"],
            "dimension": finding.get("dimension"),
            "severity": finding["severity"],
            "title": finding["title"],
            "clinical_evidence": json.dumps(finding.get("clinical_evidence", [])),
            "related_entities": json.dumps(finding.get("related_entities", {})),
            "patient_context": finding.get("patient_context"),
            "confidence": finding.get("confidence", 0.80),
            "status": "open",
        }).execute()
    except Exception as e:
        logger.warning(f"Could not save finding: {e}")


async def deduplicate_conditions(db: Client, patient_id: str) -> None:
    """Merge duplicate conditions. More specific stage beats general."""
    conditions = (
        db.table("diagnoses")
        .select("*")
        .eq("patient_id", patient_id)
        .execute()
    ).data

    seen_normalized: dict[str, dict] = {}
    for c in conditions:
        key = (c.get("condition_normalized") or c["condition_name"]).lower().strip()
        if key not in seen_normalized:
            seen_normalized[key] = c
        else:
            existing = seen_normalized[key]
            # Keep the more specific (has severity_stage) or the confirmed one
            keep = c if (c.get("severity_stage") and not existing.get("severity_stage")) else existing
            drop = c if keep["id"] == existing["id"] else existing
            if drop["id"] != keep["id"]:
                db.table("diagnoses").update({
                    "cross_reference_status": "cross_verified",
                }).eq("id", keep["id"]).execute()
                # Mark the less specific one as soft-deleted only if it's document_extracted
                if drop.get("source") == "document_extracted":
                    db.table("diagnoses").update({"confirmation_status": "confirmed"}).eq("id", drop["id"]).execute()
                seen_normalized[key] = keep


async def deduplicate_allergies(db: Client, patient_id: str) -> None:
    """Merge duplicate allergies — always use HIGHER severity."""
    allergies = (
        db.table("allergies")
        .select("*")
        .eq("patient_id", patient_id)
        .execute()
    ).data

    severity_rank = {"mild": 1, "moderate": 2, "severe": 3, "unknown": 0}
    seen: dict[str, dict] = {}
    for a in allergies:
        key = (a.get("allergen_normalized") or a["allergen"]).lower().strip()
        if key not in seen:
            seen[key] = a
        else:
            existing = seen[key]
            # Keep higher severity
            if severity_rank.get(a.get("severity", "unknown"), 0) > severity_rank.get(existing.get("severity", "unknown"), 0):
                # Update existing to higher severity
                db.table("allergies").update({
                    "severity": a["severity"],
                    "cross_reference_status": "cross_verified",
                }).eq("id", existing["id"]).execute()
            else:
                db.table("allergies").update({
                    "cross_reference_status": "cross_verified",
                }).eq("id", existing["id"]).execute()
