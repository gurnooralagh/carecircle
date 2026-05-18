-- CareCircle v3.0 Schema Migration
-- Run this in Supabase SQL editor
-- Safe to re-run (uses IF NOT EXISTS / IF EXISTS)

-- =========================================================
-- 1. UPDATE PATIENTS TABLE — new status lifecycle
-- =========================================================
-- Migrate any old v1.2 status values to valid v3.0 equivalents before adding constraint
UPDATE patients SET onboarding_status = 'complete'
WHERE onboarding_status IN ('summary_ready','drug_check_complete','questions_pending');
UPDATE patients SET onboarding_status = 'medication_verification_needed'
WHERE onboarding_status IN ('candidate_selection_needed','medication_review_needed');
UPDATE patients SET onboarding_status = 'pending'
WHERE onboarding_status NOT IN (
    'pending','processing',
    'medication_verification_needed',
    'analysis_running','findings_ready','complete','failed'
);

ALTER TABLE patients DROP CONSTRAINT IF EXISTS patients_onboarding_status_check;
ALTER TABLE patients ADD CONSTRAINT patients_onboarding_status_check CHECK (
    onboarding_status IN (
        'pending','processing',
        'medication_verification_needed',
        'analysis_running','findings_ready','complete','failed'
    )
);

-- Add completeness_score if missing
ALTER TABLE patients ADD COLUMN IF NOT EXISTS completeness_score INT DEFAULT 0;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS med_independence TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS med_missed_frequency TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS med_missed_reasons JSONB;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS daily_routine JSONB;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS primary_use_case TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS health_concerns JSONB;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS has_caregiver BOOLEAN DEFAULT FALSE;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS height_cm NUMERIC(5,2);

-- =========================================================
-- 2. UPDATE DOCUMENTS TABLE
-- =========================================================
ALTER TABLE documents ADD COLUMN IF NOT EXISTS partial_extraction BOOLEAN DEFAULT FALSE;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS unreadable_pages INT[];
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extraction_error TEXT;
-- rename mime_type alias — keep mime_type column, add file_type as alias for v3 compat
ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_type TEXT;
-- Update file_type from existing mime_type data
UPDATE documents SET file_type = mime_type WHERE file_type IS NULL;
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_extraction_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_extraction_status_check CHECK (
    extraction_status IN ('pending','processing','completed','failed','needs_review')
);

-- =========================================================
-- 3. UPDATE MEDICATIONS TABLE — v3.0 fields
-- =========================================================
ALTER TABLE medications ADD COLUMN IF NOT EXISTS drug_name_brand TEXT;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS drug_class TEXT;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS formulation TEXT;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS dose_mg NUMERIC(8,2);
ALTER TABLE medications ADD COLUMN IF NOT EXISTS dose_unit TEXT DEFAULT 'mg';
ALTER TABLE medications ADD COLUMN IF NOT EXISTS dose_text TEXT;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS route TEXT;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS duration_days INT;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS duration_text TEXT;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS is_prn BOOLEAN DEFAULT FALSE;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS is_sos BOOLEAN DEFAULT FALSE;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active';
ALTER TABLE medications ADD COLUMN IF NOT EXISTS source_document_id UUID REFERENCES documents(id);
ALTER TABLE medications ADD COLUMN IF NOT EXISTS source_extraction_id UUID REFERENCES document_extractions(id);
ALTER TABLE medications ADD COLUMN IF NOT EXISTS prescribing_doctor_id UUID REFERENCES doctors(id);
ALTER TABLE medications ADD COLUMN IF NOT EXISTS prescription_date DATE;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS prescription_age_days INT;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS is_current BOOLEAN DEFAULT TRUE;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS is_otc BOOLEAN DEFAULT FALSE;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS is_supplement BOOLEAN DEFAULT FALSE;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS currency_uncertain BOOLEAN DEFAULT FALSE;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS extraction_confidence NUMERIC(4,3);
ALTER TABLE medications ADD COLUMN IF NOT EXISTS normalization_confidence NUMERIC(4,3);
ALTER TABLE medications ADD COLUMN IF NOT EXISTS normalization_source TEXT;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS source_references JSONB;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS cross_reference_status TEXT DEFAULT 'document_only';
ALTER TABLE medications ADD COLUMN IF NOT EXISTS deleted_reason TEXT;

