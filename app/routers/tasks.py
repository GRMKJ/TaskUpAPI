from __future__ import annotations

import hashlib
import json
from datetime import datetime
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
        due_at=payload.due_at,
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
        payload={"task": payload.model_dump()},
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
        task.due_at = payload.due_at
    if payload.completed is not None and payload.completed != task.completed:
        task.completed = payload.completed
        task.completed_at = datetime.utcnow() if task.completed else None
    if payload.archived is not None:
        task.archived = payload.archived

    task.version += 1
    task.checksum = _compute_checksum(task)

    device = _resolve_device(db, current_user.id, device_uuid)
    sync = SyncService(db)
    change = sync.record_change(
        user_id=current_user.id,
        task_id=task.id,
        device_id=device.id if device else None,
        operation="update",
        payload={"fields": payload.model_dump(exclude_unset=True)},
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
