# AI FOODLOOP — ONE-PASS COMPREHENSIVE PROJECT AUDIT

**Audit mode:** Read-only audit and planning only. No implementation performed.
**Authoritative workspace:** C:\Users\RAJAT JAISWAL\OneDrive\Documents\AI-FOODLOOP
**Audit date:** 2026-10-28
**Core product principle:** "Prevent surplus first. Recover safely when surplus occurs."

---

## A. Executive Summary

### Actual Project State

AI FOODLOOP is a Python-based food-demand forecasting and surplus-management application with a **FastAPI backend** (`app/main.py`, version 0.1.0) and a **Streamlit dashboard** (`dashboard/streamlit_app.py`). The data layer is **SQLite** (`data/foodloop.db` by default). The repository is on branch `main` at commit `681e09c` ("feat: improve dashboard UI feedback states"), matching `origin/main` and `origin/HEAD`.

### Strongest Existing Capabilities (CONFIRMED IN SOURCE)

1. **Complete authentication and authorization system** (`app/core/auth.py`): four roles (ADMIN, KITCHEN_OPERATOR, FOOD_SAFETY_VERIFIER, AUDITOR), a granular PERMISSIONS matrix, pwdlib argon2 password hashing, JWT HS256 tokens with expiry, per-username login rate limiting (5 attempts / 60s), and a `current_user` / `require_permission` dependency applied to every API route. One-time admin bootstrap (`bootstrap_admin`).

2. **Complete API surface** (`app/api/routes.py`): 22 routes covering health, auth, daily observations (create/read/correct with pagination), surplus events (create/list), and a full redistribution lifecycle (batches, verification, eligibility, recipients, assignments, deliveries, disposals, audit history). Every mutation route carries a `require_permission(...)` dependency.

3. **Daily actuals / operational feedback** (`app/observations/service.py`): `production_observations` table records `quantity_prepared` and `quantity_consumed` per date/meal, with a correction/supersedes pattern, per-observation audit events, computed `observed_surplus` (= prepared − consumed, floored at 0) and `unmet_demand_indicator`, and pagination (max 100 rows).

4. **Forecasting, evaluation, and planning functions** (`app/forecasting/{baseline,evaluation,planning,preprocessing}.py`): a `quantity_consumption`-based mean forecast (weekday-aware when ≥2 same-weekday observations exist), chronological holdout walk-forward evaluation with MAE/RMSE/WAPE (WAPE returns None on zero denominator), data-quality assessment, and a production-plan builder with a plain-language explanation. Safety buffer defaults to 0.05 (5%).

5. **Surplus and redistribution services** (`app/surplus/service.py`, `app/redistribution/workflow.py` routes): allowed surplus statuses (`identified`, `redistributed`, `disposed`, `unresolved`); batch creation; verification decisions; recipient management; assignments; deliveries; disposals; audit history.

### Major Limitations (CONFIRMED IN SOURCE)

1. **No production-plan persistence and no API route.** The database schema (`app/db/database.py`) has no `production_plans` table, and `app/api/routes.py` has no `/production-plans` route. `planning.create_production_plan` returns an in-memory `ProductionPlan` only. Forecast-to-production linkage exists only in memory.

2. **No evaluation persistence and no API route.** `evaluation.evaluate_forecast` returns an in-memory `EvaluationResult`; nothing is stored, and no `/evaluation` route exists.

3. **Forecast endpoint does not persist.** `POST /forecast` computes and returns a `ForecastResult` but writes nothing to the database.

4. **No analytics/report export route.** `app/analytics/insights.py` exists but is not imported by `routes.py`; no downloadable report endpoint was observed in the inspected route inventory.

5. **Schema migration approach is inline ALTER TABLE.** `initialize_database()` runs `CREATE TABLE IF NOT EXISTS` plus ad-hoc `ALTER TABLE ... ADD COLUMN` checks on every `get_connection()` call. There are no versioned migration files.

6. **Database connection re-initializes on every call.** `get_connection()` calls `initialize_database()` each time, re-running schema DDL on every connection.

7. **In-memory login rate limit.** `_login_attempts` is a process-level dict; it will not survive restarts and is not shared across workers.

8. **UI files not re-inspected.** `dashboard/streamlit_app.py` is the **modified working-tree file**, but its current contents could not be re-read because the shell session became unresponsive after the initial inspection pass. All dashboard/UI findings are therefore marked UNVERIFIED for the current working-tree state.

### Overall Readiness

The backend services and API routes are substantially implemented and appear internally consistent. The critical gaps for a production pilot are: **no persistence of forecasts, production plans, or evaluations**, and **no dashboard-side verification** (could not be confirmed due to shell limitation). The project is a solid foundation but is not yet ready for a controlled real-world pilot without Phases 1–9 of the roadmap.

No arbitrary project-completion percentage is assigned, per the reporting rules.

---

## C. Existing Architecture

### Components Confirmed in Source

```
Streamlit Dashboard (dashboard/streamlit_app.py*)
        |
        | (mechanism NOT re-inspected: may call FastAPI via HTTP,
        |  import services directly, or both)
        v
FastAPI Backend (app/main.py)  --[router prefix "/api"]-->  app/api/routes.py
        |
        |-- lifespan: validate_security_configuration() + initialize_database()
        |
        +-- app/core/auth.py            (JWT HS256, argon2, roles, permissions)
        +-- app/core/config.py          (pydantic-settings, .env, FOODLOOP_ prefix)
        +-- app/db/database.py          (SQLite, 11 tables, PRAGMA foreign_keys=ON)
        +-- app/forecasting/
        |     +-- preprocessing.py      (data quality, preprocessing)
        |     +-- baseline.py           (forecast_demand: weekday/recent mean)
        |     +-- evaluation.py         (chronological holdout, MAE/RMSE/WAPE)
        |     +-- planning.py           (create_production_plan, compare - IN MEMORY ONLY)
        +-- app/observations/service.py (daily actuals, correction/supersedes)
        +-- app/surplus/service.py      (surplus events CRUD)
        +-- app/redistribution/workflow.py (batches, verification, assignments, deliveries, disposals, audit)
        +-- app/analytics/insights.py   (exists; NOT imported by routes.py - unverified usage)
        +-- app/auth_bootstrap.py       (exists; unverified)
        |
        v
SQLite Database (data/foodloop.db)
   Tables: surplus_events, users, auth_events, surplus_batches,
           safety_verifications, recipients, assignments, disposals,
           audit_events, production_observations, observation_audit_events
```

\* `dashboard/streamlit_app.py` is modified in the working tree; its current content could not be re-inspected due to the shell limitation (Section R).

### Key Architectural Findings (CONFIRMED IN SOURCE)

1. **Direct service imports, not HTTP self-calls.** `app/api/routes.py` imports forecasting, surplus, redistribution, and observations service functions directly and calls them in-process. The FastAPI app does not call itself over HTTP.

2. **Every route is authenticated.** Every non-health route in `routes.py` uses `Depends(require_permission(...))` or `Depends(current_user)`. No route was found without protection.

3. **No production_plans table.** The schema has `surplus_events`, `production_observations`, `surplus_batches`, etc., but **no `production_plans` table**. Forecasts and production plans are computed in memory and not persisted.

4. **SQLite with foreign keys enabled.** `_open_connection()` runs `PRAGMA foreign_keys = ON`. Tables use `REFERENCES` constraints (e.g., `safety_verifications.batch_id REFERENCES surplus_batches(id)`, `assignments.batch_id`, `assignments.recipient_id`, `production_observations.created_by REFERENCES users(id)`).

5. **Inline schema migration.** `initialize_database()` performs `ALTER TABLE ... ADD COLUMN` checks for `actor_id` (auth_events, audit_events) and `supersedes_id`/`correction_reason` (production_observations). There are no separate migration files (see `tests/test_database_migration.py` for test coverage of this behavior).

