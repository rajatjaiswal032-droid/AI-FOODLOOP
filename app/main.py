from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import validate_security_configuration
from app.db.database import initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_security_configuration()
    initialize_database()
    yield


app = FastAPI(
    title="AI FOODLOOP API",
    description="Demand planning and surplus tracking for food-service operations.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router, prefix="/api")
