import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from engine.pipeline import run_pipeline, run_stats_fetch
from engine.results import run_results_fetch
from engine.notifier import send_top_picks_alert
from config import config

logger = logging.getLogger("scheduler")


async def odds_job():
    logger.info("Scheduler: starting odds fetch + ranking pipeline")
    try:
        picks = await run_pipeline()
        logger.info(f"Scheduler: pipeline complete, {len(picks)} top picks")
    except Exception as e:
        logger.error(f"Scheduler: pipeline failed — {e}")


async def stats_job():
    logger.info("Scheduler: starting stats fetch")
    try:
        await run_stats_fetch()
    except Exception as e:
        logger.error(f"Scheduler: stats fetch failed — {e}")


async def results_job():
    logger.info("Scheduler: starting results fetch + prediction resolution")
    try:
        result = await run_results_fetch()
        logger.info(
            f"Scheduler: results complete — "
            f"{result['games_updated']} games finalized, "
            f"{result['predictions_resolved']} predictions resolved"
        )
    except Exception as e:
        logger.error(f"Scheduler: results fetch failed — {e}")


async def notify_job():
    """Send Telegram alerts for top picks if Telegram is configured."""
    if not config.telegram.enabled:
        return
    logger.info("Scheduler: running top-picks Telegram alert")
    try:
        sent = await send_top_picks_alert()
        if sent:
            logger.info("Scheduler: Telegram alert sent")
        else:
            logger.info("Scheduler: no new picks to alert (or Telegram not configured)")
    except Exception as e:
        logger.error(f"Scheduler: notify job failed — {e}")


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
    scheduler.add_job(
        stats_job,
        "interval",
        hours=6,
        max_instances=1,
        id="stats_fetch",
        name="Fetch team stats",
    )
    scheduler.add_job(
        results_job,
        "interval",
        minutes=30,
        max_instances=1,
        id="results_fetch",
        name="Fetch scores + resolve predictions",
    )
    scheduler.add_job(
        notify_job,
        "interval",
        minutes=30,
        max_instances=1,
        id="telegram_notify",
        name="Send Telegram top-picks alert",
    )
    return scheduler
