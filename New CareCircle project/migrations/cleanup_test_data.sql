-- migrations/cleanup_test_data.sql
-- Deletes ALL patient data for a fresh start.
-- user_profiles are preserved (tied to Supabase Auth accounts).
-- Run in Supabase SQL Editor.
--
-- IMPORTANT: This is IRREVERSIBLE. Back up first if needed.
-- The circular FK between longitudinal_runs ↔ document_upload_events
-- is broken first by nulling the reverse pointer before deletion.

BEGIN;

-- Step 1: Break circular / cross-table FKs before any deletes
UPDATE longitudinal_runs SET upload_event_id = NULL;
UPDATE clinical_findings SET last_seen_run_id = NULL;

-- Step 2: Longitudinal pipeline (most dependent, delete first)
DELETE FROM longitudinal_pipeline_logs;
DELETE FROM longitudinal_caregiver_concerns;
DELETE FROM longitudinal_findings;
DELETE FROM medication_state_transitions;
DELETE FROM document_upload_events;
DELETE FROM longitudinal_runs;

-- Step 3: Onboarding reasoning & analysis (caregiver_concerns before reasoning_runs)
DELETE FROM temporal_logic_evaluations;
DELETE FROM caregiver_concerns;
DELETE FROM patient_action_summaries;
DELETE FROM clinical_findings;
DELETE FROM reasoning_runs;
DELETE FROM open_flags;
DELETE FROM drug_safety_checks;
DELETE FROM monitoring_instructions;
DELETE FROM clinical_directives;
DELETE FROM restrictions;
DELETE FROM culture_findings;
DELETE FROM patient_summaries;

-- Step 4: Clinical data
DELETE FROM lab_results;
DELETE FROM diagnoses;
DELETE FROM allergies;
DELETE FROM medications;
DELETE FROM doctors;

-- Step 5: Documents
DELETE FROM document_extractions;
DELETE FROM documents;

-- Step 6: Patient links and patients
DELETE FROM patient_guardians;
DELETE FROM patients;

-- Cache tables are shared system data — intentionally NOT cleared.
-- They speed up future runs and contain no patient-identifying info.

COMMIT;
