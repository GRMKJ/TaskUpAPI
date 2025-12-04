from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user, get_device_for_user
from ..services.sync_service import SyncService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _compute_checksum(task: models.Task) -> str:
    payload = json.dumps(
        {
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "remind_at": task.remind_at.isoformat() if task.remind_at else None,
            "remind_at_local": task.remind_local_at.isoformat() if task.remind_local_at else None,
            "remind_timezone_offset_minutes": task.remind_timezone_offset_minutes,
            "completed": task.completed,
            "archived": task.archived,
            "version": task.version,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_device(db: Session, user_id: int, device_uuid: Optional[str]):
    if not device_uuid:
        return None
    device = get_device_for_user(db, user_id, device_uuid)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not registered")
    return device


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _local_to_utc(local_dt: datetime, offset_minutes: int) -> datetime:
    base = local_dt.replace(tzinfo=None)
    return base - timedelta(minutes=offset_minutes)


def _prepare_reminder_values(
    *,
    remind_at: datetime | None,
    remind_at_local: datetime | None,
    remind_timezone_offset_minutes: int | None,
) -> tuple[datetime | None, datetime | None, int | None]:
    utc_value = _normalize_datetime(remind_at)
    local_value = remind_at_local
    offset_value = remind_timezone_offset_minutes

    if local_value is not None:
        if local_value.tzinfo is not None:
            local_value = local_value.replace(tzinfo=None)
        if offset_value is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Timezone offset required when providing local reminder time",
            )
        utc_value = _local_to_utc(local_value, offset_value)
    elif utc_value is not None and offset_value is not None and local_value is None:
        local_value = (utc_value + timedelta(minutes=offset_value)).replace(tzinfo=None)

    return utc_value, local_value, offset_value


@router.get("", response_model=schemas.TaskListResponse)
def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    only_active: bool = Query(True),
    since_version: Optional[int] = Query(None, ge=0),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    base_query = db.query(models.Task).filter(models.Task.user_id == current_user.id)
    if only_active:
        base_query = base_query.filter(models.Task.archived.is_(False), models.Task.deleted_at.is_(None))
    if since_version is not None:
        base_query = base_query.filter(models.Task.version > since_version)

    total = base_query.count()
    items = base_query.order_by(models.Task.updated_at.desc()).offset(skip).limit(limit).all()
    return schemas.TaskListResponse(items=items, total=total)


@router.post("", response_model=schemas.TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: schemas.TaskCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    device_uuid: Optional[str] = Header(default=None, alias="x-device-uuid"),
):
    device = _resolve_device(db, current_user.id, device_uuid)
    task = models.Task(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority.value,
        due_at=_normalize_datetime(payload.due_at),
        remind_at=None,
        remind_local_at=None,
        remind_timezone_offset_minutes=None,
    )
    (
        task.remind_at,
        task.remind_local_at,
        task.remind_timezone_offset_minutes,
    ) = _prepare_reminder_values(
        remind_at=payload.remind_at,
        remind_at_local=payload.remind_at_local,
        remind_timezone_offset_minutes=payload.remind_timezone_offset_minutes,
    )
    db.add(task)
    db.flush()
    task.checksum = _compute_checksum(task)

    sync = SyncService(db)
    change = sync.record_change(
        user_id=current_user.id,
        task_id=task.id,
        device_id=device.id if device else None,
        operation="create",
        payload={
            "task": {
                **payload.model_dump(),
                "remind_at": task.remind_at.isoformat() if task.remind_at else None,
                "remind_at_local": task.remind_local_at.isoformat() if task.remind_local_at else None,
                "remind_timezone_offset_minutes": task.remind_timezone_offset_minutes,
            }
        },
    )
    if device:
        sync.update_cursor(device, change.id)

    db.commit()
    db.refresh(task)
    return task


@router.put("/{task_id}", response_model=schemas.TaskOut)
def update_task(
    task_id: int,
    payload: schemas.TaskUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    device_uuid: Optional[str] = Header(default=None, alias="x-device-uuid"),
):
    task = (
        db.query(models.Task)
        .filter(models.Task.id == task_id, models.Task.user_id == current_user.id)
        .one_or_none()
    )
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if payload.title is not None:
        task.title = payload.title
    if payload.description is not None:
        task.description = payload.description
    if payload.priority is not None:
        task.priority = payload.priority.value
    if payload.due_at is not None:
        task.due_at = _normalize_datetime(payload.due_at)

    reminder_fields = {
        "remind_at",
        "remind_at_local",
        "remind_timezone_offset_minutes",
    }
    reminder_updated = False
    if payload.clear_reminder:
        task.remind_at = None
        task.remind_local_at = None
        task.remind_timezone_offset_minutes = None
        task.reminder_sent_at = None
        reminder_updated = True
    elif reminder_fields & payload.model_fields_set:
        remind_at_input = payload.remind_at if "remind_at" in payload.model_fields_set else task.remind_at
        remind_local_input = (
            payload.remind_at_local if "remind_at_local" in payload.model_fields_set else task.remind_local_at
        )
        remind_offset_input = (
            payload.remind_timezone_offset_minutes
            if "remind_timezone_offset_minutes" in payload.model_fields_set
            else task.remind_timezone_offset_minutes
        )
        (
            task.remind_at,
            task.remind_local_at,
            task.remind_timezone_offset_minutes,
        ) = _prepare_reminder_values(
            remind_at=remind_at_input,
            remind_at_local=remind_local_input,
            remind_timezone_offset_minutes=remind_offset_input,
        )
        task.reminder_sent_at = None
        reminder_updated = True
    if payload.completed is not None and payload.completed != task.completed:
        task.completed = payload.completed
        task.completed_at = datetime.utcnow() if task.completed else None
    if payload.archived is not None:
        task.archived = payload.archived

    task.version += 1
    task.checksum = _compute_checksum(task)

    device = _resolve_device(db, current_user.id, device_uuid)
    sync = SyncService(db)
    change_payload = payload.model_dump(exclude_unset=True)
    if reminder_updated:
        change_payload["remind_at"] = task.remind_at.isoformat() if task.remind_at else None
        change_payload["remind_at_local"] = (
            task.remind_local_at.isoformat() if task.remind_local_at else None
        )
        change_payload["remind_timezone_offset_minutes"] = task.remind_timezone_offset_minutes
    change = sync.record_change(
        user_id=current_user.id,
        task_id=task.id,
        device_id=device.id if device else None,
        operation="update",
        payload={"fields": change_payload},
    )
    if device:
        sync.update_cursor(device, change.id)

    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    device_uuid: Optional[str] = Header(default=None, alias="x-device-uuid"),
):
    task = (
        db.query(models.Task)
        .filter(models.Task.id == task_id, models.Task.user_id == current_user.id)
        .one_or_none()
    )
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    task.archived = True
    task.deleted_at = datetime.utcnow()
    task.version += 1
    task.checksum = _compute_checksum(task)

    device = _resolve_device(db, current_user.id, device_uuid)
    sync = SyncService(db)
    change = sync.record_change(
        user_id=current_user.id,
        task_id=task.id,
        device_id=device.id if device else None,
        operation="delete",
        payload={"deleted_at": task.deleted_at.isoformat()},
    )
    if device:
        sync.update_cursor(device, change.id)

    db.commit()
    return None
