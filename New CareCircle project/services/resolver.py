"""
Brand name → generic name resolution.
Cache-first (medicine_composition_cache), Gemini fallback.
"""
import re
from supabase import Client
from config.logging import get_logger
from services import llm

logger = get_logger("RESOLVER")

_SALT_FORMS = re.compile(
    r"\s+(hydrochloride|hcl|besylate|maleate|tartrate|succinate|fumarate|mesylate"
    r"|phosphate|sulfate|sodium|potassium|calcium|gluconate|acetate|citrate)\b",
    re.IGNORECASE,
)


def _normalize_generic(name: str) -> str:
    name = _SALT_FORMS.sub("", name).strip()
    return name.title()


def _strip_dose(name: str) -> str:
    """Remove trailing dose numbers: 'Metformin 500mg' → 'Metformin'."""
    return re.sub(r"\s+\d+\s*(mg|mcg|iu|ml|g|units?)\b.*", "", name, flags=re.IGNORECASE).strip()


def _extract_drug_name_from_instruction(text: str) -> str:
    """Extract just the drug name from a full instruction string.

    'Olmezest 40 - 1 tab OD morning' → 'Olmezest'
    'Metformin 500mg twice daily' → 'Metformin'
    """
    # Strip everything after " - " (dose/instruction separator)
    text = re.split(r"\s+-\s+", text)[0]
    # Strip bare number followed by tab/cap/dose instruction
    text = re.sub(r"\s+\d+(\s*(mg|mcg|iu|ml|g|tab|cap|units?))?\b.*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _extract_formulation(name: str) -> str | None:
    m = re.search(r"\b(SR|XR|ER|LA|CR|DR|MR|XL|OD)\b", name, re.IGNORECASE)
    return m.group(0).upper() if m else None


async def resolve_drug_name(db: Client, drug_name: str) -> dict:
    """
    Returns:
    {
      drug_name_brand: original input (never overwritten),
      drug_name_generic: normalized generic or None,
      drug_class: drug class or 'unknown',
      normalization_confidence: float,
      normalization_source: 'cache' | 'gemini' | 'failed' | 'guardian_stated',
      formulation: 'SR'|'XR' etc or None
    }
    """
    if not drug_name or not drug_name.strip():
        return _failed_result(drug_name)

    brand = drug_name.strip()
    formulation = _extract_formulation(brand)
    base_name = _strip_dose(brand)
    cache_key = base_name.lower()

    # Step 1: cache lookup
    cached = (
        db.table("medicine_composition_cache")
        .select("generic_name,drug_class")
        .ilike("brand_name", base_name)
        .execute()
    )
    if cached.data:
        row = cached.data[0]
        logger.info(f"Cache HIT: {brand} → {row['generic_name']}")
        return {
            "drug_name_brand": brand,
            "drug_name_generic": _normalize_generic(row["generic_name"]),
            "drug_class": row.get("drug_class") or "unknown",
            "normalization_confidence": 0.97,
            "normalization_source": "cache",
            "formulation": formulation,
        }

    # Step 2: Gemini resolution
    logger.info(f"Cache MISS: resolving {brand} via Gemini")
    try:
        result = await llm.resolve_brand_name_v3(base_name)
    except Exception as e:
        logger.warning(f"Gemini resolution failed for {brand}: {e}")
        return _failed_result(brand, formulation)

    generic = result.get("generic_name")
    drug_class = result.get("drug_class") or "unknown"
    confidence = float(result.get("confidence") or 0)

    if not generic or confidence < 0.60:
        logger.info(f"Resolution below threshold ({confidence:.2f}) for {brand}")
        return _failed_result(brand, formulation)

    # Validate: not a disease or procedure
    generic_lower = generic.lower()
    invalid_terms = ["diabetes", "hypertension", "infection", "surgery", "therapy", "disease", "syndrome"]
    if any(t in generic_lower for t in invalid_terms):
        logger.warning(f"LLM returned non-drug generic for {brand}: {generic}")
        return _failed_result(brand, formulation)

    normalized_generic = _normalize_generic(generic)

    # Step 3: cache the result
    try:
        db.table("medicine_composition_cache").insert({
            "brand_name": base_name,
            "generic_name": normalized_generic,
            "drug_class": drug_class,
        }).execute()
    except Exception:
        pass  # conflict = already exists, ignore

    logger.info(f"Resolved: {brand} → {normalized_generic} ({drug_class}, conf={confidence:.2f})")
    return {
        "drug_name_brand": brand,
        "drug_name_generic": normalized_generic,
        "drug_class": drug_class,
        "normalization_confidence": round(confidence * 0.95, 3),  # gemini modifier
        "normalization_source": "gemini",
        "formulation": formulation,
    }


def _failed_result(brand_name: str, formulation: str | None = None) -> dict:
    return {
        "drug_name_brand": brand_name or "",
        "drug_name_generic": None,
        "drug_class": "unknown",
        "normalization_confidence": 0.0,
        "normalization_source": "failed",
        "formulation": formulation,
    }


def guardian_stated_result(drug_name: str) -> dict:
    """For guardian-stated medications: brand = generic = what they typed."""
    formulation = _extract_formulation(drug_name)
    clean = _strip_dose(drug_name.strip())
    return {
        "drug_name_brand": drug_name.strip(),
        "drug_name_generic": clean.title(),
        "drug_class": "unknown",
        "normalization_confidence": 0.80,
        "normalization_source": "guardian_stated",
        "formulation": formulation,
    }
