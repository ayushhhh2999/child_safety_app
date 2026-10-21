from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.connection import Connection, SharingPermission
from app.models.user import User
from app.schemas.connections import (
    ConnectionRequestCreate,
    ConnectionRequestResponse,
    ConnectionResponse,
    SharingPermissionResponse,
    SharingPermissionUpdate,
)

router = APIRouter(prefix="/api/connections", tags=["Connections"])

_SHARING_CATEGORIES = {
    "location": "share_location",
    "app_usage": "share_app_usage",
    "restriction_alerts": "share_restriction_alerts",
}


def _ordered_pair(user_id: int, other_user_id: int) -> tuple[int, int]:
    return min(user_id, other_user_id), max(user_id, other_user_id)


def _get_participant_connection(
    db: Session, connection_id: int, user_id: int
) -> Connection:
    connection = db.get(Connection, connection_id)
    if (
        connection is None
        or user_id not in (connection.first_user_id, connection.second_user_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )
    return connection


def _get_owner_permission(
    db: Session, connection_id: int, owner_id: int
) -> SharingPermission:
    permission = db.scalar(
        select(SharingPermission).where(
            SharingPermission.connection_id == connection_id,
            SharingPermission.owner_id == owner_id,
        )
    )
    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sharing permission is not available for this user",
        )
    return permission


@router.get("/search")
def search_users(
    username: str = Query(min_length=3, max_length=30),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int | str] | None:
    normalized_username = username.strip().lower()
    if not normalized_username:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username is required",
        )
    user = db.scalar(
        select(User).where(
            User.username == normalized_username,
            User.id != current_user.id,
        )
    )
    if user is None:
        return None
    return {"id": user.id, "username": user.username}


@router.post(
    "/request",
    response_model=ConnectionRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_connection_request(
    data: ConnectionRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectionRequestResponse:
    username = data.username.strip().lower()
    recipient = db.scalar(select(User).where(User.username == username))
    if recipient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if recipient.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot connect to yourself",
        )

    first_user_id, second_user_id = _ordered_pair(current_user.id, recipient.id)
    connection = db.scalar(
        select(Connection).where(
            Connection.first_user_id == first_user_id,
            Connection.second_user_id == second_user_id,
        )
    )

    if connection is not None and connection.status in ("pending", "accepted"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending request or accepted connection already exists",
        )

    now = datetime.now(timezone.utc)
    if connection is None:
        connection = Connection(
            first_user_id=first_user_id,
            second_user_id=second_user_id,
            requester_id=current_user.id,
            recipient_id=recipient.id,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        db.add(connection)
    else:
        connection.requester_id = current_user.id
        connection.recipient_id = recipient.id
        connection.status = "pending"
        connection.created_at = now
        connection.updated_at = now
        for permission in db.scalars(
            select(SharingPermission).where(
                SharingPermission.connection_id == connection.id
            )
        ):
            db.delete(permission)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending request or accepted connection already exists",
        ) from error
    db.refresh(connection)
    return ConnectionRequestResponse(
        id=connection.id,
        username=recipient.username,
        direction="outgoing",
        created_at=connection.created_at,
    )


@router.get("/requests", response_model=list[ConnectionRequestResponse])
def list_connection_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConnectionRequestResponse]:
    requests = db.scalars(
        select(Connection)
        .where(
            Connection.status == "pending",
            or_(
                Connection.requester_id == current_user.id,
                Connection.recipient_id == current_user.id,
            ),
        )
        .order_by(Connection.created_at.desc())
    ).all()

    results: list[ConnectionRequestResponse] = []
    for connection in requests:
        incoming = connection.recipient_id == current_user.id
        other_user_id = (
            connection.requester_id if incoming else connection.recipient_id
        )
        other_user = db.get(User, other_user_id)
        if other_user is not None:
            results.append(
                ConnectionRequestResponse(
                    id=connection.id,
                    username=other_user.username,
                    direction="incoming" if incoming else "outgoing",
                    created_at=connection.created_at,
                )
            )
    return results


def _resolve_request(
    db: Session, connection_id: int, recipient_id: int
) -> Connection:
    connection = _get_participant_connection(db, connection_id, recipient_id)
    if connection.recipient_id != recipient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection request not found",
        )
    if connection.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Connection request is no longer pending",
        )
    return connection


