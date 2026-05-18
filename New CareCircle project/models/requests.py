from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class SetRoleRequest(BaseModel):
    role: str
    full_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    relationship: Optional[str] = None


class DoctorInput(BaseModel):
    name: str
    specialty: Optional[str] = None
    hospital: Optional[str] = None
    phone: Optional[str] = None
    is_primary: bool = False


class MedicationInput(BaseModel):
    drug_name: str
    dose_text: Optional[str] = None
    dosage: Optional[str] = None  # backward compat
    frequency: Optional[str] = None
    timing: Optional[str] = None
    is_otc: bool = False
    is_supplement: bool = False


class AllergyInput(BaseModel):
    allergen: str
    reaction: Optional[str] = None
    severity: Optional[str] = None  # mild|moderate|severe|unknown


class ConflictResolution(BaseModel):
    chosen_dose_mg: Optional[float] = None
    chosen_dose_text: Optional[str] = None
    is_currently_taking: Optional[bool] = None  # None = not sure


class ConfirmedMedicationItem(BaseModel):
    medication_id: Optional[str] = None
    action: str = "confirm"  # confirm | edit | remove
    updated_fields: Optional[dict] = None
    conflict_resolution: Optional[ConflictResolution] = None
    # Fix 1C: guardian taking status + confirmed dose/frequency
    guardian_taking_status: Optional[str] = None  # yes_currently_taking | no_stopped | not_sure
    guardian_confirmed_dose_text: Optional[str] = None
    guardian_confirmed_frequency: Optional[str] = None
    # Legacy fields
    drug_name: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None


class ConfirmMedicationsRequest(BaseModel):
    confirmed_medications: list[ConfirmedMedicationItem] = []
    added_medications: list[MedicationInput] = []
    confirmed_conditions: list[str] = []


# Legacy models kept for existing test compatibility
class CandidateSelectionItem(BaseModel):
    medication_id: str
    confirmed_name: Optional[str] = None


class SelectCandidatesRequest(BaseModel):
    selections: list[CandidateSelectionItem]


class AnswerRequest(BaseModel):
    flag_id: str
    patient_id: str
    answer: str
    answer_detail: Optional[str] = None


class CorrectionRequest(BaseModel):
    section: str
    correction_text: str
