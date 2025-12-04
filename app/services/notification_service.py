from __future__ import annotations

import logging
from typing import Iterable, Sequence

import requests

from .. import models

logger = logging.getLogger(__name__)


class NotificationService:
    """Wrapper around Firebase Cloud Messaging HTTP v1 (legacy) API."""

    FCM_ENDPOINT = "https://fcm.googleapis.com/fcm/send"

    def __init__(self, server_key: str | None) -> None:
        self._server_key = server_key

    @property
    def enabled(self) -> bool:
        return bool(self._server_key)

    def send_task_reminder(
        self,
        *,
        tokens: Sequence[str],
        task: models.Task,
        user: models.User,
    ) -> bool:
        if not tokens:
            logger.debug("Skipping reminder %s because there are no device tokens", task.id)
            return False
        if not self._server_key:
            logger.warning("FCM server key not configured; skipping reminder dispatch")
            return False

        payload = {
            "registration_ids": list(tokens),
            "priority": "high",
            "notification": {
                "title": f"{user.display_name} - TaskUp",
                "body": task.title,
                "sound": "default",
            },
            "data": {
                "task_id": task.id,
                "remind_at": task.remind_at.isoformat() if task.remind_at else None,
                "priority": task.priority,
            },
        }
        headers = {
            "Authorization": f"key {self._server_key}",
            "Content-Type": "application/json",
        }

        response = requests.post(self.FCM_ENDPOINT, json=payload, headers=headers, timeout=10)
        if 200 <= response.status_code < 300:
            logger.info("Reminder dispatched for task %s to %d devices", task.id, len(tokens))
            return True

        logger.error(
            "Failed to dispatch reminder for task %s: %s - %s",
            task.id,
            response.status_code,
            response.text,
        )
        return False

    @staticmethod
    def unique_tokens(devices: Iterable[models.Device]) -> list[str]:
        seen = set()
        tokens: list[str] = []
        for device in devices:
            if device.fcm_token and device.fcm_token not in seen:
                seen.add(device.fcm_token)
                tokens.append(device.fcm_token)
        return tokens
