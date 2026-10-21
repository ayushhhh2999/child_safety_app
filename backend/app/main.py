from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.dependencies import get_current_user
from app.core.config import settings
from app.database import engine
from app.models.user import User
from app.routers.auth import router as auth_router
from app.routers.connections import router as connections_router
from app.routers.tracking import router as tracking_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.validate_startup()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    yield


app = FastAPI(
    title="Mobile Tracker API",
    description="Authentication and consent-based device monitoring",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(connections_router)
app.include_router(tracking_router)


@app.get("/")
def root():
    return {"message": "Mobile Tracker API is running"}


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from error
    return {"status": "healthy", "database": "available"}


@app.get("/api/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
    }
