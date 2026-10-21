from datetime import datetime, timedelta, timezone
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.connection import Connection
from app.models.tracking import (
    AppActivityEvent,
    LocationUpdate,
    RestrictedApp,
    RestrictionAlert,
)
from app.models.user import User
from app.routers.connections import sharing_is_allowed
from app.schemas.tracking import (
    ActivityCreate,
    ActivityResponse,
    LocationCreate,
    LocationResponse,
    RestrictedAppResponse,
    RestrictedAppsUpdate,
    RestrictionAlertCreate,
    RestrictionAlertResponse,
)

router = APIRouter(tags=["Tracking"])
_RETENTION_DAYS = 30


def _normalize_timestamp(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Timestamps must include a timezone",
        )
    return value.astimezone(timezone.utc)


def _ingestion_timestamp(value: datetime | None) -> datetime:
    recorded_at = _normalize_timestamp(value)
    now = datetime.now(timezone.utc)
    if recorded_at < now - timedelta(days=_RETENTION_DAYS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Records older than {_RETENTION_DAYS} days are not accepted",
        )
    if recorded_at > now + timedelta(minutes=5):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Record timestamp cannot be more than five minutes in the future",
        )
    return recorded_at


def _shared_owner(
    db: Session, connection_id: int, viewer_id: int, category: str
) -> int:
    connection = db.get(Connection, connection_id)
    if (
        connection is None
        or connection.status != "accepted"
        or viewer_id not in (connection.first_user_id, connection.second_user_id)
    ):
        raise HTTPException(status_code=404, detail="Connection not found")
    owner_id = (
        connection.second_user_id
        if connection.first_user_id == viewer_id
        else connection.first_user_id
    )
    if not sharing_is_allowed(db, connection_id, owner_id, category):
        raise HTTPException(status_code=403, detail="Sharing is not enabled")
    return owner_id


