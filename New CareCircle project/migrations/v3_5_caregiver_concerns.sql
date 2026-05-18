-- Phase 6.5 — Presentation Orchestration Layer
-- Run this in Supabase SQL Editor AFTER v3_schema.sql

-- =========================================================
-- Add orchestration tracking fields to reasoning_runs
-- =========================================================
ALTER TABLE reasoning_runs
  ADD COLUMN IF NOT EXISTS orchestration_status TEXT
    DEFAULT 'pending'
    CHECK (orchestration_status IN ('pending','running','done','fallback','failed')),
  ADD COLUMN IF NOT EXISTS orchestration_error TEXT,
  ADD COLUMN IF NOT EXISTS concerns_generated  INT DEFAULT 0;

-- =========================================================
-- NEW TABLE: caregiver_concerns
-- Produced by Phase 6.5. Never modified by any other phase.
-- =========================================================
CREATE TABLE IF NOT EXISTS caregiver_concerns (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id               UUID NOT NULL REFERENCES patients(id),
  reasoning_run_id         UUID REFERENCES reasoning_runs(id),

  concern_type             TEXT NOT NULL CHECK (concern_type IN (
                             'grouped',
                             'independent',
                             'partial_match_source'
                           )),

  priority                 TEXT NOT NULL CHECK (priority IN (
                             'critical_concern',
                             'high_priority',
                             'moderate',
                             'for_your_awareness'
                           )),

  title                    TEXT NOT NULL,
  summary                  TEXT NOT NULL,
  what_was_found           TEXT NOT NULL,
  why_it_matters           TEXT NOT NULL,
  what_to_do               TEXT NOT NULL,

  evidence                 JSONB NOT NULL DEFAULT '[]',
  source_documents         TEXT[],

  contributing_flag_ids    UUID[],
  contributing_finding_ids UUID[],

  is_partial_match         BOOLEAN DEFAULT FALSE,
  partial_match_group_id   UUID,

  brand_names_used         JSONB,

  display_order            INT,

  status                   TEXT DEFAULT 'active'
    CHECK (status IN ('active','resolved','acknowledged')),

  created_at               TIMESTAMPTZ DEFAULT NOW(),
  updated_at               TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast patient lookups
CREATE INDEX IF NOT EXISTS idx_caregiver_concerns_patient
  ON caregiver_concerns (patient_id, status, display_order);
