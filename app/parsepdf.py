import io
import pdfplumber

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF byte stream using pdfplumber."""
    text = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text.append(page.extract_text(x_tolerance=2, y_tolerance=2) or "")
    return "\n".join(text)