def _prune_old_records(db: Session, model: type, owner_id: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
    db.execute(
        delete(model).where(
            model.owner_id == owner_id,
            model.recorded_at < cutoff,
        ).execution_options(synchronize_session=False)
    )


@router.post(
    "/api/locations",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_location(
    data: LocationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LocationUpdate:
    record = LocationUpdate(
        owner_id=current_user.id,
        latitude=data.latitude,
        longitude=data.longitude,
        accuracy_meters=data.accuracy_meters,
        recorded_at=_ingestion_timestamp(data.recorded_at),
    )
    db.add(record)
    _prune_old_records(db, LocationUpdate, current_user.id)
    db.commit()
    db.refresh(record)
    return record


@router.get("/api/locations/me", response_model=list[LocationResponse])
def get_my_locations(
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LocationUpdate]:
    _prune_old_records(db, LocationUpdate, current_user.id)
    db.commit()
    statement = select(LocationUpdate).where(
        LocationUpdate.owner_id == current_user.id
    )
    if before is not None:
        statement = statement.where(
            LocationUpdate.recorded_at < _normalize_timestamp(before)
        )
    return list(
        db.scalars(
            statement.order_by(LocationUpdate.recorded_at.desc()).limit(limit)
        ).all()
    )


@router.get(
    "/api/connections/{connection_id}/locations",
    response_model=list[LocationResponse],
)
def get_shared_locations(
    connection_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LocationUpdate]:
    owner_id = _shared_owner(db, connection_id, current_user.id, "location")
    _prune_old_records(db, LocationUpdate, owner_id)
    db.commit()
    statement = select(LocationUpdate).where(LocationUpdate.owner_id == owner_id)
    if before is not None:
        statement = statement.where(
            LocationUpdate.recorded_at < _normalize_timestamp(before)
        )
    return list(
        db.scalars(
            statement.order_by(LocationUpdate.recorded_at.desc()).limit(limit)
        ).all()
    )


@router.post(
    "/api/activities",
    response_model=ActivityResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_activity(
    data: ActivityCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppActivityEvent:
    recorded_at = _ingestion_timestamp(data.recorded_at)
    event_key = data.event_key or sha256(
        "|".join(
            (
                data.package_name,
                data.event_type,
                recorded_at.isoformat(),
            )
        ).encode("utf-8")
    ).hexdigest()
    existing = db.scalar(
        select(AppActivityEvent).where(
            AppActivityEvent.owner_id == current_user.id,
            AppActivityEvent.event_key == event_key,
        )
    )
    if existing is not None:
        return existing
    record = AppActivityEvent(
        owner_id=current_user.id,
        package_name=data.package_name,
        app_name=data.app_name.strip(),
        event_type=data.event_type,
        recorded_at=recorded_at,
        event_key=event_key,
    )
    db.add(record)
    _prune_old_records(db, AppActivityEvent, current_user.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(AppActivityEvent).where(
                AppActivityEvent.owner_id == current_user.id,
                AppActivityEvent.event_key == event_key,
            )
        )
        if existing is None:
            raise
        return existing
    db.refresh(record)
    return record


@router.get("/api/activities/me", response_model=list[ActivityResponse])
def get_my_activities(
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AppActivityEvent]:
    _prune_old_records(db, AppActivityEvent, current_user.id)
    db.commit()
    statement = select(AppActivityEvent).where(
        AppActivityEvent.owner_id == current_user.id
    )
    if before is not None:
        statement = statement.where(
            AppActivityEvent.recorded_at < _normalize_timestamp(before)
        )
    return list(
        db.scalars(
            statement.order_by(AppActivityEvent.recorded_at.desc()).limit(limit)
        ).all()
    )


@router.get(
    "/api/connections/{connection_id}/activities",
    response_model=list[ActivityResponse],
)
def get_shared_activities(
    connection_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AppActivityEvent]:
    owner_id = _shared_owner(db, connection_id, current_user.id, "app_usage")
    _prune_old_records(db, AppActivityEvent, owner_id)
    db.commit()
    statement = select(AppActivityEvent).where(
        AppActivityEvent.owner_id == owner_id
    )
    if before is not None:
        statement = statement.where(
            AppActivityEvent.recorded_at < _normalize_timestamp(before)
        )
    return list(
        db.scalars(
            statement.order_by(AppActivityEvent.recorded_at.desc()).limit(limit)
        ).all()
    )


@router.get("/api/restrictions/me", response_model=list[RestrictedAppResponse])
def get_my_restricted_apps(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RestrictedApp]:
    return list(
        db.scalars(
            select(RestrictedApp)
            .where(RestrictedApp.owner_id == current_user.id)
            .order_by(RestrictedApp.app_name)
        ).all()
    )


@router.put("/api/restrictions/me", response_model=list[RestrictedAppResponse])
def update_my_restricted_apps(
    data: RestrictedAppsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RestrictedApp]:
    package_names = [app.package_name for app in data.apps]
    if len(package_names) != len(set(package_names)):
        raise HTTPException(
            status_code=422,
            detail="Each package can only be selected once",
        )
    db.execute(delete(RestrictedApp).where(RestrictedApp.owner_id == current_user.id))
    records = [
        RestrictedApp(
            owner_id=current_user.id,
            package_name=app.package_name,
            app_name=app.app_name.strip(),
        )
        for app in data.apps
    ]
    db.add_all(records)
    db.commit()
    for record in records:
        db.refresh(record)
    return records


@router.post(
    "/api/restrictions/alerts",
    response_model=RestrictionAlertResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_restriction_alert(
    data: RestrictionAlertCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RestrictionAlert:
    record = RestrictionAlert(
        owner_id=current_user.id,
        package_name=data.package_name,
        app_name=data.app_name.strip(),
        recorded_at=_ingestion_timestamp(data.recorded_at),
        details=data.details,
    )
    db.add(record)
    _prune_old_records(db, RestrictionAlert, current_user.id)
    db.commit()
    db.refresh(record)
    return record


@router.get(
    "/api/restrictions/alerts/me",
    response_model=list[RestrictionAlertResponse],
)
def get_my_restriction_alerts(
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RestrictionAlert]:
    _prune_old_records(db, RestrictionAlert, current_user.id)
    db.commit()
    statement = select(RestrictionAlert).where(
        RestrictionAlert.owner_id == current_user.id
    )
    if before is not None:
        statement = statement.where(
            RestrictionAlert.recorded_at < _normalize_timestamp(before)
        )
    return list(
        db.scalars(
            statement.order_by(RestrictionAlert.recorded_at.desc()).limit(limit)
        ).all()
    )


@router.get(
    "/api/connections/{connection_id}/restriction-alerts",
    response_model=list[RestrictionAlertResponse],
)
def get_shared_restriction_alerts(
    connection_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RestrictionAlert]:
    owner_id = _shared_owner(
        db, connection_id, current_user.id, "restriction_alerts"
    )
    _prune_old_records(db, RestrictionAlert, owner_id)
    db.commit()
    statement = select(RestrictionAlert).where(
        RestrictionAlert.owner_id == owner_id
    )
    if before is not None:
        statement = statement.where(
            RestrictionAlert.recorded_at < _normalize_timestamp(before)
        )
    return list(
        db.scalars(
            statement.order_by(RestrictionAlert.recorded_at.desc()).limit(limit)
        ).all()
    )
