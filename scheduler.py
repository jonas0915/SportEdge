import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from engine.pipeline import run_pipeline
from config import config

logger = logging.getLogger("scheduler")


async def odds_job():
    logger.info("Scheduler: starting odds fetch + ranking pipeline")
    try:
        picks = await run_pipeline()
        logger.info(f"Scheduler: pipeline complete, {len(picks)} top picks")
    except Exception as e:
        logger.error(f"Scheduler: pipeline failed — {e}")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        odds_job,
        "interval",
        minutes=config.odds_api.poll_interval_min,
        max_instances=1,
        id="odds_fetch",
        name="Fetch odds + rank",
    )
    return scheduler
