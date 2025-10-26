import io, csv
from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.responses import StreamingResponse, JSONResponse

from .parser_text import extract_transactions_from_text
from .pdf_parser import extract_text_from_pdf
from .categorize import predict_category, load_rules, save_rules
from . import ml  # separate ML module

app = FastAPI(title="textreport", version="1.1")

# ---- Convert from raw text ----
@app.post("/bank/convert-text")
async def convert_from_text(
    raw_text: str = Form(...),
    year: int = Form(2025),
    single_amount_col: bool = Form(True),
):
    txns = extract_transactions_from_text(raw_text, year=year)

    buf = io.StringIO()
    w = csv.writer(buf)
    if single_amount_col:
        w.writerow(["Date","Payee","Category","Memo","Amount"])
    else:
        w.writerow(["Date","Payee","Category","Memo","Outflow","Inflow"])

    for t in txns:
        date = t["date"]; payee = t["payee"]; memo = t.get("memo","")
        amount = float(t.get("amount", 0.0)); is_credit = bool(t.get("credit", False))
        cat = predict_category(payee, memo, refund_hint=is_credit, use_ml=True)

        if single_amount_col:
            amt = amount if is_credit else -amount  # credit=+, debit=-
            w.writerow([date, payee, cat, memo, f"{amt:.2f}"])
        else:
            outflow = "" if is_credit else f"{amount:.2f}"
            inflow  = f"{amount:.2f}" if is_credit else ""
            w.writerow([date, payee, cat, memo, outflow, inflow])

    data = buf.getvalue().encode("utf-8")
    return StreamingResponse(io.BytesIO(data), media_type="text/csv",
        headers={"Content-Disposition":"attachment; filename=actualbudget.csv"})

# ---- Convert from PDF ----
@app.post("/bank/convert-pdf")
async def convert_pdf(
    pdf: UploadFile = File(...),
    year: int = Form(2025),
    single_amount_col: bool = Form(True),
):
    content = await pdf.read()
    raw_text = extract_text_from_pdf(content)
    return await convert_from_text(raw_text=raw_text, year=year, single_amount_col=single_amount_col)

# ---- Rules (category-first) ----
@app.get("/bank/rules")
def get_rules():
    return load_rules()

@app.post("/bank/rules")
def upsert_rules(rules: dict = Body(..., example={"Food": ["ROYAL CABRI","STARBUCKS"], "Transport": ["GRAB"]})):
    save_rules(rules or {})
    return {"count": sum(len(v) for v in (rules or {}).values())}

# ---- ML endpoints separated ----
@app.post("/bank/train")
async def train(csvfile: UploadFile = File(...)):
    content = await csvfile.read()
    examples, cats = ml.train_from_csv(content)
    return {"examples": examples, "categories": cats}

@app.get("/bank/health")
def health():
    return {"ok": True, **ml.model_status()}

@app.get("/bank/version")
def version():
    return {"service": "textreport", "version": "1.1"}
