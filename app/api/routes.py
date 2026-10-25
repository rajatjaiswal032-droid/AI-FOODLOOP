import io
from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.forecasting.baseline import ForecastResult, forecast_demand
from app.forecasting.preprocessing import preprocess_demand_data
from app.core.config import settings
from app.core.auth import (
    AuthenticatedUser,
    Role,
    authenticate,
    check_login_rate_limit,
    clear_login_failures,
    create_user,
    current_user,
    issue_token,
    list_users,
    record_login_failure,
    require_permission,
    set_user_active,
    set_user_role,
)
from app.surplus.service import create_surplus_event, list_surplus_events
from app.redistribution.workflow import (
    check_eligibility,
    create_assignment,
    create_batch,
    create_recipient,
    get_audit_history,
    get_batch,
    list_batches,
    list_recipients,
    record_delivery,
    record_disposal,
    record_verification,
)
from app.observations.service import (
    correct_observation,
    create_observation,
    get_observation,
    list_observations,
)

router = APIRouter()


class ForecastRequest(BaseModel):
    records: list[dict]
    meal_name: str
    forecast_date: date
    safety_buffer: float = Field(default=0.05, ge=0, le=1)
    lookback_days: int = Field(default=28, gt=0)


class SurplusRequest(BaseModel):
    event_date: date
    meal_name: str = Field(min_length=1)
    quantity: float = Field(ge=0)
    status: str
    recipient: str | None = None
    notes: str | None = None


class BatchRequest(BaseModel):
    source_name: str = Field(min_length=1)
    meal_name: str = Field(min_length=1)
    prepared_at: str
    quantity_available: float = Field(gt=0)
    unit: str = Field(min_length=1)
    notes: str | None = None


class VerificationRequest(BaseModel):
    verifier_reference: str = Field(min_length=1)
    decision: str
    condition_assessment: str | None = None
    storage_information: str | None = None
    expiry_at: str | None = None
    packaging_observations: str | None = None
    reason: str | None = None
    verified_at: str | None = None


class RecipientRequest(BaseModel):
    name: str = Field(min_length=1)
    contact_reference: str | None = None
    service_area: str | None = None
    active: bool = True
    notes: str | None = None


class AssignmentRequest(BaseModel):
    recipient_id: str = Field(min_length=1)
    quantity_assigned: float = Field(gt=0)
    operator_reference: str = Field(min_length=1)
    notes: str | None = None


class DeliveryRequest(BaseModel):
    quantity_delivered: float = Field(gt=0)
    operator_reference: str = Field(min_length=1)
    recipient_confirmation: str | None = None
    notes: str | None = None


class DisposalRequest(BaseModel):
    quantity_disposed: float = Field(gt=0)
    reason: str = Field(min_length=1)
    operator_reference: str = Field(min_length=1)
    notes: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    role: Role


class UserStatusRequest(BaseModel):
    active: bool


class UserRoleRequest(BaseModel):
    role: Role


class ObservationRequest(BaseModel):
    observation_date: date
    meal_name: str = Field(min_length=1)
    quantity_prepared: float = Field(ge=0)
    quantity_consumed: float = Field(ge=0)
    notes: str | None = None


class ObservationCorrectionRequest(ObservationRequest):
    correction_reason: str = Field(min_length=1)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/login")
def login(request: LoginRequest) -> dict:
    retry_after = check_login_rate_limit(request.username)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    user = authenticate(request.username, request.password)
    if user is None:
        record_login_failure(request.username)
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    clear_login_failures(request.username)
    try:
        token = issue_token(user)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail="Authentication is not configured.") from error
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.auth_token_minutes * 60,
        "user": {"id": user.id, "username": user.username, "role": user.role.value, "active": user.active},
    }


@router.get("/auth/me")
def get_current_user(user: AuthenticatedUser = Depends(current_user)) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role.value, "active": user.active}


@router.get("/auth/users")
def get_users(_: AuthenticatedUser = Depends(require_permission("user_admin"))) -> list[dict]:
    return list_users()