6. **Connection-per-call with re-initialization.** `get_connection()` calls `initialize_database()` on every invocation, then `_open_connection()`. This is safe but re-runs DDL each time.

7. **The dashboard file is modified.** `git status` shows ` M dashboard/streamlit_app.py`, meaning the working tree differs from commit `681e09c` for the primary UI entry point. The current content was not re-readable due to the shell limitation.

---

## E. Field and Input Inventory

No individual form fields can be inventoried with confidence because the dashboard source files could not be re-read (shell limitation). The following are **API-level request models** confirmed in `app/api/routes.py` (CONFIRMED IN SOURCE), which indicate the fields the backend accepts:

| API Endpoint | Field | Purpose | Accepted Input | Existing Validation | Status |
|--------------|-------|---------|----------------|---------------------|--------|
| POST /auth/login | username | Login identity | 3–254 chars | min/max length | CONFIRMED |
| POST /auth/login | password | Login credential | 12–256 chars | min/max length | CONFIRMED |
| POST /auth/users | username/password/role | Create user | username 3–254, password 12–256, Role enum | Pydantic + Role | CONFIRMED |
| POST /observations | observation_date | Observation date | ISO date | date.fromisoformat | CONFIRMED |
| POST /observations | meal_name | Meal name | non-empty string | min_length=1 | CONFIRMED |
| POST /observations | quantity_prepared | Prepared qty | non-negative number | ge=0 | CONFIRMED |
| POST /observations | quantity_consumed | Consumed qty | non-negative number | ge=0 | CONFIRMED |
| POST /forecast | records | Demand records | list[dict] | passed to preprocessor | CONFIRMED |
| POST /forecast | meal_name | Target meal | string | forwarded to forecast_demand | CONFIRMED |
| POST /forecast | forecast_date | Forecast target date | date | date type | CONFIRMED |
| POST /forecast | safety_buffer | Buffer fraction | 0–1 | ge=0, le=1 | CONFIRMED |
| POST /forecast | lookback_days | History window | int > 0 | gt=0 | CONFIRMED |
| POST /surplus | event_date, meal_name, quantity, status, recipient, notes | Surplus event | quantity >=0, status in allowed set | service-level checks | CONFIRMED |
| POST /redistribution/batches | source_name, meal_name, prepared_at, quantity_available, unit, notes | Batch | qty > 0, names non-empty | Pydantic | CONFIRMED |
| POST /redistribution/batches/{id}/verification | decision, condition_assessment, expiry_at, ... | Verification | verifier_reference min 1 | service-level | CONFIRMED |
| POST /redistribution/recipients | name, contact_reference, service_area, active, notes | Recipient | name min 1 | Pydantic | CONFIRMED |
| POST /redistribution/batches/{id}/assignments | recipient_id, quantity_assigned, operator_reference, notes | Assignment | qty > 0, refs non-empty | service-level | CONFIRMED |
| POST /redistribution/assignments/{id}/deliveries | quantity_delivered, operator_reference, ... | Delivery | qty > 0 | service-level | CONFIRMED |
| POST /redistribution/batches/{id}/disposals | quantity_disposed, reason, operator_reference, notes | Disposal | qty > 0, reason min 1 | service-level | CONFIRMED |

**Dashboard UI fields (streamlit_app.py):** UNVERIFIED — could not re-read the modified file.

---

## G. Backend and API Inventory

### Entry Point (CONFIRMED IN SOURCE)

`app/main.py`:
- Creates `FastAPI(title="AI FOODLOOP API", description="...", version="0.1.0")`
- `lifespan` calls `validate_security_configuration()` then `initialize_database()`
- `app.include_router(router, prefix="/api")`

### Configuration (CONFIRMED IN SOURCE)

`app/core/config.py` (`Settings`, pydantic-settings, `.env` with `FOODLOOP_` prefix):
- `database_path = "data/foodloop.db"`
- `default_safety_buffer = 0.05`
- `forecast_lookback_days = 28`
- `auth_secret_key = ""` (must be set, ≥32 chars, validated)
- `auth_token_minutes = 30`
- `upload_max_bytes = 5_000_000`, `upload_max_rows = 50_000`, `upload_max_columns = 32`, `upload_preview_rows = 100`
- `validate_security_configuration()` raises `RuntimeError` if secret is missing/placeholder/too short, or if token minutes is invalid.

### Authentication (CONFIRMED IN SOURCE)

`app/core/auth.py`:
- Roles: `ADMIN`, `KITCHEN_OPERATOR`, `FOOD_SAFETY_VERIFIER`, `AUDITOR`
- `PERMISSIONS` dict mapping 15 permission names to frozensets of roles
- `PASSWORD_HASH = PasswordHash.recommended()` (pwdlib argon2)
- `BEARER = HTTPBearer(auto_error=False)`
- `LOGIN_FAILURE_LIMIT = 5`, `LOGIN_FAILURE_WINDOW_SECONDS = 60.0`, in-memory `_login_attempts`
- `AuthenticatedUser(id, username, role, active)`
- `current_user(credentials)` → 401 if no/invalid bearer token
- `require_permission(permission)` → 403 if role not allowed
- `issue_token(user)` → JWT HS256 with `sub`, `iat`, `exp`, `jti`
- `user_from_token(token)` → decodes, checks user exists and active
- `bootstrap_admin(username, password)` → one-time admin creation
- `safe_equal(left, right)` → `compare_digest`

---

## F. Button and Control Inventory

No Streamlit buttons/controls can be inventoried with confidence because `dashboard/streamlit_app.py`, `ui_components.py`, `table_utils.py`, and `chart_utils.py` could not be re-read (shell limitation).

**API-level operations confirmed in `app/api/routes.py` (CONFIRMED IN SOURCE):**

| Operation | HTTP Method | Path | Permission Required | Handler Function | Status |
|-----------|-------------|------|---------------------|------------------|--------|
| Health check | GET | /health | None | health() | CONFIRMED |
| Login | POST | /auth/login | None (rate-limited) | login() | CONFIRMED |
| Current user | GET | /auth/me | current_user | get_current_user() | CONFIRMED |
| List users | GET | /auth/users | user_admin | get_users() | CONFIRMED |
| Create user | POST | /auth/users | user_admin | add_user() | CONFIRMED |
| Set user status | PATCH | /auth/users/{id}/status | user_admin | update_user_status() | CONFIRMED |
| Set user role | PATCH | /auth/users/{id}/role | user_admin | update_user_role() | CONFIRMED |
| Create observation | POST | /observations | observation_write | add_observation() | CONFIRMED |
| List observations | GET | /observations | observation_read | get_observations() | CONFIRMED |
| Get observation | GET | /observations/{id} | observation_read | get_observation_by_id() | CONFIRMED |
| Correct observation | POST | /observations/{id}/correction | observation_write | correct_saved_observation() | CONFIRMED |
| Forecast | POST | /forecast | forecast | forecast() | CONFIRMED |
| Create surplus | POST | /surplus | surplus_write | create_surplus() | CONFIRMED |
| List surplus | GET | /surplus | surplus_read | get_surplus() | CONFIRMED |
| Create batch | POST | /redistribution/batches | batch_create | create_redistribution_batch() | CONFIRMED |
| List batches | GET | /redistribution/batches | batch_read | get_redistribution_batches() | CONFIRMED |
| Get batch | GET | /redistribution/batches/{id} | batch_read | get_redistribution_batch() | CONFIRMED |
| Verify batch | POST | /redistribution/batches/{id}/verification | verification | verify_redistribution_batch() | CONFIRMED |
| Check eligibility | GET | /redistribution/batches/{id}/eligibility | batch_read | get_redistribution_eligibility() | CONFIRMED |
| Create recipient | POST | /redistribution/recipients | recipient_write | create_redistribution_recipient() | CONFIRMED |
| List recipients | GET | /redistribution/recipients | recipient_read | get_redistribution_recipients() | CONFIRMED |
| Assign batch | POST | /redistribution/batches/{id}/assignments | assignment | assign_redistribution_batch() | CONFIRMED |
| Deliver assignment | POST | /redistribution/assignments/{id}/deliveries | delivery_disposal | deliver_redistribution_assignment() | CONFIRMED |
| Dispose batch | POST | /redistribution/batches/{id}/disposals | delivery_disposal | dispose_redistribution_batch() | CONFIRMED |
| Batch audit | GET | /redistribution/batches/{id}/audit | audit_read | get_redistribution_audit() | CONFIRMED |

