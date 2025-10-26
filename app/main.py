# app/main.py
import io
import csv
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.responses import StreamingResponse

from .parsetext import extract_transactions_from_text
from .parsepdf import extract_text_from_pdf, extract_deposit_table
from .categorize import predict_category, load_rules, save_rules
from .parsers.deposit import _ as deposit_mod

app = FastAPI(
    title="textreport",
    version="1.3-table-aware",
    description="PDF → CSV converter with category mapping and deposit-table support",
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)


# -------------------------------------------------------------------
# DEBUG ENDPOINTS
# -------------------------------------------------------------------
@app.post("/bank/debug-pdf")
async def debug_pdf(pdf: UploadFile = File(...), lines: int = Form(80)):
    """Preview text extracted from a PDF."""
    content = await pdf.read()
    raw_text = extract_text_from_pdf(content)
    sliced = raw_text.splitlines()[:lines]
    return {"line_count": len(raw_text.splitlines()), "preview": sliced}


@app.post("/bank/debug-parse")
async def debug_parse(pdf: UploadFile = File(...), year: int = Form(2025), lines: int = Form(60)):
    """Preview parsed transactions from PDF text."""
    content = await pdf.read()
    raw_text = extract_text_from_pdf(content)
    txns = extract_transactions_from_text(raw_text, year=year)
    preview = raw_text.splitlines()[:lines]
    return {"preview": preview, "txn_count": len(txns), "txns": txns[:20]}


# -------------------------------------------------------------------
# TEXT → CSV
# -------------------------------------------------------------------
@app.post("/bank/convert-text", response_class=StreamingResponse)
async def convert_from_text(
    raw_text: str = Form(...),
    year: int = Form(2025),
    single_amount_col: bool = Form(True),
):
    """Convert raw extracted text (from any parser) into a categorized CSV."""
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


# -------------------------------------------------------------------
# PDF → CSV (Auto-detect deposit or credit-card format)
# -------------------------------------------------------------------
@app.post("/bank/convert-pdf", response_class=StreamingResponse)
async def convert_pdf(
    pdf: UploadFile = File(...),
    year: int = Form(2025),
    single_amount_col: bool = Form(True),
):
    """Upload a bank statement PDF and receive a categorized CSV."""
    content = await pdf.read()
    raw_text = extract_text_from_pdf(content)

    # If it's a deposit statement, use column extraction
    if deposit_mod.detect(raw_text):
        rows = extract_deposit_table(content)
        txns = deposit_mod.parse_from_table(rows, year)

        # Write CSV directly (bypass convert_from_text)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Date", "Payee", "Category", "Memo", "Amount"])
        for t in txns:
            date = t["date"]
            payee = t["payee"]
            memo = t.get("memo", "")
            amount = float(t["amount"])
            is_credit = bool(t.get("credit", False))
            cat = predict_category(payee, memo, refund_hint=is_credit)
            amt = amount if is_credit else -amount
            w.writerow([date, payee, cat, memo, f"{amt:.2f}"])

        data = buf.getvalue().encode("utf-8")
        return StreamingResponse(
            io.BytesIO(data),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=actualbudget.csv"},
        )

    # Otherwise fallback to text-based parsing
    return await convert_from_text(raw_text=raw_text, year=year, single_amount_col=single_amount_col)


# -------------------------------------------------------------------
# RULES MANAGEMENT
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# HEALTH + VERSION
# -------------------------------------------------------------------
@app.get("/bank/health")
def health():
    rules_path = Path("/data/models/rules.json")
    return {"ok": True, "rules_exists": rules_path.exists(), "rules_path": str(rules_path)}


@app.get("/bank/version")
def version():
    return {"service": "textreport", "version": "1.3-table-aware"}
