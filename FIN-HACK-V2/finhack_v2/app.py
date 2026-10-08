from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEMO_FILE = DATA_DIR / "sample_transactions.csv"
UPLOADED_FILE = DATA_DIR / "uploaded.csv"
DB_PATH = BASE_DIR / "finhack.db"

app = Flask(__name__)

REQUIRED_COLUMNS = ["transaction_id", "amount", "hour", "location_change", "daily_frequency"]
RISK_LEVELS = {"LOW": (0, 39), "MEDIUM": (40, 69), "HIGH": (70, 100)}


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                transaction_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                note TEXT DEFAULT '',
                reviewed_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def generate_demo_dataset(n: int = 800, seed: int = 42) -> pd.DataFrame:
    """Generate reproducible synthetic transactions with naturally embedded anomalies.

    The anomaly detector never reads a ground-truth anomaly label. Labels are only retained
    internally in the generator for QA and are not written to the CSV.
    """
    rng = np.random.default_rng(seed)
    accounts = [f"ACC-{i:03d}" for i in range(1, 41)]
    categories = [
        "Office Supplies", "Inventory", "Travel", "Utilities", "Payroll",
        "Equipment Purchase", "Professional Services", "Marketing", "Software",
        "Rent", "Fuel", "Maintenance"
    ]
    cities = ["Hyderabad", "Secunderabad", "Bengaluru", "Chennai", "Pune", "Mumbai"]
    base_city = {a: cities[i % len(cities)] for i, a in enumerate(accounts)}
    rows = []
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=45)

    for i in range(n):
        account = rng.choice(accounts)
        day = int(rng.integers(0, 46))
        dt = start + timedelta(days=day)
        category = rng.choice(categories)
        is_anomaly = i < max(18, int(n * 0.035))

        # Account-specific behavioural baseline.
        typical = {
            "Office Supplies": 4500, "Inventory": 18000, "Travel": 8500,
            "Utilities": 6500, "Payroll": 32000, "Equipment Purchase": 28000,
            "Professional Services": 14500, "Marketing": 11000, "Software": 9000,
            "Rent": 25000, "Fuel": 4200, "Maintenance": 7600
        }[category]
        account_factor = 0.65 + (int(account[-3:]) % 11) * 0.07
        amount = max(300, rng.lognormal(math.log(typical * account_factor), 0.42))
        hour = int(np.clip(rng.normal(13.5, 2.7), 7, 21))
        location_change = 0
        frequency = int(np.clip(rng.poisson(3) + 1, 1, 10))
        city = base_city[account]
        recurring = int(category in {"Utilities", "Rent", "Software", "Payroll"} and rng.random() < 0.65)

        if is_anomaly:
            kind = i % 5
            if kind == 0:  # unusually large amount
                amount *= rng.uniform(7, 15)
            elif kind == 1:  # odd hour + amount spike
                amount *= rng.uniform(4, 9)
                hour = int(rng.choice([0, 1, 2, 3, 23]))
            elif kind == 2:  # location deviation
                amount *= rng.uniform(2, 6)
                location_change = 1
                city = rng.choice([c for c in cities if c != base_city[account]])
            elif kind == 3:  # frequency burst
                amount *= rng.uniform(2, 5)
                frequency = int(rng.integers(12, 24))
            else:  # combined behaviour shift
                amount *= rng.uniform(5, 11)
                hour = int(rng.choice([1, 2, 4, 22, 23]))
                location_change = 1
                frequency = int(rng.integers(10, 20))
                city = rng.choice([c for c in cities if c != base_city[account]])

        rows.append({
            "transaction_id": f"TXN-{1001 + i}",
            "account_id": account,
            "date": dt.strftime("%Y-%m-%d"),
            "time": f"{hour:02d}:{int(rng.integers(0, 60)):02d}",
            "amount": round(float(amount), 2),
            "transaction_type": rng.choice(["Debit", "Credit", "Transfer"]),
            "merchant_category": category,
            "location": city,
            "latitude": round(float(rng.uniform(16.2, 19.1)), 5),
            "longitude": round(float(rng.uniform(73.7, 80.3)), 5),
            "account_type": rng.choice(["Business", "Current", "Savings"]),
            "daily_frequency": frequency,
            "hour": hour,
"location_change": location_change,
            "previous_average_amount": round(float(typical * account_factor), 2),
            "is_recurring": recurring,
            "description": f"{category} transaction",
        })

    df = pd.DataFrame(rows)
    # Deliberately add two duplicate records so duplicate handling can be demonstrated.
    dupes = df.iloc[[12, 31]].copy()
    df = pd.concat([df, dupes], ignore_index=True)
    return df


