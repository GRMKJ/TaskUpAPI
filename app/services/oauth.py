from __future__ import annotations

from typing import Sequence

from google.auth.transport import requests
from google.oauth2 import id_token


class GoogleTokenVerifier:
    """Utility wrapper around google-auth verification helpers."""

    def __init__(self, audiences: Sequence[str] | None = None) -> None:
        self.audiences = [aud for aud in (audiences or []) if aud]
        self._request = requests.Request()

    def verify(self, token: str) -> dict:
        last_error: Exception | None = None
        if not self.audiences:
            try:
                return id_token.verify_oauth2_token(token, self._request)
            except ValueError as exc:  # noqa: TRY003
                raise ValueError("Invalid Google token") from exc

        for audience in self.audiences:
            try:
                return id_token.verify_oauth2_token(token, self._request, audience=audience)
            except ValueError as exc:  # noqa: TRY003
                last_error = exc
                continue

        raise ValueError("Invalid Google token") from last_error
