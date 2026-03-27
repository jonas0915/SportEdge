import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from logging_config import setup_logging
from db.database import run_migrations
from dashboard.routes import router as dashboard_router
from scheduler import create_scheduler
from engine.pipeline import run_pipeline
from config import config

setup_logging()
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SportEdge starting up")
    run_migrations()

    scheduler = create_scheduler()
    scheduler.start()
    logger.info(f"Scheduler started (odds every {config.odds_api.poll_interval_min} min)")

    # Run pipeline once on startup (with error handling)
    async def _startup_fetch():
        try:
            await run_pipeline()
        except Exception as e:
            logger.error(f"Startup pipeline failed: {e}")

    asyncio.create_task(_startup_fetch())

    yield

    scheduler.shutdown()
    logger.info("SportEdge shutting down")


app = FastAPI(title="SportEdge", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "dashboard" / "static")), name="static")
app.include_router(dashboard_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=config.dashboard.port)
