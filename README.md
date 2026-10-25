# AI FOODLOOP

AI FOODLOOP is an AI-driven food demand planning system for institutional kitchens, college canteens, restaurants, and food-service providers.

> **Core principle:** Prevent surplus first. Recover safely when surplus occurs.

## MVP

- Import historical meal-demand data from CSV.
- Validate and preprocess dates, meals, quantities, and optional context columns.
- Generate an explainable baseline forecast from recent comparable observations.
- Recommend a production quantity with a configurable safety buffer.
- Record surplus events and track redistribution or disposal status.
- View the workflow through a Streamlit dashboard with demand forecasting,
  historical insights, human safety verification, redistribution eligibility,
  recipient assignment, delivery/disposal tracking, and audit history.

No fabricated dataset, credentials, model accuracy, or redistribution safety certification is included. Use approved operational data.

## Stack and architecture

- **Python 3.11+** for data, API, dashboard, and tests.
- **FastAPI + Pydantic** for a typed REST API.
- **pandas** for CSV ingestion and preprocessing.
- **SQLite** for simple local MVP persistence.
- **Streamlit** for the first dashboard.
- **pytest** for automated tests.

```text
ai-foodloop/
├── app/
│   ├── api/             # FastAPI routes
│   ├── core/            # configuration
│   ├── db/              # SQLite schema and connection
│   ├── forecasting/     # preprocessing and forecast logic
│   ├── surplus/         # legacy surplus tracking service
│   ├── redistribution/  # verified surplus recovery workflow
│   ├── analytics/       # evidence-based food-waste insights
│   └── main.py
├── dashboard/
├── data/
├── tests/
├── requirements.txt
└── .env.example
```

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` to change defaults.

Authentication requires a random `FOODLOOP_AUTH_SECRET_KEY` of at least 32
characters. Do not commit `.env` or share this secret. Create the first
administrator explicitly, once, after configuring the environment:

```powershell
python -m app.auth_bootstrap --username admin@example.com
```

The command reads the password interactively and never prints it. Normal
application startup does not create or reset administrator accounts.

Available roles are `ADMIN`, `KITCHEN_OPERATOR`, `FOOD_SAFETY_VERIFIER`, and
`AUDITOR`. Protected API operations use bearer tokens obtained from
`POST /api/auth/login`; token expiration is configured by
`FOODLOOP_AUTH_TOKEN_MINUTES` and logout requires discarding the client token.

Run the API:

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

Run the dashboard in another terminal:

```powershell
streamlit run dashboard/streamlit_app.py
```

The dashboard opens with a responsive platform overview. Upload an approved
CSV to activate forecasting, evaluation, food-waste insight, and operational
workflow sections. The homepage uses real uploaded data only; it does not
display fabricated accuracy, savings, or sustainability metrics.

## CSV format

Required columns: `date`, `meal_name`, `quantity_prepared`, `quantity_consumed`.

Optional columns: `day_of_week`, `event_flag`, `weather`.

The preprocessing layer derives `quantity_waste` and normalizes dates and numeric fields. Start with `data/sample_input_template.csv`, replacing its example rows with real data.

Uploads are checked before forecasting. The default limits are 5,000,000 bytes,
50,000 data rows, 32 columns, and a 100-row dashboard preview. They can be
overridden with `FOODLOOP_UPLOAD_MAX_BYTES`, `FOODLOOP_UPLOAD_MAX_ROWS`,
`FOODLOOP_UPLOAD_MAX_COLUMNS`, and `FOODLOOP_UPLOAD_PREVIEW_ROWS`; each limit
must be a positive integer.

The validator accepts UTF-8 CSV files (including UTF-8 BOM), rejects empty,
malformed, structurally inconsistent, oversized, or ambiguously headed files,
and reports missing required values, invalid dates or quantities, negative
quantities, duplicate rows, and unexpected columns without silently repairing
the upload. Optional `day_of_week`, `event_flag`, and `weather` columns may be
omitted. A quality report includes row validity, missing values, date range,
meal counts, totals, and observed surplus when those values can be derived.

Forecast readiness is shown as `READY`, `READY WITH WARNINGS`, or `NOT READY`.
Blocking validation errors and missing historical observations in the selected
lookback window produce `NOT READY`. A valid dataset with limited history can
be `READY WITH WARNINGS`; the existing baseline forecast remains unchanged and
uses the configured lookback period and comparable weekday observations when
available. Forecast execution is blocked while readiness is `NOT READY`.

## Test

```powershell
python -m pytest
```

The focused upload and readiness tests can be run with:

```powershell
python -m pytest tests/test_data_quality.py tests/test_forecasting.py
```

## Beginner-friendly Hinglish roadmap

### Phase 1 - MVP

Pehle reliable validation aur simple explainable baseline banaya gaya hai. Kitchen team dekh sakti hai ki recommendation kaise aayi; black-box model par jaldi depend nahi karna padega.

### Phase 2 - Better forecasting

Enough real historical data collect hone ke baad moving average ko seasonal-naive, regression, ya time-series models se compare karenge. Time-based validation use hoga; accuracy invent nahi karenge.

### Phase 3 - Operations

Role-based authentication, authorized redistribution workflows, and audit
identity are implemented. Menu calendars, event/weather integrations, and
alerts remain future work.

### Phase 4 - Production

SQLite ko managed PostgreSQL se replace karna, backups, monitoring,
deployment, rate limiting, key rotation, and privacy controls add karna.

Forecast recommendation food-safety approval ka replacement nahi hai. Redistribution mein local regulations, temperature logs, allergen information, expiry rules, recipient eligibility, and authorized staff approval required honge.

## Actual production and consumption observations

Authenticated kitchen operators and administrators can record actual
production and consumption observations from the dashboard or through the
protected `/api/observations` endpoints. Observations contain a stable ID,
date, meal name, non-negative finite quantities, optional notes, creator, and
timestamps. Zero quantities are valid; invalid dates, blank meal names,
negative values, booleans, NaN, and infinity are rejected.

Observations are persisted in SQLite in `production_observations`. Each
submission receives a new ID. The system intentionally does not impose a
meal/date uniqueness constraint because the current data model permits
multiple records and does not establish whether they represent service
periods, batches, or corrections. Existing records are never overwritten and
multiple matching records are shown as ambiguous rather than automatically
aggregated. Corrections are append-only: the original record remains intact and
the new record stores its `supersedes_id` and a required correction reason.
Only the current record in a correction chain is returned by default; history
can include superseded records explicitly. A superseded record cannot be
corrected again, which prevents conflicting branches.

Creation writes an `observation_created` event to
`observation_audit_events` in the same transaction. The existing redistribution
`audit_events` table remains unchanged because its required batch/status
columns are specific to redistribution transitions. Observation writes require
an authenticated `ADMIN` or `KITCHEN_OPERATOR`; all authenticated roles may
read observations. Actor identity is derived from the authenticated context,
not from a client-supplied ID.

The protected API also supports:

```text
POST /api/observations/{observation_id}/correction
GET  /api/observations?limit=100&offset=0&include_superseded=false
```

Observation history is ordered deterministically by date, creation time, and
ID. The service enforces a page size of 1-100 and rejects negative offsets.
The dashboard offers correction only to administrators and kitchen operators;
each correction is written with its audit event in one transaction.

The dashboard keeps saved observations separate from uploaded CSV history.
When exactly one saved observation matches a selected meal and date, the
planning comparison uses its actual quantities. Multiple matches make the
comparison unavailable until the ambiguity is resolved. Forecast demand and
recommended production remain estimates; they are never replaced by actuals,
and observation records do not create redistribution or disposal records.

## Production planning and comparison

The dashboard reuses the baseline forecast to show forecast demand,
recommended production, the selected safety buffer, observations used, method,
and readiness warnings. The recommendation is calculated as:

```text
recommended production = forecast demand * (1 + safety buffer)
```

Forecast demand is an estimate, not a guarantee, and is never presented as
actual production or consumption. When the selected meal and date have exactly
one uploaded observation, the dashboard also compares that operator-provided
production and consumption record with the plan. It does not infer observations
from forecasts or combine ambiguous duplicate records.

Observed surplus requires both actual quantities and is calculated as the
positive part of `actual production - actual consumption`. A negative difference
is reported separately as unmet demand. Missing observations remain
`Unavailable`, and percentage differences are omitted when their denominator is
zero. The comparison is descriptive and does not declare food safe or
redistributable.