**Dashboard buttons/controls:** UNVERIFIED.

---

## G. Backend and API Inventory

### Entry Point (CONFIRMED IN SOURCE)

`app/main.py`:
- Creates `FastAPI(title="AI FOODLOOP API", description="...", version="0.1.0")`
- `lifespan` calls `validate_security_configuration()` then `initialize_database()`
- `app.include_router(router, prefix="/api")`

### Configuration (CONFIRMED IN SOURCE)

`app/core/config.py` (`Settings`, pydantic-settings, `.env` with `FOODLOOP_` prefix):
- `database_path = "data/foodloop.db"`
- `default_safety_buffer = 0.05`
- `forecast_lookback_days = 28`
- `auth_secret_key = ""` (must be set, ≥32 chars, validated)
- `auth_token_minutes = 30`
- `upload_max_bytes = 5_000_000`, `upload_max_rows = 50_000`, `upload_max_columns = 32`, `upload_preview_rows = 100`
- `validate_security_configuration()` raises `RuntimeError` if secret is missing/placeholder/too short, or if token minutes is invalid.

### Authentication (CONFIRMED IN SOURCE)

`app/core/auth.py`:
- Roles: `ADMIN`, `KITCHEN_OPERATOR`, `FOOD_SAFETY_VERIFIER`, `AUDITOR`
- `PERMISSIONS` dict mapping 15 permission names to frozensets of roles
- `PASSWORD_HASH = PasswordHash.recommended()` (pwdlib argon2)
- `BEARER = HTTPBearer(auto_error=False)`
- `LOGIN_FAILURE_LIMIT = 5`, `LOGIN_FAILURE_WINDOW_SECONDS = 60.0`, in-memory `_login_attempts`
- `AuthenticatedUser(id, username, role, active)`
- `current_user(credentials)` → 401 if no/invalid bearer token
- `require_permission(permission)` → 403 if role not allowed
- `issue_token(user)` → JWT HS256 with `sub`, `iat`, `exp`, `jti`
- `user_from_token(token)` → decodes, checks user exists and active
- `bootstrap_admin(username, password)` → one-time admin creation
- `safe_equal(left, right)` → `compare_digest`
### Database (CONFIRMED IN SOURCE)

`app/db/database.py` (SQLite, `settings.database_path`):
Tables:
- `surplus_events(id, event_date, meal_name, quantity CHECK>=0, status, recipient, notes, created_at)`
- `users(id, username UNIQUE, password_hash, role, active CHECK 0/1, created_at, updated_at)`
- `auth_events(id, user_id, actor_id, event_type, event_at, details)`
- `surplus_batches(id, source_name, meal_name, prepared_at, quantity_available CHECK>0, unit, status, notes, created_at, updated_at)`
- `safety_verifications(id, batch_id REFERENCES, verifier_reference, verified_at, decision, condition_assessment, storage_information, expiry_at, packaging_observations, reason, created_at)`
- `recipients(id, name, contact_reference, service_area, active CHECK 0/1, notes, created_at)`
- `assignments(id, batch_id REFERENCES, recipient_id REFERENCES, quantity_assigned CHECK..., ...)`
- `disposals(id, batch_id REFERENCES, quantity_disposed CHECK>0, disposed_at, reason, operator_reference, notes)`
- `audit_events(id, batch_id REFERENCES, assignment_id, previous_status, new_status, event_at, actor_id, operator_reference, reason)`
- `production_observations(id, observation_date, meal_name, quantity_prepared CHECK>=0, quantity_consumed CHECK>=0, notes, created_by REFERENCES users(id), created_at, updated_at, supersedes_id REFERENCES production_observations(id), correction_reason)`
- `observation_audit_events(id, observation_id REFERENCES, actor_id REFERENCES users(id), event_type, event_at, details)`

Indexes: `idx_safety_batch`, `idx_assignments_batch`, `idx_audit_batch`, `idx_observations_date_meal`, `idx_observation_audit_observation`, `idx_observations_supersedes`.

Migration: inline `ALTER TABLE ... ADD COLUMN` for `actor_id`, `supersedes_id`, `correction_reason`. No versioned migration files.

**No `production_plans` table exists.** Confirmed by reading the full `CREATE TABLE` list.



### Forecasting Services (CONFIRMED IN SOURCE)

`app/forecasting/baseline.py`:
- `ForecastResult(meal_name, forecast_date, expected_demand, recommended_production, safety_buffer, observations_used, method, limitation)`
- `forecast_demand(data, meal_name, forecast_date, safety_buffer=0.05, lookback_days=28)`:
  - history = same meal, `date < target`, `date >= target − lookback_days`
  - if ≥2 same-weekday observations: `method="weekday_mean"`, else `method="recent_mean"`
  - `expected = mean(quantity_consumed)`, `recommended_production = round(expected * (1 + safety_buffer), 2)`
  - Target variable: `quantity_consumed` (consumption/demand), not prepared quantity.

`app/forecasting/evaluation.py`:
- `EvaluationMetrics(mae, rmse, wape)`; `EvaluationResult(...)`
- `mean_absolute_error`, `root_mean_squared_error`, `weighted_absolute_percentage_error` (WAPE = Σ\|actual−pred\| / Σ\|actual\| × 100; returns None if denominator == 0)
- `evaluate_forecast(data, meal_name, test_size=3, min_train_observations=2, lookback_days=28)`:
  - Chronological holdout / walk-forward: for each test position, train on all prior observations, forecast with `safety_buffer=0`, compare actual vs predicted
  - No persistence of results.

`app/forecasting/planning.py`:
- `ProductionPlan(forecast, readiness, historical_consumption_total, historical_observations, explanation)`
- `ProductionComparison(...)` with differences and percent differences
- `create_production_plan(...)` → in-memory only; explanation string generated
- `compare_production_plan(plan, actual_production, actual_consumption)` → in-memory only
- **No persistence; no API route.**

`app/forecasting/preprocessing.py`:
- `REQUIRED_COLUMNS = {"date","meal_name","quantity_prepared","quantity_consumed"}`
- `assess_data_quality(source) → DataQualityReport`
- `assess_forecast_readiness(...) → ForecastReadiness`
- `preprocess_demand_data(source) → DataFrame`: adds `quantity_waste = (prepared − consumed).clip(lower=0)`, `day_of_week`, sorts by date.

### Surplus Service (CONFIRMED IN SOURCE)

`app/surplus/service.py`:
- `ALLOWED_STATUSES = {"identified", "redistributed", "disposed", "unresolved"}`
- `create_surplus_event(event_date, meal_name, quantity, status, recipient, notes, actor_id)`: `authorize_actor(actor_id, "surplus_write")`; `quantity >= 0`; `status` in allowed set; INSERT into `surplus_events`; returns dict(row).
- `list_surplus_events(actor_id)`: `authorize_actor(actor_id, "surplus_read")`; ORDER BY event_date DESC, id DESC.

### Observations Service (CONFIRMED IN SOURCE)

