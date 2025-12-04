from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.config import get_settings
from app.routers import auth, devices, sync, tasks
from app.services.notification_service import NotificationService
from app.services.reminder_service import ReminderDispatcher

settings = get_settings()
log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
logging.getLogger().setLevel(log_level)
logging.getLogger("app").setLevel(log_level)
notification_service = NotificationService(
    project_id=settings.firebase_project_id,
    credentials_file=settings.firebase_credentials_file,
)
reminder_dispatcher = ReminderDispatcher(settings, notification_service)

app = FastAPI(
    title="TaskUp API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:9001",
        "https://taskup.cardomomo.icu"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(tasks.router)
app.include_router(sync.router)


@app.on_event("startup")
def _start_workers():
    reminder_dispatcher.start()


@app.on_event("shutdown")
def _stop_workers():
    reminder_dispatcher.stop()

@app.get("/", tags=["system"])
def root():
    return {"name": "TaskUp API", "version": app.version}

@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}
