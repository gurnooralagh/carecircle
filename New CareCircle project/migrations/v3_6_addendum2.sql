-- Addendum 2: Three Targeted Fixes
-- Run in Supabase SQL Editor AFTER v3_5_caregiver_concerns.sql

-- =========================================================
-- FIX 1C: guardian taking status on medications
-- =========================================================
ALTER TABLE medications
  ADD COLUMN IF NOT EXISTS guardian_taking_status TEXT
    CHECK (guardian_taking_status IN ('yes_currently_taking','no_stopped','not_sure')),
  ADD COLUMN IF NOT EXISTS guardian_taking_confirmed_at TIMESTAMPTZ;

-- =========================================================
-- FIX 3: patient_action_summaries table (Phase 6.6)
-- =========================================================
CREATE TABLE IF NOT EXISTS patient_action_summaries (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id         UUID NOT NULL REFERENCES patients(id),
  reasoning_run_id   UUID REFERENCES reasoning_runs(id),
  do_now             JSONB NOT NULL DEFAULT '[]',
  follow_up          JSONB NOT NULL DEFAULT '[]',
  ongoing_monitoring JSONB NOT NULL DEFAULT '[]',
  generated_at       TIMESTAMPTZ DEFAULT NOW(),
  is_current         BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_patient_action_summaries_patient
  ON patient_action_summaries (patient_id, is_current);
