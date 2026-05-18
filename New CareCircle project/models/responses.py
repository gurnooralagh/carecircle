from __future__ import annotations
from typing import Optional, Any
from pydantic import BaseModel


class SetRoleResponse(BaseModel):
    user_profile_id: str
    role: str
    next_step: str


class SubmitResponse(BaseModel):
    patient_id: str
    status: str


class StatusResponse(BaseModel):
    patient_id: str
    status: str
    completeness_score: int


# ---- Screen 4: Medication verification ----

class SourceReference(BaseModel):
    source_type: str
    stated_name: Optional[str] = None
    document_type: Optional[str] = None
    document_date: Optional[str] = None
    extracted_as: Optional[str] = None
    prescribing_doctor: Optional[str] = None
    confidence: Optional[float] = None


class DoseConflictDetail(BaseModel):
    doses_found: list[str] = []
    sources: list[str] = []


class StatusConflictDetail(BaseModel):
    active_source: Optional[str] = None
    stopped_source: Optional[str] = None


class ConflictDetail(BaseModel):
    dose_conflict: Optional[DoseConflictDetail] = None
    status_conflict: Optional[StatusConflictDetail] = None


class MedicationItem(BaseModel):
    medication_id: str
    drug_name_brand: Optional[str] = None   # primary display on Screen 4
    drug_name_generic: Optional[str] = None  # "Also known as:" secondary
    drug_class: Optional[str] = None
    dose_text: Optional[str] = None
    frequency: Optional[str] = None
    timing: Optional[str] = None
    source: str
    source_references: list[dict] = []
    cross_reference_status: str = "document_only"
    confidence: Optional[float] = None
    normalization_confidence: Optional[float] = None
    needs_verification: bool = False
    confirmed_by_guardian: bool = False
    dedup_status: str = "unique"  # merged | dose_conflict | status_conflict | unique
    conflict_detail: Optional[ConflictDetail] = None
    # Legacy fields for backward compat
    drug_name: Optional[str] = None
    dosage: Optional[str] = None
    safety_check_status: str = "pending"
    candidates: list[str] = []


class ExtractedMedicationsResponse(BaseModel):
    medications: list[MedicationItem]
    extracted_conditions: list[str]


class ConfirmMedicationsResponse(BaseModel):
    status: str
    medications_confirmed: int
    analysis_started: bool = True
    # Legacy
    drug_check_started: bool = True


# ---- Screen 5: Findings (Phase 6.5 — caregiver_concerns) ----

class EvidenceItem(BaseModel):
    entity: str = ""
    source: str = ""
    date: str = ""


class BrandNameUsed(BaseModel):
    brand: str = ""
    generic: str = ""


class ConcernItem(BaseModel):
    concern_id: str
    concern_type: str       # grouped | independent | partial_match_source
    priority: str           # critical_concern | high_priority | moderate | for_your_awareness
    title: str
    summary: str
    what_was_found: str
    why_it_matters: str
    what_to_do: str
    evidence: list[EvidenceItem] = []
    source_documents: list[str] = []
    is_partial_match: bool = False
    partial_match_group_id: Optional[str] = None
    brand_names_used: list[BrandNameUsed] = []
    display_order: int = 0


class ConcernSummary(BaseModel):
    critical_concern: int = 0
    high_priority: int = 0
    moderate: int = 0
    for_your_awareness: int = 0
    total: int = 0


class ActionItem(BaseModel):
    action: str
    reason: Optional[str] = None
    source: Optional[str] = None


class ActionSummary(BaseModel):
    do_now: list[ActionItem] = []
    follow_up: list[ActionItem] = []
    ongoing_monitoring: list[ActionItem] = []


class FindingsResponse(BaseModel):
    status: str                    # running | ready
    concerns: list[ConcernItem] = []
    concern_summary: ConcernSummary = ConcernSummary()
    raw_flags_count: int = 0
    note: str = "raw_flags_count = total atomic findings generated. concerns = grouped presentation."
    action_summary: Optional[ActionSummary] = None
    # Legacy fields kept for backward compat
    flags_by_directive: dict[str, list[Any]] = {}
    total_flags: int = 0
    critical_count: int = 0
    high_count: int = 0


# ---- Legacy flag item (kept for backward compat) ----

class FlagItem(BaseModel):
    flag_id: str
    directive_type: str
    severity: str
    title: str
    what_was_found: str
    why_it_matters: str
    what_to_do: str
    source_reference: Optional[str] = None


# ---- Onboarding complete ----

class ConfirmResponse(BaseModel):
    status: str
    completeness_score: int
    patient_id: str
    flags_saved: int = 0


# ---- Documents ----

class DocumentUrlResponse(BaseModel):
    document_id: str
    signed_url: str
    expires_in: int


# ---- Legacy models kept for backward compat ----

class QuestionItem(BaseModel):
    flag_id: str
    flag_type: str
    severity: str
    question_text: str
    context: Optional[str] = None
    plain_language_alert: Optional[str] = None


class QuestionsResponse(BaseModel):
    questions: list[QuestionItem]
    total_remaining: int
    drug_check_status: str


class AnswerResponse(BaseModel):
    flag_resolved: bool
    more_questions: bool
    next_questions: list[QuestionItem]
    drug_check_complete: bool
    summary_ready: bool


class DrugFlagItem(BaseModel):
    flag_id: str
    medication_name: str
    flag_type: str
    severity: str
    description: Optional[str] = None
    plain_language_alert: Optional[str] = None


class DrugSafetyResultsResponse(BaseModel):
    overall_severity: str
    flagged_medications: list[DrugFlagItem]
    clear_medications_count: int
    message: str


class SummarySection(BaseModel):
    demographics: Optional[str] = None
    conditions: Optional[str] = None
    medications: Optional[str] = None
    allergies: Optional[str] = None
    recent_labs: Optional[str] = None
    open_concerns: Optional[str] = None


class ResultsResponse(BaseModel):
    patient_id: str
    summary_text: str
    sections: SummarySection
    open_flags: list[Any]
    completeness_score: int


class CorrectionResponse(BaseModel):
    correction_saved: bool
    updated_section: str
