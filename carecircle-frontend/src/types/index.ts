// ─── Auth ────────────────────────────────────────────────────────────────────

export interface AuthUser {
  user_id: string
  email: string
  full_name: string
}

// ─── Patient ─────────────────────────────────────────────────────────────────

export interface Patient {
  patient_id: string
  full_name: string
  date_of_birth: string
  gender: 'Male' | 'Female' | 'Other'
  weight_kg?: number
  height_cm?: number
  city?: string
  active_diagnoses?: string[]
  known_allergies?: string[]
  ai_summary?: string
  primary_doctor?: PrimaryDoctor
}

export interface PrimaryDoctor {
  name: string
  specialty: string
  phone?: string
}

// ─── Dashboard Summary ───────────────────────────────────────────────────────

export interface AnalysisRun {
  run_id: string
  run_type: 'onboarding' | 'longitudinal'
  label: string
  run_date: string
  upload_event_id?: string
}

export interface DashboardSummary {
  patient: {
    full_name: string
    date_of_birth: string
    gender: string
    city?: string
  }
  last_analysis_at: string
  runs: AnalysisRun[]
  active_concerns_count: number
  active_medications_count: number
  top_concerns: Concern[]
  action_summary?: {
    do_now: ActionItem[]
    follow_up: ActionItem[]
    keep_monitoring: ActionItem[]
  } | null
}

// ─── Concerns / Findings ─────────────────────────────────────────────────────

export interface Concern {
  id?: string
  title: string
  summary: string
  priority: 'critical_concern' | 'high_priority' | 'moderate' | 'for_your_awareness'
  concern_type?: 'grouped' | 'independent' | 'partial_match_source'
  what_was_found: string
  why_it_matters: string
  what_to_do: string
  source_documents?: string[]
  status?: 'new' | 'escalated' | 'resolved' | 'improved' | 'existing'
  created_at?: string
}

export interface FindingsResponse {
  concerns: Concern[]
  concern_summary?: {
    critical_concern: number
    high_priority: number
    moderate: number
    for_your_awareness: number
  }
  action_summary?: ActionSummary
}

// ─── Medications ─────────────────────────────────────────────────────────────

export interface Medication {
  medication_id: string
  drug_name_brand?: string
  drug_name_generic?: string
  drug_name?: string
  dose_text?: string
  dosage?: string
  frequency?: string
  source?: string
  dedup_status?: string
  status?: 'active' | 'held' | 'stopped'
  confidence?: number
  guardian_confirmed?: boolean
}

export interface MedicationConfirmation {
  medication_id: string
  action: 'confirm' | 'remove' | 'edit'
  guardian_taking_status?: 'yes_currently_taking' | 'no_stopped' | 'not_sure'
  guardian_confirmed_dose_text?: string
  guardian_confirmed_frequency?: string
  updated_fields?: { drug_name_brand?: string }
}

// ─── Documents ───────────────────────────────────────────────────────────────

export interface Document {
  document_id: string
  filename: string
  document_type: 'Prescription' | 'Lab Report' | 'Discharge Summary' | 'Other'
  document_date?: string
  upload_date: string
  file_url: string
  processing_status: 'pending' | 'processing' | 'completed' | 'failed'
}

// ─── Onboarding ──────────────────────────────────────────────────────────────

export interface OnboardingStatus {
  status: 'pending' | 'processing' | 'ready' | 'failed'
  progress?: number
}

export interface ActionSummary {
  do_now: ActionItem[]
  follow_up: ActionItem[]
  keep_monitoring: ActionItem[]
  ongoing_monitoring?: ActionItem[]
}

export interface ActionItem {
  id: string
  text: string
  category: 'do_now' | 'follow_up' | 'keep_monitoring'
}

// ─── To-dos ──────────────────────────────────────────────────────────────────

export interface TodoItem {
  todo_id: string
  text: string
  priority: 'high' | 'medium' | 'low'
  completed: boolean
  category?: string
}

// ─── Longitudinal Upload ─────────────────────────────────────────────────────

export interface UploadStatus {
  status: 'pending' | 'processing' | 'reconciling' | 'analysing' | 'ready' | 'failed'
  upload_event_id: string
}

export interface MedicationReconciliation {
  existing_medications: ExistingMedicationReconcile[]
  newly_extracted_medications: NewMedicationReconcile[]
  continued_medications: number
}

export interface ExistingMedicationReconcile {
  medication_id: string
  drug_name_brand?: string
  drug_name_generic?: string
  dose_text?: string
  frequency?: string
  status?: string
}

export interface NewMedicationReconcile {
  transition_id: string
  transition_type: 'added' | 'removed' | 'dose_changed' | 'frequency_changed' | 'restarted' | string
  drug_name_brand?: string
  drug_name_generic?: string
  prior_dose_mg?: string | null
  new_dose_mg?: string | null
  prior_frequency?: string | null
  new_frequency?: string | null
  source_document?: string | null
}

export interface ReconciliationConfirmation {
  confirmations: {
    transition_id: string
    action: 'confirm' | 'edit' | 'remove'
    guardian_action?: 'still_taking' | 'stopped' | 'held' | 'not_sure'
    new_dose_mg?: string | null
    new_frequency?: string | null
  }[]
}

export interface LongitudinalFindings {
  medication_changes: MedicationChange[]
  summary: {
    new_count: number
    escalated_count: number
    improved_count: number
    resolved_count: number
  }
  concerns: Concern[]
  todos: {
    do_now: TodoItem[]
    follow_up: TodoItem[]
    keep_monitoring: TodoItem[]
    resolved?: TodoItem[]
  }
}

export interface MedicationChange {
  medication_id?: string
  brand_name: string
  change_type: 'added' | 'removed' | 'modified' | 'unchanged'
  previous_dose?: string
  new_dose?: string
}

// ─── Emergency ───────────────────────────────────────────────────────────────

export interface EmergencySummary {
  patient: Patient
  active_medications: Medication[]
  allergies: string[]
  active_conditions: string[]
  primary_doctor?: PrimaryDoctor
  guardian_contacts: GuardianContact[]
  recent_documents: Document[]
}

export interface GuardianContact {
  name: string
  email: string
  phone?: string
  relationship?: string
}

// ─── File Upload ─────────────────────────────────────────────────────────────

export interface UploadFile {
  id: string
  file: File
  document_type: 'Prescription' | 'Lab Report' | 'Discharge Summary' | 'Other'
  document_date: string
}
