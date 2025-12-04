from __future__ import annotations

from datetime import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user, get_device_for_user
from ..services.sync_service import SyncService

router = APIRouter(prefix="/devices", tags=["devices"])

logger = logging.getLogger(__name__)


@router.post("", response_model=schemas.DeviceRegisterResponse)
def register_device(
    payload: schemas.DeviceRegisterRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logger.info(
        "Registering device: user=%s uuid=%s platform=%s has_fcm=%s",
        current_user.id,
        payload.device_uuid,
        payload.platform.value,
        bool(payload.fcm_token),
    )
    device = get_device_for_user(db, current_user.id, payload.device_uuid)
    if device:
        logger.debug("Found existing device id=%s", device.id)
        device.device_name = payload.device_name or device.device_name
        device.platform = payload.platform.value
        device.app_version = payload.app_version or device.app_version
        device.last_seen_at = datetime.utcnow()
    else:
        device = models.Device(
            user_id=current_user.id,
            device_uuid=payload.device_uuid,
            device_name=payload.device_name,
            platform=payload.platform.value,
            app_version=payload.app_version,
            last_seen_at=datetime.utcnow(),
        )
        db.add(device)
        db.flush()
        logger.info("Created new device id=%s for user=%s", device.id, current_user.id)

    if payload.fcm_token:
        if payload.fcm_token != device.fcm_token:
            device.fcm_token = payload.fcm_token
            device.fcm_token_updated_at = datetime.utcnow()
            logger.info(
                "Updated FCM token for device id=%s -> %s",
                device.id,
                _mask_secret(payload.fcm_token),
            )
    elif payload.fcm_token == "":
        device.fcm_token = None
        device.fcm_token_updated_at = datetime.utcnow()
        logger.info("Cleared FCM token for device id=%s", device.id)

    sync = SyncService(db)
    cursor = sync.ensure_cursor(device)
    db.commit()
    logger.info(
        "Device registration complete id=%s last_change_id=%s",
        device.id,
        cursor.last_change_id,
    )
    return schemas.DeviceRegisterResponse(device_id=device.id, last_change_id=cursor.last_change_id)


@router.get("", response_model=list[schemas.DeviceRegisterResponse])
def list_devices(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    devices = (
        db.query(models.Device)
        .filter(models.Device.user_id == current_user.id)
        .all()
    )
    sync = SyncService(db)
    response: list[schemas.DeviceRegisterResponse] = []
    for device in devices:
        cursor = sync.ensure_cursor(device)
        response.append(
            schemas.DeviceRegisterResponse(device_id=device.id, last_change_id=cursor.last_change_id)
        )
    return response


def _mask_secret(value: Optional[str]) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return f"{len(value)} chars"
    return f"{value[:4]}...{value[-4:]} ({len(value)} chars)"
