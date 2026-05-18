"""
LLM service — all Gemini calls via OpenRouter.
v3.0: full clinical entity extraction, reasoning engine, flag generation, patient summary.
"""
import json
import asyncio
import httpx
from config.settings import settings
from config.logging import get_logger

logger = get_logger("LLM")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = "google/gemini-2.5-flash"
_HEADERS = {
    "HTTP-Referer": "https://carecircle.app",
    "X-Title": "CareCircle",
    "Content-Type": "application/json",
}

_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 5]


async def _call(system_prompt: str, user_prompt: str, timeout: int = 120) -> dict:
    logger.info(f"LLM call — model: {LLM_MODEL}")
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    OPENROUTER_URL,
                    headers={**_HEADERS, "Authorization": f"Bearer {settings.openrouter_api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            logger.info(f"LLM response — {len(content)} chars")
            return _parse_json(content)
        except Exception as e:
            last_error = e
            if attempt < len(_RETRY_DELAYS):
                logger.warning(f"LLM attempt {attempt + 1} failed: {e} — retrying in {_RETRY_DELAYS[attempt]}s")
                await asyncio.sleep(_RETRY_DELAYS[attempt])
            else:
                logger.error(f"LLM failed after {_MAX_RETRIES} attempts: {e}")
    raise RuntimeError(f"LLM failed: {last_error}")


def _parse_json(content: str) -> dict:
    """Parse JSON from LLM response, handling markdown code fences."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return {"items": result}
        return result
    except json.JSONDecodeError:
        # Salvage: try to find JSON object in the response
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        logger.warning(f"Could not parse LLM response as JSON: {text[:200]}")
        return {}


# =========================================================
# PHASE 2: Full Clinical Entity Extraction
# =========================================================

_PRESCRIPTION_SYSTEM = """You are a clinical entity extraction system for an Indian healthcare platform.
Extract ALL clinically meaningful information from this prescription.
Do not extract only medications — extract every clinical entity present.
Return only valid JSON. Dates in ISO YYYY-MM-DD. If a field cannot be read clearly, return null.
Never guess drug names — return the exact text as written on the prescription."""

_PRESCRIPTION_USER = """Extract all clinical entities from this prescription text.

Return JSON with this exact structure:
{{
  "medications": [
    {{
      "drug_name_brand": "brand name as written",
      "drug_name_generic": "generic name if clearly stated, else null",
      "drug_class": "drug class if known, else null",
      "dose_mg": null,
      "dose_text": "dose as written e.g. 500mg",
      "frequency": "once_daily|twice_daily|three_times_daily|alternate_days|as_needed|sos|other",
      "route": "oral|topical|inhaled|injection|other or null",
      "timing": "before_meals|after_meals|bedtime|morning|evening|null",
      "duration_days": null,
      "duration_text": "7 days|1 week|null",
      "is_prn": false,
      "is_sos": false,
      "confidence": 0.0
    }}
  ],
  "diagnoses_mentioned": [
    {{"condition_name": "string", "chronic_or_acute": "chronic|acute|unknown", "severity_stage": "null or string", "confidence": 0.0}}
  ],
  "clinical_directives": [
    {{
      "directive_type": "hold_medication|stop_medication|avoid_drug_class|avoid_specific_drug|avoid_food|avoid_activity|dose_adjustment|timing_change|monitor_before_continuing|conditional_restart|other",
      "target_entity": "exact name of drug/food/activity",
      "target_entity_type": "medication|drug_class|food|activity|lab_test|other",
      "instruction_text": "verbatim text from prescription",
      "condition_for_execution": "null or condition text e.g. until K+ < 5.0",
      "condition_type": "lab_threshold|time_elapsed|clinical_event|doctor_review|indefinite|null",
      "confidence": 0.0
    }}
  ],
  "restrictions": [
    {{"restriction_type": "drug_class|specific_drug|food_substance|food_category|activity|other", "target": "string", "reason": "null or string", "instruction_text": "verbatim", "confidence": 0.0}}
  ],
  "monitoring_instructions": [
    {{"test_or_vital": "string", "monitoring_category": "lab_test|vital_sign|clinical_review|imaging|other", "frequency_text": "null or string", "timing_text": "null or string", "urgency": "routine|urgent|stat", "confidence": 0.0}}
  ],
  "allergies_mentioned": [
    {{"allergen": "string", "reaction_type": "null or string", "severity": "mild|moderate|severe|unknown", "confidence": 0.0}}
  ],
  "prescribing_doctor": {{"name": "null or string", "specialty": "null or string", "hospital": "null or string", "phone": "null or string"}},
  "prescription_date": "YYYY-MM-DD or null",
  "follow_up_date": "YYYY-MM-DD or null",
  "doctor_observations": "null or string",
  "overall_confidence": 0.0
}}

Prescription text:
{ocr_text}"""


async def extract_prescription(ocr_text: str) -> dict:
    return await _call(_PRESCRIPTION_SYSTEM, _PRESCRIPTION_USER.format(ocr_text=ocr_text))


_LAB_SYSTEM = """You are a clinical lab report parser for an Indian healthcare platform.
Extract all test results and any clinical instructions.
For Indian lab shorthand: SGPT=ALT, SGOT=AST, Sr.Creatinine=Serum Creatinine, KFT=Kidney Function, LFT=Liver Function, RBS=Random Glucose, FBS=Fasting Glucose, HbA1c=Glycated Haemoglobin, CBC=Complete Blood Count.
Return only valid JSON. Dates in ISO YYYY-MM-DD."""

_LAB_USER = """Extract all test results from this lab report.

Return JSON:
{{
  "report_date": "YYYY-MM-DD or null",
  "lab_name": "null or string",
  "ordering_doctor": "null or string",
  "patient_fasting_status": "fasting|non_fasting|unknown",
  "tests": [
    {{
      "test_name": "original name as in report",
      "test_name_normalized": "standardized name e.g. Serum Potassium",
      "test_category": "blood_glucose|kidney_function|liver_function|electrolytes|thyroid|lipid_profile|complete_blood_count|coagulation|inflammation|cardiac|iron_studies|vitamin_mineral|hormone|urinalysis|culture|other",
      "value_numeric": null,
      "value_text": "value as written",
      "unit": "null or string",
      "reference_low": null,
      "reference_high": null,
      "is_flagged_by_lab": false,
      "flag_direction": "high|low|critical_high|critical_low|null",
      "confidence": 0.0
    }}
  ],
  "culture_findings": [
    {{
      "organism": "null or string",
      "organism_normalized": "null or string",
      "specimen_type": "null or string",
      "collection_date": "YYYY-MM-DD or null",
      "resistant_to": [],
      "sensitive_to": [],
      "intermediate_to": []
    }}
  ],
  "overall_confidence": 0.0
}}

Lab report text:
{text}"""


_LAB_CHUNK_SIZE = 6000


async def extract_lab_report(text: str) -> dict:
    if len(text) <= _LAB_CHUNK_SIZE:
        return await _call(_LAB_SYSTEM, _LAB_USER.format(text=text))

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + _LAB_CHUNK_SIZE, len(text))
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start:
                end = nl
        chunks.append(text[start:end])
        start = end

    logger.info(f"Lab report chunked into {len(chunks)} parts")
    results = []
    for i, chunk in enumerate(chunks):
        try:
            result = await _call(_LAB_SYSTEM, _LAB_USER.format(text=chunk))
            results.append(result)
        except Exception as e:
            logger.warning(f"Lab chunk {i+1} failed: {e}")

    merged = {
        "report_date": next((r.get("report_date") for r in results if r.get("report_date")), None),
        "lab_name": next((r.get("lab_name") for r in results if r.get("lab_name")), None),
        "ordering_doctor": next((r.get("ordering_doctor") for r in results if r.get("ordering_doctor")), None),
        "patient_fasting_status": next((r.get("patient_fasting_status") for r in results if r.get("patient_fasting_status")), "unknown"),
        "tests": [],
        "culture_findings": [],
        "overall_confidence": sum(r.get("overall_confidence", 0.7) for r in results) / max(len(results), 1),
    }
    seen_tests: set[tuple] = set()
    for r in results:
        for t in r.get("tests") or []:
            if not isinstance(t, dict):
                continue
            key = (
                (t.get("test_name") or "").lower().strip(),
                (t.get("value_text") or "").lower().strip(),
            )
            if key[0] and key not in seen_tests:
                seen_tests.add(key)
                merged["tests"].append(t)
        merged["culture_findings"].extend(r.get("culture_findings") or [])
    return merged


_DISCHARGE_SYSTEM = """You are a clinical discharge summary parser for an Indian healthcare platform.
Extract all structured clinical information from this discharge summary.
Return only valid JSON. Dates in ISO YYYY-MM-DD."""

_DISCHARGE_USER = """Extract all clinical entities from this discharge summary.

Return JSON:
{{
  "admission_date": "YYYY-MM-DD or null",
  "discharge_date": "YYYY-MM-DD or null",
  "hospital_name": "null or string",
  "treating_doctor": "null or string",
  "discharge_condition": "null or string",
  "primary_diagnosis": "null or string",
  "secondary_diagnoses": [],
  "procedures_performed": [],
  "medications_at_admission": [{{"drug_name_brand": "string", "dose_text": "null or string"}}],
  "medications_at_discharge": [
    {{"drug_name_brand": "string", "dose_text": "null or string", "frequency": "null or string", "instructions": "null or string", "confidence": 0.0}}
  ],
  "medications_started": [{{"drug_name_brand": "string", "reason": "null or string"}}],
  "medications_stopped": [{{"drug_name_brand": "string", "reason": "null or string"}}],
  "medications_changed": [{{"drug_name_brand": "string", "change": "dose_changed|frequency_changed|formulation_changed", "detail": "null or string"}}],
  "discharge_directives": [
    {{
      "directive_type": "hold_medication|stop_medication|avoid_drug_class|avoid_specific_drug|avoid_food|avoid_activity|dose_adjustment|conditional_restart|other",
      "target_entity": "string",
      "target_entity_type": "medication|drug_class|food|activity|other",
      "instruction_text": "verbatim",
      "condition_for_execution": "null or string",
      "condition_type": "lab_threshold|time_elapsed|clinical_event|doctor_review|indefinite|null",
      "confidence": 0.0
    }}
  ],
  "discharge_restrictions": [
    {{"restriction_type": "food_substance|food_category|activity|specific_drug|drug_class|other", "target": "string", "reason": "null or string", "instruction_text": "verbatim", "confidence": 0.0}}
  ],
  "monitoring_required": [
    {{"test_or_vital": "string", "frequency_text": "null or string", "timing_text": "null or string", "urgency": "routine|urgent|stat", "confidence": 0.0}}
  ],
  "follow_up_instructions": "null or string",
  "warning_signs": "null or string",
  "culture_findings": [],
  "overall_confidence": 0.0
}}

Discharge summary text:
{text}"""


async def extract_discharge_summary(text: str) -> dict:
    return await _call(_DISCHARGE_SYSTEM, _DISCHARGE_USER.format(text=text))


# =========================================================
# PHASE 3.1: Drug Name Resolution
# =========================================================

_RESOLVE_SYSTEM = """You are a clinical pharmacology reference for an Indian healthcare platform.
Your job is to identify the generic name and drug class of medications commonly prescribed in India.
Return only valid JSON. Never invent drug names."""

_RESOLVE_USER = """What is the generic name and drug class of this medication commonly prescribed in India?

Medication: {drug_name}

Return JSON:
{{"generic_name": "string or null", "drug_class": "string or null", "confidence": 0.0}}

Rules:
- generic_name: the INN (International Nonproprietary Name), not a brand name
- drug_class: one of the standard pharmacological classes (e.g. Biguanide, ACE Inhibitor, Statin)
- confidence: how certain you are this is a real drug name (0.0-1.0)
- If this is not a medication (it's a disease, food, procedure): return null for generic_name and confidence 0.0"""


async def resolve_brand_name_v3(drug_name: str) -> dict:
    return await _call(_RESOLVE_SYSTEM, _RESOLVE_USER.format(drug_name=drug_name))


# =========================================================
# PHASE 5: Reasoning Engine
# =========================================================

_REASONING_SYSTEM = """You are a clinical reasoning engine for a caregiver intelligence platform in India.
Your job is to analyze a patient's complete medical record and identify ALL clinically meaningful findings.

CRITICAL RULES:
1. You MUST check every reasoning dimension — do not stop at drug-drug interactions.
2. Every finding MUST cite specific patient data: exact drug names, exact lab values with dates, exact directive text as written. Generic statements are not acceptable.
3. Every finding must explain WHY it applies to THIS patient specifically — their age, their other conditions, their other medications, their specific lab values.
4. Be conservative — it is safer to flag a potential risk than to miss one.
5. Severity must be accurate. Do not over-alarm on minor issues or under-alarm on critical ones.
6. If a dimension cannot be checked due to missing data, note it as a missing_data_finding with severity=informational.
7. You reason as a clinical information system, not a doctor. You identify patterns. You do not diagnose or prescribe.
8. Return ONLY valid JSON. No preamble. No explanation outside the JSON structure.

SEVERITY DEFINITIONS:
critical: Immediate patient safety risk. Potentially life-threatening. Requires action today.
high: Significant clinical risk. Requires prompt attention within days.
moderate: Clinically meaningful. Attention needed but not urgent.
low: Worth noting. Lower priority.
informational: Context or awareness. No action required. Missing data notes."""

_REASONING_USER = """Analyze the following complete patient state and return ALL clinically meaningful findings.

PATIENT STATE:
{patient_state_json}

CHECK ALL 13 DIMENSIONS:

1. MEDICATION-MEDICATION
   - Exact duplicates (same generic twice)
   - Therapeutic duplication: Two NSAIDs, two anticoagulants (CRITICAL), two potassium-sparing diuretics, ACE inhibitor + ARB, two loop diuretics, two sulfonylureas, two insulins same type, two statins, two benzodiazepines
   - Additive adverse effects: hypotension (multiple antihypertensives), hypoglycemia (sulfonylurea+insulin), hyperkalemia (ACE/ARB+K-sparing), QT prolongation (fluoroquinolone+azithromycin), nephrotoxicity (NSAIDs+ACE/ARB+diuretic triple whammy = CRITICAL), bleeding risk (NSAID+anticoagulant)

2. MEDICATION-CONDITION
   - NSAIDs + CKD: high (critical if eGFR<30)
   - Metformin + eGFR<30: CRITICAL
   - NSAIDs + active peptic ulcer: CRITICAL
   - NSAIDs + heart failure: high
   - Beta-blockers + severe asthma/COPD: high
   - Fluoroquinolones + QT prolongation history: CRITICAL
   - Opioids + severe COPD: high
   - Digoxin + hypokalemia: CRITICAL
   - Thiazolidinediones + heart failure: CRITICAL

3. MEDICATION-LAB
   - K+ >5.5 + potassium-raising drug: high; K+ >6.0: CRITICAL
   - K+ <2.5 + potassium-lowering drug: CRITICAL
   - eGFR <30 + metformin: CRITICAL
   - eGFR <30 + NSAIDs: CRITICAL
   - INR >4.0 + warfarin: CRITICAL
   - INR <2.0 + warfarin for AF: moderate
   - ALT >10x ULN + hepatotoxic drug: CRITICAL
   - CK >10x ULN + statin: CRITICAL (rhabdomyolysis)
   - Fasting glucose <54 + insulin/sulfonylurea: CRITICAL

4. MEDICATION-DIRECTIVE
   - Stop directive: medication still active → CRITICAL
   - Avoid drug class: medication of that class active → CRITICAL
   - Hold directive: check if condition_for_execution is met

5. MEDICATION-ALLERGY
   - Exact allergen match → CRITICAL
   - Penicillin allergy + cephalosporins: high (10% cross-reactivity)
   - Sulfonamide allergy + trimethoprim-sulfamethoxazole: CRITICAL
   - Prior anaphylaxis: any cross-reactive drug → CRITICAL

6. CULTURE-ANTIBIOTIC
   - Antibiotic active but culture shows resistance → CRITICAL
   - Culture exists but no antibiotic prescribed → high

7. DIAGNOSIS-DIAGNOSIS
   - CKD + heart failure: CRITICAL (potassium/fluid management)
   - Diabetes + CKD: high
   - Heart failure + COPD: high (beta-blocker dilemma)
   - Atrial fibrillation + NSAID prescription: CRITICAL

8. DIAGNOSIS-LAB
   - Lab suggests undiagnosed condition (creatinine >1.5 without CKD diagnosis)
   - Condition poorly controlled (HbA1c >9.0%)
   - Lab worsening trend (>20% deterioration)

9. DIRECTIVE-LAB THRESHOLD
   - Evaluate condition_for_execution for each conditional directive
   - "Hold until K+ < 5.0" — is current K+ below 5.0?

10. RESTRICTION-ACTIVE STATE
    - Active medication violates extracted restriction → CRITICAL

11. TEMPORAL LOGIC
    - Duration-limited medication where duration may have expired (non-chronic only)
    - Hold directive where time component has elapsed
    - Monitoring overdue (specified timing passed, no new test)
    - Follow-up date passed

12. CROSS-DOCUMENT RECONCILIATION
    - Same medication, different doses across documents → high
    - Medication stopped in discharge but active in outpatient prescription → CRITICAL
    - Contradicting directives from different prescribing doctors → high

13. LONGITUDINAL PATTERNS (if prior_findings present)
    - Same finding recurring → severity escalates one level
    - Lab value worsening trend
    - Prior unresolved finding still active

For EACH finding return:
{{
  "finding_type": "exact type string",
  "dimension": "D1: Medication-Medication | D2: Medication-Condition | etc",
  "severity": "critical | high | moderate | low | informational",
  "title": "max 10 words plain text",
  "clinical_evidence": [
    {{ "entity": "EXACT value from patient_state", "source": "specific document name or source", "date": "ISO date if applicable" }}
  ],
  "patient_specific_reasoning": "why this applies specifically to THIS patient",
  "related_entities": {{
    "medications": ["exact drug names involved"],
    "labs": ["exact test names with values and dates"],
    "conditions": ["exact condition names"],
    "directives": ["exact directive text"]
  }},
  "confidence": 0.0
}}

Return: {{ "findings": [ ...all findings... ] }}

IMPORTANT: If clinical_evidence is empty for any finding, DO NOT include that finding.
Every finding must have at least one specific data point from the patient_state."""


async def run_reasoning(patient_state: dict) -> dict:
    patient_state_json = json.dumps(patient_state, indent=2, default=str)
    return await _call(
        _REASONING_SYSTEM,
        _REASONING_USER.format(patient_state_json=patient_state_json),
        timeout=120,
    )


# =========================================================
# PHASE 6: Flag Generation
# =========================================================

_FLAG_SYSTEM = """You are a caregiver communication specialist for an Indian healthcare platform.
Your job is to translate a clinical finding into guidance a non-medical caregiver can understand and act on.

RULES:
1. Write in plain language. Define any medical term you use in the same sentence.
2. Always reference the specific source: name the document, the doctor, the lab, the date.
3. Always reference brand names first, generic in brackets: "Glycomet (Metformin)".
4. Never say "do not give this medicine" unless a doctor explicitly wrote STOP in a directive. Instead say "discuss with doctor before continuing."
5. Never present the finding as a confirmed medical fact. Always attribute: "The lab report from [date] shows...", "The prescription from Dr. X says..."
6. Do not terrify. Do not minimize. Be calm, specific, and clear.
7. The what_to_do must be actionable. "Consult a doctor" alone is NOT acceptable. Tell them specifically what to bring, what to say, what to show.
8. Return ONLY valid JSON.

"""

_FLAG_USER = """Translate this clinical finding into caregiver guidance.

Clinical finding:
{finding_json}

Patient context:
- Age: {age}
- Gender: {gender}
- Diagnosed conditions: {conditions}

Return:
{{
  "title": "max 10 words plain language no jargon",
  "what_was_found": "2-3 sentences. Name specific drug (brand name first), specific lab value with date, specific document. No generic statements.",
  "why_it_matters": "2-3 sentences. Explain clinical significance in plain language. Reference this patient's specific situation.",
  "what_to_do": "1-3 sentences. Specific actionable instruction. Name what to bring to doctor, what test to schedule, what to stop.",
  "source_reference": "List documents that contain evidence. Include document type, doctor name if known, date."
}}"""


async def generate_flag(finding: dict, patient_age, patient_gender: str, conditions: list[str]) -> dict:
    finding_json = json.dumps(finding, indent=2, default=str)
    conditions_str = ", ".join(conditions) if conditions else "None stated"
    return await _call(
        _FLAG_SYSTEM,
        _FLAG_USER.format(
            finding_json=finding_json,
            age=patient_age,
            gender=patient_gender,
            conditions=conditions_str,
        ),
        timeout=60,
    )


# =========================================================
# PHASE 7: Patient Summary (Silent)
# =========================================================

_SUMMARY_SYSTEM = """You are a clinical documentation system generating an internal patient health summary for a care coordination platform.
This summary is for system use and future reasoning only — it will NOT be shown to the patient or guardian.
Write in clinical language appropriate for a medical record. Be comprehensive."""

_SUMMARY_USER = """Generate a comprehensive clinical summary for this patient.

Patient state:
{patient_state_json}

Open findings (after reasoning engine):
{findings_json}

Include:
1. Demographics and identifying information
2. Active diagnosed conditions with severity/control status
3. Complete confirmed medication list with doses, frequencies, and timing
4. Key lab values with trend direction where multiple reports available
5. Active clinical directives and restrictions
6. Pending monitoring items
7. Clinical narrative: brief paragraph synthesizing the patient's overall clinical picture
8. Open findings summary: list all findings by severity

Return as two parts in JSON:
{{
  "summary_text": "full clinical narrative as plain text",
  "snapshot_data": {{
    "demographics": {{}},
    "conditions": [],
    "medications": [],
    "key_labs": [],
    "active_directives": [],
    "pending_monitoring": [],
    "open_flags_summary": {{"critical": 0, "high": 0, "moderate": 0, "low": 0, "informational": 0}}
  }}
}}"""


async def generate_patient_summary(patient_state: dict, findings: list[dict]) -> dict:
    return await _call(
        _SUMMARY_SYSTEM,
        _SUMMARY_USER.format(
            patient_state_json=json.dumps(patient_state, indent=2, default=str),
            findings_json=json.dumps(findings, indent=2, default=str),
        ),
        timeout=90,
    )


# =========================================================
# PHASE 6.6: Intelligent Action Summary
# =========================================================

_ACTION_SYSTEM = """\
You are a clinical action planner for a caregiver intelligence platform in India.

Your job is to reason across a patient's complete medical record and produce
a clear, personalized, actionable summary of what the caregiver needs to do —
organized into three lists: what to do now, what to follow up on, and what to monitor ongoing.

IMPORTANT: You are not a copy-paste engine. You reason about the evidence.

PERSONALIZATION RULES (most important):
- Every action item must feel like it was written specifically for this patient and this caregiver. Not generic. Not template-based.
- Always use the patient's actual name: "Rajesh's potassium level..." not "the patient's..."
- Always use actual medication brand names: "Aldactone (Spironolactone)" not "his medication"
- Always use actual doctor names when available: "Dr. Sharma recommended..." not "the doctor"
- Always use actual test names and values: "his potassium reading of 5.7 mmol/L from March 2026"
- Always use actual hospital/facility names when available
- Speak to the caregiver directly using their relationship to the patient where natural

TEMPORAL REASONING RULES:
- Always check dates before deciding if something is pending or done.
- If a discharge summary says "repeat KFT in 5 days" and the discharge date is [date], check whether any lab report in the record was collected AFTER [date]. If yes: the repeat may have been done. If no: it is likely still pending.
- If a directive says "hold medication until [lab test] reviewed" — check if the relevant lab was done after the directive date.

WHAT GOES ON EACH LIST:
DO NOW: Urgent medication reviews, unmet hold conditions, anything critical or high priority requiring action today.
FOLLOW-UP: Repeat tests or labs not yet done, overdue doctor appointments, medication reviews needing a visit.
ONGOING MONITORING: Regular tracking requirements, routine labs to repeat periodically, dietary/activity restrictions, SOS conditions.

TONE RULES (non-negotiable):
- Advisory only. Never command. Use: "it may be advisable," "consider," "we recommend discussing," "it would be worth checking."
- Never use: stop, discontinue, do not take, do not give, restart, reduce dose, increase dose, you must, you should not.
- Even when a doctor's document says stop a medication, say: "The records show [doctor/hospital] instructed that [Aldactone (Spironolactone)] be held or stopped — it may be worth confirming with the doctor whether this is still current."
- Calm, caring, specific. Never generic. Never alarming. Never dismissive.

ADDITIONAL RULES:
- Brand names first, generic in brackets: "Aldactone (Spironolactone)"
- Deduplicate: if two sources say the same thing, show once
- Never drop an item — if uncertain whether it is pending, include it
- Each item must cite its source document with date
- One sentence per action item. Plain language.
- Return only valid JSON.\
"""

_ACTION_USER = """\
Full patient context:
{action_context_json}

Based on this complete context — reasoning across the evidence, the dates,
the documents, and what has and has not been done — produce three action lists
that are specific to {patient_name} and feel personally tailored to their situation.

For each item, reason about WHY it belongs there. Do not relay what was extracted —
assess whether it is actually pending, whether it has been done, and what the
caregiver genuinely needs to do for this specific patient.

Return:
{{
  "do_now": [
    {{
      "action": "one personalized sentence — uses patient name, drug name, specific values",
      "reason": "brief explanation of why this needs attention now, with dates",
      "source": "document name and date"
    }}
  ],
  "follow_up": [
    {{
      "action": "one personalized sentence",
      "reason": "brief explanation including temporal reasoning if relevant",
      "source": "document name and date"
    }}
  ],
  "ongoing_monitoring": [
    {{
      "action": "one personalized sentence",
      "reason": "brief explanation",
      "source": "document name and date"
    }}
  ]
}}\
"""


async def generate_action_summary(action_context: dict, patient_name: str) -> dict:
    return await _call(
        _ACTION_SYSTEM,
        _ACTION_USER.format(
            action_context_json=json.dumps(action_context, indent=2, default=str),
            patient_name=patient_name,
        ),
        timeout=120,
    )


# =========================================================
# Legacy compatibility — kept for existing code references
# =========================================================

async def resolve_brand_name(brand_name: str) -> dict:
    """Backward-compat wrapper. Returns {"generic_name", "composition", "confidence"}."""
    result = await resolve_brand_name_v3(brand_name)
    return {
        "generic_name": result.get("generic_name"),
        "composition": result.get("drug_class"),
        "confidence": result.get("confidence", 0),
    }