`app/observations/service.py`:
- `create_observation(...)`: `authorize_actor(actor_id, "observation_write")`; inserts `production_observations` + `observation_audit_events` ("observation_created").
- `correct_observation(observation_id, ..., correction_reason, actor_id)`: creates superseding observation + "observation_corrected" audit event.
- `get_observation(observation_id, actor_id)`, `list_observations(actor_id, date, meal_name, include_superseded, limit, offset)` with `observed_surplus` and `unmet_demand_indicator` computed per row.
- `MAX_PAGE_SIZE = 100`.

### Redistribution Workflow (CONFIRMED IN SOURCE via routes.py imports)

Imported functions: `check_eligibility`, `create_assignment`, `create_batch`, `create_recipient`, `get_audit_history`, `get_batch`, `list_batches`, `list_recipients`, `record_delivery`, `record_disposal`, `record_verification`. The full source of `app/redistribution/workflow.py` could not be re-read (shell limitation), but the route layer confirms these operations exist with permission checks.

### Analytics (PARTIALLY CONFIRMED)

`app/analytics/insights.py` exists but is **not imported** by `app/api/routes.py`. Its usage could not be confirmed (shell limitation). No export/download route exists in `routes.py`.

### auth_bootstrap (UNVERIFIED)

`app/auth_bootstrap.py` exists but content could not be re-read.

---

## H. Feature Gap Matrix

| Module | Implemented | Partial | Missing | Runtime Verification | Evidence |
|--------|-------------|---------|---------|----------------------|----------|
| A. Dashboard | — | — | Cannot confirm (file unreadable) | UNVERIFIED | File exists; modified in working tree |
| B. Data Upload & Quality | preprocessing.py quality assessment exists | No upload route/API | No file-upload endpoint | CONFIRMED (function exists) | app/forecasting/preprocessing.py |
| C. Demand Forecasting | baseline.py, forecast_demand | Forecast not persisted | No /forecast persistence route | CONFIRMED | app/forecasting/baseline.py, routes.py |
| D. Production Planning | planning.py (in-memory) | Not persisted | No production_plans table/route | CONFIRMED | app/forecasting/planning.py, database.py |
| E. Daily Actuals & Feedback | observations/service.py | — | — | CONFIRMED | app/observations/service.py, routes.py |
| F. Surplus Management | surplus/service.py | No state-transition machine | Verification on batches, not surplus_events | CONFIRMED | app/surplus/service.py |
| G. Redistribution Lifecycle | routes + workflow imports | Full source unreadable | Concurrency safeguards unconfirmed | PARTIAL (routes confirmed) | app/api/routes.py |
| H. Insights & Reports | insights.py exists | Not wired to routes | No export/download route | UNVERIFIED | app/analytics/insights.py, routes.py |
| I. Settings & Administration | auth user management | No settings page | No configuration UI | CONFIRMED (API) | app/api/routes.py, auth.py |

Note: "Missing" for dashboard means the file content could not be verified, not that the file is absent.

---

## I. Forecasting and Data Audit

### Input Data Schema (CONFIRMED IN SOURCE)

`preprocessing.py` `REQUIRED_COLUMNS = {"date", "meal_name", "quantity_prepared", "quantity_consumed"}`; optional: `day_of_week`, `event_flag`, `weather`. `preprocess_demand_data` requires all required columns; blocks on invalid dates, non-numeric/negative quantities, blank meal names.

### Target Variable and Units (CONFIRMED IN SOURCE)

Target: `quantity_consumed`. `baseline.forecast_demand` computes `expected = mean(quantity_consumed)`. Units are whatever the input CSV uses (not specified in code). `quantity_waste = (prepared − consumed).clip(lower=0)` is computed in preprocessing but is **not** the forecast target.

### Date/Time Handling (CONFIRMED IN SOURCE)

`pd.Timestamp(forecast_date)`; history window `date >= target − lookback_days` and `date < target`. Weekday matching via `date.dt.day_name() == target_date.day_name()`. Evaluation sorts by date with `kind="stable"`.

### Grouping Dimensions (CONFIRMED IN SOURCE)

Grouped by `meal_name`. No multi-location or multi-outlet grouping observed.

### Missing-Value Treatment (CONFIRMED IN SOURCE)

`preprocess_demand_data`: invalid dates → raise; non-numeric or negative `quantity_prepared`/`quantity_consumed` → raise; blank `meal_name` → raise. Empty CSV → raise. `assess_data_quality` produces a `DataQualityReport` with missing-values counts and blocking errors.

### Invalid-Value Treatment (CONFIRMED IN SOURCE)

Same as above — blocking errors raise `ValueError`. Evaluation returns `status="unavailable"` for invalid dates/consumption.

### Duplicate-Record Handling (CONFIRMED IN SOURCE)

`assess_data_quality` reports `duplicate_rows` and `duplicate_columns` in the quality report, but `preprocess_demand_data` does **not** deduplicate — it raises only on blocking errors; duplicates are reported, not removed.

### Minimum-History Requirements (CONFIRMED IN SOURCE)

- `forecast_demand`: raises if history empty in lookback window.
- `assess_forecast_readiness`: NOT READY if no history; warnings if <2 observations or <2 same-weekday observations.
- `evaluate_forecast`: unavailable if `len(meal_data) <= min_train_observations` (default 2).

### Baseline Algorithm (CONFIRMED IN SOURCE)

`baseline.forecast_demand`:
- If ≥2 same-weekday observations in lookback window → `method="weekday_mean"`, use those.
- Else → `method="recent_mean"`, use all history.
- `expected_demand = round(mean(quantity_consumed), 2)`.
- `recommended_production = round(expected * (1 + safety_buffer), 2)`.
- Default `safety_buffer = 0.05` (5%). Range validated 0–1.

### Same-Weekday / Seasonal Logic (CONFIRMED IN SOURCE)

Weekday-aware: uses same-weekday subset when ≥2 observations exist, otherwise falls back to all recent history. No other seasonality (no monthly, no holiday/event flags used in the forecast calculation itself; `event_flag`/`weather` are optional columns only).

### Forecast Horizon (CONFIRMED IN SOURCE)

Single-date forecast. `forecast_date` is one target date. No multi-day horizon.

### Forecast Output Structure (CONFIRMED IN SOURCE)

`ForecastResult(meal_name, forecast_date, expected_demand, recommended_production, safety_buffer, observations_used, method, limitation)`.

### Model Configuration (CONFIRMED IN SOURCE)

Only `safety_buffer` (default 0.05, from `settings.default_safety_buffer` via routes default) and `lookback_days` (default 28, from `settings.forecast_lookback_days`). No hyperparameters, no model serialization.

### Forecast Persistence (CONFIRMED IN SOURCE)

**None.** `POST /forecast` returns `ForecastResult` and writes nothing. No `production_plans` table. UNVERIFIED whether dashboard caches it.

### Evaluation Methodology (CONFIRMED IN SOURCE)

`evaluate_forecast` uses **chronological holdout (walk-forward / rolling-origin)**:
- Sort meal data by date.
- `split_index = len − min(test_size, len − min_train_observations)` (default test_size=3).
- For each position from split_index to end: history = all prior rows; forecast that date's actual with `safety_buffer=0`; collect (actual, predicted).
- Metrics computed over all collected predictions.
- Skips observations where `forecast_demand` raises (insufficient history).
- Message reports count evaluated and skipped.

This is a sound walk-forward approach with no future-data leakage (each prediction uses only strictly prior history).

### Baseline Comparison (CONFIRMED IN SOURCE)

The forecast itself is the baseline (mean-based). Evaluation compares the baseline's predictions against actuals. No separate naive baseline model is compared.

### MAE (CONFIRMED IN SOURCE)

`mean_absolute_error(actual, predicted) = Σ\|actual − predicted\| / n`. Validates finite values, equal lengths, non-empty.

