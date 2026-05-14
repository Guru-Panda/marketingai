from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response

from backend.data_retention import delete_old_leads
from backend.database import Base, engine, settings
from backend.migrate import run_migrations
from backend.monitor.sync import run_sync
from backend.routes import auth, business, channels, leads, users
from backend.routes import admin

Base.metadata.create_all(bind=engine)
run_migrations()

_scheduler = AsyncIOScheduler(timezone="UTC")
_scheduler.add_job(
    delete_old_leads,
    trigger=CronTrigger(hour=3, minute=0),
    id="delete_old_leads",
    replace_existing=True,
    max_instances=1,
    misfire_grace_time=3600,
)
_scheduler.add_job(
    run_sync,
    trigger=IntervalTrigger(hours=settings.SYNC_INTERVAL_HOURS),
    id="sync_channels",
    replace_existing=True,
    max_instances=1,
    misfire_grace_time=3600,
    next_run_time=datetime.now(timezone.utc),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _scheduler.start()
    yield
    _scheduler.shutdown(wait=False)


app = FastAPI(title="Marketing API", version="1.0.0", lifespan=lifespan)

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Max-Age": "600",
}


@app.middleware("http")
async def cors_and_security(request: Request, call_next) -> Response:
    # Handle CORS preflight
    if request.method == "OPTIONS":
        return Response(status_code=200, headers=_CORS_HEADERS)

    response = await call_next(request)

    # Add CORS + security headers to every response
    for k, v in _CORS_HEADERS.items():
        response.headers[k] = v
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(business.router)
app.include_router(channels.router)
app.include_router(channels.suggested_router)
app.include_router(leads.router)
app.include_router(admin.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    return {"status": "ok", "version": "cors-fix-v4"}
