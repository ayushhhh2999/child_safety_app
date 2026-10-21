from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, ge=0, le=100_000)
    recorded_at: datetime | None = None


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    latitude: float
    longitude: float
    accuracy_meters: float | None
    recorded_at: datetime


class ActivityCreate(BaseModel):
    package_name: str = Field(min_length=3, max_length=255, pattern=r"^[A-Za-z0-9_.]+$")
    app_name: str = Field(min_length=1, max_length=120)
    event_type: Literal["opened", "closed"]
    recorded_at: datetime | None = None
    event_key: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    package_name: str
    app_name: str
    event_type: Literal["opened", "closed"]
    recorded_at: datetime


class RestrictedAppEntry(BaseModel):
    package_name: str = Field(min_length=3, max_length=255, pattern=r"^[A-Za-z0-9_.]+$")
    app_name: str = Field(min_length=1, max_length=120)


class RestrictedAppsUpdate(BaseModel):
    apps: list[RestrictedAppEntry] = Field(max_length=200)


class RestrictedAppResponse(RestrictedAppEntry):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class RestrictionAlertCreate(RestrictedAppEntry):
    recorded_at: datetime | None = None
    details: str | None = Field(default=None, max_length=500)


class RestrictionAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    package_name: str
    app_name: str
    recorded_at: datetime
    details: str | None
