# AI FOODLOOP Project Status

Last updated: 2026-10-14

## Evidence-based progress

Current checkpoint: **34%** (rounded down to the nearest 2%).

This is an evidence-based estimate, not a claim of production readiness. The core local MVP is implemented and tested, while validation depth, analytics, redistribution controls, and production hardening remain incomplete.

## Milestone tracker

| ID | Milestone | Priority | Weight | Status | Implementation evidence | Test evidence | Remaining work | Blockers |
|---|---|---:|---:|---|---|---|---|---|
| M1 | Project audit and local setup | Critical | 8 | VERIFIED | Existing structure, `.venv`, manifest, and entry points inspected | Existing suite run in `.venv` | Keep status docs current | None |
| M2 | CSV upload and validation | Critical | 14 | TESTED | Strict required/optional columns, empty/malformed/duplicate/missing-value checks, and configured upload limits | Invalid CSV cases pass in the focused suite | Add richer UI validation summary | None |
| M3 | Data preprocessing | Critical | 10 | TESTED | Dates, numeric quantities, weekday, derived surplus | Existing preprocessing tests pass | Add context-column normalization | None |
| M4 | Baseline demand forecasting | Critical | 14 | VERIFIED | Recent mean plus weekday mean when evidence is sufficient | Chronological holdout with MAE/RMSE/WAPE, leakage, zero denominator, and insufficient-data tests pass | Add evaluation across multiple meal categories | None |
| M5 | Production recommendation | High | 10 | TESTED | Safety-buffer recommendation with validation | Covered by forecast tests | Add operational caps when requirements exist | None |
| M6 | Surplus and waste analytics | High | 12 | IMPLEMENTED | Dashboard totals, daily chart, meal summary, processed report download | Existing dashboard workflow verified | Add filters and trend tests | None |
| M7 | Data-driven insights | Medium | 8 | TESTED | Reusable meal, weekday, chronological trend, and cautious planning-signal service | Focused analytics tests cover totals, rates, empty/invalid data, ordering, and insufficient history | Add richer filters and domain review | None |
| M8 | Safe redistribution workflow | Medium | 10 | TESTED | Batch, human verification, eligibility, recipient, assignment, delivery, disposal, and audit services | Workflow and API coverage pass | Add policy-specific configuration | Policy requirements |
| M9 | Database and API hardening | High | 8 | TESTED | Normalized SQLite schema, parameterized transactions, typed workflow endpoints, role authorization | Authentication/security, API, and redistribution tests pass | Add concurrency hardening and rate limiting | No key rotation |
| M10 | Documentation and regression testing | Critical | 6 | TESTED | Workflow, security, and dashboard documentation maintained | 99 tests pass; compilation, API, and dashboard checks pass | Expand authenticated browser acceptance coverage | None |

## Verified facts

- The project uses Streamlit for the user-facing dashboard.
- FastAPI exposes health, forecast, and surplus endpoints.
- SQLite initialization is shared and lazy for direct service usage.
- The baseline does not claim accuracy or safety certification.
- Current automated suite result: 99 passed with 1 dependency-level warning from
  the Starlette/httpx test-client deprecation. The application-owned NumPy
  timedelta and Streamlit API deprecations were removed.
- Historical insights are calculated only from validated uploaded records.
- Meal surplus rate is `total_surplus / total_prepared * 100`; it is unavailable when prepared quantity is zero.
- Weekday extremes require at least two observations per weekday by default.
- Trend summaries are chronological descriptive aggregates and do not claim statistical significance.
- Surplus recovery uses separate normalized records for batches, verifications,
  recipients, assignments, deliveries, disposals, and audit events.
- New batches begin in `pending_verification`; eligibility requires an approved
  human decision, condition/storage evidence, and a future validated expiry/time-limit.
- Assigned, delivered, and disposed quantities are checked transactionally to prevent over-allocation.
- Passwords use Argon2 hashes through `pwdlib`; JWTs use configured HS256 signing
  with required expiry and identity claims.
- Protected routes use centralized role permissions. Direct redistribution writes
  require an active server-side actor ID with the same permission.
- Authentication test fixtures use temporary SQLite databases and test-only secrets.

## Current limitations

- Evaluation uses a chronological rolling-origin holdout for one selected meal at a time.
- Evaluation metrics are not live future-prediction accuracy and are unavailable when the holdout lacks enough history.
- Forecast output is not persisted.
- Redistribution records do not yet contain food-safety verification fields.
- No token revocation list or refresh-token flow exists; logout is client-side token disposal.
- The Streamlit dashboard authenticates through the local service layer rather than
  an independent browser/API session, and should not be treated as a production identity boundary.
- Dashboard filters are not yet implemented; upload-size limits are enforced by
  the CSV quality-validation layer.
- Insights do not establish causal relationships or guarantee future surplus.
- Small histories may produce an explicit insufficient-history signal instead of a weekday comparison.
- Dashboard upload verification rendered the insight section for a multi-row sample and showed
  the insufficient-weekday-history warning for a one-row upload.
- Legacy descriptive verifier/operator reference columns remain for compatibility;
  protected API actions derive audit actor identity from the authenticated account.
- Regulatory temperature, holding-time, expiry, and contamination rules are intentionally
  not hardcoded because no jurisdictional source or operating policy was supplied.
- Browser verification confirmed batch recording, blocked-before-verification behavior,
  and the human-verification form. Complete lifecycle behavior is additionally covered
  by automated service/API tests.
