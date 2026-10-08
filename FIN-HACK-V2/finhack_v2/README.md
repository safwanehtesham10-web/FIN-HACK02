# FIN-HACK V2

**AI-Based Financial Anomaly Detection & Risk Monitoring System**

> From checking everything → to knowing what to check first.

FIN-HACK is a student-friendly Flask prototype that helps accountants and CAs prioritize transactions that deserve attention. **AI assists; the accountant decides.** It is an anomaly-prioritization demonstration, not a production fraud detector.

## Features

- Generates an approximately 800-row reproducible synthetic demo dataset.
- CSV/XLSX upload with validation and normalization.
- Account-specific amount baselines using robust medians.
- Isolation Forest anomaly detection with a consistent StandardScaler pipeline.
- Transparent 0–100 risk score and LOW / MEDIUM / HIGH levels.
- Explainable risk signals for amount, time, location, frequency and duplicates.
- Transaction investigation modal.
- Review workflow: Pending, Reviewed, False Positive, Escalated.
- SQLite persistence for review decisions.
- Offline-safe dashboard charts built with HTML/CSS; no CDN is required.
- Clearly marked simulated demo stream using synthetic transactions only.

## Requirements

Python 3.10+ recommended.

## Run locally

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start:

```bash
python app.py
```

Open:

`http://127.0.0.1:5000`

## Demo flow

1. Open the dashboard.
2. Click **Load Demo Dataset** to generate fresh synthetic transactions.
3. Explain the High / Medium / Low priority cards.
4. Open a high-risk transaction and show its reasons.
5. Mark it Reviewed, False Positive or Escalated.
6. Start **Simulated Demo Stream** and explain that it is synthetic, not a bank feed.
7. Upload a CSV/XLSX if you want to demonstrate custom data.

## Risk scoring

The score combines model and transparent rule signals:

- 45% — Isolation Forest anomaly ranking
- 25% — amount deviation from the account-specific median
- 10% — unusual transaction time
- 10% — location deviation
- 7% — unusually high daily frequency
- 3% — duplicate transaction signal

Risk levels:

- **LOW:** 0–39
- **MEDIUM:** 40–69
- **HIGH:** 70–100

The exact score is a prioritization score, not a probability of fraud.

## Dataset columns

Minimum uploaded columns:

`transaction_id, amount, hour, location_change, daily_frequency`

Additional columns such as `account_id`, `date`, `time`, `merchant_category`, `location`, `account_type`, and `description` improve the explanations.

## Limitations

- Synthetic demo data is not real banking data.
- Isolation Forest identifies unusual patterns; it does not prove fraud.
- Risk thresholds are demonstration thresholds and require domain validation before production use.
- SQLite is suitable for this local student prototype, not a high-volume production deployment.
- The simulated stream is not a real-time bank integration.

## Future scope

Explainable feature-contribution models, richer time-series baselines, geo-distance/impossible-travel analysis, document/OCR verification, real-time integrations, role-based access, audit trails, cloud deployment, and bank/accounting integrations.

## 3–5 minute presentation script

**0:00–0:30 — Problem:** Accountants may have many transactions to inspect, so the challenge is deciding what deserves attention first.

**0:30–1:15 — Solution:** FIN-HACK analyzes transaction patterns, detects unusual behaviour, assigns a 0–100 priority score and ranks transactions for human review.

**1:15–2:00 — Dashboard:** Show the risk cards, top signals and priority list. Explain that the system combines Isolation Forest with transparent rules.

**2:00–2:45 — Investigation:** Open a high-risk transaction and explain the account-specific amount deviation, unusual time, location or frequency signals.

**2:45–3:30 — Human decision:** Mark the transaction Reviewed, False Positive or Escalated. Emphasize: **AI assists; accountant decides.**

**3:30–4:15 — Simulated stream:** Start the synthetic stream and show new transactions being scored. Explicitly state that it is a local demo simulation, not a bank connection.

**4:15–5:00 — Impact:** FIN-HACK does not ask accountants to blindly trust AI. It helps them move from **“check everything” to “check what matters.”**
