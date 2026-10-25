# AI FOODLOOP Roadmap

## Master flowchart

```text
PROJECT AUDIT
    |
    v
CORE MVP
    |
    v
CSV UPLOAD AND VALIDATION
    |
    v
DATA PREPROCESSING
    |
    v
DEMAND FORECASTING
    |
    v
PRODUCTION RECOMMENDATIONS
    |
    v
SURPLUS AND WASTE ANALYTICS
    |
    v
DATA-DRIVEN AI INSIGHTS
    |
    v
SAFE REDISTRIBUTION
    |
    v
DATABASE AND API HARDENING
    |
    v
INTEGRATION AND REGRESSION TESTING
    |
    v
DOCUMENTATION
    |
    v
DEPLOYMENT
    |
    v
FINAL ACCEPTANCE TESTING
```

## Current position

The project is between **database/API hardening** and **integration/regression verification**. CSV validation, preprocessing, baseline forecasting, chronological holdout evaluation, production recommendations, historical insights, authentication, and an auditable surplus recovery workflow are implemented. Human verification is required before eligibility; jurisdiction-specific food-safety policy configuration remains future work.

## Feedback loop

```text
Actual consumption
    -> Forecast evaluation
    -> Model improvement
    -> Better demand predictions
```

## Next milestones

1. Complete authenticated browser workflow verification.
2. Configure jurisdiction- and organization-specific food-safety policies from approved sources.
3. Add dashboard filters and operational report views.
4. Add concurrency, correction, and cancellation workflows.

## Scope guardrails

- No external AI API is required for the current milestones.
- No forecast accuracy is reported without chronological evaluation.
- No surplus is automatically marked safe for redistribution.
- No real delivery or recipient outcome is claimed without recorded confirmation.