def ensure_demo_file() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not DEMO_FILE.exists() or len(pd.read_csv(DEMO_FILE)) < 100:
        generate_demo_dataset().to_csv(DEMO_FILE, index=False)


def load_raw_data() -> pd.DataFrame:
    ensure_demo_file()
    path = UPLOADED_FILE if UPLOADED_FILE.exists() else DEMO_FILE
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path)
    return pd.read_csv(path)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        raise ValueError("The dataset is empty.")

    out = df.copy()
    missing = [c for c in REQUIRED_COLUMNS if c not in out.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))

    out.columns = [str(c).strip() for c in out.columns]
    out["transaction_id"] = out["transaction_id"].astype(str).str.strip()
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
    out["hour"] = pd.to_numeric(out["hour"], errors="coerce")
    out["location_change"] = pd.to_numeric(out["location_change"], errors="coerce")
    out["daily_frequency"] = pd.to_numeric(out["daily_frequency"], errors="coerce")

    # Friendly defaults for the minimum viable uploaded format.
    out["amount"] = out["amount"].fillna(0).clip(lower=0)
    out["hour"] = out["hour"].fillna(12).clip(lower=0, upper=23)
    out["location_change"] = out["location_change"].fillna(0).clip(lower=0, upper=1)
    out["daily_frequency"] = out["daily_frequency"].fillna(1).clip(lower=1)

    defaults = {
        "account_id": "UNKNOWN",
        "account_type": "Unknown",
        "merchant_category": "Unspecified",
        "location": "Unknown",
        "transaction_type": "Unknown",
        "description": "",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": "12:00",
        "previous_average_amount": np.nan,
        "is_recurring": 0,
    }
    for col, default in defaults.items():
        if col not in out.columns:
            out[col] = default

    out["account_id"] = out["account_id"].fillna("UNKNOWN").astype(str)
    out["merchant_category"] = out["merchant_category"].fillna("Unspecified").astype(str)
    out["location"] = out["location"].fillna("Unknown").astype(str)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").fillna(pd.Timestamp.now()).dt.strftime("%Y-%m-%d")
    out["is_recurring"] = pd.to_numeric(out["is_recurring"], errors="coerce").fillna(0).astype(int).clip(0, 1)

    # Remove exact duplicate transaction IDs, keeping the first and recording the count.
    out["duplicate_count"] = out.duplicated("transaction_id", keep=False).astype(int)
    out = out.drop_duplicates("transaction_id", keep="first").reset_index(drop=True)
    return out


def robust_deviation(values: pd.Series, baseline) -> pd.Series:
    if isinstance(baseline, pd.Series):
        baseline = baseline.astype(float).clip(lower=1)
    else:
        baseline = max(float(baseline), 1.0)

    return (values - baseline).abs() / baseline

def pct_rank(series: pd.Series) -> pd.Series:
    if len(series) <= 1:
        return pd.Series([50.0] * len(series), index=series.index)
    return series.rank(method="average", pct=True) * 100


