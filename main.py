from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, devices, sync, tasks

settings = get_settings()

app = FastAPI(title="TaskUp API", version="1.0.0", docs_url="/docs", redoc_url="/redoc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"]
    , allow_headers=["*"]
)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(tasks.router)
app.include_router(sync.router)


@app.get("/", tags=["system"])
def root():
    return {"name": "TaskUp API", "version": app.version}


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}