@router.post("/observations", status_code=201)
def add_observation(
    request: ObservationRequest,
    user: AuthenticatedUser = Depends(require_permission("observation_write")),
) -> dict:
    try:
        return create_observation(
            request.observation_date,
            request.meal_name,
            request.quantity_prepared,
            request.quantity_consumed,
            request.notes,
            user.id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/observations")
def get_observations(
    observation_date: date | None = None,
    meal_name: str | None = None,
    include_superseded: bool = False,
    limit: int = 100,
    offset: int = 0,
    user: AuthenticatedUser = Depends(require_permission("observation_read")),
) -> list[dict]:
    try:
        return list_observations(
            user.id,
            observation_date,
            meal_name,
            include_superseded,
            limit,
            offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/observations/{observation_id}")
def get_observation_by_id(
    observation_id: str,
    user: AuthenticatedUser = Depends(require_permission("observation_read")),
) -> dict:
    try:
        return get_observation(observation_id, user.id)
    except ValueError as error:
        status_code = 404 if str(error) == "Observation was not found." else 400
        raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.post("/observations/{observation_id}/correction", status_code=201)
def correct_saved_observation(
    observation_id: str,
    request: ObservationCorrectionRequest,
    user: AuthenticatedUser = Depends(require_permission("observation_write")),
) -> dict:
    try:
        return correct_observation(
            observation_id,
            request.observation_date,
            request.meal_name,
            request.quantity_prepared,
            request.quantity_consumed,
            request.correction_reason,
            request.notes,
            user.id,
        )
    except ValueError as error:
        status_code = 404 if str(error) == "Observation was not found." else 400
        raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.post("/auth/users", status_code=201)
def add_user(
    request: UserCreateRequest,
    user: AuthenticatedUser = Depends(require_permission("user_admin")),
) -> dict:
    try:
        return create_user(request.username, request.password, request.role, actor_id=user.id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.patch("/auth/users/{user_id}/status")
def update_user_status(
    user_id: str,
    request: UserStatusRequest,
    actor: AuthenticatedUser = Depends(require_permission("user_admin")),
) -> dict:
    try:
        return set_user_active(user_id, request.active, actor.id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/auth/users/{user_id}/role")
def update_user_role(
    user_id: str,
    request: UserRoleRequest,
    actor: AuthenticatedUser = Depends(require_permission("user_admin")),
) -> dict:
    try:
        return set_user_role(user_id, request.role, actor.id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/forecast", response_model=ForecastResult)
def forecast(
    request: ForecastRequest,
    _: AuthenticatedUser = Depends(require_permission("forecast")),
) -> ForecastResult:
    try:
        data = preprocess_demand_data(
            io.BytesIO(pd.DataFrame(request.records).to_csv(index=False).encode())
        )
        return forecast_demand(
            data,
            request.meal_name,
            request.forecast_date.isoformat(),
            request.safety_buffer,
            request.lookback_days,
        )
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/surplus", status_code=201)
def create_surplus(
    request: SurplusRequest,
    _: AuthenticatedUser = Depends(require_permission("surplus_write")),
) -> dict:
    try:
        return create_surplus_event(**request.model_dump(), actor_id=_.id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/surplus")
def get_surplus(_: AuthenticatedUser = Depends(require_permission("surplus_read"))) -> list[dict]:
    return list_surplus_events(actor_id=_.id)


@router.post("/redistribution/batches", status_code=201)
def create_redistribution_batch(
    request: BatchRequest,
    user: AuthenticatedUser = Depends(require_permission("batch_create")),
) -> dict:
    try:
        return create_batch(**request.model_dump(), actor_id=user.id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/redistribution/batches")
def get_redistribution_batches(_: AuthenticatedUser = Depends(require_permission("batch_read"))) -> list[dict]:
    return list_batches()


@router.get("/redistribution/batches/{batch_id}")
def get_redistribution_batch(
    batch_id: str,
    _: AuthenticatedUser = Depends(require_permission("batch_read")),
) -> dict:
    try:
        return get_batch(batch_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/redistribution/batches/{batch_id}/verification", status_code=201)
def verify_redistribution_batch(
    batch_id: str,
    request: VerificationRequest,
    user: AuthenticatedUser = Depends(require_permission("verification")),
) -> dict:
    try:
        return record_verification(
            batch_id,
            verifier_reference=user.username,
            actor_id=user.id,
            decision=request.decision,
            condition_assessment=request.condition_assessment,
            storage_information=request.storage_information,
            expiry_at=request.expiry_at,
            packaging_observations=request.packaging_observations,
            reason=request.reason,
            verified_at=request.verified_at,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/redistribution/batches/{batch_id}/eligibility")
def get_redistribution_eligibility(
    batch_id: str,
    _: AuthenticatedUser = Depends(require_permission("batch_read")),
) -> dict:
    result = check_eligibility(batch_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail=result["reasons"][0])
    return result


@router.post("/redistribution/recipients", status_code=201)
def create_redistribution_recipient(
    request: RecipientRequest,
    user: AuthenticatedUser = Depends(require_permission("recipient_write")),
) -> dict:
    try:
        return create_recipient(**request.model_dump(), actor_id=user.id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/redistribution/recipients")
def get_redistribution_recipients(
    _: AuthenticatedUser = Depends(require_permission("recipient_read")),
) -> list[dict]:
    return list_recipients()


@router.post("/redistribution/batches/{batch_id}/assignments", status_code=201)
def assign_redistribution_batch(
    batch_id: str,
    request: AssignmentRequest,
    user: AuthenticatedUser = Depends(require_permission("assignment")),
) -> dict:
    try:
        return create_assignment(
            batch_id,
            recipient_id=request.recipient_id,
            quantity_assigned=request.quantity_assigned,
            operator_reference=user.username,
            actor_id=user.id,
            notes=request.notes,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/redistribution/assignments/{assignment_id}/deliveries", status_code=201)
def deliver_redistribution_assignment(
    assignment_id: str,
    request: DeliveryRequest,
    user: AuthenticatedUser = Depends(require_permission("delivery_disposal")),
) -> dict:
    try:
        return record_delivery(
            assignment_id,
            quantity_delivered=request.quantity_delivered,
            operator_reference=user.username,
            actor_id=user.id,
            recipient_confirmation=request.recipient_confirmation,
            notes=request.notes,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/redistribution/batches/{batch_id}/disposals", status_code=201)
def dispose_redistribution_batch(
    batch_id: str,
    request: DisposalRequest,
    user: AuthenticatedUser = Depends(require_permission("delivery_disposal")),
) -> dict:
    try:
        return record_disposal(
            batch_id,
            quantity_disposed=request.quantity_disposed,
            reason=request.reason,
            operator_reference=user.username,
            actor_id=user.id,
            notes=request.notes,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/redistribution/batches/{batch_id}/audit")
def get_redistribution_audit(
    batch_id: str,
    _: AuthenticatedUser = Depends(require_permission("audit_read")),
) -> list[dict]:
    try:
        return get_audit_history(batch_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
