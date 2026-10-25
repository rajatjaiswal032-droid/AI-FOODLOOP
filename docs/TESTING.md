# AI FOODLOOP Testing

## Local test command

From the project root, use the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Current test coverage

- Preprocessing derives waste and weekday values.
- Baseline forecast uses historical consumption and safety buffer.
- Missing required columns are rejected.
- Missing forecast history is rejected.
- API health endpoint responds.
- API forecast endpoint returns a calculated recommendation.

## Current verified result

The analytics-focused suite passed in the project `.venv`:

```text
11 passed
```

The complete regression suite then passed:

```text
99 passed, 1 warning
```

The remaining warning is the dependency-level Starlette/httpx test-client
deprecation. The application-owned NumPy timedelta and Streamlit
`use_container_width` deprecations were removed. They are not application
failures. Python compilation also passed with `compileall -q app dashboard tests`.

## Required next tests

- Empty CSV and header-only CSV.
- Malformed CSV.
- Missing required values.
- Negative and non-numeric quantities.
- Duplicate records.
- Unexpected columns.
- Weekday forecast selection and fallback limitation.
- Chronological holdout ordering and future-data leakage prevention.
- MAE, RMSE, WAPE, shape validation, and zero-denominator WAPE handling.
- Empty and insufficient evaluation datasets.
- Meal, weekday, and chronological surplus insights.
- Zero-prepared rate handling and no-surplus behavior.
- Invalid dates, missing columns, missing values, and insufficient weekday history.
- Surplus batch validation and pending/rejected/incomplete safety verification.
- Eligibility blocking, active recipients, assignment limits, partial delivery,
  disposal limits, double-count prevention, and audit history.
- Redistribution API creation, verification, assignment, and delivery workflow.
- SQLite initialization and surplus CRUD.
- Processed report output.
- API invalid request responses.

## Manual smoke test

1. Start Streamlit with `.\.venv\Scripts\python.exe -m streamlit run dashboard\streamlit_app.py`.
2. Open the displayed local URL.
3. Confirm the workflow cards and template download are visible.
4. Upload `data/sample_input_template.csv`.
5. Confirm validation, totals, forecast controls, surplus form, chart, and processed CSV download.
6. Separately start FastAPI and open `/api/health` and `/docs`.

## Evaluation assumptions

- The final chronological observations for the selected meal form the holdout.
- Each prediction uses only earlier observations for that meal.
- Previous actual observations become available to later rolling-origin predictions.
- WAPE is `sum(abs(actual - predicted)) / sum(abs(actual)) * 100`.
- WAPE is explicitly unavailable when total actual consumption is zero.
- Evaluation metrics describe historical holdout behavior, not guaranteed future accuracy.

## Historical insight assumptions

- Analytics accepts the validated core columns: `date`, `meal_name`,
  `quantity_prepared`, and `quantity_consumed`.
- Surplus is `max(quantity_prepared - quantity_consumed, 0)`.
- Weekday is derived from the parsed calendar date, not trusted from an uploaded label.
- Weekday highest/lowest comparisons require two observations per weekday by default.
- Empty history, invalid dates, missing values, and missing columns are explicit unavailable
  or validation states; they are not converted to zero.
- Insight signals are descriptive planning prompts for human review, not causal findings,
  automatic production changes, or food-safety approval.

## Safe redistribution workflow assumptions

- A batch is physically recorded surplus, not a forecasted quantity.
- New batches start as `pending_verification`.
- Only a recorded human verification can move a batch toward eligibility.
- Eligibility is blocked unless the latest verification is approved and includes
  condition assessment, storage information, and a future validated expiry/time-limit.
- Missing or uncertain safety evidence is blocked; it is never treated as safe.
- Assignment reserves quantity. Delivery can be partial and cannot exceed the
  undelivered assignment. Disposal can use only unassigned remaining quantity.
- Every status change is retained in `audit_events`; historical records are not overwritten.
- Authentication and role authorization are implemented for API and service
  operations. Client-supplied `verifier_reference` and `operator_reference`
  values are not trusted as identity; authenticated actor identity is recorded.
- No legal temperature, holding-time, expiry, or contamination threshold is inferred
  or hardcoded. Applicable local rules and qualified human judgment remain required.

## Authentication and authorization checks

- Passwords are stored as Argon2 hashes through `pwdlib`; API responses omit hashes.
- JWT bearer tokens require `sub`, `iat`, `exp`, and `jti`, use the configured secret,
  validate expiry/signature, and are rejected when malformed, tampered, expired, or
  issued with another key.
- Protected endpoints require authentication and centralized role permissions.
- `ADMIN` manages users; `KITCHEN_OPERATOR` performs kitchen and recovery operations;
  `FOOD_SAFETY_VERIFIER` performs human safety decisions; `AUDITOR` is read-only.
- Safety verification is verifier/admin-only. Client-supplied verifier/operator fields
  are ignored as identity proof.
- Direct redistribution service calls require an active database user ID with the
  required permission.
- Initial administrator creation uses the interactive one-time command:
  `python -m app.auth_bootstrap --username admin@example.com`.
- Authentication tests use temporary SQLite databases and test-only credentials.
- JWT logout is client-side token disposal; server-side revocation lists are not
  implemented, but disabled accounts are checked on every authenticated request.

## Verified UI/API checks

- `http://127.0.0.1:8000/api/health` returned HTTP 200 with `{"status":"ok"}`.
- `http://127.0.0.1:8501` returned HTTP 200.
- Browser verification rendered the historical insights section with an uploaded
  multi-row CSV and displayed the insufficient weekday-history warning for a one-row CSV.
- Browser verification rendered the Safe Food Redistribution & Traceability section,
  recorded a test batch, showed it blocked before human verification, and rendered the
  human verification form. Complete assignment, partial delivery, disposal, and audit
  lifecycle checks passed through automated service/API tests.
- Browser verification of the redesigned homepage confirmed the hero CTAs,
  capability links, honest no-upload empty state, uploaded operational sections,
  and no horizontal overflow at the tested viewport.
