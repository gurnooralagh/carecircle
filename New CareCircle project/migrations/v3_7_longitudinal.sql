-- migrations/v3_7_longitudinal.sql
-- Run ONCE in Supabase SQL editor.
-- Creates 6 new tables and alters clinical_findings + patients.

-- TABLE 1: longitudinal_runs (created before document_upload_events so FK works)
CREATE TABLE IF NOT EXISTS longitudinal_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    baseline_patient_state JSONB,
    new_medications INT DEFAULT 0,
    changed_medications INT DEFAULT 0,
    new_lab_results INT DEFAULT 0,
    new_diagnoses INT DEFAULT 0,
    new_directives INT DEFAULT 0,
    findings_new INT DEFAULT 0,
    findings_recurring INT DEFAULT 0,
    findings_escalated INT DEFAULT 0,
    findings_resolved INT DEFAULT 0,
    findings_suppressed INT DEFAULT 0,
    status TEXT DEFAULT 'success' CHECK (status IN ('success', 'partial', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 2: document_upload_events
CREATE TABLE IF NOT EXISTS document_upload_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    longitudinal_run_id UUID REFERENCES longitudinal_runs(id),
    processing_status TEXT DEFAULT 'pending'
        CHECK (processing_status IN ('pending','extracting','reconciling','reasoning','orchestrating','ready','failed')),
    uploaded_files JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add reverse FK from longitudinal_runs → document_upload_events (circular, nullable)
ALTER TABLE longitudinal_runs ADD COLUMN IF NOT EXISTS upload_event_id UUID REFERENCES document_upload_events(id);

-- TABLE 3: medication_state_transitions
CREATE TABLE IF NOT EXISTS medication_state_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES longitudinal_runs(id),
    upload_event_id UUID REFERENCES document_upload_events(id),
    medication_id UUID REFERENCES medications(id),
    drug_name_brand TEXT,
    drug_name_generic TEXT,
    transition_type TEXT NOT NULL
        CHECK (transition_type IN ('added','removed','continued','dose_changed','frequency_changed','status_changed','restarted')),
    prior_dose_mg NUMERIC,
    new_dose_mg NUMERIC,
    prior_frequency TEXT,
    new_frequency TEXT,
    source_document TEXT,
    guardian_confirmed BOOLEAN DEFAULT FALSE,
    guardian_action TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 4: longitudinal_findings
CREATE TABLE IF NOT EXISTS longitudinal_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES longitudinal_runs(id),
    clinical_finding_id UUID REFERENCES clinical_findings(id),
    prior_clinical_finding_id UUID REFERENCES clinical_findings(id),
    classification TEXT NOT NULL
        CHECK (classification IN ('new','recurring','escalated','resolved','improved')),
    is_suppressed_from_caregiver BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 5: longitudinal_caregiver_concerns
CREATE TABLE IF NOT EXISTS longitudinal_caregiver_concerns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES longitudinal_runs(id),
    upload_event_id UUID REFERENCES document_upload_events(id),
    concern_type TEXT,
    concern_category TEXT
        CHECK (concern_category IN ('new','escalated','resolved','improved','nudge')),
    priority TEXT,
    title TEXT,
    summary TEXT,
    what_was_found TEXT,
    why_it_matters TEXT,
    what_to_do TEXT,
    evidence JSONB,
    source_documents JSONB,
    is_nudge BOOLEAN DEFAULT FALSE,
    nudge_original_finding_date TIMESTAMPTZ,
    display_order INT DEFAULT 0,
    is_acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 6: longitudinal_pipeline_logs
CREATE TABLE IF NOT EXISTS longitudinal_pipeline_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES longitudinal_runs(id),
    upload_event_id UUID REFERENCES document_upload_events(id),
    phase TEXT,
    event TEXT,
    level TEXT DEFAULT 'INFO',
    detail JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_long_logs_run_id ON longitudinal_pipeline_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_long_logs_level ON longitudinal_pipeline_logs(level);
CREATE INDEX IF NOT EXISTS idx_long_logs_phase ON longitudinal_pipeline_logs(phase);

-- ALTER existing tables (ADD COLUMN only — never drops or modifies existing columns)
ALTER TABLE clinical_findings ADD COLUMN IF NOT EXISTS last_seen_run_id UUID REFERENCES longitudinal_runs(id);
ALTER TABLE clinical_findings ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;
ALTER TABLE clinical_findings ADD COLUMN IF NOT EXISTS times_seen INT DEFAULT 1;

ALTER TABLE patients ADD COLUMN IF NOT EXISTS post_onboarding_upload_count INT DEFAULT 0;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS last_document_upload_at TIMESTAMPTZ;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS longitudinal_status TEXT DEFAULT 'idle'
    CHECK (longitudinal_status IN ('idle','processing','ready','failed'));

-- ADD upload_context to documents if not already present (needed to tag post-onboarding docs)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS upload_context TEXT DEFAULT 'onboarding';

-- ADD resolved_since_last_upload to patient_action_summaries (longitudinal only field)
ALTER TABLE patient_action_summaries ADD COLUMN IF NOT EXISTS resolved_since_last_upload JSONB DEFAULT '[]';
