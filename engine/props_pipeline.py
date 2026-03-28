import logging
from fetchers.props_fetcher import PropsFetcher
from engine.props_edge import find_prop_edges
from db.models import insert_prop, insert_prop_pick, get_top_prop_picks
from db.database import get_connection
from config import config

logger = logging.getLogger("engine.props_pipeline")


def _rebuild_picks_from_db(sport: str, min_edge: float) -> list[dict]:
    """
    Re-compute prop picks from recently stored raw props when a live fetch fails.
    This prevents prop_picks from going empty when the circuit breaker is open.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM props WHERE sport = ? AND created_at >= datetime('now', '-24 hours')",
            (sport,),
        ).fetchall()
        if not rows:
            return get_top_prop_picks(sport=sport, limit=50)
        props_data = [dict(r) for r in rows]
    finally:
        conn.close()

    picks = find_prop_edges(props_data, min_edge=min_edge)
    if not picks:
        logger.info(f"No edges in stored props for {sport} — returning existing picks")
        return get_top_prop_picks(sport=sport, limit=50)

    # Persist the re-computed picks
    conn = get_connection()
    try:
        conn.execute("DELETE FROM prop_picks WHERE sport = ?", (sport,))
        conn.commit()
    finally:
        conn.close()

    from db.models import insert_prop_pick as _insert
    saved = 0
    for pick in picks:
        try:
            _insert(
                game_id=pick.get("game_id"),
                sport=pick["sport"],
                player_name=pick["player_name"],
                stat_type=pick["stat_type"],
                direction=pick["direction"],
                consensus_line=pick["consensus_line"],
                best_line=pick["best_line"],
                best_book=pick["best_book"],
                edge_pct=pick["edge_pct"],
                pp_line=pick.get("pp_line"),
            )
            saved += 1
        except Exception as e:
            logger.warning(f"Failed to save rebuilt prop pick: {e}")

    logger.info(f"Rebuilt {saved} prop picks from stored DB props for {sport}")
    return get_top_prop_picks(sport=sport, limit=50)


async def run_props_pipeline(
    sport_key: str = "basketball_nba",
) -> list[dict]:
    """
    Orchestrates the full props pipeline for a sport:
      1. Fetch upcoming events (free)
      2. Fetch player props for each event
      3. Find edges across books
      4. Save props + picks to DB
      5. Return top picks

    Returns list of top prop picks.
    """
    props_cfg = getattr(config, "props", None)
    if props_cfg and not props_cfg.enabled:
        logger.info("Props pipeline disabled in config")
        return []

    markets = list(props_cfg.markets) if props_cfg else [
        "player_points", "player_rebounds", "player_assists", "player_threes"
    ]
    min_edge = props_cfg.min_edge if props_cfg else 0.05
    sport = sport_key.split("_")[1] if "_" in sport_key else sport_key

    fetcher = PropsFetcher()
    try:
        logger.info(f"Props pipeline starting for {sport_key}")

        props = await fetcher.fetch_all_props(sport_key=sport_key, markets=markets)

        if not props:
            logger.info(f"No props fetched for {sport_key} — rebuilding picks from stored DB props")
            return _rebuild_picks_from_db(sport=sport, min_edge=min_edge)

        # Save raw prop lines to DB
        saved_props = 0
        for p in props:
            if p.get("line") is None:
                continue
            try:
                insert_prop(
                    game_id=p.get("game_id"),
                    sport=p["sport"],
                    player_name=p["player_name"],
                    stat_type=p["stat_type"],
                    line=p["line"],
                    bookmaker=p["bookmaker"],
                    over_price=p.get("over_price"),
                    under_price=p.get("under_price"),
                )
                saved_props += 1
            except Exception as e:
                logger.warning(f"Failed to save prop line: {e}")

        logger.info(f"Saved {saved_props} raw prop lines")

        # Find edges
        picks = find_prop_edges(props, min_edge=min_edge)

        # Only replace existing picks when we have fresh data
        conn = get_connection()
        try:
            conn.execute("DELETE FROM prop_picks WHERE sport = ?", (sport,))
            conn.commit()
        finally:
            conn.close()

        # Save prop picks to DB
        saved_picks = 0
        for pick in picks:
            try:
                insert_prop_pick(
                    game_id=pick.get("game_id"),
                    sport=pick["sport"],
                    player_name=pick["player_name"],
                    stat_type=pick["stat_type"],
                    direction=pick["direction"],
                    consensus_line=pick["consensus_line"],
                    best_line=pick["best_line"],
                    best_book=pick["best_book"],
                    edge_pct=pick["edge_pct"],
                    pp_line=pick.get("pp_line"),
                )
                saved_picks += 1
            except Exception as e:
                logger.warning(f"Failed to save prop pick: {e}")

        logger.info(
            f"Props pipeline complete: {len(props)} lines fetched, "
            f"{len(picks)} edges found, {saved_picks} picks saved"
        )

        return get_top_prop_picks(sport=sport, limit=50)

    except Exception as e:
        logger.error(f"Props pipeline failed: {e}")
        return []
    finally:
        await fetcher.close()
