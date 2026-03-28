import json
import logging

logger = logging.getLogger("engine.rationale")


def _fmt_pct(prob: float) -> str:
    """Format a probability as an integer percentage string, e.g. '62%'."""
    return f"{round(prob * 100)}%"


def _fmt_odds(odds: float) -> str:
    """Format American odds with sign, e.g. '+145' or '-110'."""
    val = int(round(odds))
    return f"+{val}" if val > 0 else str(val)


def _edge_pct(edge: float) -> str:
    """Format edge as '+X%'."""
    return f"+{round(edge * 100)}%"


def _fmt_record(wins: int, losses: int) -> str:
    return f"{wins}-{losses}"


def _streak_phrase(streak: int) -> str:
    """Return a human-readable streak description."""
    if streak > 0:
        return f"{streak}-game win streak"
    elif streak < 0:
        return f"{abs(streak)}-game losing streak"
    return ""


def _ufc_extra(stats: dict) -> dict:
    """Safely parse extra_json from UFC fighter stats."""
    try:
        return json.loads(stats.get("extra_json") or "{}")
    except (ValueError, TypeError):
        return {}


def _build_stat_clause_team(sport: str, stats: dict, is_home: bool) -> str:
    """
    Build the key-stat phrase for a standard team sport (NBA/NFL/MLB/NHL).
    Returns an empty string if nothing useful is available.
    """
    if not stats:
        return ""

    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    wins_l10 = stats.get("wins_l10", 0)
    losses_l10 = stats.get("losses_l10", 0)
    pts_for = stats.get("points_for", 0)
    pts_against = stats.get("points_against", 0)
    streak = stats.get("streak", 0)

    parts = []

    # Recent form (L10)
    l10_total = wins_l10 + losses_l10
    if l10_total > 0:
        parts.append(f"{wins_l10}-{losses_l10} L10 record")

    # Points differential
    if pts_for and pts_against:
        diff = round(pts_for - pts_against, 1)
        sign = "+" if diff >= 0 else ""
        parts.append(f"{sign}{diff} point differential")

    # Streak
    streak_str = _streak_phrase(streak)
    if streak_str:
        parts.append(streak_str)

    if not parts:
        # Fallback: overall record
        if wins + losses > 0:
            parts.append(f"{_fmt_record(wins, losses)} overall record")

    return ", ".join(parts[:2])  # cap at 2 facts to stay concise


def _build_stat_clause_ufc(stats: dict) -> str:
    """
    Build the key-stat phrase for a UFC fighter.
    """
    if not stats:
        return ""

    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    extra = _ufc_extra(stats)

    finish_rate = extra.get("finish_rate")
    parts = []

    if wins + losses > 0:
        parts.append(f"{_fmt_record(wins, losses)} record")

    if finish_rate is not None:
        parts.append(f"{round(finish_rate * 100)}% finish rate")

    return ", ".join(parts[:2])


def _elo_clause(
    sport: str,
    selection: str,
    home_team: str,
    away_team: str,
    home_elo: float | None,
    away_elo: float | None,
    threshold: int = 50,
) -> str:
    """
    Return an Elo advantage sentence when the gap is significant.
    Returns empty string otherwise.
    """
    if home_elo is None or away_elo is None:
        return ""
    gap = round(home_elo - away_elo)
    if abs(gap) < threshold:
        return ""

    if gap > 0:
        favored_team = home_team
        gap_str = gap
    else:
        favored_team = away_team
        gap_str = abs(gap)

    return f"Elo edge: {favored_team} leads by {gap_str} rating points."


def generate_rationale(
    # Core prediction numbers
    model_prob: float,
    market_prob: float,
    edge: float,
    selection: str,        # 'home' | 'away'
    best_book: str,
    best_odds: float,
    # Game context
    home_team: str,
    away_team: str,
    sport: str,
    # Optional enrichment
    home_stats: dict | None = None,
    away_stats: dict | None = None,
    home_elo: float | None = None,
    away_elo: float | None = None,
) -> str:
    """
    Generate a concise 2-3 sentence human-readable rationale for a prediction.

    Template logic (no LLM calls — fast and deterministic):
    - Sentence 1: model vs market probability comparison + edge
    - Sentence 2: key stat driving the edge (if stats available) or consensus note
    - Sentence 3: best book and odds
    """
    try:
        # Identify the team being bet on
        if selection == "home":
            bet_team = home_team
            opponent = away_team
            sel_stats = home_stats
            opp_stats = away_stats
        else:
            bet_team = away_team
            opponent = home_team
            sel_stats = away_stats
            opp_stats = home_stats

        model_pct = _fmt_pct(model_prob)
        market_pct = _fmt_pct(market_prob)
        edge_str = _edge_pct(edge)
        odds_str = _fmt_odds(best_odds)

        # --- Sentence 1: probability comparison ---
        sentence1 = (
            f"Model gives {bet_team} a {model_pct} chance vs market's "
            f"{market_pct} ({edge_str} edge)."
        )

        # --- Sentence 2: key stat ---
        if sport == "ufc":
            stat_clause = _build_stat_clause_ufc(sel_stats)
            opp_stat_clause = _build_stat_clause_ufc(opp_stats)
            if stat_clause:
                if opp_stat_clause:
                    sentence2 = (
                        f"{bet_team} brings {stat_clause} vs {opponent}'s "
                        f"{opp_stat_clause}."
                    )
                else:
                    sentence2 = f"{bet_team} brings {stat_clause}."
            else:
                # No stats — fall back to consensus language
                sentence2 = (
                    f"Consensus of multiple books shows {edge_str} edge "
                    f"on {bet_team}; market may be undervaluing this fighter."
                )
        elif sel_stats:
            stat_clause = _build_stat_clause_team(sport, sel_stats, is_home=(selection == "home"))
            elo_clause = _elo_clause(
                sport, selection, home_team, away_team, home_elo, away_elo
            )
            if stat_clause:
                sentence2 = f"{bet_team} shows {stat_clause}."
                if elo_clause:
                    sentence2 += f" {elo_clause}"
            elif elo_clause:
                sentence2 = elo_clause
            else:
                sentence2 = (
                    f"Model consensus favors {bet_team} based on "
                    f"team performance metrics."
                )
        else:
            # No stats available at all — consensus-only pick
            sentence2 = (
                f"Consensus of 40+ books shows {edge_str} edge on the "
                f"{'home' if selection == 'home' else 'away'} side. "
                f"Market may be overvaluing {opponent}."
            )

        # --- Sentence 3: best book / odds ---
        sentence3 = f"Best value at {best_book} {odds_str}."

        return f"{sentence1} {sentence2} {sentence3}"

    except Exception as e:
        logger.warning(f"Rationale generation failed: {e}")
        return ""
