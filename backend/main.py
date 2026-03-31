import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from routers.api import router
from services.scanner import run_scan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

app = FastAPI(title="Polymarket Scout", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def startup():
    log.info("Starting Polymarket Scout backend...")

    scheduler.add_job(
        run_scan,
        "interval",
        minutes=settings.scan_interval_minutes,
        id="periodic_scan",
        replace_existing=True,
    )
    scheduler.start()
    log.info(f"Scheduler started — first scan in {settings.scan_interval_minutes} min")


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)
    log.info("Scheduler stopped")
