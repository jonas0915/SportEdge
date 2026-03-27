import logging
from fetchers.base import BaseFetcher
from db.database import get_connection

logger = logging.getLogger("fetchers.stats")

ESPN_BASE = "https://site.api.espn.com/apis/v2/sports"

SPORT_ESPN_MAP = {
    "nba": ("basketball", "nba"),
    "nfl": ("football", "nfl"),
    "mlb": ("baseball", "mlb"),
    "nhl": ("hockey", "nhl"),
}


def _parse_record(summary: str) -> tuple[int, int]:
    """Parse '30-3' into (30, 3)."""
    try:
        parts = summary.split("-")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 0, 0


def parse_espn_standings(data: dict, sport: str) -> list[dict]:
    teams = []
    for conference in data.get("children", []):
        for entry in conference.get("standings", {}).get("entries", []):
            team_info = entry.get("team", {})
            stats_raw = {s["name"]: s for s in entry.get("stats", [])}

            wins = int(stats_raw.get("wins", {}).get("value", 0))
            losses = int(stats_raw.get("losses", {}).get("value", 0))
            pts_for = stats_raw.get("avgPointsFor", {}).get("value", 0)
            pts_against = stats_raw.get("avgPointsAgainst", {}).get("value", 0)
            streak_val = stats_raw.get("streak", {}).get("value", 0)

            home_rec = stats_raw.get("Home Record", {}).get("summary", "0-0")
            away_rec = stats_raw.get("Away Record", {}).get("summary", "0-0")
            l10_rec = stats_raw.get("Last Ten Games Record", {}).get("summary", "0-0")

            hw, hl = _parse_record(home_rec)
            aw, al = _parse_record(away_rec)
            l10w, l10l = _parse_record(l10_rec)

            teams.append({
                "sport": sport,
                "team_name": team_info.get("displayName", ""),
                "abbreviation": team_info.get("abbreviation", ""),
                "wins": wins,
                "losses": losses,
                "wins_l10": l10w,
                "losses_l10": l10l,
                "home_wins": hw,
                "home_losses": hl,
                "away_wins": aw,
                "away_losses": al,
                "points_for": pts_for,
                "points_against": pts_against,
                "streak": int(streak_val),
                "rest_days": 1,
            })
    return teams


def save_team_stats(teams: list[dict]):
    conn = get_connection()
    try:
        for t in teams:
            conn.execute(
                """INSERT INTO team_stats
                   (sport, team_name, wins, losses, wins_l10, losses_l10,
                    home_wins, home_losses, away_wins, away_losses,
                    points_for, points_against, streak, rest_days)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(sport, team_name) DO UPDATE SET
                    wins=excluded.wins, losses=excluded.losses,
                    wins_l10=excluded.wins_l10, losses_l10=excluded.losses_l10,
                    home_wins=excluded.home_wins, home_losses=excluded.home_losses,
                    away_wins=excluded.away_wins, away_losses=excluded.away_losses,
                    points_for=excluded.points_for, points_against=excluded.points_against,
                    streak=excluded.streak, rest_days=excluded.rest_days,
                    updated_at=datetime('now')
                """,
                (t["sport"], t["team_name"], t["wins"], t["losses"],
                 t["wins_l10"], t["losses_l10"], t["home_wins"], t["home_losses"],
                 t["away_wins"], t["away_losses"], t["points_for"], t["points_against"],
                 t["streak"], t["rest_days"]),
            )
        conn.commit()
        logger.info(f"Saved stats for {len(teams)} teams")
    finally:
        conn.close()


def get_team_stats(sport: str, team_name: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM team_stats WHERE sport = ? AND team_name = ?",
            (sport, team_name),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


class StatsFetcher(BaseFetcher):
    async def fetch_sport_stats(self, sport: str) -> list[dict]:
        mapping = SPORT_ESPN_MAP.get(sport)
        if not mapping:
            logger.warning(f"No ESPN mapping for sport: {sport}")
            return []

        espn_sport, espn_league = mapping
        url = f"{ESPN_BASE}/{espn_sport}/{espn_league}/standings"

        data = await self._request("GET", url)
        teams = parse_espn_standings(data, sport=sport)
        logger.info(f"Fetched {len(teams)} {sport} teams from ESPN")
        return teams

    async def fetch_and_save(self, sport: str) -> int:
        teams = await self.fetch_sport_stats(sport)
        if teams:
            save_team_stats(teams)
        return len(teams)

    async def fetch_all_sports(self) -> int:
        total = 0
        for sport in SPORT_ESPN_MAP:
            try:
                count = await self.fetch_and_save(sport)
                total += count
            except Exception as e:
                logger.error(f"Failed to fetch {sport} stats: {e}")
        return total