-- Backfill drug_name_brand from drug_name_normalized for existing rows
UPDATE medications SET drug_name_brand = drug_name_normalized WHERE drug_name_brand IS NULL AND drug_name_normalized IS NOT NULL;
-- Backfill drug_name_generic if it exists
-- (drug_name_generic was already added in previous migration)

-- =========================================================
-- 4. UPDATE LAB_RESULTS TABLE — v3.0 fields
-- =========================================================
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS test_name_normalized TEXT;
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS test_category TEXT;
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS value_numeric NUMERIC(12,4);
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS value_text TEXT;
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS reference_low NUMERIC(12,4);
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS reference_high NUMERIC(12,4);
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS flag_direction TEXT;
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS is_age_gender_adjusted_flag BOOLEAN DEFAULT FALSE;
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS report_date DATE;
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS is_stale BOOLEAN DEFAULT FALSE;
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS ordering_doctor TEXT;
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS fasting_status TEXT;
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS extraction_confidence NUMERIC(4,3);
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS source_extraction_id UUID REFERENCES document_extractions(id);

-- =========================================================
-- 4b. UPDATE DOCUMENT_EXTRACTIONS TABLE
-- =========================================================
ALTER TABLE document_extractions ADD COLUMN IF NOT EXISTS overall_confidence NUMERIC(4,3);
ALTER TABLE document_extractions ADD COLUMN IF NOT EXISTS extraction_model TEXT;

-- =========================================================
-- 5. UPDATE DIAGNOSES TABLE
-- =========================================================
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS confirmed_by_guardian BOOLEAN DEFAULT FALSE;
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS source_document_id UUID REFERENCES documents(id);
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS condition_normalized TEXT;
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS icd_code TEXT;
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS chronic_or_acute TEXT;
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS severity_stage TEXT;
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS cross_reference_status TEXT DEFAULT 'document_only';
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS managing_doctor_id UUID REFERENCES doctors(id);
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS diagnosed_date DATE;
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE diagnoses ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- =========================================================
-- 6. UPDATE ALLERGIES TABLE
-- =========================================================
ALTER TABLE allergies ADD COLUMN IF NOT EXISTS allergen_normalized TEXT;
ALTER TABLE allergies ADD COLUMN IF NOT EXISTS drug_class TEXT;
ALTER TABLE allergies ADD COLUMN IF NOT EXISTS cross_reference_status TEXT DEFAULT 'document_only';
ALTER TABLE allergies ADD COLUMN IF NOT EXISTS reaction_type TEXT;
ALTER TABLE allergies ADD COLUMN IF NOT EXISTS source_document_id UUID REFERENCES documents(id);
-- Expand severity constraint to include 'unknown'
ALTER TABLE allergies DROP CONSTRAINT IF EXISTS allergies_severity_check;
ALTER TABLE allergies ADD CONSTRAINT allergies_severity_check CHECK (
    severity IN ('mild','moderate','severe','anaphylaxis','unknown')
);

-- =========================================================
-- 6b. UPDATE MEDICATIONS SOURCE CONSTRAINT
-- =========================================================
-- v3.0 uses 'document_extracted'; v1.2 only allowed prescription/discharge_extracted
ALTER TABLE medications DROP CONSTRAINT IF EXISTS medications_source_check;
ALTER TABLE medications ADD CONSTRAINT medications_source_check CHECK (
    source IN ('guardian_stated','document_extracted','prescription_extracted','discharge_extracted','lab_extracted')
);

-- =========================================================
-- 6c. UPDATE DIAGNOSES SOURCE CONSTRAINT
-- =========================================================
ALTER TABLE diagnoses DROP CONSTRAINT IF EXISTS diagnoses_source_check;
ALTER TABLE diagnoses ADD CONSTRAINT diagnoses_source_check CHECK (
    source IN ('guardian_stated','document_extracted','lab_extracted','discharge_extracted')
);

