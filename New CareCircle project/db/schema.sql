-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- user_profiles: one row per Meera / caregiver account
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID UNIQUE NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('guardian', 'caregiver', 'admin')),
    full_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    relationship TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- patients: the elderly parent being cared for
CREATE TABLE patients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name TEXT NOT NULL,
    date_of_birth DATE NOT NULL,
    gender TEXT CHECK (gender IN ('male', 'female', 'other')),
    blood_group TEXT,
    weight_kg NUMERIC,
    city TEXT,
    state TEXT,
    primary_language TEXT DEFAULT 'hindi',
    onboarding_status TEXT NOT NULL DEFAULT 'pending' CHECK (onboarding_status IN (
        'pending','processing','medication_verification_needed',
        'clarification_needed','drug_check_running','drug_check_complete',
        'ready_for_review','complete'
    )),
    completeness_score INTEGER DEFAULT 0,
    onboarding_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- patient_guardians: Meera + any caregivers linked to a patient
CREATE TABLE patient_guardians (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    user_profile_id UUID NOT NULL REFERENCES user_profiles(id),
    relationship TEXT,
    is_primary_guardian BOOLEAN DEFAULT FALSE,
    permissions JSONB DEFAULT '{"can_edit": true, "can_view_documents": true}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    UNIQUE(patient_id, user_profile_id)
);

-- doctors: each doctor the patient sees
CREATE TABLE doctors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    name TEXT NOT NULL,
    specialty TEXT,
    hospital TEXT,
    phone TEXT,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- documents: Layer 1 — raw files in Supabase Storage
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    document_type TEXT NOT NULL CHECK (document_type IN (
        'prescription','lab_report','discharge_summary','other'
    )),
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    extraction_status TEXT DEFAULT 'pending' CHECK (extraction_status IN (
        'pending','processing','complete','failed','needs_review'
    )),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- document_extractions: Layer 2 — raw OCR + structured JSON per document
CREATE TABLE document_extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id),
    patient_id UUID NOT NULL REFERENCES patients(id),
    raw_ocr_text TEXT,
    ocr_confidence NUMERIC,
    extracted_data JSONB,
    guardian_corrections JSONB DEFAULT '[]',
    extraction_model TEXT,
    extraction_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- medications: Layer 3 — confirmed medication list
CREATE TABLE medications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    document_id UUID REFERENCES documents(id),
    drug_name_original_ocr TEXT,
    drug_name_normalized TEXT NOT NULL,
    drug_name_generic TEXT,
    dosage TEXT,
    frequency TEXT,
    timing TEXT,
    route TEXT DEFAULT 'oral',
    instructions TEXT,
    source TEXT CHECK (source IN ('guardian_stated','prescription_extracted','discharge_extracted')),
    confidence NUMERIC,
    confirmed_by_guardian BOOLEAN DEFAULT FALSE,
    safety_check_status TEXT DEFAULT 'pending' CHECK (safety_check_status IN (
        'pending','clear','flagged','check_failed'
    )),
    start_date DATE,
    prescribed_by UUID REFERENCES doctors(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- diagnoses: Layer 3 — confirmed conditions
CREATE TABLE diagnoses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    condition_name TEXT NOT NULL,
    icd_code TEXT,
    source TEXT CHECK (source IN ('guardian_stated','lab_extracted','discharge_extracted')),
    confidence NUMERIC,
    confirmation_status TEXT DEFAULT 'confirmed' CHECK (confirmation_status IN (
        'confirmed','unconfirmed','rejected'
    )),
    onset_date DATE,
    diagnosed_by UUID REFERENCES doctors(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- allergies: Layer 3
CREATE TABLE allergies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    allergen TEXT NOT NULL,
    reaction TEXT,
    severity TEXT CHECK (severity IN ('mild','moderate','severe','anaphylaxis')),
    source TEXT DEFAULT 'guardian_stated',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- lab_results: Layer 3 — individual test results from lab reports
CREATE TABLE lab_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    document_id UUID REFERENCES documents(id),
    report_date DATE,
    lab_name TEXT,
    ordering_doctor UUID REFERENCES doctors(id),
    test_name TEXT NOT NULL,
    value TEXT,
    unit TEXT,
    reference_range TEXT,
    is_flagged_by_lab BOOLEAN DEFAULT FALSE,
    confidence NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- open_flags: every finding, anomaly, or question needing Meera's input
CREATE TABLE open_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    flag_type TEXT NOT NULL CHECK (flag_type IN (
        'lab_anomaly','stale_report','conflict_unresolved','unconfirmed_diagnosis',
        'missing_doctor_info','currency_uncertain','ocr_low_confidence',
        'drug_interaction','drug_allergy_conflict','drug_condition_conflict',
        'safety_check_failed','brand_name_unresolved'
    )),
    severity TEXT NOT NULL CHECK (severity IN ('low','moderate','high','critical')),
    title TEXT NOT NULL,
    description TEXT,
    plain_language_alert TEXT,
    linked_medication_id UUID REFERENCES medications(id),
    linked_document_id UUID REFERENCES documents(id),
    linked_diagnosis_id UUID REFERENCES diagnoses(id),
    linked_lab_result_id UUID REFERENCES lab_results(id),
    status TEXT DEFAULT 'open' CHECK (status IN ('open','resolved','dismissed','escalated')),
    meera_answer TEXT,
    meera_answer_detail TEXT,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- patient_summaries: Gemini-generated plain-language patient profile
CREATE TABLE patient_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    summary_text TEXT,
    sections JSONB,
    version INTEGER DEFAULT 1,
    is_current BOOLEAN DEFAULT FALSE,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ,
    is_deleted BOOLEAN DEFAULT FALSE
);

-- drug_safety_checks: audit trail for every safety check run
CREATE TABLE drug_safety_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    check_type TEXT CHECK (check_type IN ('drug_drug','drug_allergy','drug_condition')),
    medications_checked JSONB,
    findings JSONB,
    checked_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- medicine_composition_cache: brand → generic resolution cache
CREATE TABLE medicine_composition_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_name TEXT UNIQUE NOT NULL,
    generic_name TEXT,
    composition TEXT,
    resolved_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- drug_interaction_cache: 90-day cache; drug_1 < drug_2 alphabetically
CREATE TABLE drug_interaction_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_1 TEXT NOT NULL,
    drug_2 TEXT NOT NULL,
    severity TEXT,
    interaction_description TEXT,
    confidence NUMERIC,
    recommendation TEXT,
    cached_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    UNIQUE(drug_1, drug_2)
);

-- drug_condition_cache: 90-day cache for drug-condition contraindications
CREATE TABLE drug_condition_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name TEXT NOT NULL,
    condition_name TEXT NOT NULL,
    severity TEXT,
    interaction_description TEXT,
    confidence NUMERIC,
    recommendation TEXT,
    cached_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    UNIQUE(drug_name, condition_name)
);

-- telegram_groups: for future Telegram bot integration
CREATE TABLE telegram_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id),
    telegram_chat_id TEXT UNIQUE NOT NULL,
    group_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);
