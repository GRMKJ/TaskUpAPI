from __future__ import annotations
import requests
from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import get_settings
from ..database import get_db
from ..dependencies import get_current_user
from ..security import create_access_token, create_refresh_token, hash_password, verify_password
from ..services.oauth import GoogleTokenVerifier
from fastapi.responses import JSONResponse


router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
google_verifier = GoogleTokenVerifier(settings.google_client_ids)


def _issue_tokens(db: Session, user: models.User, device_id: int | None = None) -> schemas.TokenResponse:
    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token()
    expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_expires_days)
    session = models.UserSession(
        user_id=user.id,
        device_id=device_id,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    return schemas.TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expires_minutes * 60,
    )


@router.post("/register", response_model=schemas.TokenResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = models.User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_tokens(db, user)


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")
    user.last_login_at = datetime.utcnow()
    db.add(user)
    db.commit()
    return _issue_tokens(db, user)


@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh_token(payload: schemas.RefreshRequest, db: Session = Depends(get_db)):
    session = (
        db.query(models.UserSession)
        .filter(models.UserSession.refresh_token == payload.refresh_token)
        .one_or_none()
    )
    if not session or session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    session.revoked_at = datetime.utcnow()
    db.add(session)
    db.commit()

    user = db.get(models.User, session.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User missing")
    return _issue_tokens(db, user, device_id=session.device_id)


@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/google", response_model=schemas.TokenResponse)
def login_with_google(payload: schemas.GoogleOAuthRequest, db: Session = Depends(get_db)):
    claims: dict | None = None

    if payload.id_token:
        try:
            claims = google_verifier.verify(payload.id_token)
        except ValueError:
            claims = None

    if claims is None and payload.access_token:
        try:
            google_userinfo = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {payload.access_token}"},
                timeout=5,
            )
            if google_userinfo.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Google access token",
                )
            claims = google_userinfo.json()
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to validate Google token",
            )

    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to validate Google token",
        )

    # 2. Extraemos email y verificamos
    email = claims.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google token missing email"
        )

    # 3. Buscar o crear usuario
    user = db.query(models.User).filter(models.User.email == email).one_or_none()

    if not user:
        display_name = claims.get("name") or email.split("@")[0]
        random_password = secrets.token_urlsafe(32)
        user = models.User(
            email=email,
            display_name=display_name,
            password_hash=hash_password(random_password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.last_login_at = datetime.utcnow()
        db.add(user)
        db.commit()

    # 4. Emitir tokens
    return _issue_tokens(db, user)
