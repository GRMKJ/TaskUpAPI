from __future__ import annotations
from typing import Sequence
from google.auth.transport import requests
from google.oauth2 import id_token


GOOGLE_ISSUERS = [
    "accounts.google.com",
    "https://accounts.google.com",
]


class GoogleTokenVerifier:

    def __init__(self, audiences: Sequence[str] | None = None) -> None:
        self.audiences = [aud for aud in (audiences or []) if aud]
        self._request = requests.Request()

    def verify(self, token: str) -> dict:
        last_error = None

        # Try each audience until one works
        audiences_to_try = self.audiences or [None]

        for audience in audiences_to_try:
            try:
                payload = id_token.verify_oauth2_token(
                    token,
                    self._request,
                    audience=audience
                )

                # Extra validation
                if payload.get("iss") not in GOOGLE_ISSUERS:
                    raise ValueError("Invalid issuer")

                if not payload.get("email_verified", False):
                    raise ValueError("Email not verified")

                return payload

            except ValueError as exc:
                last_error = exc
                continue

        raise ValueError("Invalid Google token") from last_error
