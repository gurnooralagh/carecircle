import pytest
from services.llm import extract_prescription, extract_lab_report, extract_discharge_summary
from services.llm import (
    reconcile_medications, resolve_brand_name,
    run_drug_safety_check, generate_plain_language_alert,
    generate_patient_summary, parse_correction,
)


@pytest.mark.asyncio
async def test_extract_prescription():
    sample_text = (
        "Dr. Verma, Cardiologist, Medanta Lucknow\n"
        "Date: 15 March 2026\n"
        "Patient: Rajesh Kumar, 67M\n"
        "Rx:\n"
        "1. Amlodipine 5mg - once daily morning\n"
        "2. Atorvastatin 10mg - once daily at bedtime\n"
        "Next visit: 4 weeks\n"
        "Follow up with ECG before visit"
    )
    result = await extract_prescription(sample_text)
    print(f"\nPrescription extraction:\n{result}")
    assert isinstance(result, dict)
    assert "medications" in result
    assert isinstance(result["medications"], list)
    assert len(result["medications"]) >= 1
    med = result["medications"][0]
    assert "drug_name" in med
    assert "dosage" in med


@pytest.mark.asyncio
async def test_extract_lab_report():
    sample_text = (
        "Apollo Diagnostics, Lucknow\n"
        "Date: 10 March 2026\n"
        "Patient: Rajesh Kumar\n"
        "Ordering Doctor: Dr. Sharma\n"
        "HbA1c: 7.8% (Ref: <5.7%) HIGH\n"
        "Fasting Blood Sugar: 142 mg/dL (Ref: 70-100) HIGH\n"
        "Serum Creatinine: 1.1 mg/dL (Ref: 0.7-1.2) Normal\n"
    )
    result = await extract_lab_report(sample_text)
    print(f"\nLab report extraction:\n{result}")
    assert isinstance(result, dict)
    assert "tests" in result
    assert isinstance(result["tests"], list)
    assert len(result["tests"]) >= 1
    test_item = result["tests"][0]
    assert "test_name" in test_item
    assert "value" in test_item


@pytest.mark.asyncio
async def test_extract_discharge_summary():
    sample_text = (
        "DISCHARGE SUMMARY - Medanta Lucknow\n"
        "Admission: 05 Jan 2026  Discharge: 08 Jan 2026\n"
        "Patient: Rajesh Kumar, 67M\n"
        "Diagnosis: Hypertensive urgency, T2DM\n"
        "Medications at Discharge:\n"
        "- Amlodipine 5mg OD\n"
        "- Metformin 500mg BD after meals\n"
        "Follow-up: Cardiology in 2 weeks\n"
    )
    result = await extract_discharge_summary(sample_text)
    print(f"\nDischarge extraction:\n{result}")
    assert isinstance(result, dict)
    assert "medications_at_discharge" in result
    assert isinstance(result["medications_at_discharge"], list)


@pytest.mark.asyncio
async def test_reconcile_medications():
    stated = [{"drug_name": "Metformin 500mg", "source": "guardian_stated"}]
    extracted = [
        {"drug_name": "Metformin 500 mg", "dosage": "500mg", "source": "prescription_extracted"},
        {"drug_name": "Amlodipine 5mg", "dosage": "5mg", "source": "prescription_extracted"},
    ]
    result = await reconcile_medications(stated, extracted)
    print(f"\nReconcile result:\n{result}")
    assert isinstance(result, dict)
    assert "conflicts" in result
    assert "new_medications" in result


@pytest.mark.asyncio
async def test_resolve_brand_name():
    result = await resolve_brand_name("Glycomet")
    print(f"\nBrand name result:\n{result}")
    assert isinstance(result, dict)
    assert "generic_name" in result


@pytest.mark.asyncio
async def test_run_drug_safety_check():
    result = await run_drug_safety_check(
        medications=["Amlodipine 5mg", "Metformin 500mg", "Glimepiride 1mg"],
        allergies=["Penicillin"],
        conditions=["Type 2 Diabetes", "Hypertension"],
        patient_age=67,
        gender="male",
    )
    print(f"\nDrug safety result:\n{result}")
    assert isinstance(result, dict)
    assert "interactions" in result
    assert "allergy_conflicts" in result
    assert "condition_conflicts" in result


@pytest.mark.asyncio
async def test_generate_plain_language_alert():
    result = await generate_plain_language_alert(
        flag_type="drug_interaction",
        drugs=["Amlodipine", "Metformin"],
        severity="moderate",
        description="Possible interaction affecting blood pressure control",
    )
    print(f"\nAlert text: {result}")
    assert isinstance(result, str)
    assert len(result) > 20
    assert "doctor" in result.lower()


@pytest.mark.asyncio
async def test_generate_patient_summary():
    snapshot = {
        "patient": {"name": "Rajesh Kumar", "age": 67, "gender": "male"},
        "conditions": ["Type 2 Diabetes", "Hypertension"],
        "medications": [
            {"drug_name": "Metformin 500mg", "frequency": "twice daily"},
            {"drug_name": "Amlodipine 5mg", "frequency": "once daily"},
        ],
        "allergies": [],
        "open_flags_count": 1,
    }
    result = await generate_patient_summary(snapshot)
    print(f"\nSummary:\n{result}")
    assert isinstance(result, dict)
    assert "summary_text" in result
    assert len(result["summary_text"]) > 50


@pytest.mark.asyncio
async def test_parse_correction():
    result = await parse_correction(
        section="medications",
        correction_text="Actually Metformin dose is 1000mg not 500mg",
        current_value={"drug_name": "Metformin", "dosage": "500mg"},
    )
    print(f"\nCorrection parse:\n{result}")
    assert isinstance(result, dict)
    assert "field" in result
    assert "new_value" in result