@router.post("/{connection_id}/accept", response_model=ConnectionResponse)
def accept_connection_request(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectionResponse:
    connection = _resolve_request(db, connection_id, current_user.id)
    connection.status = "accepted"
    connection.updated_at = datetime.now(timezone.utc)
    db.add_all(
        [
            SharingPermission(
                connection_id=connection.id,
                owner_id=connection.first_user_id,
            ),
            SharingPermission(
                connection_id=connection.id,
                owner_id=connection.second_user_id,
            ),
        ]
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Connection request has already been resolved",
        ) from error
    requester = db.get(User, connection.requester_id)
    return ConnectionResponse(
        id=connection.id,
        username=requester.username if requester else "",
        status="accepted",
        created_at=connection.created_at,
    )


@router.post("/{connection_id}/reject", response_model=ConnectionResponse)
def reject_connection_request(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectionResponse:
    connection = _resolve_request(db, connection_id, current_user.id)
    connection.status = "rejected"
    connection.updated_at = datetime.now(timezone.utc)
    db.commit()
    requester = db.get(User, connection.requester_id)
    return ConnectionResponse(
        id=connection.id,
        username=requester.username if requester else "",
        status="rejected",
        created_at=connection.created_at,
    )


@router.get("", response_model=list[ConnectionResponse])
def list_connections(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConnectionResponse]:
    connections = db.scalars(
        select(Connection)
        .where(
            Connection.status == "accepted",
            or_(
                Connection.first_user_id == current_user.id,
                Connection.second_user_id == current_user.id,
            ),
        )
        .order_by(Connection.created_at.desc())
    ).all()

    results: list[ConnectionResponse] = []
    for connection in connections:
        other_user_id = (
            connection.second_user_id
            if connection.first_user_id == current_user.id
            else connection.first_user_id
        )
        other_user = db.get(User, other_user_id)
        if other_user is not None:
            results.append(
                ConnectionResponse(
                    id=connection.id,
                    username=other_user.username,
                    status="accepted",
                    created_at=connection.created_at,
                )
            )
    return results


@router.get(
    "/{connection_id}/permissions",
    response_model=SharingPermissionResponse,
)
def get_sharing_permissions(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SharingPermissionResponse:
    connection = _get_participant_connection(db, connection_id, current_user.id)
    if connection.status != "accepted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sharing permissions require an accepted connection",
        )
    permission = _get_owner_permission(db, connection_id, current_user.id)
    return SharingPermissionResponse.model_validate(permission)


@router.patch(
    "/{connection_id}/permissions",
    response_model=SharingPermissionResponse,
)
def update_sharing_permissions(
    connection_id: int,
    data: SharingPermissionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SharingPermissionResponse:
    connection = _get_participant_connection(db, connection_id, current_user.id)
    if connection.status != "accepted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sharing permissions require an accepted connection",
        )
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one sharing setting must be provided",
        )
    permission = _get_owner_permission(db, connection_id, current_user.id)
    for field, value in updates.items():
        setattr(permission, field, value)
    permission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(permission)
    return SharingPermissionResponse.model_validate(permission)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    connection = _get_participant_connection(db, connection_id, current_user.id)
    if connection.status == "disconnected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Connection is already disconnected",
        )
    connection.status = "disconnected"
    connection.updated_at = datetime.now(timezone.utc)
    for permission in db.scalars(
        select(SharingPermission).where(
            SharingPermission.connection_id == connection_id
        )
    ):
        permission.share_location = False
        permission.share_app_usage = False
        permission.share_restriction_alerts = False
        permission.paused = True
        permission.updated_at = datetime.now(timezone.utc)
    db.commit()


def sharing_is_allowed(
    db: Session, connection_id: int, owner_id: int, category: str
) -> bool:
    permission_field = _SHARING_CATEGORIES.get(category)
    if permission_field is None:
        raise ValueError(f"Unsupported sharing category: {category}")
    connection = db.get(Connection, connection_id)
    if (
        connection is None
        or connection.status != "accepted"
        or owner_id not in (connection.first_user_id, connection.second_user_id)
    ):
        return False
    permission = db.scalar(
        select(SharingPermission).where(
            SharingPermission.connection_id == connection_id,
            SharingPermission.owner_id == owner_id,
        )
    )
    return bool(
        permission is not None
        and not permission.paused
        and getattr(permission, permission_field)
    )
