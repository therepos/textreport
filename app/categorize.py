import json, re, shutil
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from rapidfuzz import fuzz
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

# Runtime data directory (mounted in Docker)
MODEL_DIR  = Path("/data/models")
MODEL_PATH = MODEL_DIR / "category_model.joblib"
RULES_PATH = MODEL_DIR / "rules.json"

# NEW: ship a default rules file in the repo
DEFAULT_RULES_PATH = Path(__file__).parent / "rules.json"

def _norm(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _coerce_to_category_dict(data) -> Dict[str, List[str]]:
    """
    Accepts either:
      - dict: { "Food": ["STARBUCKS", ...], ... }
      - list: [{ "pattern": "STARBUCKS", "category": "Food" }, ...]  (back-compat)
    Returns canonical dict-of-arrays with unique, non-empty patterns.
    """
    out: Dict[str, List[str]] = {}

    if isinstance(data, dict):
        for cat, pats in data.items():
            arr = [str(p).strip() for p in (pats or []) if str(p).strip()]
            if arr:
                out[cat] = sorted(set(arr))
        return out

    if isinstance(data, list):
        for item in data:
            cat = str(item.get("category", "")).strip()
            pat = str(item.get("pattern", "")).strip()
            if cat and pat:
                out.setdefault(cat, []).append(pat)
        for cat in list(out.keys()):
            out[cat] = sorted(set(out[cat]))
        return out

    return {}

def load_rules() -> Dict[str, List[str]]:
    """
    Load category rules. If /data/models/rules.json does not exist,
    attempt to bootstrap it from app/rules.json (if present).
    """
    # Bootstrap from default on first run
    if not RULES_PATH.exists() and DEFAULT_RULES_PATH.exists():
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEFAULT_RULES_PATH, RULES_PATH)

    if not RULES_PATH.exists():
        return {}

    try:
        raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        return _coerce_to_category_dict(raw)
    except Exception:
        return {}

def save_rules(rules: Dict[str, List[str]]) -> None:
    """Persist rules as a dict-of-arrays: {category: [patterns...]}."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = _coerce_to_category_dict(rules)
    RULES_PATH.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")

def apply_rules(payee: str, memo: str, threshold: int = 80) -> Optional[str]:
    """Fuzzy match payee/memo against user patterns (category-first)."""
    rules = load_rules()
    if not rules:
        return None
    s = _norm(f"{payee} {memo}")
    best_cat, best_score = None, -1
    for cat, pats in rules.items():
        for pat in pats:
            score = fuzz.partial_ratio(_norm(pat), s)
            if score > best_score:
                best_cat, best_score = cat, score
    return best_cat if best_score >= threshold else None

# -------- Optional ML fallback --------
def _pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1,2), min_df=2, max_features=50000)),
        ("clf", LogisticRegression(max_iter=200)),
    ])

def predict_category(payee: str, memo: str, refund_hint: bool = False) -> str:
    # 1) Rules first
    cat = apply_rules(payee, memo)
    if cat:
        return cat
    # 2) Optional hint for credits/refunds
    if refund_hint:
        return apply_rules("REFUND", memo) or "Other"
    # 3) ML fallback
    if MODEL_PATH.exists():
        model: Pipeline = joblib.load(MODEL_PATH)
        return str(model.predict([f"{payee} {memo}"])[0])
    return "Other"

def train_from_csv(csv_bytes: bytes) -> Tuple[int, List[str]]:
    """Train/update from CSV with Date,Payee,Category,Memo,Amount|Outflow|Inflow, and seed rules."""
    import io
    df = pd.read_csv(io.BytesIO(csv_bytes))
    df.columns = [c.strip().title() for c in df.columns]
    if "Category" not in df.columns or "Payee" not in df.columns:
        return 0, []

    x = (df["Payee"].astype(str) + " " + df.get("Memo", "").astype(str)).tolist()
    y = df["Category"].astype(str).tolist()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model = _pipeline().fit(x, y)
    joblib.dump(model, MODEL_PATH)

    # Seed rules with frequent payee/category pairs (non-destructive merge)
    top = (df.groupby(["Category", "Payee"]).size()
             .reset_index(name="n").sort_values("n", ascending=False))
    rules = load_rules()
    for _, row in top.iterrows():
        cat = str(row["Category"])
        payee = str(row["Payee"])
        if len(_norm(payee)) < 4:
            continue
        rules.setdefault(cat, [])
        if payee not in rules[cat]:
            rules[cat].append(payee)
    save_rules(rules)

    return len(df), sorted(df["Category"].astype(str).unique().tolist())

def model_status():
    return {
        "model_exists": MODEL_PATH.exists(),
        "rules_exists": RULES_PATH.exists(),
        "model_path": str(MODEL_PATH),
        "rules_path": str(RULES_PATH),
    }
