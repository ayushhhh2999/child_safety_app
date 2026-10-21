from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.services.login_throttle import (
    clear_login_attempts,
    record_login_attempt,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def signup(data: SignupRequest, db: Session = Depends(get_db)):
    username = data.username.strip().lower()
    email = str(data.email).strip().lower()

    if not username.replace("_", "").isalnum():
        raise HTTPException(
            status_code=422,
            detail="Username can contain letters, numbers and underscores",
        )

    existing = db.scalar(
        select(User).where(
            or_(User.username == username, User.email == email)
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Username or email is already registered",
        )

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(data.password),
    )

    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered",
        ) from error
    db.refresh(user)

    return user


@router.post("/login", response_model=TokenResponse)
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    username = data.username.strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    throttle_identifier = f"{client_ip}\0{username}"
    allowed, retry_after = record_login_attempt(db, throttle_identifier)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.scalar(
        select(User).where(User.username == username)
    )

    if not user or not verify_password(
        data.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    clear_login_attempts(db, throttle_identifier)
    return TokenResponse(
        access_token=create_access_token(user.id)
    )
