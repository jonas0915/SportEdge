from sports.base import SportModule


class UFCModule(SportModule):
    sport_key = "ufc"
    espn_sport = "mma"
    espn_league = "ufc"
    elo_k_factor = 40.0
    home_advantage = 0.0

    def extract_features(self, home_stats: dict, away_stats: dict) -> dict:
        def win_pct(w, l):
            total = w + l
            return w / total if total > 0 else 0.5

        h_games = home_stats["wins"] + home_stats["losses"]
        a_games = away_stats["wins"] + away_stats["losses"]

        # points_for = finish rate, points_against = finish loss rate
        h_finish = home_stats.get("points_for", 0)
        a_finish = away_stats.get("points_for", 0)
        h_finish_loss = home_stats.get("points_against", 0)
        a_finish_loss = away_stats.get("points_against", 0)

        return {
            "home_win_pct": win_pct(home_stats["wins"], home_stats["losses"]),
            "away_win_pct": win_pct(away_stats["wins"], away_stats["losses"]),
            # UFC has no L10 from ESPN, use overall win% as proxy
            "home_l10_pct": win_pct(home_stats["wins"], home_stats["losses"]),
            "away_l10_pct": win_pct(away_stats["wins"], away_stats["losses"]),
            # No home/away in UFC — use finish rate as offensive metric
            "home_home_pct": h_finish if h_finish > 0 else 0.5,
            "away_away_pct": a_finish if a_finish > 0 else 0.5,
            # pts_diff = finish rate - finish loss rate (offensive vs defensive)
            "home_pts_diff": (h_finish - h_finish_loss) / max(h_games, 1),
            "away_pts_diff": (a_finish - a_finish_loss) / max(a_games, 1),
            "home_streak": home_stats["streak"] / 10.0,
            "away_streak": away_stats["streak"] / 10.0,
            "home_rest_advantage": 0.0,  # No rest data for UFC
        }
