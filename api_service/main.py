import time
from datetime import datetime

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from api_service.auth import (
    authenticate_user,
    create_access_token,
    create_user_account,
    get_current_username,
)
from api_service.rpc import RpcTimeoutError, RpcWorkerError, request_recommendations
from service_logging import configure_logging, get_logger


configure_logging("api-service")
logger = get_logger(__name__, "api-service")
app = FastAPI(title="DSAssignment API Service", version="0.1.0")
api_v1_router = APIRouter(prefix="/api/v1")


class HealthResponse(BaseModel):
    status: str
    service: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: datetime


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class RegisterResponse(BaseModel):
    user_id: int
    username: str


class RecommendationRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)


class RecommendationItem(BaseModel):
    show_id: str
    title: str
    content_type: str
    language: str
    score: float


class RecommendationResponse(BaseModel):
    username: str
    title: str
    recommendations: list[RecommendationItem]


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="api-service")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.exception(
            "http_request_failed method=%s path=%s duration_ms=%s",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    logger.info(
        "http_request_completed method=%s path=%s status_code=%s duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@api_v1_router.post("/auth/token", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    if not authenticate_user(form_data.username, form_data.password):
        logger.warning("login_failed username=%s", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, expires_at = create_access_token(form_data.username)
    logger.info("login_succeeded username=%s", form_data.username)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_at=expires_at,
    )


@api_v1_router.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest) -> RegisterResponse:
    try:
        user = create_user_account(request.username, request.password)
    except ValueError as exc:
        logger.warning("register_failed username=%s reason=duplicate_username", request.username)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    logger.info("register_succeeded username=%s", request.username)
    return RegisterResponse(
        user_id=int(user["user_id"]),
        username=str(user["username"]),
    )


@api_v1_router.post("/recommendations", response_model=RecommendationResponse)
def get_recommendations(
    request: RecommendationRequest,
    username: str = Depends(get_current_username),
) -> RecommendationResponse:
    logger.info("recommendations_request_received username=%s title=%s", request.username, request.title)
    if request.username != username:
        logger.warning(
            "recommendations_request_rejected username=%s authenticated_username=%s reason=username_mismatch",
            request.username,
            username,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user does not match request username",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        worker_items = request_recommendations(request.username, request.title)
    except RpcTimeoutError as exc:
        logger.warning("recommendations_request_timeout username=%s title=%s", request.username, request.title)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except RpcWorkerError as exc:
        logger.warning("recommendations_request_worker_error username=%s title=%s", request.username, request.title)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    recommendations = [RecommendationItem(**item) for item in worker_items]
    logger.info(
        "recommendations_request_completed username=%s title=%s result_count=%s",
        username,
        request.title,
        len(recommendations),
    )
    return RecommendationResponse(
        username=username,
        title=request.title,
        recommendations=recommendations,
    )


app.include_router(api_v1_router)