def analyze(df: pd.DataFrame) -> pd.DataFrame:
    data = normalize(df)

    # Account-specific baseline: median is more robust than mean for transaction spikes.
    data["account_median"] = data.groupby("account_id")["amount"].transform("median").replace(0, np.nan)
    data["account_median"] = data["account_median"].fillna(data["amount"].median()).fillna(1)
    data["amount_ratio"] = data["amount"] / data["account_median"].clip(lower=1)
    data["amount_deviation"] = robust_deviation(data["amount"], data["account_median"])

    # A single fitted scaler is used consistently for model fit and score.
    features = pd.DataFrame({
        "amount_log": np.log1p(data["amount"]),
        "amount_ratio_log": np.log1p(data["amount_ratio"]),
        "hour": data["hour"],
        "location_change": data["location_change"],
        "frequency_log": np.log1p(data["daily_frequency"]),
    })
    scaler = StandardScaler()
    X = scaler.fit_transform(features)

    if len(data) >= 8:
        model = IsolationForest(n_estimators=200, contamination="auto", random_state=42)
        model.fit(X)
        raw_anomaly = -model.decision_function(X)
        ml_score = pct_rank(pd.Series(raw_anomaly, index=data.index))
    else:
        ml_score = pd.Series([50.0] * len(data), index=data.index)

    # Transparent rule signals, each normalized to 0–100.
    amount_signal = np.clip(np.log1p(data["amount_ratio"]) / np.log1p(10) * 100, 0, 100)
    odd_time_signal = np.where((data["hour"] < 6) | (data["hour"] >= 22), 100, 0)
    location_signal = data["location_change"].astype(float) * 100
    frequency_signal = np.clip((data["daily_frequency"] - 6) / 12 * 100, 0, 100)
    duplicate_signal = data["duplicate_count"] * 100

    data["risk_score"] = np.round(
        0.45 * ml_score
        + 0.25 * amount_signal
        + 0.10 * odd_time_signal
        + 0.10 * location_signal
        + 0.07 * frequency_signal
        + 0.03 * duplicate_signal
    ).clip(0, 100).astype(int)

    def make_reasons(row):
        reasons = []
        if row.amount_ratio >= 3:
            reasons.append(f"Amount is {row.amount_ratio:.1f}× the account median")
        elif row.amount_ratio >= 1.8:
            reasons.append("Amount is above the account's usual range")
        if row.hour < 6 or row.hour >= 22:
            reasons.append(f"Unusual transaction time ({int(row.hour):02d}:00)")
        if row.location_change >= 1:
            reasons.append("Location differs from the account's usual activity")
        if row.daily_frequency >= 10:
            reasons.append(f"Sudden frequency increase ({int(row.daily_frequency)} today)")
        if row.duplicate_count:
            reasons.append("Possible duplicate transaction ID")
        if not reasons:
            reasons.append("No strong rule-based risk signal")
        return reasons

    data["reasons"] = data.apply(make_reasons, axis=1)
    data["risk_level"] = pd.cut(
        data["risk_score"], bins=[-1, 39, 69, 100], labels=["LOW", "MEDIUM", "HIGH"]
    ).astype(str)

    # Context-aware explanation for large but historically consistent transactions.
    category_median = data.groupby(["account_id", "merchant_category"])["amount"].transform("median").replace(0, np.nan)
    data["category_median"] = category_median.fillna(data["account_median"])
    data["context_note"] = np.where(
        (data["amount_ratio"] >= 3) & (data["amount"] / data["category_median"].clip(lower=1) < 1.8),
        "Large amount, but consistent with this account's category history.",
        "Review the risk signals before making a final decision."
    )

    data = data.sort_values(["risk_score", "amount"], ascending=[False, False]).reset_index(drop=True)
    return data


def review_map():
    with db_conn() as conn:
        rows = conn.execute("SELECT transaction_id, status, note, reviewed_at FROM reviews").fetchall()
    return {r["transaction_id"]: dict(r) for r in rows}


def build_summary(data: pd.DataFrame):
    counts = data["risk_level"].value_counts().to_dict()
    return {
        "total": int(len(data)),
        "high": int(counts.get("HIGH", 0)),
        "medium": int(counts.get("MEDIUM", 0)),
        "low": int(counts.get("LOW", 0)),
    }


def dashboard_payload(data: pd.DataFrame):
    reviews = review_map()
    rows = []
    for _, r in data.head(120).iterrows():
        item = r.to_dict()
        item["reasons"] = list(r["reasons"])
        item["review"] = reviews.get(r["transaction_id"], {"status": "Pending", "note": ""})
        rows.append(item)

    reason_counts = {}
    for reasons in data["reasons"]:
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    top_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:6]

    trend = (
        data.assign(date_dt=pd.to_datetime(data["date"], errors="coerce"))
        .groupby("date_dt")
        .agg(transactions=("transaction_id", "count"), high=("risk_level", lambda s: int((s == "HIGH").sum())))
        .reset_index()
        .sort_values("date_dt")
        .tail(14)
    )
    trend_data = [
        {"date": d.strftime("%d %b"), "transactions": int(t), "high": int(h)}
        for d, t, h in zip(trend["date_dt"], trend["transactions"], trend["high"])
    ]

    return rows, top_reasons, trend_data


