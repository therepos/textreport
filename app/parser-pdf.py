import pdfplumber

def extract_text_from_pdf(file_bytes: bytes) -> str:
    text = []
    with pdfplumber.open(io=file_bytes) as pdf:  # pdfplumber accepts bytes-like via "io="
        for page in pdf.pages:
            text.append(page.extract_text(x_tolerance=2, y_tolerance=2) or "")
    return "\n".join(text)
