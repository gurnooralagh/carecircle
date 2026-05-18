import base64
import json
import httpx
from config.settings import settings
from config.logging import get_logger

logger = get_logger("OCR")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OCR_MODEL = "openai/gpt-4o-mini"
OCR_CONFIDENCE_RETRY_THRESHOLD = 0.80
_HEADERS = {
    "HTTP-Referer": "https://carecircle.app",
    "X-Title": "CareCircle",
    "Content-Type": "application/json",
}


async def _ocr_call(b64: str, mime_type: str, strict: bool = False) -> tuple[str, float]:
    instruction = (
        "Extract ALL text from this medical document exactly as it appears. "
        "Read every single line carefully — do not skip any line. "
        "Pay special attention to medicine names: spell each one exactly as written, character by character. "
        "If you are unsure of any word, write it as best you can rather than skipping it. "
        "Return ONLY a JSON object: "
        '{"text": "<full extracted text>", "confidence": <float 0.0-1.0>}. '
        "Set confidence below 0.75 if any part of the document was hard to read."
    ) if strict else (
        "Extract all text from this medical document exactly as it appears. "
        "Return ONLY a JSON object with two fields: "
        '{"text": "<full extracted text>", "confidence": <float 0.0-1.0>}. '
        "confidence reflects how clearly you could read the document."
    )

    payload = {
        "model": OCR_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                {"type": "text", "text": instruction},
            ],
        }],
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            OPENROUTER_URL,
            headers={**_HEADERS, "Authorization": f"Bearer {settings.openrouter_api_key}"},
            json=payload,
        )
        resp.raise_for_status()

    raw = resp.json()["choices"][0]["message"]["content"]
    logger.debug(f"OCR raw response:\n{raw}")

    try:
        data = json.loads(raw)
        text = str(data.get("text", raw))
        confidence = float(data.get("confidence", 0.5))
    except (json.JSONDecodeError, ValueError, TypeError):
        text = raw
        confidence = 0.5

    return text, confidence


async def extract_text_from_image(file_bytes: bytes, mime_type: str) -> tuple[str, float]:
    logger.info(f"OCR start — model: {OCR_MODEL}, size: {len(file_bytes)} bytes")
    b64 = base64.b64encode(file_bytes).decode()

    text, confidence = await _ocr_call(b64, mime_type, strict=False)
    logger.info(f"OCR first pass — confidence: {confidence:.2f}, chars: {len(text)}")

    if confidence < OCR_CONFIDENCE_RETRY_THRESHOLD:
        logger.info(f"Confidence {confidence:.2f} below threshold — retrying with strict prompt")
        text2, confidence2 = await _ocr_call(b64, mime_type, strict=True)
        logger.info(f"OCR retry — confidence: {confidence2:.2f}, chars: {len(text2)}")
        # Take the result with more text (likely more complete extraction)
        if len(text2) > len(text) or confidence2 > confidence:
            text, confidence = text2, confidence2
            logger.info(f"OCR retry result accepted — confidence: {confidence:.2f}")
        else:
            logger.info("OCR retry did not improve — keeping first result")

    logger.info(f"OCR complete — confidence: {confidence:.2f}, chars: {len(text)}")
    return text, confidence
