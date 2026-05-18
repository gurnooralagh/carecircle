from supabase import Client
from config.logging import get_logger
from datetime import datetime, timezone

logger = get_logger("STORAGE")
BUCKET = "documents"


def upload_file(
    db: Client,
    patient_id: str,
    document_type: str,
    filename: str,
    file_bytes: bytes,
    mime_type: str,
) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = f"{patient_id}/{document_type}/{timestamp}_{filename}"
    logger.info(f"Uploading to Supabase Storage: {path} ({len(file_bytes)} bytes)")

    db.storage.from_(BUCKET).upload(
        path=path,
        file=file_bytes,
        file_options={"content-type": mime_type, "upsert": "true"},
    )
    logger.info(f"Upload complete → {path}")
    return path


def generate_signed_url(db: Client, storage_path: str) -> str:
    logger.info(f"Generating 15-min signed URL for: {storage_path}")
    result = db.storage.from_(BUCKET).create_signed_url(storage_path, 900)
    url = result["signedURL"]
    logger.info("Signed URL generated")
    return url