@app.route("/")
def dashboard():
    try:
        data = analyze(load_raw_data())
        rows, top_reasons, trend_data = dashboard_payload(data)
        return render_template(
            "dashboard.html",
            summary=build_summary(data),
            rows=rows,
            top_reasons=top_reasons,
            trend_data=trend_data,
            demo_active=not UPLOADED_FILE.exists(),
        )
    except Exception as exc:
        return render_template("error.html", error=str(exc)), 400


@app.post("/load-demo")
def load_demo():
    DATA_DIR.mkdir(exist_ok=True)
    generate_demo_dataset(800, 42).to_csv(DEMO_FILE, index=False)
    if UPLOADED_FILE.exists():
        UPLOADED_FILE.unlink()
    return jsonify({"ok": True, "message": "Generated 800 synthetic demo transactions."})


@app.post("/upload")
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "Choose a CSV or XLSX file."}), 400
    ext = Path(file.filename).suffix.lower()
    if ext not in {".csv", ".xlsx"}:
        return jsonify({"ok": False, "error": "Only CSV and XLSX files are supported."}), 400
    DATA_DIR.mkdir(exist_ok=True)
    target = DATA_DIR / ("uploaded.xlsx" if ext == ".xlsx" else "uploaded.csv")
    file.save(target)
    # Keep a single active upload path for the app.
    other = DATA_DIR / ("uploaded.csv" if ext == ".xlsx" else "uploaded.xlsx")
    if other.exists():
        other.unlink()
    try:
        analyze(pd.read_excel(target) if ext == ".xlsx" else pd.read_csv(target))
    except Exception as exc:
        target.unlink(missing_ok=True)
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True})


@app.post("/review")
def review():
    payload = request.get_json(silent=True) or {}
    tid = str(payload.get("transaction_id", "")).strip()
    status = str(payload.get("status", "")).strip()
    note = str(payload.get("note", "")).strip()[:500]
    allowed = {"Pending", "Reviewed", "False Positive", "Escalated"}
    if not tid or status not in allowed:
        return jsonify({"ok": False, "error": "Invalid review request."}), 400
    with db_conn() as conn:
        conn.execute(
            "INSERT INTO reviews(transaction_id,status,note,reviewed_at) VALUES(?,?,?,?) "
            "ON CONFLICT(transaction_id) DO UPDATE SET status=excluded.status,note=excluded.note,reviewed_at=excluded.reviewed_at",
            (tid, status, note, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    return jsonify({"ok": True, "transaction_id": tid, "status": status})


@app.get("/api/transaction/<tid>")
def transaction_details(tid):
    data = analyze(load_raw_data())
    match = data[data["transaction_id"].astype(str) == str(tid)]
    if match.empty:
        return jsonify({"ok": False, "error": "Transaction not found."}), 404
    row = match.iloc[0].to_dict()
    row["reasons"] = list(row["reasons"])
    row["review"] = review_map().get(tid, {"status": "Pending", "note": ""})
    # Convert numpy types for JSON.
    clean = json.loads(json.dumps(row, default=lambda x: x.item() if hasattr(x, "item") else str(x)))
    return jsonify({"ok": True, "transaction": clean})


@app.get("/api/stream/next")
def stream_next():
    # Generate one synthetic transaction and score it with the same pipeline as uploaded data.
    df = generate_demo_dataset(40, seed=int(datetime.now().timestamp()) % 100000)
    scored = analyze(df)
    # Pick the highest-priority synthetic transaction so the demo visibly exercises the scoring pipeline.
    result = scored.iloc[0].to_dict()
    result["reasons"] = list(result["reasons"])
    clean = json.loads(json.dumps(result, default=lambda x: x.item() if hasattr(x, "item") else str(x)))
    return jsonify({"ok": True, "transaction": clean, "simulated": True})


@app.post("/reset")
def reset():
    if UPLOADED_FILE.exists():
        UPLOADED_FILE.unlink()
    with db_conn() as conn:
        conn.execute("DELETE FROM reviews")
        conn.commit()
    ensure_demo_file()
    return dashboard()


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "FIN-HACK", "mode": "demo" if not UPLOADED_FILE.exists() else "uploaded"})


if __name__ == "__main__":
    init_db()
    ensure_demo_file()
    app.run(host="127.0.0.1", port=5000, debug=True)
else:
    init_db()
    ensure_demo_file()