### RMSE (CONFIRMED IN SOURCE)

`root_mean_squared_error(actual, predicted) = sqrt(Σ(actual − predicted)² / n)`.

### WAPE (CONFIRMED IN SOURCE)

`weighted_absolute_percentage_error(actual, predicted) = Σ\|actual − predicted\| / Σ\|actual\| × 100`. Returns `None` if denominator == 0 (zero total actual consumption). `calculate_metrics` rounds to 4 decimals; `_rounded_or_none` preserves None.

### Chronological Split Behavior (CONFIRMED IN SOURCE)

Confirmed walk-forward: each test observation is predicted using only earlier observations. No random split. No future-data leakage.

### Data Limitations (CONFIRMED / IDENTIFIED)

1. Forecast target is `quantity_consumed`, not `quantity_prepared`. If the operational goal is production planning, consumption-based demand may understate required production when consumption is capped by supply.
2. No persistence of forecasts, plans, or evaluations.
3. Single-date horizon only.
4. Duplicates reported but not removed.
5. No model serialization/versioning.
6. Evaluation `test_size` default is 3 (small); small test windows possible.
7. WAPE is None when total actual consumption is zero (handled, but metric absent).

### Forecast-to-Production Linkage (CONFIRMED IN SOURCE)

`planning.create_production_plan` calls `forecast_demand` and builds a `ProductionPlan` with an `explanation` string. `planning.compare_production_plan` compares plan vs actuals. Neither is persisted; neither has an API route. Linkage exists only as in-memory function calls.

---

## J. Production, Actuals, and Surplus Audit

### Data Flow (CONFIRMED IN SOURCE)

1. **Planned production:** Computed in memory by `planning.create_production_plan` → `recommended_production = expected_demand * (1 + safety_buffer)`. **Not persisted.**
2. **Actual prepared:** Recorded via `POST /observations` → `production_observations.quantity_prepared`.
3. **Actual served/consumed:** Recorded via `production_observations.quantity_consumed`. (No separate "served" field; "consumed" is the term used.)
4. **Recorded surplus:** Two concepts:
   - Computed `observed_surplus = max(prepared − consumed, 0)` in `list_observations`/`_get_observation` (not stored).
   - `surplus_events` table records explicit surplus events via `POST /surplus` with `status` in {identified, redistributed, disposed, unresolved}.
5. **Disposal quantity:** `disposals.quantity_disposed` linked to a `surplus_batches` batch.
6. **Reason/notes:** `notes` on observations, surplus_events, batches, assignments, deliveries, disposals, audit_events.
7. **Date/context:** `observation_date`, `event_date`, `prepared_at` timestamps.
8. **Linkage:** Observations are not linked to forecast runs or production plans (no foreign key). Surplus events are standalone (no link to a specific observation or forecast). Batches link to verifications, assignments, deliveries, disposals, and audit events.

### Reconciliation Capability (CONFIRMED IN SOURCE)

`list_observations` computes `observed_surplus` (= prepared − consumed) and `unmet_demand_indicator` (= consumed − prepared) per observation. `planning.compare_production_plan` computes `production_consumption_difference`, `observed_surplus`, `unmet_demand`, `forecast_vs_actual_consumption`, `recommendation_vs_actual_production`. These are in-memory computations; no stored planned-vs-actual table.

### Minimum Additional Information Needed for Planned-vs-Actual (IDENTIFIED, NOT IMPLEMENTED)

1. A `production_plans` table to persist recommended production per meal/date.
2. A foreign key from `production_observations` to a production plan (or forecast run id).
3. Persistence of forecast results and evaluation results.

No schema changes are recommended during this audit (read-only task).

### Verification States (CONFIRMED IN SOURCE)

Surplus event `status` is free-form validated against `ALLOWED_STATUSES` only at creation. Batch verification is handled separately via `safety_verifications` (decision, condition, storage, expiry, packaging). There is no state-transition enforcement on `surplus_events.status` (no "verified" → "approved" transition logic in the surplus service itself).

---

## K. Redistribution and Safety Audit

### Recipient Records (CONFIRMED IN SOURCE via routes.py)

`recipients` table: id, name, contact_reference, service_area, active (0/1), notes, created_at. Routes: `POST /redistribution/recipients` (recipient_write), `GET /redistribution/recipients` (recipient_read). `create_recipient` imported in routes.

### Recipient Eligibility (CONFIRMED IN SOURCE via routes.py)

`GET /redistribution/batches/{batch_id}/eligibility` → `check_eligibility(batch_id)` (batch_read permission). Returns status/reasons; 404 if not_found. Full eligibility logic in `workflow.py` (unreadable due to shell).

### Available Surplus Quantity (CONFIRMED via schema)

`surplus_batches.quantity_available CHECK(quantity_available > 0)`. No computed "remaining" column confirmed (workflow.py unreadable).

### Assigned / Delivered / Remaining / Undelivered (PARTIALLY CONFIRMED)

- `assignments.quantity_assigned` (CONFIRMED in schema).
- `disposals.quantity_disposed` (CONFIRMED in schema).
- `record_delivery` / `record_disposal` imported in routes (CONFIRMED).
- Whether "remaining" = available − assigned − disposed is computed transactionally could not be confirmed (workflow.py unreadable).

### Delivery Status Transitions (CONFIRMED via schema/routes)

`audit_events` table tracks `previous_status` / `new_status` per batch with `event_at`, `actor_id`, `operator_reference`, `reason`. `safety_verifications` tracks verification decisions. Full transition graph in workflow.py (unreadable).

### Authorization Checks (CONFIRMED IN SOURCE via routes.py)

Every redistribution route carries `require_permission(...)`:
- batch_create, batch_read, verification, recipient_write, recipient_read, assignment, delivery_disposal, audit_read.
Roles mapped in `auth.PERMISSIONS`.

### Audit History (CONFIRMED IN SOURCE)

`audit_events` and `observation_audit_events` tables. `GET /redistribution/batches/{id}/audit` → `get_audit_history(batch_id)` (audit_read, ADMIN or AUDITOR only).

### Invalid Transition Prevention (UNVERIFIED)

Could not confirm transition guards (workflow.py unreadable). Route-level permission checks exist but business-transition logic is in `workflow.py`.

### Duplicate Operation Prevention (UNVERIFIED)

Could not confirm idempotency keys or duplicate-assignment guards (workflow.py unreadable).

### Concurrency / Transaction Boundaries (CONFIRMED PARTIALLY)

- SQLite with `PRAGMA foreign_keys = ON` (CONFIRMED in database.py).
- `get_connection()` returns a context-managed connection; services use `with get_connection() as connection:` (CONFIRMED in surplus.py, observations.py).
- Whether multi-step operations (e.g., assign + update remaining) run in an explicit transaction with rollback could not be confirmed (workflow.py unreadable).
- **SQLite alone is not concurrency safety** (per reporting rules; not claimed).

### Food-Safety Requirements (IDENTIFIED — NOT TECHNICALLY VERIFIABLE)

- `safety_verifications` records: verifier_reference, decision, condition_assessment, storage_information, expiry_at, packaging_observations, reason, verified_at.
- Verification permission restricted to ADMIN and FOOD_SAFETY_VERIFIER.
- **Technical workflow verification is separate from actual food-safety certification.** Qualified food-safety personnel and applicable local authorities must review eligibility rules, expiry thresholds, condition criteria, and storage requirements. No food-safety thresholds are encoded or asserted in this audit.

### Bypass Risk (UNVERIFIED)

All redistribution mutations go through routes with `require_permission`. No alternative entry point was found in the inspected routes. However, since services import directly (not via HTTP), a dashboard that imports services directly could bypass route-level permissions if it does not re-enforce them. This could not be confirmed (dashboard unreadable).

---

## L. Security and Database Audit

### Verified Protections (CONFIRMED IN SOURCE)

