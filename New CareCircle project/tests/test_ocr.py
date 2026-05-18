import pytest
from services.ocr import extract_text_from_image


@pytest.mark.asyncio
async def test_ocr_extracts_text_from_prescription(sample_prescription_bytes):
    text, confidence = await extract_text_from_image(
        file_bytes=sample_prescription_bytes,
        mime_type="image/jpeg",
    )
    assert isinstance(text, str)
    assert len(text) > 20, f"Expected meaningful text, got: {repr(text)}"
    assert isinstance(confidence, float)
    assert 0.0 <= confidence <= 1.0
    print(f"\nOCR confidence: {confidence}")
    print(f"OCR text snippet: {text[:300]}")


@pytest.mark.asyncio
async def test_ocr_returns_confidence_above_zero(sample_prescription_bytes):
    _, confidence = await extract_text_from_image(
        file_bytes=sample_prescription_bytes,
        mime_type="image/jpeg",
    )
    assert confidence > 0.0
