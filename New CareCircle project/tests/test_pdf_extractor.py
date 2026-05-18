import pytest
from services.pdf_extractor import extract_text_from_pdf


def test_extract_text_from_normal_pdf(sample_lab_pdf_bytes):
    text = extract_text_from_pdf(sample_lab_pdf_bytes)
    assert isinstance(text, str)
    assert len(text) >= 50
    assert "HbA1c" in text or "Blood Sugar" in text or "Rajesh" in text


def test_extract_text_from_discharge_pdf(sample_discharge_pdf_bytes):
    text = extract_text_from_pdf(sample_discharge_pdf_bytes)
    assert len(text) >= 50
    assert "Amlodipine" in text or "Metformin" in text or "Discharge" in text


def test_returns_string_not_none(sample_lab_pdf_bytes):
    result = extract_text_from_pdf(sample_lab_pdf_bytes)
    assert result is not None
    assert isinstance(result, str)
