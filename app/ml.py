from pathlib import Path
from typing import Tuple, List
import io, joblib, pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

MODEL_DIR  = Path("/data/models")
MODEL_PATH = MODEL_DIR / "category_model.joblib"

def _pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1,2), min_df=2, max_features=50000)),
        ("clf", LogisticRegression(max_iter=200)),
    ])

def is_model_available() -> bool:
    return MODEL_PATH.exists()

def predict_category_ml(text: str) -> str:
    """Assumes model exists; returns a label string."""
    model: Pipeline = joblib.load(MODEL_PATH)
    return str(model.predict([text])[0])

def train_from_csv(csv_bytes: bytes) -> Tuple[int, List[str]]:
    """Train/update ML model from CSV with columns:
       Date, Payee, Category, Memo, Amount (or Outflow/Inflow)."""
    df = pd.read_csv(io.BytesIO(csv_bytes))
    df.columns = [c.strip().title() for c in df.columns]
    if "Category" not in df.columns or "Payee" not in df.columns:
        return 0, []

    X = (df["Payee"].astype(str) + " " + df.get("Memo", "").astype(str)).tolist()
    y = df["Category"].astype(str).tolist()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model = _pipeline().fit(X, y)
    joblib.dump(model, MODEL_PATH)
    return len(df), sorted(df["Category"].astype(str).unique().tolist())

def model_status():
    return {
        "model_exists": MODEL_PATH.exists(),
        "model_path": str(MODEL_PATH),
    }
