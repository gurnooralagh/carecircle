from datetime import datetime, timezone, timedelta
from supabase import Client
from config.logging import get_logger
from services import llm
from services.flags import create_flag

logger = get_logger("DRUG_SAFETY")
CACHE_TTL_DAYS = 90


def _cache_fresh(cached_at_str: str) -> bool:
    cached_at = datetime.fromisoformat(cached_at_str.replace("Z", "+00:00"))
    return datetime.now(timezone.utc) - cached_at < timedelta(days=CACHE_TTL_DAYS)


def _drug_pair_key(a: str, b: str) -> tuple[str, str]:
    """Always return (min, max) alphabetically — Rule 10."""
    a_lower, b_lower = a.lower().strip(), b.lower().strip()
    return (a_lower, b_lower) if a_lower <= b_lower else (b_lower, a_lower)


async def run_drug_safety_checks(patient_id: str, db: Client) -> None:
    logger.info(f"=== Phase 4 drug safety starting for patient {patient_id} ===")

    meds_result = (
        db.table("medications").select("id,drug_name_normalized,dosage")
        .eq("patient_id", patient_id)
        .eq("confirmed_by_guardian", True)
        .eq("is_deleted", False)
        .execute()
    )
    meds = meds_result.data
    med_names = [m["drug_name_normalized"] for m in meds]

    allergies_result = db.table("allergies").select("allergen").eq("patient_id", patient_id).execute()
    allergies = [a["allergen"] for a in allergies_result.data]

    conditions_result = (
        db.table("diagnoses").select("condition_name")
        .eq("patient_id", patient_id)
        .eq("confirmation_status", "confirmed")
        .execute()
    )
    conditions = [c["condition_name"] for c in conditions_result.data]

    patient_result = db.table("patients").select("date_of_birth,gender").eq("id", patient_id).execute()
    patient = patient_result.data[0]
    dob = datetime.fromisoformat(str(patient["date_of_birth"]))
    age = int((datetime.now() - dob).days / 365.25)
    gender = patient.get("gender", "unknown")

    logger.info(f"Checking {len(med_names)} medications, {len(allergies)} allergies, {len(conditions)} conditions")

    all_findings = {"drug_drug": [], "drug_allergy": [], "drug_condition": []}

    # Check A: Drug-Drug Interactions (90-day cache, alphabetical pairs)
    if len(med_names) >= 2:
        for i in range(len(med_names)):
            for j in range(i + 1, len(med_names)):
                d1, d2 = _drug_pair_key(med_names[i], med_names[j])
                finding = await _check_drug_pair(d1, d2, patient_id, meds, db)
                if finding:
                    all_findings["drug_drug"].append(finding)

    # Check B: Drug-Allergy (no cache, single batch call)
    if med_names and allergies:
        result = await llm.run_drug_safety_check(med_names, allergies, [], age, gender)
        for conflict in result.get("allergy_conflicts", []):
            if float(conflict.get("confidence", 0)) >= 0.60:
                all_findings["drug_allergy"].append(conflict)
                _create_drug_flag(db, patient_id, "drug_allergy_conflict", conflict, meds)

    # Check C: Drug-Condition (90-day cache)
    for med_name in med_names:
        for condition in conditions:
            finding = await _check_drug_condition(med_name.lower(), condition.lower(), patient_id, meds, db)
            if finding:
                all_findings["drug_condition"].append(finding)

    db.table("drug_safety_checks").insert({
        "patient_id": patient_id,
        "check_type": "drug_drug",
        "medications_checked": med_names,
        "findings": all_findings,
    }).execute()

    db.table("patients").update({"onboarding_status": "drug_check_complete"}).eq("id", patient_id).execute()
    logger.info(f"Drug safety complete — {sum(len(v) for v in all_findings.values())} total findings")


