from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


TaskPriorityEnum = Enum("low", "medium", "high", name="task_priority")
TaskStatusEnum = Enum("active", "inactive", "blocked", name="user_status")
OperationEnum = Enum(
    "create",
    "update",
    "complete",
    "reopen",
    "delete",
    "restore",
    name="task_operation",
)
PlatformEnum = Enum("android", "ios", "web", "desktop", name="device_platform")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(60), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(TaskStatusEnum, nullable=False, default="active")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    devices: Mapped[list[Device]] = relationship(back_populates="user")
    tasks: Mapped[list[Task]] = relationship(back_populates="user")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    device_name: Mapped[Optional[str]] = mapped_column(String(150))
    platform: Mapped[str] = mapped_column(PlatformEnum, nullable=False)
    app_version: Mapped[Optional[str]] = mapped_column(String(50))
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    fcm_token: Mapped[Optional[str]] = mapped_column(String(512))
    fcm_token_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="devices")
    sync_cursor: Mapped[Optional[DeviceSyncCursor]] = relationship(back_populates="device", uselist=False)

    __table_args__ = (Index("uniq_device_user_uuid", "user_id", "device_uuid", unique=True),)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    refresh_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))

    user: Mapped[User] = relationship()
    device: Mapped[Optional[Device]] = relationship()


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(TaskPriorityEnum, default="medium", nullable=False)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    remind_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    remind_local_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    remind_timezone_offset_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
    version: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    checksum: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped[User] = relationship(back_populates="tasks")
    change_log: Mapped[list[TaskChangeLog]] = relationship(back_populates="task")

    __table_args__ = (
        Index("idx_tasks_user", "user_id"),
        Index("idx_tasks_user_version", "user_id", "version"),
        Index("idx_tasks_user_completed", "user_id", "completed", "archived"),
    )


class TaskChangeLog(Base):
    __tablename__ = "task_change_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    operation: Mapped[str] = mapped_column(OperationEnum, nullable=False)
    change_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

    task: Mapped[Task] = relationship(back_populates="change_log")

    __table_args__ = (Index("idx_change_user_created", "user_id", "created_at"),)


class DeviceSyncCursor(Base):
    __tablename__ = "device_sync_cursors"

    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True)
    last_change_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))

    device: Mapped[Device] = relationship(back_populates="sync_cursor")
