"""
Dashboard router.

Active endpoints:
  GET /api/dashboard/runs/{patient_id}
  GET /api/dashboard/summary/{patient_id}
  GET /api/dashboard/findings/{patient_id}?run_id=onboarding|<uuid>
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client
from db.client import get_db
from dependencies import get_current_user
from config.logging import get_logger

logger = get_logger("DASHBOARD")
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

PRIORITY_RANK = {
    "critical_concern": 0,
    "high_priority": 1,
    "moderate": 2,
    "for_your_awareness": 3,
}


def _parse_action_items(data) -> list[dict]:
    if not data:
        return []
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    result = []
    for i, item in enumerate(data):
        if isinstance(item, dict):
            result.append({
                "id": item.get("id") or f"item-{i}",
                "text": item.get("action") or item.get("text") or "",
                "category": item.get("category") or "keep_monitoring",
            })
        elif isinstance(item, str):
            result.append({"id": f"item-{i}", "text": item, "category": "keep_monitoring"})
    return result


def _get_runs(patient_id: str, db: Client) -> list[dict]:
    """Returns all analysis runs for a patient, oldest first."""
    patient_row = db.table("patients").select(
        "id, updated_at, onboarding_status"
    ).eq("id", patient_id).execute()

    if not patient_row.data:
        return []

    p = patient_row.data[0]
    runs = []

    if p.get("onboarding_status") in ("findings_ready", "complete"):
        runs.append({
            "run_id": "onboarding",
            "run_type": "onboarding",
            "label": "Initial analysis",
            "run_date": p.get("updated_at") or "",
        })

    events = (
        db.table("document_upload_events")
        .select("id, longitudinal_run_id, created_at")
        .eq("patient_id", patient_id)
        .eq("processing_status", "ready")
        .order("created_at")
        .execute()
    ).data or []

    for ev in events:
        if ev.get("longitudinal_run_id"):
            runs.append({
                "run_id": str(ev["longitudinal_run_id"]),
                "run_type": "longitudinal",
                "label": "Upload",
                "run_date": ev.get("created_at") or "",
                "upload_event_id": str(ev["id"]),
            })

    return runs


def _concerns_for_onboarding(patient_id: str, db: Client) -> tuple[int, list[dict]]:
    """Returns (active_count, top_2_concerns) from caregiver_concerns."""
    rows = (
        db.table("caregiver_concerns")
        .select("id, priority, title, summary, what_was_found, why_it_matters, what_to_do, source_documents, display_order")
        .eq("patient_id", patient_id)
        .eq("status", "active")
        .order("display_order")
        .execute()
    ).data or []

    sorted_rows = sorted(
        rows,
        key=lambda c: (PRIORITY_RANK.get(c.get("priority") or "for_your_awareness", 3), c.get("display_order") or 0)
    )

    top = [
        {
            "id": str(c["id"]),
            "title": c.get("title") or "",
            "summary": c.get("summary") or "",
            "priority": c.get("priority") or "for_your_awareness",
            "what_was_found": c.get("what_was_found") or "",
            "why_it_matters": c.get("why_it_matters") or "",
            "what_to_do": c.get("what_to_do") or "",
            "source_documents": c.get("source_documents") or [],
            "status": None,
        }
        for c in sorted_rows[:2]
    ]

    return len(rows), top


def _concerns_for_longitudinal(run_id: str, db: Client) -> tuple[int, list[dict]]:
    """Returns (active_count, top_2_concerns) from longitudinal_caregiver_concerns."""
    rows = (
        db.table("longitudinal_caregiver_concerns")
        .select("id, priority, title, summary, what_was_found, why_it_matters, what_to_do, source_documents, display_order, concern_category")
        .eq("run_id", run_id)
        .order("display_order")
        .execute()
    ).data or []

    # Active = not resolved and not nudge
    active_rows = [r for r in rows if r.get("concern_category") not in ("resolved", "nudge")]

    sorted_rows = sorted(
        active_rows,
        key=lambda c: (PRIORITY_RANK.get(c.get("priority") or "for_your_awareness", 3), c.get("display_order") or 0)
    )

    top = [
        {
            "id": str(c["id"]),
            "title": c.get("title") or "",
            "summary": c.get("summary") or "",
            "priority": c.get("priority") or "for_your_awareness",
            "what_was_found": c.get("what_was_found") or "",
            "why_it_matters": c.get("why_it_matters") or "",
            "what_to_do": c.get("what_to_do") or "",
            "source_documents": c.get("source_documents") or [],
            "status": c.get("concern_category"),  # new/escalated/improved/resolved
        }
        for c in sorted_rows[:2]
    ]

    return len(active_rows), top


@router.get("/runs/{patient_id}")
async def get_runs(
    patient_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """All analysis runs for a patient: onboarding + each completed upload."""
    patient_row = db.table("patients").select("id").eq("id", patient_id).execute()
    if not patient_row.data:
        raise HTTPException(status_code=404, detail="Patient not found")

    return {"runs": _get_runs(patient_id, db)}


@router.get("/summary/{patient_id}")
async def get_dashboard_summary(
    patient_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Everything needed for DashboardHome in one call."""
    patient_row = db.table("patients").select(
        "id, full_name, date_of_birth, gender, city, updated_at, onboarding_status"
    ).eq("id", patient_id).execute()

    if not patient_row.data:
        raise HTTPException(status_code=404, detail="Patient not found")

    p = patient_row.data[0]
    runs = _get_runs(patient_id, db)

    # Use most recent run for concerns
    most_recent = runs[-1] if runs else None

    if most_recent and most_recent["run_type"] == "longitudinal":
        active_concerns_count, top_concerns = _concerns_for_longitudinal(most_recent["run_id"], db)
    else:
        active_concerns_count, top_concerns = _concerns_for_onboarding(patient_id, db)

    # Active medications
    meds_rows = (
        db.table("medications")
        .select("id, guardian_taking_status")
        .eq("patient_id", patient_id)
        .eq("is_deleted", False)
        .execute()
    ).data or []

    # Match what MedicationsTab shows: non-deleted meds that aren't stopped
    active_medications_count = sum(
        1 for m in meds_rows
        if m.get("guardian_taking_status") != "no_stopped"
    )

    # Action summary (always current)
    action_row = (
        db.table("patient_action_summaries")
        .select("do_now, follow_up, ongoing_monitoring")
        .eq("patient_id", patient_id)
        .eq("is_current", True)
        .limit(1)
        .execute()
    ).data

    action_summary = None
    if action_row:
        raw = action_row[0]
        action_summary = {
            "do_now": _parse_action_items(raw.get("do_now")),
            "follow_up": _parse_action_items(raw.get("follow_up")),
            "keep_monitoring": _parse_action_items(raw.get("ongoing_monitoring")),
        }

    return {
        "patient": {
            "full_name": p.get("full_name") or "",
            "date_of_birth": p.get("date_of_birth") or "",
            "gender": p.get("gender") or "",
            "city": p.get("city") or "",
        },
        "last_analysis_at": p.get("updated_at") or "",
        "runs": runs,
        "active_concerns_count": active_concerns_count,
        "active_medications_count": active_medications_count,
        "top_concerns": top_concerns,
        "action_summary": action_summary,
    }


