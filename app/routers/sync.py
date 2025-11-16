from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user, get_device_for_user
from ..services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid datetime") from exc


def _apply_task_payload(task: models.Task, payload: dict[str, Any]):
    if "title" in payload:
        task.title = payload["title"]
    if "description" in payload:
        task.description = payload["description"]
    if "priority" in payload:
        task.priority = payload["priority"]
    if "due_at" in payload:
        task.due_at = _coerce_datetime(payload["due_at"])
    if "completed" in payload:
        task.completed = bool(payload["completed"])
        task.completed_at = datetime.utcnow() if task.completed else None
    if "archived" in payload:
        task.archived = bool(payload["archived"])
    if payload.get("deleted_at"):
        task.deleted_at = _coerce_datetime(payload["deleted_at"])


def _compute_checksum(task: models.Task) -> str:
    import hashlib
    import json

    payload = json.dumps(
        {
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "completed": task.completed,
            "archived": task.archived,
            "deleted_at": task.deleted_at.isoformat() if task.deleted_at else None,
            "version": task.version,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _apply_change(
    *,
    change: schemas.SyncChangeIn,
    user: models.User,
    device: models.Device,
    db: Session,
    sync: SyncService,
) -> tuple[bool, str | None, int | None, int | None]:
    device_id = device.id
    payload = change.payload

    if change.operation == schemas.SyncOperation.create:
        task = models.Task(
            user_id=user.id,
            title=payload.get("title", "Nueva tarea"),
            description=payload.get("description"),
            priority=payload.get("priority", "medium"),
            due_at=_coerce_datetime(payload.get("due_at")) if payload.get("due_at") else None,
            completed=bool(payload.get("completed", False)),
            archived=bool(payload.get("archived", False)),
        )
        task.version = 1
        db.add(task)
        db.flush()
        task.checksum = _compute_checksum(task)
        change_row = sync.record_change(
            user_id=user.id,
            task_id=task.id,
            device_id=device_id,
            operation="create",
            payload=payload,
        )
        return True, None, change_row.id, task.id

    # operations below require task_id
    if not change.task_id:
        return False, "task_id required", None, None

    task = db.get(models.Task, change.task_id)
    if not task or task.user_id != user.id:
        return False, "Task not found", None, None

    if change.operation == schemas.SyncOperation.delete:
        task.deleted_at = datetime.utcnow()
        task.archived = True
    elif change.operation == schemas.SyncOperation.complete:
        task.completed = True
        task.completed_at = datetime.utcnow()
    elif change.operation == schemas.SyncOperation.reopen:
        task.completed = False
        task.completed_at = None
    else:  # update or restore
        _apply_task_payload(task, payload)
        if change.operation == schemas.SyncOperation.restore:
            task.deleted_at = None
            task.archived = False

    task.version += 1
    task.checksum = _compute_checksum(task)

    change_row = sync.record_change(
        user_id=user.id,
        task_id=task.id,
        device_id=device_id,
        operation=change.operation.value,
        payload=payload or {"task_id": task.id},
    )
    return True, None, change_row.id, task.id


@router.post("/push", response_model=schemas.SyncPushResponse)
def push_changes(
    payload: schemas.SyncPushRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = get_device_for_user(db, current_user.id, payload.device_uuid)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device unknown")
    sync = SyncService(db)
    results: list[schemas.SyncPushResult] = []

    for change in payload.changes:
        applied, error, change_id, task_id = _apply_change(
            change=change,
            user=current_user,
            device=device,
            db=db,
            sync=sync,
        )
        results.append(
            schemas.SyncPushResult(
                client_change_id=change.client_change_id,
                task_id=task_id or change.task_id,
                applied=applied,
                error=error,
                server_change_id=change_id,
            )
        )
        if applied and change_id:
            sync.update_cursor(device, change_id)

    db.commit()
    latest_id = sync.latest_change_id(current_user.id)
    return schemas.SyncPushResponse(results=results, latest_change_id=latest_id)


@router.post("/pull", response_model=schemas.SyncPullResponse)
def pull_changes(
    payload: schemas.SyncPullRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = get_device_for_user(db, current_user.id, payload.device_uuid)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device unknown")

    sync = SyncService(db)
    changes = sync.fetch_changes(current_user.id, payload.last_change_id, payload.limit)
    if changes:
        sync.update_cursor(device, changes[-1].id)

    db.commit()
    latest_id = sync.latest_change_id(current_user.id)
    response_changes = [
        schemas.SyncChangeOut(
            change_id=change.id,
            task_id=change.task_id,
            operation=schemas.SyncOperation(change.operation),
            payload=change.change_payload,
            created_at=change.created_at,
        )
        for change in changes
    ]
    return schemas.SyncPullResponse(changes=response_changes, latest_change_id=latest_id)