-- =========================================================
-- 6d. UPDATE DOCTORS TABLE — v3.0 adds full_name, hospital_name, source columns
-- =========================================================
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS hospital_name TEXT;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'guardian_stated';
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS source_document_id UUID REFERENCES documents(id);
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS is_primary_physician BOOLEAN DEFAULT FALSE;
-- Backfill new columns from original columns
UPDATE doctors SET full_name = name WHERE full_name IS NULL;
UPDATE doctors SET hospital_name = hospital WHERE hospital_name IS NULL;
UPDATE doctors SET is_primary_physician = is_primary WHERE is_primary_physician IS NULL;

-- =========================================================
-- 7. UPDATE OPEN_FLAGS TABLE — v3.0 directive-based structure
-- =========================================================
ALTER TABLE open_flags ADD COLUMN IF NOT EXISTS finding_id UUID;
ALTER TABLE open_flags ADD COLUMN IF NOT EXISTS directive_type TEXT;
ALTER TABLE open_flags ADD COLUMN IF NOT EXISTS what_was_found TEXT;
ALTER TABLE open_flags ADD COLUMN IF NOT EXISTS why_it_matters TEXT;
ALTER TABLE open_flags ADD COLUMN IF NOT EXISTS what_to_do TEXT;
ALTER TABLE open_flags ADD COLUMN IF NOT EXISTS source_reference TEXT;
ALTER TABLE open_flags ADD COLUMN IF NOT EXISTS is_personalized BOOLEAN DEFAULT TRUE;
ALTER TABLE open_flags DROP CONSTRAINT IF EXISTS open_flags_status_check;
ALTER TABLE open_flags ADD CONSTRAINT open_flags_status_check CHECK (
    status IN ('open','acknowledged','resolved','recurring','escalated')
);

-- =========================================================
-- 8. UPDATE PATIENT_SUMMARIES TABLE
-- =========================================================
ALTER TABLE patient_summaries ADD COLUMN IF NOT EXISTS snapshot_data JSONB;
ALTER TABLE patient_summaries ADD COLUMN IF NOT EXISTS open_flags_count JSONB;
ALTER TABLE patient_summaries ADD COLUMN IF NOT EXISTS version INT DEFAULT 1;
ALTER TABLE patient_summaries ADD COLUMN IF NOT EXISTS generated_by_model TEXT DEFAULT 'google/gemini-2.5-flash';
ALTER TABLE patient_summaries ADD COLUMN IF NOT EXISTS trigger_event TEXT;

-- =========================================================
-- 9. NEW TABLE: clinical_directives
-- =========================================================
CREATE TABLE IF NOT EXISTS clinical_directives (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id             UUID NOT NULL REFERENCES patients(id),
    source_document_id     UUID NOT NULL REFERENCES documents(id),
    source_extraction_id   UUID NOT NULL REFERENCES document_extractions(id),
    directive_type         TEXT NOT NULL CHECK (directive_type IN (
                             'hold_medication','stop_medication','start_medication',
                             'avoid_drug_class','avoid_specific_drug','avoid_food',
                             'avoid_activity','dose_adjustment','timing_change',
                             'monitor_before_continuing','conditional_restart','other'
                           )),
    target_entity          TEXT NOT NULL,
    target_entity_type     TEXT CHECK (target_entity_type IN ('medication','drug_class','food','activity','lab_test','other')),
    instruction_text       TEXT NOT NULL,
    condition_for_execution TEXT,
    condition_type         TEXT CHECK (condition_type IN ('lab_threshold','time_elapsed','clinical_event','doctor_review','indefinite')),
    condition_met          BOOLEAN,
    prescribing_doctor_id  UUID REFERENCES doctors(id),
    directive_date         DATE,
    cross_reference_status TEXT DEFAULT 'document_only' CHECK (cross_reference_status IN ('cross_verified','document_only','unverifiable','contradicted')),
    extraction_confidence  NUMERIC(4,3),
    currency_uncertain     BOOLEAN DEFAULT FALSE,
    is_active              BOOLEAN DEFAULT TRUE,
    created_at             TIMESTAMPTZ DEFAULT NOW(),
    updated_at             TIMESTAMPTZ DEFAULT NOW()
);

