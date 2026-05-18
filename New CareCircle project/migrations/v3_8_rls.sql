-- migrations/v3_8_rls.sql
-- Row Level Security for all tables + Storage bucket policy.
-- Run ONCE in Supabase SQL Editor AFTER all other migrations.
--
-- KEY FACT: The backend uses SUPABASE_SERVICE_KEY (service role).
-- Service role BYPASSES all RLS policies automatically.
-- These policies only apply to direct Supabase client access
-- using user JWTs (e.g., future mobile/web frontend).
--
-- Access model: a user can only read data for patients they are
-- a guardian of (linked via patient_guardians table).


-- ─────────────────────────────────────────────────────────────────
-- HELPER: is_patient_guardian(patient_id)
-- TRUE if the current JWT user is a guardian of the given patient.
-- SECURITY DEFINER so it can read patient_guardians regardless of
-- that table's own RLS policies.
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION is_patient_guardian(pid UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM patient_guardians pg
    JOIN user_profiles up ON up.id = pg.user_profile_id
    WHERE pg.patient_id = pid
      AND up.auth_user_id = auth.uid()
      AND pg.is_deleted = FALSE
      AND up.is_deleted = FALSE
  );
$$;


-- ─────────────────────────────────────────────────────────────────
-- user_profiles: each user sees only their own profile
-- ─────────────────────────────────────────────────────────────────
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_profiles_select_own"
  ON user_profiles FOR SELECT
  USING (auth_user_id = auth.uid());


-- ─────────────────────────────────────────────────────────────────
-- patients: guardian sees their patients
-- ─────────────────────────────────────────────────────────────────
ALTER TABLE patients ENABLE ROW LEVEL SECURITY;

CREATE POLICY "patients_select_guardian"
  ON patients FOR SELECT
  USING (is_patient_guardian(id));


-- ─────────────────────────────────────────────────────────────────
-- patient_guardians: users see their own guardian links
-- ─────────────────────────────────────────────────────────────────
ALTER TABLE patient_guardians ENABLE ROW LEVEL SECURITY;

CREATE POLICY "patient_guardians_select_own"
  ON patient_guardians FOR SELECT
  USING (
    user_profile_id IN (
      SELECT id FROM user_profiles WHERE auth_user_id = auth.uid()
    )
  );


-- ─────────────────────────────────────────────────────────────────
-- Patient-data tables: all use is_patient_guardian(patient_id)
-- ─────────────────────────────────────────────────────────────────

ALTER TABLE doctors ENABLE ROW LEVEL SECURITY;
CREATE POLICY "doctors_select_guardian"
  ON doctors FOR SELECT USING (is_patient_guardian(patient_id));

-- documents: caregivers can view/download their patient's documents
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "documents_select_guardian"
  ON documents FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE document_extractions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "document_extractions_select_guardian"
  ON document_extractions FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE medications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "medications_select_guardian"
  ON medications FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE diagnoses ENABLE ROW LEVEL SECURITY;
CREATE POLICY "diagnoses_select_guardian"
  ON diagnoses FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE allergies ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allergies_select_guardian"
  ON allergies FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE lab_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "lab_results_select_guardian"
  ON lab_results FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE open_flags ENABLE ROW LEVEL SECURITY;
CREATE POLICY "open_flags_select_guardian"
  ON open_flags FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE patient_summaries ENABLE ROW LEVEL SECURITY;
CREATE POLICY "patient_summaries_select_guardian"
  ON patient_summaries FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE drug_safety_checks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "drug_safety_checks_select_guardian"
  ON drug_safety_checks FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE telegram_groups ENABLE ROW LEVEL SECURITY;
CREATE POLICY "telegram_groups_select_guardian"
  ON telegram_groups FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE clinical_directives ENABLE ROW LEVEL SECURITY;
CREATE POLICY "clinical_directives_select_guardian"
  ON clinical_directives FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE monitoring_instructions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "monitoring_instructions_select_guardian"
  ON monitoring_instructions FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE restrictions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "restrictions_select_guardian"
  ON restrictions FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE culture_findings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "culture_findings_select_guardian"
  ON culture_findings FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE clinical_findings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "clinical_findings_select_guardian"
  ON clinical_findings FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE temporal_logic_evaluations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "temporal_logic_evaluations_select_guardian"
  ON temporal_logic_evaluations FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE reasoning_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "reasoning_runs_select_guardian"
  ON reasoning_runs FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE caregiver_concerns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "caregiver_concerns_select_guardian"
  ON caregiver_concerns FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE patient_action_summaries ENABLE ROW LEVEL SECURITY;
CREATE POLICY "patient_action_summaries_select_guardian"
  ON patient_action_summaries FOR SELECT USING (is_patient_guardian(patient_id));


-- ─────────────────────────────────────────────────────────────────
-- Cache tables: shared system data, no patient_id.
-- Any authenticated user can read — these are drug/medicine lookups.
-- ─────────────────────────────────────────────────────────────────
ALTER TABLE medicine_composition_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "medicine_cache_authenticated_read"
  ON medicine_composition_cache FOR SELECT
  USING (auth.role() = 'authenticated');

ALTER TABLE drug_interaction_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "drug_interaction_cache_authenticated_read"
  ON drug_interaction_cache FOR SELECT
  USING (auth.role() = 'authenticated');

ALTER TABLE drug_condition_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "drug_condition_cache_authenticated_read"
  ON drug_condition_cache FOR SELECT
  USING (auth.role() = 'authenticated');


-- ─────────────────────────────────────────────────────────────────
-- Longitudinal tables
-- ─────────────────────────────────────────────────────────────────
ALTER TABLE document_upload_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "document_upload_events_select_guardian"
  ON document_upload_events FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE longitudinal_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "longitudinal_runs_select_guardian"
  ON longitudinal_runs FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE medication_state_transitions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "medication_state_transitions_select_guardian"
  ON medication_state_transitions FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE longitudinal_findings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "longitudinal_findings_select_guardian"
  ON longitudinal_findings FOR SELECT USING (is_patient_guardian(patient_id));

ALTER TABLE longitudinal_caregiver_concerns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "longitudinal_caregiver_concerns_select_guardian"
  ON longitudinal_caregiver_concerns FOR SELECT USING (is_patient_guardian(patient_id));

-- longitudinal_pipeline_logs has no direct patient_id — join via run
ALTER TABLE longitudinal_pipeline_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "longitudinal_pipeline_logs_select_guardian"
  ON longitudinal_pipeline_logs FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM longitudinal_runs lr
      WHERE lr.id = longitudinal_pipeline_logs.run_id
        AND is_patient_guardian(lr.patient_id)
    )
  );


-- ─────────────────────────────────────────────────────────────────
-- STORAGE RLS: documents bucket
-- Path format: {patient_id}/{document_type}/{timestamp}_{filename}
--
-- Signed URLs (generated by backend) already bypass storage RLS.
-- This policy covers direct bucket access from the frontend.
-- Caregivers can read/download files for their own patients.
-- ─────────────────────────────────────────────────────────────────
CREATE POLICY "documents_bucket_guardian_download"
  ON storage.objects FOR SELECT
  USING (
    bucket_id = 'documents'
    AND is_patient_guardian(
      ((storage.foldername(name))[1])::uuid
    )
  );