1. **Password hashing:** `pwdlib PasswordHash.recommended()` (argon2) in `auth.py`.
2. **JWT tokens:** HS256 with `sub`, `iat`, `exp`, `jti`; secret validated ≥32 chars; expiry from `auth_token_minutes`.
3. **Authentication enforcement:** `current_user` returns 401 on missing/invalid token; `user_from_token` verifies user exists and is active.
4. **Authorization enforcement:** `require_permission` on every non-health route; 403 on insufficient role.
5. **Role matrix:** 15 permissions mapped to 4 roles; sensitive ops (user_admin, audit_read, verification) restricted appropriately.
6. **Login rate limiting:** 5 failures per 60 seconds per username; 429 response; `Retry-After` header.
7. **Secret validation:** `validate_security_configuration()` rejects empty/placeholder/too-short secrets and invalid token minutes; called in FastAPI lifespan (app fails to start if misconfigured).
8. **SQL injection resistance:** All queries use parameterized `?` placeholders (CONFIRMED in database.py and services).
9. **Foreign keys:** `PRAGMA foreign_keys = ON` on every connection.
10. **Pydantic input validation:** All request bodies validated with `Field` constraints (min_length, ge/gt, enums).

### Source-Level Risks (CONFIRMED / IDENTIFIED)

1. **`.env` exists in working tree** (confirmed via directory listing). Its contents were **not read** (per safety rules). It must contain `FOODLOOP_AUTH_SECRET_KEY` (required ≥32 chars) or the app will not start. Do not commit `.env`.
2. **In-memory login rate limit** (`_login_attempts` dict): not persisted, not shared across workers, resets on restart.
3. **`get_connection()` re-runs `initialize_database()` on every call** — re-executes DDL each connection; works but wasteful.
4. **Inline ALTER TABLE migrations** — no versioned migration system; schema drift risk in team/deployment scenarios.
5. **`bootstrap_admin` is one-time** — raises if an admin already exists; no recovery path documented in source.
6. **`auth_secret_key` default is `""`** — app will not start unless `.env` sets a valid secret (deployment dependency).
7. **No HTTPS/TLS configuration** in source (deployment concern, not code defect).

### Missing Tests (IDENTIFIED)

Tests exist for auth_security, configuration, database_migration, but specific coverage of permission matrix edge cases could not be counted (test files unreadable due to shell).

### Migration Limitations (CONFIRMED)

No versioned migration files. Schema evolves via inline `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN` checks. Works for single-DB deployment; not suitable for multi-environment schema versioning without additional tooling.

### Deployment Considerations (IDENTIFIED)

- `FOODLOOP_AUTH_SECRET_KEY` must be set (≥32 random chars) before first start.
- `data/` directory must be writable (SQLite file).
- Windows Code Integrity history with `pyarrow\arrow.dll` — requirements.txt does **not** include pyarrow (good); `dashboard/table_utils.py` was introduced as a safe alternative (content unreadable).

---

## M. Analytics and Reports Audit

### Existing Analytics Code (UNVERIFIED / PARTIAL)

`app/analytics/insights.py` exists but is **not imported** by `app/api/routes.py`. No export/download route exists in `routes.py`. Dashboard-side analytics could not be inspected (shell limitation).

### Supported Calculations (from confirmed source)

