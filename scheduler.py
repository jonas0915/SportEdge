import asyncio
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from engine.pipeline import run_pipeline, run_stats_fetch
from engine.results import run_results_fetch
from engine.notifier import send_top_picks_alert
from engine.props_pipeline import run_props_pipeline
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


async def props_job():
    """Fetch player props and find edges. Runs every 60 min to conserve credits."""
    props_cfg = getattr(config, "props", None)
    if props_cfg and not props_cfg.enabled:
        return

    # Only run if there are NBA games today (saves credits)
    from db.database import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM games "
            "WHERE sport = 'nba' AND status = 'upcoming' "
            "AND date(start_time) = date('now')"
        ).fetchone()
        has_nba_today = row["cnt"] > 0
    finally:
        conn.close()

    if not has_nba_today:
        logger.info("Scheduler: no NBA games today — skipping props fetch")
        return

    logger.info("Scheduler: starting props pipeline")
    try:
        picks = await run_props_pipeline(sport_key="basketball_nba")
        logger.info(f"Scheduler: props pipeline complete, {len(picks)} top picks")
    except Exception as e:
        logger.error(f"Scheduler: props pipeline failed — {e}")


async def kalshi_job():
    """Fetch Kalshi market data and update the DB. Runs every 30 min."""
    kalshi_cfg = getattr(config, "kalshi", None)
    if kalshi_cfg and not kalshi_cfg.enabled:
        logger.info("Scheduler: Kalshi disabled in config — skipping")
        return
    logger.info("Scheduler: starting Kalshi market fetch")
    try:
        from fetchers.kalshi_fetcher import KalshiFetcher
        fetcher = KalshiFetcher()
        markets = await fetcher.fetch_all()
        logger.info(f"Scheduler: Kalshi fetch complete, {len(markets)} markets updated")
        await fetcher.close()
    except Exception as e:
        logger.error(f"Scheduler: Kalshi fetch failed — {e}")


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
    props_cfg = getattr(config, "props", None)
    if props_cfg and props_cfg.enabled:
        scheduler.add_job(
            props_job,
            "interval",
            minutes=props_cfg.poll_interval_min,
            max_instances=1,
            id="props_fetch",
            name="Fetch player props + find edges",
            next_run_time=datetime.now(timezone.utc),  # run immediately on startup
        )
    kalshi_cfg = getattr(config, "kalshi", None)
    if not kalshi_cfg or kalshi_cfg.enabled:
        scheduler.add_job(
            kalshi_job,
            "interval",
            minutes=getattr(kalshi_cfg, "poll_interval_min", 30) if kalshi_cfg else 30,
            max_instances=1,
            id="kalshi_fetch",
            name="Fetch Kalshi prediction markets",
        )
    return scheduler