async def _check_drug_pair(d1: str, d2: str, patient_id: str, meds: list, db: Client) -> dict | None:
    cache = (
        db.table("drug_interaction_cache")
        .select("*").eq("drug_1", d1).eq("drug_2", d2).execute()
    )
    if cache.data and _cache_fresh(cache.data[0]["cached_at"]):
        hit = cache.data[0]
        logger.info(f"Cache HIT: {d1} + {d2} → severity: {hit['severity']}")
        if float(hit.get("confidence", 0)) >= 0.60 and hit.get("severity", "none") != "none":
            _create_drug_flag(db, patient_id, "drug_interaction", hit, meds,
                              title_override=f"Drug interaction: {d1} + {d2}")
        return hit

    logger.info(f"Cache MISS: checking {d1} + {d2} via LLM")
    result = await llm.run_drug_safety_check([d1, d2], [], [], 60, "unknown")
    interactions = result.get("interactions", [])

    finding = interactions[0] if interactions else {
        "drug_1": d1, "drug_2": d2, "severity": "none",
        "confidence": 0.9, "description": "No significant interaction found", "recommendation": ""
    }

    try:
        db.table("drug_interaction_cache").upsert({
            "drug_1": d1, "drug_2": d2,
            "severity": finding.get("severity", "none"),
            "interaction_description": finding.get("description", ""),
            "confidence": finding.get("confidence", 0.0),
            "recommendation": finding.get("recommendation", ""),
        }).execute()
    except Exception as exc:
        logger.warning(f"Cache write failed: {exc}")

    if float(finding.get("confidence", 0)) >= 0.60 and finding.get("severity", "none") != "none":
        _create_drug_flag(db, patient_id, "drug_interaction", finding, meds,
                          title_override=f"Drug interaction: {d1} + {d2}")
    return finding


async def _check_drug_condition(drug: str, condition: str, patient_id: str, meds: list, db: Client) -> dict | None:
    cache = (
        db.table("drug_condition_cache")
        .select("*").eq("drug_name", drug).eq("condition_name", condition).execute()
    )
    if cache.data and _cache_fresh(cache.data[0]["cached_at"]):
        hit = cache.data[0]
        logger.info(f"Cache HIT (condition): {drug} + {condition}")
        if float(hit.get("confidence", 0)) >= 0.60 and hit.get("severity", "none") != "none":
            _create_drug_flag(db, patient_id, "drug_condition_conflict", hit, meds,
                              title_override=f"Drug-condition caution: {drug}")
        return hit

    logger.info(f"Cache MISS (condition): {drug} + {condition}")
    result = await llm.run_drug_safety_check([drug], [], [condition], 60, "unknown")
    conflicts = result.get("condition_conflicts", [])

    finding = conflicts[0] if conflicts else {
        "drug": drug, "condition": condition, "severity": "none",
        "confidence": 0.9, "description": "", "recommendation": ""
    }

    try:
        db.table("drug_condition_cache").upsert({
            "drug_name": drug, "condition_name": condition,
            "severity": finding.get("severity", "none"),
            "interaction_description": finding.get("description", ""),
            "confidence": finding.get("confidence", 0.0),
            "recommendation": finding.get("recommendation", ""),
        }).execute()
    except Exception as exc:
        logger.warning(f"Condition cache write failed: {exc}")

    if float(finding.get("confidence", 0)) >= 0.60 and finding.get("severity", "none") != "none":
        _create_drug_flag(db, patient_id, "drug_condition_conflict", finding, meds,
                          title_override=f"Drug-condition caution: {drug}")
    return finding


def _create_drug_flag(
    db: Client,
    patient_id: str,
    flag_type: str,
    finding: dict,
    meds: list,
    title_override: str = None,
) -> None:
    severity = finding.get("severity", "moderate")
    if severity == "none":
        return

    title = title_override or flag_type
    description = finding.get("description", "")
    recommendation = finding.get("recommendation", "Discuss with your doctor.")

    linked_med_id = None
    drug_name = finding.get("drug_1") or finding.get("drug") or ""
    for med in meds:
        if drug_name.lower() in med.get("drug_name_normalized", "").lower():
            linked_med_id = med.get("id")
            break

    create_flag(
        db=db, patient_id=patient_id,
        flag_type=flag_type, severity=severity,
        title=title,
        description=description,
        plain_language_alert=recommendation,
        linked_medication_id=linked_med_id,
    )