-- =========================================================
-- 10. NEW TABLE: monitoring_instructions
-- =========================================================
CREATE TABLE IF NOT EXISTS monitoring_instructions (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id               UUID NOT NULL REFERENCES patients(id),
    source_document_id       UUID NOT NULL REFERENCES documents(id),
    test_or_vital            TEXT NOT NULL,
    monitoring_category      TEXT CHECK (monitoring_category IN ('lab_test','vital_sign','clinical_review','imaging','other')),
    frequency_text           TEXT,
    timing_text              TEXT,
    trigger_event            TEXT,
    urgency                  TEXT CHECK (urgency IN ('routine','urgent','stat')),
    ordered_by               TEXT,
    due_date                 DATE,
    status                   TEXT DEFAULT 'pending' CHECK (status IN ('pending','completed','overdue','cancelled')),
    completed_by_document_id UUID REFERENCES documents(id),
    extraction_confidence    NUMERIC(4,3),
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    updated_at               TIMESTAMPTZ DEFAULT NOW()
);

-- =========================================================
-- 11. NEW TABLE: restrictions
-- =========================================================
CREATE TABLE IF NOT EXISTS restrictions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id            UUID NOT NULL REFERENCES patients(id),
    source_document_id    UUID NOT NULL REFERENCES documents(id),
    restriction_type      TEXT CHECK (restriction_type IN ('drug_class','specific_drug','food_substance','food_category','activity','other')),
    target                TEXT NOT NULL,
    reason                TEXT,
    instruction_text      TEXT NOT NULL,
    cross_reference_status TEXT DEFAULT 'document_only' CHECK (cross_reference_status IN ('cross_verified','document_only','unverifiable','contradicted')),
    current_violation     BOOLEAN DEFAULT FALSE,
    violation_detail      TEXT,
    extraction_confidence NUMERIC(4,3),
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- =========================================================
-- 12. NEW TABLE: culture_findings
-- =========================================================
CREATE TABLE IF NOT EXISTS culture_findings (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id                  UUID NOT NULL REFERENCES patients(id),
    source_document_id          UUID NOT NULL REFERENCES documents(id),
    organism_name               TEXT,
    organism_normalized         TEXT,
    specimen_type               TEXT,
    collection_date             DATE,
    resistant_to                TEXT[],
    sensitive_to                TEXT[],
    intermediate_to             TEXT[],
    current_antibiotic_conflict BOOLEAN DEFAULT FALSE,
    conflict_detail             TEXT,
    extraction_confidence       NUMERIC(4,3),
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- =========================================================
-- 13. NEW TABLE: clinical_findings (reasoning engine output)
-- =========================================================
CREATE TABLE IF NOT EXISTS clinical_findings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id          UUID NOT NULL REFERENCES patients(id),
    finding_type        TEXT NOT NULL,
    dimension           TEXT,
    severity            TEXT NOT NULL CHECK (severity IN ('critical','high','moderate','low','informational')),
    title               TEXT NOT NULL,
    clinical_evidence   JSONB NOT NULL,
    source_documents    TEXT[],
    related_entities    JSONB,
    is_patient_specific BOOLEAN DEFAULT TRUE,
    patient_context     TEXT,
    confidence          NUMERIC(4,3),
    status              TEXT DEFAULT 'open' CHECK (status IN ('open','monitoring','resolved','recurring','escalated','acknowledged')),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    resolved_reason     TEXT
);

