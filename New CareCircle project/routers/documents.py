from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client
from db.client import get_db
from dependencies import get_current_user
from models.responses import DocumentUrlResponse
from services.storage import generate_signed_url
from config.logging import get_logger

logger = get_logger("DOCUMENTS")
router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/{document_id}/url", response_model=DocumentUrlResponse)
async def get_document_url(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    logger.info(f"Signed URL requested: document {document_id} by user {current_user['id']}")

    doc_result = (
        db.table("documents").select("*")
        .eq("id", document_id).eq("is_deleted", False).execute()
    )
    if not doc_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    doc = doc_result.data[0]

    profile_result = (
        db.table("user_profiles").select("id")
        .eq("auth_user_id", current_user["id"]).execute()
    )
    if not profile_result.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile not found")
    profile_id = profile_result.data[0]["id"]

    ownership = (
        db.table("patient_guardians")
        .select("id")
        .eq("patient_id", doc["patient_id"])
        .eq("user_profile_id", profile_id)
        .execute()
    )
    if not ownership.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to view this document")

    signed_url = generate_signed_url(db=db, storage_path=doc["storage_path"])
    logger.info(f"Signed URL generated for document {document_id}")

    return DocumentUrlResponse(
        document_id=document_id,
        signed_url=signed_url,
        expires_in=900,
    )
