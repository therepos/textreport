import json, re, io
from typing import List, Tuple, Optional
from pathlib import Path
from rapidfuzz import fuzz, process
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

MODEL_DIR  = Path("/data/models")
MODEL_PATH = MODEL_DIR / "category_model.joblib"
RULES_PATH = MODEL_DIR / "rules.json"

SEED_RULES = [
    # Transport
    ("BUS/MRT","Transport"), ("GRAB","Transport"), ("RIDES","Transport"),
    ("TNG EWALLET","Transport"), ("TAXI","Transport"),
    # Groceries
    ("SHENGSIONG","Groceries"), ("CHEERS","Groceries"),
    ("FAIRPRICE","Groceries"), ("SCOOP WHOLEFOODS","Groceries"),
    # Food & Dining
    ("MCDONALD","Food & Dining"), ("BURGER KING","Food & Dining"),
    ("POPEYES","Food & Dining"), ("STARBUCKS","Food & Dining"),
    ("TOAST BOX","Food & Dining"), ("KOPITIAM","Food & Dining"),
    ("STUFF'D","Food & Dining"), ("SOUPERSTAR","Food & Dining"),
    ("DAILY CUT","Food & Dining"), ("SONG FA","Food & Dining"),
    ("TIM HORTONS","Food & Dining"), ("GREENDOT","Food & Dining"),
    ("LAO HUO TANG","Food & Dining"), ("SALMON SAMURAI","Food & Dining"),
    ("AN ACAI AFFAIR","Food & Dining"), ("DELIBOWL","Food & Dining"),
    # Shopping
    ("LAZADA","Shopping"), ("SHOPEE","Shopping"), ("UNIQLO","Shopping"),
    ("BENJAMIN BARKER","Shopping"), ("TECH HOUSE","Shopping"),
    ("CHALLENGER","Shopping"), ("EPITEX","Shopping"), ("DAISO","Shopping"),
    ("GUARDIAN","Shopping"), ("CLIPPERS","Shopping"), ("BESTPERFUM","Shopping"),
    # Subscriptions
    ("APPLE.COM","Subscriptions"), ("OPENAI","Subscriptions"),
    ("AMZNPRIMESG","Subscriptions"), ("NEWSGROUP.NINJA","Subscriptions"),
    ("DBRAND","Subscriptions"),
    # Insurance & Utilities
    ("PRUDENTIAL","Insurance"), ("STARHUB","Utilities"),
    # Debt/Loan (instalments)
    ("01CARDS","Debt/Loan"), ("IPP","Debt/Loan"),
    ("PREFERRED PAYMENT PLAN","Debt/Loan"),
]

def _norm(s: str) -> str:
    return re.sub(r"\s+"," ", (s or "").upper()).strip()

def _dedupe(pairs: List[Tuple[str,str]]) -> List[Tuple[str,str]]:
    out, seen = [], set()
    for pat, cat in pairs:
        if (pat, cat) not in seen:
            seen.add((pat, cat))
            out.append((pat, cat))
    return out

def load_rules() -> List[Tuple[str,str]]:
    rules = SEED_RULES.copy()
    if RULES_PATH.exists():
        try:
            rules += json.loads(RULES_PATH.read_text())
        except Exception:
            pass
    return _dedupe(rules)

def save_rules(extras: List[Tuple[str,str]]) -> None:
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text(json.dumps(extras, ensure_ascii=False, indent=2))

def apply_rules(text: str, rules: List[Tuple[str,str]]) -> Optional[str]:
    t = _norm(text)
    # direct contains
    for pat, cat in rules:
        if pat in t:
            return cat
    # fuzzy
    choices = [pat for pat,_ in rules if len(pat) >= 5]
    if choices:
        m = process.extractOne(t, choices, scorer=fuzz.partial_ratio)
        if m and m[1] >= 90:
            for pat, cat in rules:
                if pat == m[0]:
                    return cat
    return None

def predict_category(payee: str, memo: str = "", refund_hint: bool=False) -> str:
    if refund_hint:
        return "Refunds"  # credits default to refunds
    rules = load_rules()
    cat = apply_rules((payee or "") + " " + (memo or ""), rules)
    if cat:
        return cat
    if MODEL_PATH.exists():
        try:
            pipe = joblib.load(MODEL_PATH)
            text = _norm((payee or "") + " " + (memo or ""))
            if hasattr(pipe.named_steps.get("clf"), "predict_proba"):
                proba = pipe.predict_proba([text])[0]
                pred = pipe.classes_[proba.argmax()]
                if float(proba.max()) >= 0.60:
                    return str(pred)
            return str(pipe.predict([text])[0])
        except Exception:
            pass
    return "Uncategorized"

def train_from_csv(csv_bytes: bytes):
    df = pd.read_csv(io.BytesIO(csv_bytes))
    if not {"Payee","Category"}.issubset(df.columns):
        return 0, []
    df["text"] = (df["Payee"].fillna("") + " " + df.get("Memo","").fillna("")).astype(str)
    df["text"] = df["text"].apply(_norm)
    df = df[df["Category"].notna() & (df["Category"].astype(str).str.len() > 0)]
    if df.empty:
        return 0, []

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1,2), min_df=1)),
        ("clf", LogisticRegression(max_iter=1000)),
    ])
    pipe.fit(df["text"], df["Category"])
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, MODEL_PATH)

    # augment rules with top merchants per category
    top = (df.groupby(["Category", "Payee"]).size()
             .reset_index(name="n")
             .sort_values(["Category","n"], ascending=[True, False]))
    extras: List[Tuple[str,str]] = []
    for cat in sorted(df["Category"].astype(str).unique()):
        for _, row in top[top["Category"] == cat].head(5).iterrows():
            pat = _norm(str(row["Payee"]))
            if len(pat) >= 4:
                extras.append((pat, cat))
    save_rules(extras)
    return len(df), sorted(df["Category"].astype(str).unique().tolist())

def model_status():
    return {
        "model_exists": MODEL_PATH.exists(),
        "rules_exists": RULES_PATH.exists(),
        "model_path": str(MODEL_PATH),
        "rules_path": str(RULES_PATH),
    }
