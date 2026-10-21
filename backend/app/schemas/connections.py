from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConnectionRequestCreate(BaseModel):
    username: str = Field(min_length=3, max_length=30)


class ConnectionRequestResponse(BaseModel):
    id: int
    username: str
    direction: Literal["incoming", "outgoing"]
    created_at: datetime


class ConnectionResponse(BaseModel):
    id: int
    username: str
    status: Literal["accepted", "rejected"]
    created_at: datetime


class SharingPermissionUpdate(BaseModel):
    share_location: bool | None = None
    share_app_usage: bool | None = None
    share_restriction_alerts: bool | None = None
    paused: bool | None = None


class SharingPermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    share_location: bool
    share_app_usage: bool
    share_restriction_alerts: bool
    paused: bool
