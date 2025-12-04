from __future__ import annotations

import logging
from typing import Iterable, Sequence

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from .. import models

logger = logging.getLogger(__name__)


class NotificationService:
    """Wrapper around Firebase Cloud Messaging HTTP v1 API."""

    FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
    FCM_ENDPOINT_TEMPLATE = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

    def __init__(self, project_id: str | None, credentials_file: str | None) -> None:
        self._project_id = project_id
        self._request_adapter = Request()
        self._credentials = None

        if project_id and credentials_file:
            try:
                self._credentials = service_account.Credentials.from_service_account_file(
                    credentials_file,
                    scopes=[self.FCM_SCOPE],
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to load Firebase credentials: %s", exc)
        else:
            pairs = (("project_id", project_id), ("credentials_file", credentials_file))
            missing = [name for name, value in pairs if not value]
            if missing:
                logger.warning("FCM notifications disabled; missing %s", ", ".join(missing))

    @property
    def enabled(self) -> bool:
        return bool(self._project_id and self._credentials)

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
        if not self.enabled:
            logger.warning("FCM configuration incomplete; skipping reminder dispatch")
            return False

        masked_tokens = _mask_tokens(tokens)
        logger.debug(
            "Dispatching reminder task_id=%s target_count=%s targets=%s",
            task.id,
            len(tokens),
            masked_tokens,
        )

        endpoint = self.FCM_ENDPOINT_TEMPLATE.format(project_id=self._project_id)
        successes = 0
        for idx, token in enumerate(tokens):
            message = self._build_message(token, task, user)
            try:
                headers = self._auth_headers()
                response = requests.post(
                    endpoint,
                    json={"message": message},
                    headers=headers,
                    timeout=10,
                )
            except requests.RequestException as exc:  # noqa: BLE001
                logger.exception(
                    "FCM request failed for task %s token=%s: %s",
                    task.id,
                    masked_tokens[idx],
                    exc,
                )
                continue

            if 200 <= response.status_code < 300:
                successes += 1
                continue

            logger.error(
                "Failed to dispatch reminder task_id=%s token=%s status=%s body=%s headers=%s",
                task.id,
                masked_tokens[idx],
                response.status_code,
                response.text,
                {
                    "content-type": response.headers.get("Content-Type"),
                    "date": response.headers.get("Date"),
                },
            )

        if successes:
            logger.info(
                "Reminder dispatched for task %s to %d/%d devices",
                task.id,
                successes,
                len(tokens),
            )
            return True

        return False

    def _auth_headers(self) -> dict[str, str]:
        if not self._credentials:
            raise RuntimeError("FCM credentials not configured")
        if not self._credentials.valid:
            self._credentials.refresh(self._request_adapter)
        return {
            "Authorization": f"Bearer {self._credentials.token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    @staticmethod
    def _build_message(token: str, task: models.Task, user: models.User) -> dict:
        return {
            "token": token,
            "notification": {
                "title": f"{user.display_name} - TaskUp",
                "body": task.title,
            },
            "data": {
                "task_id": str(task.id),
                "remind_at": task.remind_at.isoformat() if task.remind_at else "",
                "priority": str(task.priority),
            },
        }

    @staticmethod
    def unique_tokens(devices: Iterable[models.Device]) -> list[str]:
        seen = set()
        tokens: list[str] = []
        for device in devices:
            if device.fcm_token and device.fcm_token not in seen:
                seen.add(device.fcm_token)
                tokens.append(device.fcm_token)
        return tokens


def _mask_tokens(tokens: Sequence[str]) -> list[str]:
    masked: list[str] = []
    for token in tokens:
        if not token:
            masked.append("<empty>")
            continue
        if len(token) <= 8:
            masked.append(f"{len(token)} chars")
            continue
        masked.append(f"{token[:4]}...{token[-4:]} ({len(token)} chars)")
    return masked
