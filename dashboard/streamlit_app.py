import io
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from app.forecasting.evaluation import evaluate_forecast
from app.forecasting.planning import compare_production_plan, create_production_plan
from app.forecasting.preprocessing import (
    assess_data_quality,
    assess_forecast_readiness,
    preprocess_demand_data,
)
from app.analytics.insights import analyze_insights
from app.core.auth import Role, authenticate
from app.core.config import settings
from app.surplus.service import create_surplus_event, list_surplus_events
from app.redistribution.workflow import (
    check_eligibility,
    create_assignment,
    create_batch,
    create_recipient,
    get_audit_history,
    list_batches,
    list_assignments,
    list_recipients,
    record_delivery,
    record_disposal,
    record_verification,
)
from app.observations.service import (
    correct_observation,
    create_observation,
    list_observations,
)
from dashboard.chart_utils import finite_chart_frame, finite_chart_series
from dashboard.table_utils import render_table


st.set_page_config(
    page_title="AI FOODLOOP | Food intelligence",
    page_icon="🍲",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
    :root {
        --foodloop-forest: #12372a;
        --foodloop-emerald: #2f6f4e;
        --foodloop-mint: #dcefe2;
        --foodloop-ink: #20332a;
        --foodloop-muted: #64756b;
        --foodloop-line: #dce8df;
        --foodloop-surface: #f7fbf8;
    }
    .block-container {
        max-width: 1380px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }
    .hero {
        padding: 3.25rem 3.5rem;
        border-radius: 1.5rem;
        background:
            radial-gradient(circle at 90% 15%, rgba(143,188,143,.28), transparent 28%),
            linear-gradient(130deg, #102f24 0%, #1f533b 68%, #2f6f4e 100%);
        color: white;
        margin-bottom: 1.2rem;
        border: 1px solid rgba(220,239,226,.2);
        box-shadow: 0 18px 45px rgba(18,55,42,.16);
    }
    .hero .eyebrow {
        color: #cdebd6;
        font-size: .78rem;
        font-weight: 700;
        letter-spacing: .14em;
        text-transform: uppercase;
    }
    .hero h1 { margin: .65rem 0 .5rem; font-size: clamp(2.2rem, 5vw, 4.4rem); line-height: 1.02; }
    .hero .hero-copy { margin: 0; max-width: 730px; font-size: 1.13rem; line-height: 1.65; color: #edf8ef; }
    .hero .hero-principle {
        display: inline-block;
        margin-top: 1.25rem;
        padding: .65rem .9rem;
        border-left: 3px solid #9fd2ac;
        color: #dff2e3;
        font-weight: 650;
    }
    .section-kicker {
        color: var(--foodloop-emerald);
        font-size: .76rem;
        font-weight: 750;
        letter-spacing: .13em;
        text-transform: uppercase;
        margin: 1.7rem 0 .3rem;
    }
    .section-title {
        color: var(--foodloop-ink);
        font-size: 1.65rem;
        font-weight: 750;
        margin-bottom: .3rem;
    }
    .section-copy { color: var(--foodloop-muted); margin-bottom: 1rem; }
    .overview-card, .feature-card, .workflow-card {
        min-height: 142px;
        padding: 1.1rem 1.2rem;
        border: 1px solid var(--foodloop-line);
        border-radius: 1rem;
        background: var(--foodloop-surface);
        box-shadow: 0 5px 18px rgba(18,55,42,.05);
    }
    .overview-card .label, .feature-card .label {
        color: var(--foodloop-muted);
        font-size: .78rem;
        font-weight: 650;
        text-transform: uppercase;
        letter-spacing: .06em;
    }
    .overview-card .value {
        color: var(--foodloop-forest);
        font-size: 1.6rem;
        font-weight: 760;
        margin-top: .55rem;
    }
    .overview-card .hint, .feature-card p, .workflow-card p {
        color: var(--foodloop-muted);
        font-size: .9rem;
        line-height: 1.45;
        margin: .4rem 0 0;
    }
    .feature-card { min-height: 165px; background: white; }
    .feature-card .icon {
        color: var(--foodloop-emerald);
        font-size: 1.35rem;
        font-weight: 800;
        margin-bottom: .45rem;
    }
    .feature-card strong, .workflow-card strong { color: var(--foodloop-forest); font-size: 1rem; }
    .workflow-card { min-height: 170px; background: linear-gradient(145deg, #f7fbf8, #edf7ef); }
    .workflow-card .step {
        color: var(--foodloop-emerald);
        font-size: .73rem;
        font-weight: 800;
        letter-spacing: .1em;
    }
    .workflow-card p { margin-top: .7rem; }
    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid var(--foodloop-line);
        border-radius: .9rem;
        padding: .85rem 1rem;
        box-shadow: 0 4px 14px rgba(18,55,42,.04);
    }
    div[data-testid="stForm"] {
        border-color: var(--foodloop-line);
        border-radius: 1rem;
        background: #fbfdfb;
    }
    .status-note {
        padding: .75rem .9rem;
        border-radius: .7rem;
        background: #f1f8f2;
        color: var(--foodloop-ink);
        border: 1px solid var(--foodloop-line);
        font-size: .9rem;
    }
    .action-row {
        margin: .25rem 0 .75rem;
    }
    @media (max-width: 800px) {
        .hero { padding: 2rem 1.35rem; }
        .block-container { padding-left: 1rem; padding-right: 1rem; }
        .action-row { margin-top: 0; }
    }
    @media (prefers-color-scheme: dark) {
        .section-title { color: #dcefe2; }
        .section-copy { color: #b4c7bb; }
        .feature-card, .overview-card {
            background: #18251e;
            border-color: #345140;
        }
        .feature-card strong, .workflow-card strong { color: #e2f3e5; }
        .feature-card p, .overview-card .hint, .workflow-card p { color: #b4c7bb; }
        .workflow-card { background: linear-gradient(145deg, #18251e, #20392b); }
        .status-note { background: #1c3325; color: #dcefe2; border-color: #345140; }
    }
    .foodloop-table-wrap { overflow-x: auto; margin: .5rem 0 1rem; }
    .foodloop-table { width: 100%; border-collapse: collapse; font-size: .9rem; }
    .foodloop-table th, .foodloop-table td { border: 1px solid #dce8df; padding: .45rem .6rem; text-align: left; vertical-align: top; }
    .foodloop-table th { background: #edf6ef; color: #12372a; font-weight: 700; }
    .foodloop-table tbody tr:nth-child(even) { background: #f7fbf8; }
    .foodloop-table--empty { color: #64756b; font-style: italic; }
    </style>
    <section class="hero">
        <div class="eyebrow">Food intelligence · responsible recovery</div>
        <h1>Predict smarter.<br>Prevent surplus. Feed more.</h1>
        <p class="hero-copy">AI FOODLOOP helps food-service teams anticipate demand, reduce avoidable surplus, and manage human-verified food recovery through traceable workflows.</p>
        <div class="hero-principle">Prevent surplus first. Recover safely when surplus occurs.</div>
    </section>
    """,
    unsafe_allow_html=True,
)

if "authenticated_user" not in st.session_state:
    st.session_state.authenticated_user = None

if st.session_state.authenticated_user is None:
    st.markdown(
        """
        <div class="section-kicker">Secure workspace</div>
        <div class="section-title">Sign in to access operational workflows</div>
        <div class="section-copy">Forecasting views and redistribution actions are available only to an authenticated account.</div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("login_form"):
        login_username = st.text_input("Username")
        login_password = st.text_input("Password", type="password")
        login_submitted = st.form_submit_button("Sign in", width="stretch")
        if login_submitted:
            user = authenticate(login_username, login_password)
            if user is None:
                st.error("Invalid username or password.")
            else:
                st.session_state.authenticated_user = user
                st.rerun()
    st.stop()

authenticated_user = st.session_state.authenticated_user
user_bar = st.columns([3, 1])
with user_bar[0]:
    st.caption(f"Signed in as **{authenticated_user.username}** · `{authenticated_user.role.value}`")
with user_bar[1]:
    if st.button("Sign out", width="stretch"):
        st.session_state.pop("authenticated_user", None)
        st.rerun()
st.markdown('<div class="action-row"></div>', unsafe_allow_html=True)
hero_actions = st.columns([1.25, 1.15, 2.6])
with hero_actions[0]:
    st.link_button("Forecast demand", "#forecasting", width="stretch")
with hero_actions[1]:
    st.link_button("View insights", "#insights", width="stretch")

st.markdown(
    """
    <div class="section-kicker">Platform overview</div>
    <div class="section-title">One operating loop for better food decisions</div>
    <div class="section-copy">From validated historical data to accountable recovery actions—without overstating what the evidence can prove.</div>
    """,
    unsafe_allow_html=True,
)
nav_columns = st.columns(4)
for column, label, anchor in zip(
    nav_columns,
    ["Explore forecasting", "View food insights", "Manage surplus", "Open safety workflow"],
    ["forecasting", "insights", "surplus", "redistribution"],
):
    with column:
        st.markdown(f"[{label} →](#{anchor})")

st.markdown(
    """
    <div class="section-kicker">How it works</div>
    <div class="section-title">From demand signal to responsible action</div>
    """,
    unsafe_allow_html=True,
)
workflow = [
    ("01", "Data input", "Validated production, consumption, meal, and operational records."),
    ("02", "Demand intelligence", "Chronological baseline forecasting using available history."),
    ("03", "Production planning", "Transparent recommendations with an operator-controlled buffer."),
    ("04", "Surplus identification", "Compare recorded production and consumption patterns."),
    ("05", "Safety assessment", "Require human verification before redistribution eligibility."),
    ("06", "Responsible recovery", "Assign, deliver, dispose, and preserve traceability."),
    ("07", "Feedback loop", "Use observed patterns to inform future planning."),
]
workflow_columns = st.columns(4)
for column, (step, title, description) in zip(workflow_columns, workflow):
    with column:
        st.markdown(
            f"""
            <div class="workflow-card">
                <div class="step">{step}</div>
                <strong>{title}</strong>
                <p>{description}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
st.markdown("<div style='height:.7rem'></div>", unsafe_allow_html=True)
workflow_columns = st.columns(3)
for column, (step, title, description) in zip(workflow_columns, workflow[4:]):
    with column:
        st.markdown(
            f"""
            <div class="workflow-card">
                <div class="step">{step}</div>
                <strong>{title}</strong>
                <p>{description}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown(
    """
    <div class="section-kicker">Capabilities</div>
    <div class="section-title">Built for the full food-service decision cycle</div>
    """,
    unsafe_allow_html=True,
)
features = [
    ("01", "Demand forecasting", "Estimate upcoming demand and support informed production planning.", "forecasting"),
    ("02", "Forecast evaluation", "Review MAE, RMSE, and WAPE when historical holdout data is sufficient.", "evaluation"),
    ("03", "Food waste insights", "Explore meal-level, weekday, and chronological surplus observations.", "insights"),
    ("04", "Surplus management", "Record physically confirmed surplus events and current handling status.", "surplus"),
    ("05", "Safety verification", "Capture human food-safety decisions before redistribution eligibility.", "redistribution"),
    ("06", "Responsible recovery", "Manage recipients, assignments, delivery records, and disposal.", "redistribution"),
    ("07", "Audit history", "Review recorded workflow transitions and operational evidence.", "audit"),
]
feature_columns = st.columns(4)
for index, (icon, title, description, anchor) in enumerate(features):
    with feature_columns[index % 4]:
        st.markdown(
            f"""
            <div class="feature-card">
                <div class="icon">{icon}</div>
                <strong>{title}</strong>
                <p>{description}</p>
                <a href="#{anchor}">Open section →</a>
            </div>
            """,
            unsafe_allow_html=True,
        )
st.markdown("<div style='height:.8rem'></div>", unsafe_allow_html=True)
with st.columns(4)[0]:
    st.markdown(
        '<div class="feature-card"><div class="icon">08</div><strong>Evidence first</strong><p>No fabricated metrics, predictions, or safety approvals.</p></div>',
        unsafe_allow_html=True,
    )

st.markdown('<div id="data-input"></div>', unsafe_allow_html=True)
st.divider()
st.markdown(
    """
    <div class="section-kicker">Get started</div>
    <div class="section-title">Bring your operational data</div>
    <div class="section-copy">Upload an approved CSV to activate forecasting, evaluation, insights, and workflow views.</div>
    """,
    unsafe_allow_html=True,
)
st.caption(
    "The dashboard does not claim food-safety approval or model accuracy. Use approved operational data."
)

uploaded = st.file_uploader("Historical demand CSV upload karein", type="csv")
template_path = Path(__file__).resolve().parents[1] / "data" / "sample_input_template.csv"
st.download_button(
    "Download sample CSV template",
    data=template_path.read_bytes(),
    file_name="foodloop_demand_template.csv",
    mime="text/csv",
)

st.markdown('<div id="observations"></div>', unsafe_allow_html=True)
st.subheader("Record actual production & consumption")
st.caption(
    "These are operator-entered observations, stored separately from uploaded "
    "historical CSV data and forecast estimates."
)
with st.form("observation_form"):
    observation_date = st.date_input("Observation date", key="observation_date")
    observation_meal = st.text_input("Meal name", key="observation_meal")
    observation_prepared = st.number_input(
        "Actual quantity prepared", min_value=0.0, step=1.0, key="observation_prepared"
    )
    observation_consumed = st.number_input(
        "Actual quantity consumed", min_value=0.0, step=1.0, key="observation_consumed"
    )
    observation_notes = st.text_area("Notes (optional)", key="observation_notes")
    observation_submitted = st.form_submit_button("Save observation")
    if observation_submitted:
        try:
            created_observation = create_observation(
                observation_date,
                observation_meal,
                observation_prepared,
                observation_consumed,
                observation_notes,
                authenticated_user.id,
            )
            st.success(
                f"Observation saved successfully. ID: {created_observation['id']}"
            )
        except ValueError as error:
            st.error(str(error))

history_date = st.date_input("Filter observation history by date (optional)", value=None)
history_meal = st.text_input("Filter observation history by meal (optional)")
show_superseded = st.checkbox(
    "Show superseded observation records",
    help="Disabled by default so operational views show only the current record in each correction chain.",
)
try:
    saved_observations = list_observations(
        authenticated_user.id,
        history_date,
        history_meal or None,
        include_superseded=show_superseded,
    )
except ValueError as error:
    saved_observations = []
    st.error(str(error))
if saved_observations:
    history_frame = pd.DataFrame(saved_observations)
    render_table(
        history_frame[
            [
                "id",
                "observation_date",
                "meal_name",
                "quantity_prepared",
                "quantity_consumed",
                "observed_surplus",
                "unmet_demand_indicator",
                "is_current",
                "supersedes_id",
                "correction_reason",
                "created_at",
            ]
        ]
    )
else:
    st.info("No saved observations match the selected filters.")

if authenticated_user.role in {Role.ADMIN, Role.KITCHEN_OPERATOR} and saved_observations:
    st.subheader("Correct a saved observation")
    st.caption(
        "Corrections append a new record and preserve the original values and audit history."
    )
    correction_options = {
        f"{record['observation_date']} · {record['meal_name']} · {record['id']}": record
        for record in saved_observations
        if record["is_current"]
    }
    if correction_options:
        selected_label = st.selectbox(
            "Current observation to correct",
            options=list(correction_options),
        )
        selected_record = correction_options[selected_label]
        with st.form("observation_correction_form"):
            correction_date = st.date_input(
                "Corrected observation date",
                value=pd.Timestamp(selected_record["observation_date"]).date(),
            )
            correction_meal = st.text_input(
                "Corrected meal name",
                value=selected_record["meal_name"],
            )
            correction_prepared = st.number_input(
                "Corrected quantity prepared",
                min_value=0.0,
                value=float(selected_record["quantity_prepared"]),
                step=1.0,
            )
            correction_consumed = st.number_input(
                "Corrected quantity consumed",
                min_value=0.0,
                value=float(selected_record["quantity_consumed"]),
                step=1.0,
            )
            correction_reason = st.text_area("Correction reason")
            correction_notes = st.text_area(
                "Corrected notes (optional)",
                value=selected_record["notes"] or "",
            )
            correction_submitted = st.form_submit_button("Save correction")
            if correction_submitted:
                try:
                    corrected = correct_observation(
                        selected_record["id"],
                        correction_date,
                        correction_meal,
                        correction_prepared,
                        correction_consumed,
                        correction_reason,
                        correction_notes,
                        authenticated_user.id,
                    )
                    st.success(
                        f"Correction saved successfully. New observation ID: {corrected['id']}"
                    )
                except ValueError as error:
                    st.error(str(error))

if uploaded is None:
    st.markdown(
        '<div class="status-note">No historical data available yet. Upload a valid dataset to begin forecasting and insights.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

uploaded_bytes = uploaded.getvalue()
quality = assess_data_quality(uploaded_bytes)
st.markdown("### Data-quality summary")
quality_columns = st.columns(4)
quality_columns[0].metric("Rows", f"{quality.total_rows:,}")
quality_columns[1].metric("Columns", f"{quality.total_columns:,}")
quality_columns[2].metric("Valid rows", f"{quality.valid_rows:,}")
quality_columns[3].metric("Invalid rows", f"{quality.invalid_rows:,}")

preview_frame = None
try:
    preview_frame = pd.read_csv(
        io.BytesIO(uploaded_bytes),
        encoding="utf-8-sig",
        nrows=settings.upload_preview_rows,
    )
except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError):
    pass
if preview_frame is not None:
    st.caption(
        f"Previewing up to {settings.upload_preview_rows:,} rows without changing the uploaded file."
    )
    render_table(preview_frame)

if quality.missing_values:
    st.write("Missing values:", quality.missing_values)
if quality.earliest_date and quality.latest_date:
    st.caption(
        f"Valid date range: {quality.earliest_date} to {quality.latest_date} · "
        f"{quality.distinct_meals or 0:,} distinct meal(s)"
    )
if quality.prepared_total is not None and quality.consumed_total is not None:
    st.caption(
        f"Prepared: {quality.prepared_total:,.2f} · "
        f"Consumed: {quality.consumed_total:,.2f} · "
        f"Observed surplus: {quality.observed_surplus or 0:,.2f}"
    )

if quality.forecast_readiness == "NOT READY":
    st.error("Forecast readiness: NOT READY")
else:
    st.success(f"Forecast readiness: {quality.forecast_readiness}")
for message in quality.blocking_errors:
    st.error(message)
for message in quality.warnings:
    st.warning(message)
if quality.blocking_errors:
    st.stop()

try:
    data = preprocess_demand_data(uploaded_bytes)
except ValueError as error:
    st.error(str(error))
    st.stop()

st.markdown('<div id="overview"></div>', unsafe_allow_html=True)
st.markdown(
    """
    <div class="section-kicker">Operational overview</div>
    <div class="section-title">Your current food intelligence snapshot</div>
    """,
    unsafe_allow_html=True,
)
overview_columns = st.columns(4)
overview_columns[0].metric("Historical records", f"{len(data):,}")
overview_columns[1].metric("Meals analyzed", f"{data['meal_name'].nunique():,}")
overview_columns[2].metric("Prepared quantity", f"{data['quantity_prepared'].sum():,.0f}")
overview_columns[3].metric("Observed surplus", f"{data['quantity_waste'].sum():,.0f}")

st.markdown('<div id="validated-data"></div>', unsafe_allow_html=True)
st.subheader("Validated data")
render_table(data)
metric_columns = st.columns(4)
metric_columns[0].metric("Records", len(data))
metric_columns[1].metric("Prepared", f"{data['quantity_prepared'].sum():,.0f}")
metric_columns[2].metric("Consumed", f"{data['quantity_consumed'].sum():,.0f}")
metric_columns[3].metric("Derived surplus", f"{data['quantity_waste'].sum():,.0f}")

st.markdown('<div id="forecasting"></div>', unsafe_allow_html=True)
st.markdown(
    """
    <div class="section-kicker">Intelligence</div>
    <div class="section-title">Demand forecasting and production planning</div>
    <div class="section-copy">Use historical consumption patterns to support a transparent next-step production decision.</div>
    """,
    unsafe_allow_html=True,
)
meals = sorted(data["meal_name"].unique().tolist())
meal = st.selectbox("Meal", meals)
forecast_date = st.date_input("Forecast date")
buffer_percent = st.slider("Safety buffer (%)", 0, 50, 5)
forecast_readiness = assess_forecast_readiness(
    data,
    meal,
    forecast_date.isoformat(),
    settings.forecast_lookback_days,
)
if forecast_readiness.status == "NOT READY":
    st.error("Selected forecast: NOT READY")
else:
    st.success(f"Selected forecast: {forecast_readiness.status}")
for message in forecast_readiness.messages:
    st.warning(message)

st.markdown('<div id="evaluation"></div>', unsafe_allow_html=True)
st.subheader("Historical holdout evaluation")
evaluation = evaluate_forecast(data, meal)
st.caption(
    "These metrics come from a chronological historical holdout. "
    "They are not live future-prediction accuracy."
)
if evaluation.status == "evaluated" and evaluation.metrics is not None:
    evaluation_columns = st.columns(4)
    evaluation_columns[0].metric(
        "Evaluation status", "Evaluated"
    )
    evaluation_columns[1].metric("MAE", evaluation.metrics.mae)
    evaluation_columns[2].metric("RMSE", evaluation.metrics.rmse)
    evaluation_columns[3].metric(
        "WAPE",
        "Unavailable"
        if evaluation.metrics.wape is None
        else f"{evaluation.metrics.wape:.2f}%",
    )
    st.caption(
        f"Period: {evaluation.evaluation_start} to {evaluation.evaluation_end} · "
        f"{evaluation.evaluated_observations} observation(s)"
    )
    st.info(
        "MAE is the average absolute error. RMSE penalizes larger errors more heavily. "
        "WAPE is total absolute error divided by total actual consumption."
    )
else:
    st.warning(evaluation.message)

if st.button(
    "Forecast nikalein",
    disabled=(
        authenticated_user.role not in {Role.ADMIN, Role.KITCHEN_OPERATOR, Role.AUDITOR}
        or forecast_readiness.status == "NOT READY"
    ),
):
    try:
        plan = create_production_plan(
            data,
            meal,
            forecast_date.isoformat(),
            safety_buffer=buffer_percent / 100,
            lookback_days=settings.forecast_lookback_days,
        )
        result = plan.forecast
        st.caption("Forecast and recommendation are estimates, not guarantees.")
        planning_columns = st.columns(4)
        planning_columns[0].metric("Forecast demand", result.expected_demand)
        planning_columns[1].metric(
            "Recommended production", result.recommended_production
        )
        planning_columns[2].metric("Safety buffer", f"{result.safety_buffer:.0%}")
        planning_columns[3].metric("Observations used", result.observations_used)
        st.caption(
            f"Method: {result.method.replace('_', ' ')} · "
            f"{plan.explanation}"
        )
        if result.limitation:
            st.info(result.limitation)
        selected_observations = list_observations(
            authenticated_user.id, forecast_date, meal
        )
        actual_production = actual_consumption = None
        if len(selected_observations) == 1:
            observed = selected_observations[0]
            actual_production = observed["quantity_prepared"]
            actual_consumption = observed["quantity_consumed"]
        elif len(selected_observations) > 1:
            st.warning(
                "Multiple saved observations match this meal and date; comparison "
                "is unavailable until one record is selected."
            )
        comparison = compare_production_plan(
            plan,
            actual_production=actual_production,
            actual_consumption=actual_consumption,
        )
        st.subheader("Plan versus selected-date observations")
        st.caption(
            "Observed values come only from an exact uploaded record for the selected "
            "meal and date; they are not inferred from the forecast."
        )
        comparison_columns = st.columns(4)
        comparison_columns[0].metric(
            "Actual production",
            "Unavailable"
            if comparison.actual_production is None
            else comparison.actual_production,
        )
        comparison_columns[1].metric(
            "Actual consumption",
            "Unavailable"
            if comparison.actual_consumption is None
            else comparison.actual_consumption,
        )
        comparison_columns[2].metric(
            "Observed surplus",
            "Unavailable"
            if comparison.observed_surplus is None
            else comparison.observed_surplus,
        )
        comparison_columns[3].metric(
            "Unmet demand",
            "Unavailable"
            if comparison.unmet_demand is None
            else comparison.unmet_demand,
        )
        for message in comparison.warnings:
            st.warning(message)
    except ValueError as error:
        st.error(str(error))

st.markdown('<div id="surplus"></div>', unsafe_allow_html=True)
st.markdown(
    """
    <div class="section-kicker">Operations</div>
    <div class="section-title">Surplus management</div>
    <div class="section-copy">Record physically confirmed surplus separately from forecasts and preserve its handling status.</div>
    """,
    unsafe_allow_html=True,
)
with st.form("surplus_form"):
    event_date = st.date_input("Surplus date")
    surplus_quantity = st.number_input("Surplus quantity", min_value=0.0, step=1.0)
    status = st.selectbox("Status", ["identified", "redistributed", "disposed", "unresolved"])
    recipient = st.text_input("Authorized recipient (optional)")
    notes = st.text_area("Notes")
    submitted = st.form_submit_button("Surplus record karein")
    if submitted and authenticated_user.role in {Role.ADMIN, Role.KITCHEN_OPERATOR}:
        try:
            create_surplus_event(
                event_date,
                meal,
                surplus_quantity,
                status,
                recipient or None,
                notes or None,
                actor_id=authenticated_user.id,
            )
            st.success("Surplus event record ho gaya.")
        except ValueError as error:
            st.error(str(error))

events = list_surplus_events(actor_id=authenticated_user.id)
if events:
    render_table(events)

st.markdown('<div id="redistribution"></div>', unsafe_allow_html=True)
st.markdown(
    """
    <div class="section-kicker">Safety & recovery</div>
    <div class="section-title">Safe food redistribution and traceability</div>
    <div class="section-copy">Human verification is required before a batch can become eligible. The system never declares food safe automatically.</div>
    """,
    unsafe_allow_html=True,
)
st.caption(
    "This workflow records physically available surplus separately from forecasts. "
    "It never declares food safe automatically; an authorized human must verify it."
)
with st.form("redistribution_batch_form"):
    batch_source = st.text_input("Source kitchen or institution")
    batch_quantity = st.number_input("Recorded available quantity", min_value=0.0, step=1.0)
    batch_unit = st.text_input("Unit of measurement", value="portions")
    batch_notes = st.text_area("Batch notes")
    create_batch_button = st.form_submit_button(
        "Record surplus batch",
        disabled=authenticated_user.role not in {Role.ADMIN, Role.KITCHEN_OPERATOR},
    )
    if create_batch_button:
        try:
            created_batch = create_batch(
                batch_source,
                meal,
                datetime.now(timezone.utc).isoformat(),
                batch_quantity,
                batch_unit,
                batch_notes or None,
                actor_id=authenticated_user.id,
            )
            st.success(f"Batch recorded: {created_batch['id']}")
        except ValueError as error:
            st.error(str(error))

batches = list_batches()
if batches:
    batch_ids = [batch["id"] for batch in batches]
    selected_batch_id = st.selectbox("Batch", batch_ids, key="workflow_batch")
    selected_batch = next(batch for batch in batches if batch["id"] == selected_batch_id)
    eligibility = check_eligibility(selected_batch_id)
    render_table(pd.DataFrame([selected_batch]))
    if eligibility["eligible"]:
        st.success("Eligibility: eligible for redistribution.")
    else:
        st.warning("Eligibility blocked: " + " ".join(eligibility["reasons"]))

    with st.form("safety_verification_form"):
        verifier = st.text_input("Human verifier reference")
        decision = st.selectbox(
            "Human safety decision",
            ["pending", "approved", "requires_review", "rejected"],
        )
        condition = st.text_area("Food condition assessment")
        storage = st.text_area("Preparation/storage information")
        expiry = st.text_input("Validated expiry/time-limit (ISO-8601)")
        verification_reason = st.text_area("Verification reason or notes")
        verify_button = st.form_submit_button(
            "Record human verification",
            disabled=authenticated_user.role not in {Role.ADMIN, Role.FOOD_SAFETY_VERIFIER},
        )
        if verify_button:
            try:
                record_verification(
                    selected_batch_id,
                    authenticated_user.username,
                    decision,
                    condition or None,
                    storage or None,
                    expiry or None,
                    reason=verification_reason or None,
                    actor_id=authenticated_user.id,
                )
                st.success("Human verification record saved.")
            except ValueError as error:
                st.error(str(error))

    with st.form("recipient_form"):
        recipient_name = st.text_input("Recipient organization/name")
        recipient_area = st.text_input("Service area (optional)")
        recipient_button = st.form_submit_button(
            "Register recipient",
            disabled=authenticated_user.role not in {Role.ADMIN, Role.KITCHEN_OPERATOR},
        )
        if recipient_button:
            try:
                create_recipient(
                    recipient_name,
                    service_area=recipient_area or None,
                    actor_id=authenticated_user.id,
                )
                st.success("Recipient registered.")
            except ValueError as error:
                st.error(str(error))

    recipients = list_recipients()
    if recipients:
        recipient_ids = [recipient["id"] for recipient in recipients if recipient["active"]]
        if recipient_ids:
            with st.form("assignment_form"):
                recipient_id = st.selectbox("Active recipient", recipient_ids)
                assignment_quantity = st.number_input(
                    "Quantity to assign", min_value=0.0, step=1.0
                )
                operator = st.text_input("Assignment operator reference")
                assignment_button = st.form_submit_button(
                    "Create assignment",
                    disabled=authenticated_user.role not in {Role.ADMIN, Role.KITCHEN_OPERATOR},
                )
                if assignment_button:
                    try:
                        create_assignment(
                            selected_batch_id,
                            recipient_id,
                            assignment_quantity,
                            authenticated_user.username,
                            actor_id=authenticated_user.id,
                        )
                        st.success("Assignment recorded.")
                    except ValueError as error:
                        st.error(str(error))

    assignments = list_assignments(selected_batch_id)
    if assignments:
        st.markdown("**Assignments and delivery**")
        render_table(pd.DataFrame(assignments))
        assignment_ids = [assignment["id"] for assignment in assignments]
        with st.form("delivery_form"):
            delivery_assignment = st.selectbox("Assignment", assignment_ids)
            delivered_quantity = st.number_input(
                "Quantity delivered", min_value=0.0, step=1.0
            )
            delivery_operator = st.text_input("Delivery operator reference")
            confirmation = st.text_input("Recipient confirmation (optional)")
            delivery_button = st.form_submit_button(
                "Record delivery",
                disabled=authenticated_user.role not in {Role.ADMIN, Role.KITCHEN_OPERATOR},
            )
            if delivery_button:
                try:
                    record_delivery(
                        delivery_assignment,
                        delivered_quantity,
                        authenticated_user.username,
                        actor_id=authenticated_user.id,
                        recipient_confirmation=confirmation or None,
                    )
                    st.success("Delivery outcome recorded.")
                except ValueError as error:
                    st.error(str(error))

    with st.form("disposal_form"):
        disposal_quantity = st.number_input(
            "Quantity disposed", min_value=0.0, step=1.0
        )
        disposal_reason = st.text_input("Disposal reason")
        disposal_operator = st.text_input("Disposal operator reference")
        disposal_button = st.form_submit_button(
            "Record disposal",
            disabled=authenticated_user.role not in {Role.ADMIN, Role.KITCHEN_OPERATOR},
        )
        if disposal_button:
            try:
                record_disposal(
                    selected_batch_id,
                    disposal_quantity,
                    disposal_reason,
                    authenticated_user.username,
                    actor_id=authenticated_user.id,
                )
                st.success("Disposal outcome recorded.")
            except ValueError as error:
                st.error(str(error))

    st.markdown('<div id="audit"></div>', unsafe_allow_html=True)
    st.markdown("**Audit history**")
    render_table(pd.DataFrame(get_audit_history(selected_batch_id)))

st.markdown('<div id="insights"></div>', unsafe_allow_html=True)
st.markdown(
    """
    <div class="section-kicker">Evidence</div>
    <div class="section-title">Historical surplus analytics</div>
    <div class="section-copy">Descriptive observations from the validated dataset—not guaranteed future outcomes.</div>
    """,
    unsafe_allow_html=True,
)
chart_data = (
    data.assign(surplus=data["quantity_waste"])
    .groupby("date", as_index=True)[
        ["quantity_prepared", "quantity_consumed", "surplus"]
    ]
    .sum()
)
chart_data = finite_chart_frame(
    chart_data.reset_index(), ("quantity_prepared", "quantity_consumed", "surplus")
)
if chart_data.empty:
    st.info("Historical surplus chart is unavailable for the current data.")
else:
    st.line_chart(chart_data.set_index("date"))
meal_summary = (
    data.groupby("meal_name", as_index=False)[
        ["quantity_prepared", "quantity_consumed", "quantity_waste"]
    ]
    .sum()
)
render_table(meal_summary)
st.download_button(
    "Download processed demand report",
    data=data.to_csv(index=False).encode("utf-8"),
    file_name="foodloop_processed_demand.csv",
    mime="text/csv",
)
evaluation_report = evaluation.predictions.copy()
if evaluation.metrics is not None:
    evaluation_report["mae"] = evaluation.metrics.mae
    evaluation_report["rmse"] = evaluation.metrics.rmse
    evaluation_report["wape_percent"] = evaluation.metrics.wape
st.download_button(
    "Download evaluation report",
    data=evaluation_report.to_csv(index=False).encode("utf-8"),
    file_name="foodloop_forecast_evaluation.csv",
    mime="text/csv",
)

st.markdown('<div id="food-insights"></div>', unsafe_allow_html=True)
st.subheader("Historical Food Waste Insights")
insights = analyze_insights(data)
st.caption(
    "These are descriptive signals from historical observations. "
    "They are not guaranteed future outcomes or automatic production orders."
)
if insights.status == "available":
    st.markdown("**Meal-wise surplus summary**")
    render_table(insights.meal_summary)

    st.markdown("**Weekday surplus comparison**")
    if insights.weekday_summary.empty:
        st.info("Weekday insights are unavailable for the uploaded history.")
    else:
        if insights.highest_surplus_weekday is None:
            st.warning(
                "Weekday comparison is limited: each weekday needs at least "
                "two observations before an extreme is reported."
            )
        weekday_chart = finite_chart_series(
            insights.weekday_summary.set_index("weekday")["mean_surplus"]
        )
        if weekday_chart.empty:
            st.info("Weekday surplus chart is unavailable for the current data.")
        else:
            st.bar_chart(weekday_chart, width="stretch")
        render_table(insights.weekday_summary)

    st.markdown("**Chronological surplus trend**")
    trend_chart = finite_chart_series(
        insights.trend_summary.set_index("date")["total_surplus"]
    )
    if trend_chart.empty:
        st.info("Chronological surplus chart is unavailable for the current data.")
    else:
        st.line_chart(trend_chart, width="stretch")

    st.markdown("**Evidence-backed planning signals**")
    for signal in insights.signals:
        with st.container(border=True):
            st.markdown(f"**{signal.title}**")
            st.write(signal.explanation)
            st.caption(
                f"Evidence: {signal.evidence} · "
                f"Relevant observations: {signal.observations}"
            )
            st.info(f"Limitation: {signal.limitation}")

    insight_report = pd.concat(
        [
            insights.meal_summary.assign(analysis_type="meal"),
            insights.weekday_summary.assign(analysis_type="weekday"),
            insights.trend_summary.assign(analysis_type="trend"),
        ],
        ignore_index=True,
        sort=False,
    )
    st.download_button(
        "Download historical insights report",
        data=insight_report.to_csv(index=False).encode("utf-8"),
        file_name="foodloop_historical_insights.csv",
        mime="text/csv",
    )
else:
    st.warning(insights.message)
