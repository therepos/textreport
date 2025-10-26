import io
import csv
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.responses import StreamingResponse

from .parsetext import extract_transactions_from_text
from .parsepdf import extract_text_from_pdf
from .categorize import predict_category, load_rules, save_rules

app = FastAPI(
    title="textreport",
    version="1.2-rules-only",
    description="PDF → CSV converter with category mapping and rules.json support",
    docs_url="/docs",            # Swagger UI
    redoc_url=None,              # disable ReDoc to simplify
    openapi_url="/openapi.json"  # default path
)

# --- DEBUG: show raw text lines extracted from PDF ---
@app.post("/bank/debug-pdf")
async def debug_pdf(pdf: UploadFile = File(...), lines: int = Form(80)):
    content = await pdf.read()
    raw_text = extract_text_from_pdf(content)
    sliced = [ln for ln in raw_text.splitlines()][:lines]
    return {"line_count": len(raw_text.splitlines()), "preview": sliced}

# --- DEBUG: show parsed transactions + first lines of text ---
@app.post("/bank/debug-parse")
async def debug_parse(pdf: UploadFile = File(...), year: int = Form(2025), lines: int = Form(60)):
    content = await pdf.read()
    raw_text = extract_text_from_pdf(content)
    from .parsetext import extract_transactions_from_text
    txns = extract_transactions_from_text(raw_text, year=year)
    preview = [ln for ln in raw_text.splitlines()][:lines]
    return {"preview": preview, "txn_count": len(txns), "txns": txns[:20]}

# -----------------------------------------------------------------------------
# Convert from raw text
# -----------------------------------------------------------------------------
@app.post("/bank/convert-text", response_class=StreamingResponse)
async def convert_from_text(
    raw_text: str = Form(...),
    year: int = Form(2025),
    single_amount_col: bool = Form(True),
):
    txns = extract_transactions_from_text(raw_text, year=year)

    buf = io.StringIO()
    w = csv.writer(buf)
    if single_amount_col:
        w.writerow(["Date", "Payee", "Category", "Memo", "Amount"])
    else:
        w.writerow(["Date", "Payee", "Category", "Memo", "Outflow", "Inflow"])

    for t in txns:
        date = t["date"]
        payee = t["payee"]
        memo = t.get("memo", "")
        amount = float(t.get("amount", 0.0))
        is_credit = bool(t.get("credit", False))
        cat = predict_category(payee, memo, refund_hint=is_credit)

        if single_amount_col:
            amt = amount if is_credit else -amount  # credit=+, debit=-
            w.writerow([date, payee, cat, memo, f"{amt:.2f}"])
        else:
            outflow = "" if is_credit else f"{amount:.2f}"
            inflow = f"{amount:.2f}" if is_credit else ""
            w.writerow([date, payee, cat, memo, outflow, inflow])

    data = buf.getvalue().encode("utf-8")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=actualbudget.csv"},
    )


# -----------------------------------------------------------------------------
# Convert from PDF
# -----------------------------------------------------------------------------
@app.post("/bank/convert-pdf", response_class=StreamingResponse)
async def convert_pdf(
    pdf: UploadFile = File(...),
    year: int = Form(2025),
    single_amount_col: bool = Form(True),
):
    """Upload a bank statement PDF and receive a categorized CSV."""
    content = await pdf.read()
    raw_text = extract_text_from_pdf(content)
    return await convert_from_text(
        raw_text=raw_text, year=year, single_amount_col=single_amount_col
    )


# -----------------------------------------------------------------------------
# Rules management (category-first)
# -----------------------------------------------------------------------------
@app.get("/bank/rules")
def get_rules():
    return load_rules()


@app.post("/bank/rules")
def upsert_rules(
    rules: dict = Body(
        ...,
        example={"Food": ["ROYAL CABRI", "STARBUCKS"], "Transport": ["GRAB"]},
    )
):
    save_rules(rules or {})
    return {"count": sum(len(v) for v in (rules or {}).values())}


# -----------------------------------------------------------------------------
# Health/version
# -----------------------------------------------------------------------------
@app.get("/bank/health")
def health():
    rules_path = Path("/data/models/rules.json")
    return {"ok": True, "rules_exists": rules_path.exists(), "rules_path": str(rules_path)}


@app.get("/bank/version")
def version():
    return {"service": "textreport", "version": "1.2-rules-only"}
