"""
L6 — Deterministic finding classification.
L7 — Nudge card generation for recurring findings.

Deterministic classification is law — no LLM override.
Classification: new | recurring | escalated | resolved | improved
"""
import json
import logging
from datetime import datetime, timezone
from supabase import Client

logger = logging.getLogger("carecircle.longitudinal")

_SEVERITY_RANK = {"critical": 4, "high": 3, "moderate": 2, "low": 1, "informational": 0}
_SEVERITY_TIERS = ["critical", "high", "moderate", "low"]


def classify_findings(
    db: Client,
    patient_id: str,
    run_id: str,
    new_finding_ids: list[str],
    prior_findings: list[dict],
) -> tuple[list[str], list[str]]:
    """
    Classify each new finding against prior findings deterministically.
    Returns (unsuppressed_ids, suppressed_recurring_ids).
    """
    unsuppressed: list[str] = []
    suppressed: list[str] = []
    counts = {"new": 0, "recurring": 0, "escalated": 0, "resolved": 0, "improved": 0}

    for fid in new_finding_ids:
        row = (db.table("clinical_findings").select("*")
               .eq("id", fid).limit(1).execute()).data
        if not row:
            continue
        finding = row[0]

        classification, prior_match = _deterministic_classify(finding, prior_findings)
        counts[classification] += 1
        is_suppressed = (classification == "recurring")

        try:
            db.table("longitudinal_findings").insert({
                "patient_id": patient_id,
                "run_id": run_id,
                "clinical_finding_id": fid,
                "prior_clinical_finding_id": prior_match["id"] if prior_match else None,
                "classification": classification,
                "is_suppressed_from_caregiver": is_suppressed,
            }).execute()
        except Exception as e:
            logger.warning(f"L6: could not save longitudinal_finding for {fid}: {e}")

        if prior_match:
            _update_prior_finding(db, prior_match, run_id, classification)

        if is_suppressed:
            suppressed.append(fid)
        else:
            unsuppressed.append(fid)

    try:
        db.table("longitudinal_runs").update({
            "findings_new": counts["new"],
            "findings_recurring": counts["recurring"],
            "findings_escalated": counts["escalated"],
            "findings_resolved": counts["resolved"],
            "findings_suppressed": counts["recurring"],
        }).eq("id", run_id).execute()
    except Exception as e:
        logger.warning(f"L6: could not update run finding counts: {e}")

    logger.info(f"L6 classification complete: {counts}")
    return unsuppressed, suppressed


def _deterministic_classify(
    finding: dict,
    prior_findings: list[dict],
) -> tuple[str, dict | None]:
    """
    Match by finding_type + related_entities overlap.
    Compare severity to determine escalated/improved/recurring.
    Returns (classification, prior_match_or_None).
    """
    finding_type = finding.get("finding_type", "")
    new_entities = _parse_json(finding.get("related_entities"))
    new_meds = {m.lower() for m in (new_entities.get("medications") or [])}
    new_labs = {l.lower() for l in (new_entities.get("labs") or [])}
    new_conds = {c.lower() for c in (new_entities.get("conditions") or [])}

    best_match: dict | None = None
    best_overlap = 0

    for pf in prior_findings:
        if pf.get("finding_type") != finding_type:
            continue
        prior_entities = _parse_json(pf.get("related_entities"))
        prior_meds = {m.lower() for m in (prior_entities.get("medications") or [])}
        prior_labs = {l.lower() for l in (prior_entities.get("labs") or [])}
        prior_conds = {c.lower() for c in (prior_entities.get("conditions") or [])}

        overlap = (
            len(new_meds & prior_meds)
            + len(new_labs & prior_labs)
            + len(new_conds & prior_conds)
        )
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = pf

    if best_match is None or best_overlap == 0:
        return "new", None

    new_rank = _SEVERITY_RANK.get(finding.get("severity", "informational"), 0)
    prior_rank = _SEVERITY_RANK.get(best_match.get("severity", "informational"), 0)

    if new_rank > prior_rank:
        return "escalated", best_match
    if new_rank < prior_rank:
        return "improved", best_match
    return "recurring", best_match


def _update_prior_finding(
    db: Client,
    prior: dict,
    run_id: str,
    classification: str,
) -> None:
    times_seen = (prior.get("times_seen") or 1) + 1
    updates: dict = {
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
        "last_seen_run_id": run_id,
        "times_seen": times_seen,
    }
    if classification == "escalated":
        updates["status"] = "escalated"
    elif classification in ("resolved", "improved"):
        updates["status"] = "resolved"
    try:
        db.table("clinical_findings").update(updates).eq("id", prior["id"]).execute()
    except Exception as e:
        logger.warning(f"L6: could not update prior finding {prior['id']}: {e}")


def generate_nudge_cards(
    db: Client,
    patient_id: str,
    run_id: str,
    upload_event_id: str,
    suppressed_finding_ids: list[str],
) -> list[dict]:
    """
    L7: Group recurring findings by severity tier, max 4 nudge cards.
    Returns list of dicts ready to INSERT into longitudinal_caregiver_concerns.
    """
    if not suppressed_finding_ids:
        return []

    rows = (db.table("clinical_findings").select("*")
            .in_("id", suppressed_finding_ids).execute()).data

    by_tier: dict[str, list[dict]] = {t: [] for t in _SEVERITY_TIERS}
    for row in rows:
        sev = row.get("severity", "low")
        tier = sev if sev in by_tier else "low"
        by_tier[tier].append(row)

    nudge_cards: list[dict] = []
    display_order = 1000  # nudges always last

    for tier in _SEVERITY_TIERS:
        findings_in_tier = by_tier[tier]
        if not findings_in_tier:
            continue

        titles = [f.get("title", "") for f in findings_in_tier[:3]]
        title_text = titles[0] if len(titles) == 1 else f"{len(findings_in_tier)} recurring {tier}-severity findings"

        oldest_date = None
        for f in findings_in_tier:
            ca = f.get("created_at")
            if ca and (oldest_date is None or ca < oldest_date):
                oldest_date = ca

        nudge_cards.append({
            "patient_id": patient_id,
            "run_id": run_id,
            "upload_event_id": upload_event_id,
            "concern_type": "nudge",
            "concern_category": "nudge",
            "priority": "for_your_awareness",
            "title": f"Still monitoring: {title_text}",
            "summary": (
                f"{len(findings_in_tier)} previously flagged finding(s) at {tier} severity "
                "remain unchanged in the new documents."
            ),
            "what_was_found": "; ".join(f.get("title", "") for f in findings_in_tier),
            "why_it_matters": "These findings have been tracked across visits. No new changes detected.",
            "what_to_do": "Continue current management. Mention at next doctor visit.",
            "evidence": [],
            "source_documents": [],
            "is_nudge": True,
            "nudge_original_finding_date": oldest_date,
            "display_order": display_order,
        })
        display_order += 1

        if len(nudge_cards) >= 4:
            break

    logger.info(f"L7: generated {len(nudge_cards)} nudge cards from {len(suppressed_finding_ids)} suppressed findings")
    return nudge_cards


def _parse_json(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}
    return {}