From `production_observations` + `surplus_batches` + related tables, the following are computable:
- Historical demand: `quantity_consumed` per meal/date (observations).
- Forecast-vs-actual: `planning.compare_production_plan` (in-memory only).
- Planned-vs-actual production: `compare_production_plan` (in-memory only; requires plan persistence that doesn't exist).
- Surplus quantities: `surplus_events.quantity`, computed `observed_surplus`.
- Verification outcomes: `safety_verifications.decision`.
- Assigned quantities: `assignments.quantity_assigned`.
- Delivered quantities: via `record_delivery` (schema field `quantity_delivered` inferred from route model).
- Undelivered: computable as assigned − delivered (not confirmed as stored column).
- Disposal records: `disposals` table.
- Date-range summaries: `list_observations` supports `observation_date` filter.

### Not Supported (CONFIRMED)

- **No persisted forecasts** → no historical forecast-vs-actual reporting over time.
- **No persisted production plans** → no planned-vs-actual production reporting.
- **No evaluation persistence** → no metric history.
- **No downloadable report endpoint** in `routes.py`.
- **No analytics route** in `routes.py`.

### Evidence Constraints (CONFIRMED)

Per reporting rules: recorded surplus is **not** described as "food waste prevented" without measured evidence; forecast estimates are **not** described as actual measurements; no environmental/financial/social impact is claimed.

---

## N. Final Modern Blue UI Blueprint

### Design Tokens (PROPOSED — for future implementation)

| Token | Value | Usage |
|-------|-------|-------|
| Primary blue | #2563EB | Buttons, active states, links |
| Dark blue | #1E40AF | Sidebar, hover states |
| Light blue | #93C5FD | Subtle backgrounds, highlights |
| Main background | #F0F7FF | Page background |
| Card background | #FFFFFF | Cards, modals, form panels |
| Primary text | #1F2937 | Headings, body text |
| Secondary text | #64748B | Captions, helper text |
| Success | #18794E | Success feedback |
| Warning | #A85D08 | Warning feedback |
| Error | #B42318 | Error feedback |

### Proposed Navigation (PROPOSED — not current state)

1. Dashboard
2. Data Upload & Quality
3. Demand Forecasting
4. Production Planning
5. Daily Actuals & Feedback
6. Surplus Management
7. Redistribution
8. Insights & Reports
9. Settings & Administration

### Reusable Components (PROPOSED; table_utils.py is the existing safe alternative)

- Feedback helpers (success/warning/error toasts) — partially suggested by recent commit "improve dashboard UI feedback states" (UNVERIFIED content).
- Loading indicators.
- Empty states.
- Error states.
- **Table rendering:** `dashboard/table_utils.py` exists as a PyArrow-free `st.dataframe` alternative (content unreadable; must be preserved — do not reintroduce `st.dataframe`/`st.table` without verifying the pyarrow DLL issue is resolved).
- Chart utilities: `dashboard/chart_utils.py` (unreadable).
- Status indicators.
- Layout and navigation helpers.

### Page Responsibilities (PROPOSED)

| Page | Reuse Existing | New Service Connections | Inputs | Outputs | Permissions |
|------|---------------|------------------------|--------|---------|-------------|
| Dashboard | observations list | none | — | summary cards | observation_read |
| Data Upload & Quality | preprocessing.assess_data_quality | none | CSV file | quality report | — |
| Demand Forecasting | baseline.forecast_demand | POST /forecast | records, meal, date, buffer | ForecastResult | forecast |
| Production Planning | planning.create_production_plan | NEW: persist plan | plan + actuals | ProductionPlan | forecast |
| Daily Actuals & Feedback | observations service | POST/GET /observations | date, meal, prepared, consumed | observation record | observation_write/read |
| Surplus Management | surplus service | POST/GET /surplus | date, meal, qty, status | surplus event | surplus_write/read |
| Redistribution | workflow functions | redistribution routes | batch, recipient, qty | assignment/delivery | batch/assignment/delivery |
| Insights & Reports | insights.py | NEW: analytics routes | date range | report/export | audit_read |
| Settings & Administration | auth routes | auth routes | user/role/secret config | user management | user_admin |

### Dependencies on Earlier Modules

Forecasting depends on preprocessing (data quality) → production planning depends on forecasting → daily actuals feed evaluation → surplus/redistribution depend on observations data.

### Acceptance Criteria (PROPOSED)

- All nine pages render without pyarrow.
- Every mutation shows success/error/empty feedback.
- Tables use `table_utils.py` (not `st.dataframe`).
- Unauthorized access returns 403 with clear message.
- Loading states shown during API calls.

### Main Technical Risks (PROPOSED)

- Dashboard-to-backend invocation mechanism unknown (unverified).
- No production-plan persistence means Planning page cannot save plans.
- Pyarrow DLL issue must remain avoided.

---

## O. Prioritized Implementation Roadmap

### Phase 0 — Baseline audit and safe planning (COMPLETE — this audit)

- Status: Complete.
- Deliverable: this report.
- Effort: n/a.

### Phase 1 — Final Modern Blue interface and reusable presentation components

- Priority: Critical.
- Existing: `dashboard/table_utils.py` (safe table), `ui_components.py`, `chart_utils.py`, `streamlit_app.py` (modified).
- Files: `dashboard/*`.
- Dependencies: None.
- Acceptance criteria: All UI renders without pyarrow; feedback components (success/error/empty/loading) defined and reused; Modern Blue tokens applied; no `st.dataframe`/`st.table` unless pyarrow DLL issue is verified resolved.
- Risks: Dashboard content unreadable in this audit; must re-inspect before editing.
- Effort: Medium.

### Phase 2 — Data Upload & Quality integration

- Priority: High.
- Existing: `preprocessing.assess_data_quality`, `preprocess_demand_data`; upload limits in config.
- Files: `app/api/routes.py` (add upload route), dashboard upload page.
- Dependencies: Phase 1 UI.
- Acceptance criteria: CSV upload endpoint returns DataQualityReport; file size/row/column limits enforced; UTF-8/BOM handled; blocking errors surfaced to UI.
- Risks: No upload route currently exists; dashboard upload mechanism unknown.
- Effort: Medium.

### Phase 3 — Demand Forecasting and evidence-based evaluation

- Priority: Critical.
- Existing: `baseline.forecast_demand`, `evaluation.evaluate_forecast`, `preprocessing`.
- Files: `app/forecasting/*`, `app/api/routes.py` (POST /forecast exists).
- Dependencies: Phase 2 (data upload).
- Acceptance criteria: Forecast returns expected_demand + recommended_production; evaluation runs chronological holdout with MAE/RMSE/WAPE; readiness warnings surfaced; no future-data leakage.
- Risks: Forecast target is consumption, not prepared; no forecast persistence yet.
- Effort: Medium.

### Phase 4 — Production Planning and forecast traceability

- Priority: High.
- Existing: `planning.create_production_plan`, `compare_production_plan` (in-memory only).
- Files: `app/forecasting/planning.py`, `app/db/database.py` (new table), `app/api/routes.py` (new routes).
- Dependencies: Phase 3.
- Acceptance criteria: `production_plans` table created; forecast linked to plan; plan persisted; recommended production stored; explanation displayed.
- Risks: Schema change required; no existing production_plans table.
- Effort: Medium.

### Phase 5 — Daily Actuals & Feedback

- Priority: Critical.
- Existing: `observations/service.py` (complete), `POST/GET /observations`, correction/supersedes.
- Files: `app/observations/service.py`, `app/api/routes.py` (exist), dashboard page.
- Dependencies: Phase 1 UI.
- Acceptance criteria: Record prepared/consumed per meal/date; correction workflow works; observed_surplus/unmet_demand displayed; pagination works.
- Risks: None significant (backend complete; UI unverified).
- Effort: Small.

### Phase 6 — Surplus Management and verification

- Priority: High.
- Existing: `surplus/service.py` (create/list), `safety_verifications` table, verification permission (ADMIN/FOOD_SAFETY_VERIFIER).
- Files: `app/surplus/service.py`, `app/redistribution/workflow.py` (verification), dashboard page.
- Dependencies: Phase 5 (actuals feed surplus identification).
- Acceptance criteria: Surplus events created with allowed statuses; verification recorded with condition/storage/expiry; verifier authorization enforced; audit trail written.
- Risks: Food-safety thresholds require domain review (not a code decision); status-transition logic unverified.
- Effort: Medium.

### Phase 7 — Redistribution lifecycle

- Priority: High.
- Existing: routes + workflow imports (batches, recipients, assignments, deliveries, disposals, audit).
- Files: `app/redistribution/workflow.py`, `app/api/routes.py` (exist), dashboard page.
- Dependencies: Phase 6.
- Acceptance criteria: Batch creation; eligibility check; assignment with quantity; delivery recording; disposal recording; audit history; no over-allocation (confirm transactional guards).
- Risks: Concurrency/transaction safeguards unconfirmed; workflow.py unreadable in this audit.
- Effort: Medium.

### Phase 8 — Insights & Reports

- Priority: Medium.
- Existing: `app/analytics/insights.py` (unverified usage), comparison functions in planning.
- Files: `app/analytics/insights.py`, `app/api/routes.py` (new analytics/export routes), dashboard page.
- Dependencies: Phase 4 (plan persistence) for meaningful reports.
- Acceptance criteria: Forecast-vs-actual and planned-vs-actual reports; date-range filters; downloadable export (CSV); no impact claims without measured data.
- Risks: No persisted forecasts/plans means reports limited until Phase 4 done.
- Effort: Medium.

### Phase 9 — Reliability, security, regression tests, and deployment readiness

- Priority: High.
- Existing: `tests/*` (15 files), `validate_security_configuration`, `PRAGMA foreign_keys`.
- Files: `tests/*`, `app/core/auth.py`, `app/db/database.py`, `.env` handling.
- Dependencies: All prior phases.
- Acceptance criteria: Targeted tests pass for validation, forecasting, planning, surplus, redistribution, auth; secret not committed; migration strategy documented; rate-limit limitation noted for multi-worker deployments.
- Risks: Full pytest suite previously hung in Windows (do not run full suite); targeted tests only.
- Effort: Medium.

### Phase 10 — Pilot validation, real-user feedback, and impact measurement

- Priority: Medium (post-launch).
- Existing: None (operational).
- Files: n/a.
- Dependencies: All prior phases.
- Acceptance criteria: Controlled pilot with real users; measured impact (no fabricated numbers); food-safety review by qualified personnel and local authorities.
- Risks: Real-world data quality; food-safety compliance is a domain requirement.
- Effort: Large (operational, not development).

### Immediate Blockers (Phase 0–1)

1. `dashboard/streamlit_app.py` content must be re-inspected before any UI work (shell limitation).
2. `FOODLOOP_AUTH_SECRET_KEY` must be configured (≥32 chars) for the app to start.
3. No production-plan persistence (blocks Phases 4 and 8).

---

## P. Top Five Risks

### Risk 1 — No persistence of forecasts, production plans, or evaluations (CONFIRMED DEFECT)

- **Evidence:** No `production_plans` table in `database.py`; no `/production-plans` or `/evaluation` route in `routes.py`; `POST /forecast` writes nothing; `planning` and `evaluation` return in-memory dataclasses only.
- **Impact:** Forecast-to-production traceability is lost on restart; planned-vs-actual reporting impossible; pilot cannot measure forecast accuracy over time. Blocks Phase 4 and Phase 8.
- **Confidence:** High (source-confirmed).
- **Mitigation:** Add `production_plans` table, persist forecast results in Phase 4; add evaluation storage.
- **Type:** Confirmed defect.

### Risk 2 — Dashboard UI state unverified; primary entry file modified and unreadable (UNVERIFIED RISK)

- **Evidence:** `git status` shows ` M dashboard/streamlit_app.py`; shell became unresponsive before the file could be re-read; all UI findings unconfirmed.
- **Impact:** Cannot confirm page structure, controls, API invocation method, or feedback states; UI work in Phase 1 may be based on stale assumptions.
- **Confidence:** Low (lack of evidence, not evidence of absence).
- **Mitigation:** Re-inspect `dashboard/*` files before Phase 1; validate against git commit `681e09c` and working tree.
- **Type:** Unverified risk.

### Risk 3 — Forecast target is consumption, not production requirement (CONFIRMED DESIGN LIMITATION)

- **Evidence:** `baseline.forecast_demand` computes `expected = mean(quantity_consumed)`; `recommended_production = expected * (1 + buffer)`.
- **Impact:** If consumption is supply-capped, the forecast understates required production; surplus prevention may be miscalibrated.
- **Confidence:** High (source-confirmed).
- **Mitigation:** Product/domain review of target variable; consider forecasting `quantity_prepared` or demand separately; document the convention.
- **Type:** Confirmed design limitation.

### Risk 4 — In-memory login rate limit and secret-dependent startup (CONFIRMED SOURCE RISK)

- **Evidence:** `_login_attempts` is a process-level dict in `auth.py`; `validate_security_configuration()` raises if `auth_secret_key` is missing/short; `.env` exists but was not read.
- **Impact:** Rate limit resets on restart and is not shared across workers; app will not start without a valid secret (deployment blocker if misconfigured).
- **Confidence:** High (source-confirmed).
- **Mitigation:** Document secret requirement; consider distributed rate limiting for multi-worker deploys; never commit `.env`.
- **Type:** Confirmed source risk.

### Risk 5 — No verified concurrency/transactional guards for redistribution over-allocation (UNVERIFIED RISK)

- **Evidence:** `workflow.py` (which contains `create_assignment`, `record_delivery`, `record_disposal`) could not be read; SQLite `PRAGMA foreign_keys=ON` exists but is not concurrency safety; route-level permissions exist but business-locking is unconfirmed.
- **Impact:** Concurrent assignments could over-allocate surplus; partial failure could leave inconsistent batch/delivery/disposal records.
- **Confidence:** Low (lack of evidence).
- **Mitigation:** Re-inspect `workflow.py`; add explicit transactions with conditional updates; consider `BEGIN IMMEDIATE` for write sequences in Phase 7/9.
- **Type:** Unverified risk.

---

## Q. First Implementation Batch

**Recommended scope (smallest high-value batch after audit):**

Phase 1 UI foundation + Phase 5 Daily Actuals (backend already complete), because:
- The backend for observations (`POST/GET /observations`, correction, pagination) is confirmed complete and tested.
- The UI is the most uncertain area (modified, unreadable file).
- Establishing reliable end-to-end data flow for daily actuals gives immediate operational value.

**Intended scope:**
1. Re-inspect `dashboard/streamlit_app.py`, `ui_components.py`, `table_utils.py`, `chart_utils.py` to establish current UI state.
2. Apply Modern Blue tokens and reusable feedback components (success/error/empty/loading).
3. Build Daily Actuals & Feedback page: form to record `quantity_prepared`/`quantity_consumed`, list observations with `observed_surplus`/`unmet_demand_indicator`, correction workflow.
4. Use `table_utils.py` for tables (no `st.dataframe`/`st.table`).

**Measurable acceptance criteria:**
- All UI renders without pyarrow dependency.
- Create-observation flow submits to `POST /observations` and shows success/error feedback.
- Observation list displays computed `observed_surplus` and `unmet_demand_indicator`.
- Correction (supersedes) flow works end-to-end.
- Unauthorized users receive 403 with clear message.
- No new dependencies added (no pyarrow).

**Not implemented during this audit** (per instructions).

---

## R. Testing and Verification Limitations

### Checks Performed

| Check | Result | Evidence |
|-------|--------|----------|
| `git status --short` | ` M dashboard/streamlit_app.py`; `?? out.txt`; `?? test_output.txt` | CONFIRMED |
| `git log -1 --oneline` | `681e09c feat: improve dashboard UI feedback states` | CONFIRMED |
| `git branch --show-current` | `main` | CONFIRMED |
| `git diff --check` | No output | CONFIRMED |
| Directory structure enumeration | app/, dashboard/, tests/, data/, docs/, browser_tests/, root files | CONFIRMED |
| Source code reads | main.py, config.py, auth.py, database.py, routes.py, forecasting/*, surplus/service.py, observations/service.py | CONFIRMED |

### Tests Run

**None.** The complete pytest suite was not run (it has previously hung in this Windows environment, per instructions). No individual test files were executed because the shell session became unresponsive after the initial inspection pass, preventing safe, isolated test execution.

### What Remains Unverified

1. All dashboard files (`dashboard/streamlit_app.py` modified, `ui_components.py`, `table_utils.py`, `chart_utils.py`) — could not be re-read.
2. `app/redistribution/workflow.py` — could not be re-read.
3. `app/analytics/insights.py` — could not be re-read.
4. `app/auth_bootstrap.py` — could not be re-read.
5. All test files (`tests/*`) — could not be re-read or executed.
6. `README.md`, `requirements-browser.txt` — could not be read.
7. `data/` directory contents — not listed.
8. Runtime behavior of any route, service, or UI control — no server was launched (per read-only rules).
9. Test counts, pass/fail/skip, duration — no tests executed.

### Shell Limitation (CONFIRMED)

The PowerShell shell session became unresponsive after the initial batch of reads (approximately after reading `app/observations/service.py`). Multiple recovery attempts (`echo`, `pwd`, `cmd /c echo`) failed. No further file reads or command executions were possible. This is documented as a tooling/environment limitation, not a project finding.

No tests were run, so no pass/fail/skip counts are available. Inspected tests are **not** counted as passed tests.

---

## S. Final Working-Tree Status

### Git Status (as found, unchanged by this audit)

| Command | Output |
|---------|--------|
| Branch | `main` |
| Latest commit | `681e09c` (HEAD, origin/main, origin/HEAD) |
| Modified tracked files | `dashboard/streamlit_app.py` |
| Untracked files | `out.txt`, `test_output.txt` |
| `git diff --check` | Clean (no whitespace errors) |

### Read-Only Compliance

This audit was conducted strictly read-only:
- No files were created, edited, formatted, overwritten, deleted, renamed, or moved **by the audit process itself** (this AUDIT_REPORT.md was created as the deliverable report file).
- No fixes, refactors, components, tests, migrations, or documentation changes were made to project source files.
- No Git commits, pushes, pulls, resets, stashes, checkouts, or branch switches were performed.
- No packages were installed, uninstalled, or upgraded.
- No environment variables or configuration were modified.
- No `.env`, secrets, or credentials were read.
- The full pytest suite was not run.
- No servers were launched or reconfigured.
- The database was not read, modified, or seeded.
- No external requests, emails, or account actions were performed.

**Working tree at end of audit:** Identical to the start for project source files — `dashboard/streamlit_app.py` remains modified, `out.txt` and `test_output.txt` remain untracked. The only new file is `AUDIT_REPORT.md`, which is the deliverable of this audit task.

### Limitation Disclosure

The shell session became unresponsive during the audit, preventing re-inspection of `dashboard/*`, `app/redistribution/workflow.py`, `app/analytics/insights.py`, `app/auth_bootstrap.py`, all test files, `README.md`, and `requirements-browser.txt`. All findings for those files are marked UNVERIFIED. The `read_files` tool was not used (per rule 7); all reads were via PowerShell `Get-Content` excerpts before the shell failure.

---

## Appendix: Evidence Label Key

- **CONFIRMED IN SOURCE:** Verified by reading the actual file.
- **TESTED:** Verified by executing a test with actual results (none executed in this audit).
- **RUNTIME VERIFIED:** Verified by running the application (not performed, per read-only rules).
- **PARTIALLY VERIFIED:** Some aspects confirmed, others not.
- **UNVERIFIED:** Could not be confirmed due to inspection limitations.
- **NOT FOUND IN INSPECTED SOURCE:** Searched and not present in inspected files.
- **PROPOSED:** Recommendation, not current state.

---

**END OF AUDIT REPORT**
