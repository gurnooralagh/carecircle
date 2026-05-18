import pytest
from services.storage import upload_file, generate_signed_url


def test_upload_and_sign(db, test_patient, sample_lab_pdf_bytes):
    path = upload_file(
        db=db,
        patient_id=test_patient,
        document_type="lab_report",
        filename="test_lab.pdf",
        file_bytes=sample_lab_pdf_bytes,
        mime_type="application/pdf",
    )
    assert test_patient in path
    assert "lab_report" in path
    assert "test_lab.pdf" in path

    url = generate_signed_url(db=db, storage_path=path)
    assert url.startswith("https://")
    assert "supabase" in url or "storage" in url