-- =========================================================
-- 14. NEW TABLE: temporal_logic_evaluations
-- =========================================================
CREATE TABLE IF NOT EXISTS temporal_logic_evaluations (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id         UUID NOT NULL REFERENCES patients(id),
    parent_entity_type TEXT NOT NULL CHECK (parent_entity_type IN ('clinical_directive','monitoring_instruction','medication')),
    parent_entity_id   UUID NOT NULL,
    logic_type         TEXT NOT NULL CHECK (logic_type IN ('time_elapsed','lab_threshold_met','clinical_event','doctor_review_done','indefinite')),
    condition_text     TEXT NOT NULL,
    evaluation_status  TEXT DEFAULT 'pending' CHECK (evaluation_status IN ('pending','met','not_met','unknown')),
    evidence_used      JSONB,
    evaluated_at       TIMESTAMPTZ,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);

-- =========================================================
-- 15. NEW TABLE: reasoning_runs
-- =========================================================
CREATE TABLE IF NOT EXISTS reasoning_runs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id            UUID NOT NULL REFERENCES patients(id),
    trigger_event         TEXT CHECK (trigger_event IN ('onboarding','new_document','manual_rerun')),
    patient_state_hash    TEXT,
    documents_attempted   INT DEFAULT 0,
    documents_succeeded   INT DEFAULT 0,
    documents_failed      INT DEFAULT 0,
    entities_extracted    JSONB,
    normalization_failures INT DEFAULT 0,
    dimensions_run        TEXT[],
    findings_generated    INT DEFAULT 0,
    findings_discarded    INT DEFAULT 0,
    discarded_reasons     JSONB,
    flags_generated       INT DEFAULT 0,
    llm_calls_made        INT DEFAULT 0,
    llm_calls_failed      INT DEFAULT 0,
    total_processing_ms   INT,
    status                TEXT CHECK (status IN ('success','partial','failed')),
    error_message         TEXT,
    raw_llm_response      JSONB,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- =========================================================
-- 16. NEW TABLE: medicine_composition_cache (global)
-- =========================================================
CREATE TABLE IF NOT EXISTS medicine_composition_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_name      TEXT NOT NULL,
    brand_name_lower TEXT GENERATED ALWAYS AS (LOWER(brand_name)) STORED,
    generic_name    TEXT NOT NULL,
    drug_class      TEXT,
    composition     TEXT,
    cached_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (brand_name_lower)
);

-- =========================================================
-- 17. NEW TABLE: drug_interaction_cache (global)
-- =========================================================
CREATE TABLE IF NOT EXISTS drug_interaction_cache (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_1_generic    TEXT NOT NULL,
    drug_2_generic    TEXT NOT NULL,
    interaction_found BOOLEAN NOT NULL,
    severity          TEXT CHECK (severity IN ('none','low','moderate','high','critical')),
    description       TEXT,
    mechanism         TEXT,
    source            TEXT CHECK (source IN ('openfda','drugbank','llm')),
    cached_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (drug_1_generic, drug_2_generic)
);

-- =========================================================
-- 18. NEW TABLE: drug_condition_cache (global)
-- =========================================================
CREATE TABLE IF NOT EXISTS drug_condition_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_generic    TEXT NOT NULL,
    condition_name  TEXT NOT NULL,
    contraindicated BOOLEAN NOT NULL,
    severity        TEXT CHECK (severity IN ('none','low','moderate','high','critical')),
    description     TEXT,
    source          TEXT DEFAULT 'llm',
    cached_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (drug_generic, condition_name)
);

-- =========================================================
-- 19. NEW TABLE: contradictions
-- =========================================================
CREATE TABLE IF NOT EXISTS contradictions (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id         UUID NOT NULL REFERENCES patients(id),
    finding_id         UUID REFERENCES clinical_findings(id),
    contradiction_type TEXT NOT NULL,
    severity           TEXT NOT NULL CHECK (severity IN ('critical','high','moderate','low')),
    description        TEXT NOT NULL,
    evidence           JSONB NOT NULL,
    entity_a           TEXT,
    entity_b           TEXT,
    status             TEXT DEFAULT 'open' CHECK (status IN ('open','resolved','acknowledged')),
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

-- Done.
SELECT 'v3.0 migration complete' AS result;
