from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models


class SyncService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_cursor(self, device: models.Device) -> models.DeviceSyncCursor:
        cursor = device.sync_cursor
        if cursor is None:
            cursor = models.DeviceSyncCursor(device_id=device.id, last_change_id=0)
            self.db.add(cursor)
            self.db.flush()
            self.db.refresh(cursor)
        return cursor

    def record_change(
        self,
        *,
        user_id: int,
        task_id: int,
        device_id: int | None,
        operation: str,
        payload: dict,
    ) -> models.TaskChangeLog:
        change = models.TaskChangeLog(
            user_id=user_id,
            task_id=task_id,
            device_id=device_id,
            operation=operation,
            change_payload=payload,
            created_at=datetime.utcnow(),
        )
        self.db.add(change)
        self.db.flush()
        return change

    def fetch_changes(self, user_id: int, last_change_id: int, limit: int = 100):
        stmt = (
            select(models.TaskChangeLog)
            .where(models.TaskChangeLog.user_id == user_id)
            .where(models.TaskChangeLog.id > last_change_id)
            .order_by(models.TaskChangeLog.id.asc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def latest_change_id(self, user_id: int) -> int:
        stmt = (
            select(models.TaskChangeLog.id)
            .where(models.TaskChangeLog.user_id == user_id)
            .order_by(models.TaskChangeLog.id.desc())
            .limit(1)
        )
        result = self.db.execute(stmt).scalar_one_or_none()
        return int(result or 0)

    def update_cursor(self, device: models.Device, change_id: int) -> None:
        cursor = self.ensure_cursor(device)
        cursor.last_change_id = change_id
        cursor.last_synced_at = datetime.utcnow()
        self.db.add(cursor)
