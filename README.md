# CareCircle

**Frontend (live):** https://carecircle-livid.vercel.app/

A medical records management app for family caregivers. Upload prescriptions, lab reports, and discharge summaries for a loved one — CareCircle extracts the data, checks for drug interactions and concerning lab values, and gives you a plain-language summary with a clear action plan.

---

## What it does

1. **Onboarding** — create a patient profile and upload their medical documents
2. **AI analysis** — the backend extracts medications and lab results, checks drug safety, and generates a prioritised list of concerns
3. **Dashboard** — view the analysis, to-do list, and all uploaded documents
4. **Follow-up uploads** — upload new documents at any time; CareCircle compares them against the existing record, reconciles medication changes, and shows you what changed

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4 |
| State / data | Zustand, TanStack Query, React Hook Form + Zod |
| Backend | FastAPI (Python 3.12), Uvicorn |
| Database / auth | Supabase (PostgreSQL + Row Level Security) |
| File storage | Supabase Storage |
| AI | OpenRouter API - Gemini 2.0 Flash (LLM) and Open AI mini 4 (OCR) |
| PDF extraction | pdfplumber, PyMuPDF |
| Frontend hosting | Vercel |
| Backend hosting | Railway |

---

## Project structure

```
carecircle/
├── carecircle-frontend/        # React app (deployed to Vercel)
│   ├── src/
│   │   ├── pages/              # Route-level components
│   │   │   ├── auth/           # Login / sign-up
│   │   │   ├── onboarding/     # 5-step onboarding flow
│   │   │   └── dashboard/      # Main dashboard + upload flow
│   │   ├── components/         # Shared UI components
│   │   ├── store/              # Zustand stores (patient, toast)
│   │   ├── lib/                # Supabase client, Axios instance, utils
│   │   └── types/              # Shared TypeScript types
│   ├── vercel.json             # SPA routing config
│   └── .env.example
│
├── New CareCircle project/     # FastAPI backend (deployed to Railway)
│   ├── routers/                # API route handlers
│   │   ├── auth.py             # /api/auth/*
│   │   ├── documents.py        # /api/documents/*
│   │   ├── onboarding.py       # /api/onboarding/*
│   │   ├── longitudinal.py     # /api/longitudinal/*
│   │   └── dashboard.py        # /api/dashboard/*
│   ├── services/               # Business logic
│   │   ├── extraction_pipeline.py
│   │   ├── llm.py              # OpenRouter calls
│   │   ├── drug_safety.py
│   │   ├── ocr.py / pdf_extractor.py
│   │   ├── longitudinal_pipeline.py
│   │   └── ...
│   ├── db/
│   │   ├── schema.sql          # Full DB schema
│   │   └── client.py           # Supabase client wrapper
│   ├── models/                 # Pydantic request/response models
│   ├── migrations/             # SQL migration files
│   ├── tests/                  # pytest test suite
│   ├── main.py                 # FastAPI app entry point
│   ├── requirements.txt
│   └── .env.example
│
└── railway.toml                # Railway build config (points at backend dir)
```

---

## How data is processed

When a document is uploaded, it goes through a multi-stage backend pipeline running entirely in the background.

### Stage 1 — Document extraction
Each uploaded file is run through two parallel extraction methods:
- **PDF text extraction** (pdfplumber + PyMuPDF) — pulls structured text from digital PDFs
- **OCR** — runs on scanned or image-based pages where text extraction fails - Model (Open AI Gpt mini 4)

The raw text from both methods is merged and cleaned before passing to the AI.

### Stage 2 — AI extraction (Gemini via OpenRouter)
The cleaned document text is sent to gemnin 2.0 flash with structured prompts that extract:
- **Medications** — brand name, generic name, dose, frequency, timing, prescribing doctor
- **Lab results** — test name, value, unit, reference range, date
- **Diagnoses** — condition name, status, source
- **Allergies** — allergen, reaction type, severity
- **Doctor details** — name, specialty, hospital

Each extracted entity is returned with a confidence score. Low-confidence extractions are rerun again.

### Stage 3 — Deduplication and normalisation
- Medications extracted from multiple documents are cross-referenced and deduplicated
- Drug names are normalised to a canonical brand/generic pair
- Dose conflicts (same drug, two different doses across documents) are surfaced as flags
- Stopped medications still appearing in a new prescription are flagged

### Stage 4 — Drug safety analysis
All confirmed medications are checked together for:
- **Drug-drug interactions** — pairs of medications with known interaction risks
- **Drug-condition contraindications** — medications that conflict with a patient's diagnosed conditions
- **Drug-allergy conflicts** — medications the patient is known to be allergic to
- **Dosage concerns** — doses that appear high or unusual for the patient's age/weight

Each finding is classified with a risk level and a plain-language explanation.

### Stage 5 — Concern generation
All flags and safety findings are grouped and ranked by an AI reasoning step into **caregiver concerns** — the final output shown to the user. Each concern includes:
- A plain-language title and summary
- What was found and why it matters
- A specific action to take
- The source document(s) that triggered it
- A priority level: **Critical concern**, **High priority**, **Moderate**, or **For your awareness**

### Stage 6 — Action plan
A final AI pass across all concerns generates a structured to-do list:
- **Do now** — urgent actions (e.g. call the doctor today, do not take this medication)
- **Follow up** — actions for the next appointment or within days
- **Keep monitoring** — ongoing things to watch

---

## What the output looks like

After processing, the guardian sees:

**Findings screen** — a prioritised list of concerns, each card showing the plain-language summary, why it matters, and exactly what to do. Concerns are colour-coded by priority.

**Action plan** — the do now / follow up / keep monitoring checklist, which the guardian can tick off.

**Dashboard** — a home screen showing the active concern count, current medication count, and the top concerns at a glance. Updates automatically after every new upload.

**Medications tab** — the full deduplicated medication list with dose, frequency, source document, and guardian-confirmed taking status.

**Documents tab** — all uploaded files with extraction status (pending / processing / analysed / failed) and a link to view the original file.

**Longitudinal view** — when new documents are uploaded after onboarding, the pipeline compares them against the existing record and shows what changed: new concerns, escalated concerns, resolved concerns, medication changes (added / removed / dose changed / frequency changed).

---

## Key user flows

```
Sign up → Onboarding (patient details → upload docs → AI analysis → findings → action plan)
             ↓
         Dashboard (concerns, to-dos, medications, documents)
             ↓
         Upload new documents → Medication reconciliation → What changed → Updated dashboard
```

---

## Document types supported

- Prescription
- Lab Report
- Discharge Summary
- Other
