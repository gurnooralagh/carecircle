import pytest
from services.extraction_pipeline import run_extraction_pipeline


@pytest.mark.asyncio
async def test_pipeline_processes_prescription(db, test_patient, sample_prescription_bytes):
    from services.storage import upload_file
    storage_path = upload_file(
        db=db, patient_id=test_patient, document_type="prescription",
        filename="test_prescription.jpg", file_bytes=sample_prescription_bytes,
        mime_type="image/jpeg",
    )
    doc_result = db.table("documents").insert({
        "patient_id": test_patient,
        "document_type": "prescription",
        "original_filename": "test_prescription.jpg",
        "storage_path": storage_path,
        "mime_type": "image/jpeg",
        "file_type": "image/jpeg",
        "extraction_status": "pending",
        "is_deleted": False,
    }).execute()
    doc_id = doc_result.data[0]["id"]

    await run_extraction_pipeline(patient_id=test_patient, db=db)

    extractions = db.table("document_extractions").select("*").eq("document_id", doc_id).execute()
    assert len(extractions.data) >= 1
    extraction = extractions.data[0]
    assert extraction["raw_ocr_text"] is not None
    print(f"\nExtracted data keys: {list((extraction.get('extracted_data') or {}).keys())}")

    patient = db.table("patients").select("onboarding_status").eq("id", test_patient).execute()
    assert patient.data[0]["onboarding_status"] == "medication_verification_needed"


@pytest.mark.asyncio
async def test_pipeline_creates_low_confidence_flag(db, test_patient):
    """Pipeline creates a FOR_YOUR_AWARENESS flag when OCR confidence is below 0.40."""
    from unittest.mock import AsyncMock, patch
    from services.storage import upload_file

    storage_path = upload_file(
        db=db, patient_id=test_patient, document_type="prescription",
        filename="blurry.jpg", file_bytes=b"fake-image-bytes",
        mime_type="image/jpeg",
    )
    db.table("documents").insert({
        "patient_id": test_patient,
        "document_type": "prescription",
        "original_filename": "blurry.jpg",
        "storage_path": storage_path,
        "mime_type": "image/jpeg",
        "file_type": "image/jpeg",
        "extraction_status": "pending",
        "is_deleted": False,
    }).execute()

    with patch("services.extraction_pipeline.ocr.extract_text_from_image",
               new=AsyncMock(return_value=("partial text", 0.3))):
        await run_extraction_pipeline(patient_id=test_patient, db=db)

    flags = db.table("open_flags").select("*").eq("patient_id", test_patient).execute()
    assert len(flags.data) >= 1
    print(f"\nFlag created: {flags.data[0]['title']}")
