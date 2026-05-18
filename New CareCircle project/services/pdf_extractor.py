import io
import pdfplumber
import fitz  # PyMuPDF
from config.logging import get_logger

logger = get_logger("PDF")


def extract_text_from_pdf(file_bytes: bytes) -> str:
    logger.info(f"Starting PDF extraction — {len(file_bytes)} bytes")

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if len(text.strip()) >= 50:
            logger.info(f"pdfplumber: extracted {len(text)} chars")
            return text
        logger.info(f"pdfplumber only got {len(text.strip())} chars — trying PyMuPDF")
    except Exception as exc:
        logger.warning(f"pdfplumber failed ({exc}) — trying PyMuPDF")

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = "".join(page.get_text() for page in doc)
    logger.info(f"PyMuPDF extracted {len(text)} chars")
    return text


def render_pdf_to_images(file_bytes: bytes, dpi: int = 150) -> list[bytes]:
    """Render each page of a PDF to a PNG image. Used for scanned PDFs with no selectable text."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    images = []
    for page in doc:
        pix = page.get_pixmap(matrix=matrix)
        images.append(pix.tobytes("png"))
    logger.info(f"Rendered {len(images)} PDF page(s) to PNG at {dpi} dpi")
    return images
