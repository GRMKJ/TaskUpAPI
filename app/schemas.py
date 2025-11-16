from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Platform(str, Enum):
    android = "android"
    ios = "ios"
    web = "web"
    desktop = "desktop"


class SyncOperation(str, Enum):
    create = "create"
    update = "update"
    complete = "complete"
    reopen = "reopen"
    delete = "delete"
    restore = "restore"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class GoogleOAuthRequest(BaseModel):
    id_token: str = Field(min_length=10)
    device_uuid: Optional[str] = Field(default=None, max_length=36)


class UserOut(BaseModel):
    id: int
    email: EmailStr
    display_name: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class DeviceRegisterRequest(BaseModel):
    device_uuid: str = Field(min_length=1, max_length=36)
    device_name: Optional[str]
    platform: Platform
    app_version: Optional[str]


class DeviceRegisterResponse(BaseModel):
    device_id: int
    last_change_id: int


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str]
    priority: Priority = Priority.medium
    due_at: Optional[datetime]


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str]
    description: Optional[str]
    priority: Optional[Priority]
    due_at: Optional[datetime]
    completed: Optional[bool]
    archived: Optional[bool]


class TaskOut(TaskBase):
    id: int
    completed: bool
    archived: bool
    version: int
    checksum: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SyncChangeIn(BaseModel):
    client_change_id: str = Field(min_length=1, max_length=64)
    operation: SyncOperation
    task_id: Optional[int]
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncChangeOut(BaseModel):
    change_id: int
    task_id: int
    operation: SyncOperation
    payload: dict[str, Any]
    created_at: datetime


class SyncPushRequest(BaseModel):
    device_uuid: str
    changes: list[SyncChangeIn]


class SyncPushResult(BaseModel):
    client_change_id: str
    task_id: Optional[int]
    applied: bool
    error: Optional[str]
    server_change_id: Optional[int]


class SyncPushResponse(BaseModel):
    results: list[SyncPushResult]
    latest_change_id: int


class SyncPullRequest(BaseModel):
    device_uuid: str
    last_change_id: int = 0
    limit: int = Field(default=100, le=500)


class SyncPullResponse(BaseModel):
    changes: list[SyncChangeOut]
    latest_change_id: int


class TaskListResponse(BaseModel):
    items: list[TaskOut]
    total: int
