from fastapi import APIRouter, Depends
from supabase import Client
from db.client import get_db
from dependencies import get_current_user
from models.requests import SetRoleRequest
from models.responses import SetRoleResponse
from config.logging import get_logger

logger = get_logger("AUTH")
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/set-role", response_model=SetRoleResponse)
async def set_role(
    body: SetRoleRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    logger.info(f"set-role called — user: {current_user['id']}, role: {body.role}")

    existing = (
        db.table("user_profiles")
        .select("id")
        .eq("auth_user_id", current_user["id"])
        .execute()
    )

    if existing.data:
        profile_id = existing.data[0]["id"]
        db.table("user_profiles").update({
            "role": body.role,
            "full_name": body.full_name,
            "phone": body.phone,
            "email": body.email,
            "relationship": body.relationship,
        }).eq("id", profile_id).execute()
        logger.info(f"User profile updated: {profile_id}")
    else:
        result = db.table("user_profiles").insert({
            "auth_user_id": current_user["id"],
            "role": body.role,
            "full_name": body.full_name,
            "phone": body.phone,
            "email": body.email,
            "relationship": body.relationship,
        }).execute()
        profile_id = result.data[0]["id"]
        logger.info(f"User profile created: {profile_id}")

    return SetRoleResponse(
        user_profile_id=profile_id,
        role=body.role,
        next_step="onboarding",
    )