@router.get("/findings/{patient_id}")
async def get_findings_for_run(
    patient_id: str,
    run_id: str = Query(default="onboarding"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Returns all concerns for a specific run.
    run_id=onboarding → caregiver_concerns
    run_id=<uuid>     → longitudinal_caregiver_concerns
    """
    patient_row = db.table("patients").select("id").eq("id", patient_id).execute()
    if not patient_row.data:
        raise HTTPException(status_code=404, detail="Patient not found")

    if run_id == "onboarding":
        rows = (
            db.table("caregiver_concerns")
            .select("*")
            .eq("patient_id", patient_id)
            .eq("status", "active")
            .order("display_order")
            .execute()
        ).data or []

        concerns = [
            {
                "id": str(r["id"]),
                "title": r.get("title") or "",
                "summary": r.get("summary") or "",
                "priority": r.get("priority") or "for_your_awareness",
                "concern_type": r.get("concern_type"),
                "what_was_found": r.get("what_was_found") or "",
                "why_it_matters": r.get("why_it_matters") or "",
                "what_to_do": r.get("what_to_do") or "",
                "source_documents": r.get("source_documents") or [],
                "status": None,
            }
            for r in rows
        ]
    else:
        rows = (
            db.table("longitudinal_caregiver_concerns")
            .select("*")
            .eq("run_id", run_id)
            .order("display_order")
            .execute()
        ).data or []

        concerns = [
            {
                "id": str(r["id"]),
                "title": r.get("title") or "",
                "summary": r.get("summary") or "",
                "priority": r.get("priority") or "for_your_awareness",
                "concern_type": r.get("concern_type"),
                "what_was_found": r.get("what_was_found") or "",
                "why_it_matters": r.get("why_it_matters") or "",
                "what_to_do": r.get("what_to_do") or "",
                "source_documents": r.get("source_documents") or [],
                "status": r.get("concern_category"),  # new/escalated/improved/resolved
            }
            for r in rows
        ]

    return {"concerns": concerns, "run_id": run_id}
