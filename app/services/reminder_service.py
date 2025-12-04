from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from sqlalchemy.orm import selectinload

from .. import models
from ..config import Settings
from ..database import SessionLocal
from .notification_service import NotificationService

logger = logging.getLogger(__name__)


class ReminderDispatcher:
    def __init__(self, settings: Settings, notification_service: NotificationService) -> None:
        self._settings = settings
        self._notification_service = notification_service
        self._interval = max(15, settings.reminder_poll_interval_seconds)
        self._batch_size = settings.reminder_batch_size
        self._enabled = settings.enable_reminder_worker
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if not self._enabled:
            logger.info("Reminder dispatcher disabled via configuration")
            return
        if not self._notification_service.enabled:
            logger.warning("Reminder dispatcher enabled but FCM server key missing; skipping start")
            return
        if self._thread and self._thread.is_alive():
            return
        logger.info("Starting reminder dispatcher (interval=%ss)", self._interval)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="ReminderDispatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop_event.set()
        self._thread.join(timeout=5)
        self._thread = None
        logger.info("Reminder dispatcher stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            started_at = time.monotonic()
            try:
                self._process_due_reminders()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Reminder dispatcher tick failed: %s", exc)
            elapsed = time.monotonic() - started_at
            wait_time = max(1.0, self._interval - elapsed)
            self._stop_event.wait(wait_time)

    def _process_due_reminders(self) -> None:
        now = datetime.utcnow()
        with SessionLocal() as db:
            tasks = (
                db.query(models.Task)
                .options(selectinload(models.Task.user).selectinload(models.User.devices))
                .filter(models.Task.remind_at.is_not(None))
                .filter(models.Task.remind_at <= now)
                .filter(models.Task.reminder_sent_at.is_(None))
                .filter(models.Task.archived.is_(False))
                .filter(models.Task.deleted_at.is_(None))
                .filter(models.Task.completed.is_(False))
                .order_by(models.Task.remind_at.asc())
                .limit(self._batch_size)
                .all()
            )

            if not tasks:
                return

            logger.info("Processing %d due reminders", len(tasks))
            for task in tasks:
                user = task.user
                if not user:
                    continue
                tokens = NotificationService.unique_tokens(user.devices)
                dispatched = False
                try:
                    dispatched = self._notification_service.send_task_reminder(
                        tokens=tokens,
                        task=task,
                        user=user,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to dispatch reminder for task %s: %s", task.id, exc)

                if dispatched:
                    task.reminder_sent_at = datetime.utcnow()
                    logger.debug("Marked reminder as sent for task %s", task.id)

            db.commit()
