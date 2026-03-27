from sports.base import SportModule


class NHLModule(SportModule):
    sport_key = "nhl"
    espn_sport = "hockey"
    espn_league = "nhl"
    elo_k_factor = 20.0
    home_advantage = 30.0

    def extract_features(self, home_stats: dict, away_stats: dict) -> dict:
        def win_pct(w, l):
            total = w + l
            return w / total if total > 0 else 0.5

        def pts_diff(pf, pa):
            return pf - pa

        h_games = home_stats["wins"] + home_stats["losses"]
        a_games = away_stats["wins"] + away_stats["losses"]

        return {
            "home_win_pct": win_pct(home_stats["wins"], home_stats["losses"]),
            "away_win_pct": win_pct(away_stats["wins"], away_stats["losses"]),
            "home_l10_pct": win_pct(home_stats["wins_l10"], home_stats["losses_l10"]),
            "away_l10_pct": win_pct(away_stats["wins_l10"], away_stats["losses_l10"]),
            "home_home_pct": win_pct(home_stats["home_wins"], home_stats["home_losses"]),
            "away_away_pct": win_pct(away_stats["away_wins"], away_stats["away_losses"]),
            "home_pts_diff": pts_diff(home_stats["points_for"], home_stats["points_against"]) / max(h_games, 1),
            "away_pts_diff": pts_diff(away_stats["points_for"], away_stats["points_against"]) / max(a_games, 1),
            "home_streak": home_stats["streak"] / 10.0,
            "away_streak": away_stats["streak"] / 10.0,
            "home_rest_advantage": min(home_stats["rest_days"] - away_stats["rest_days"], 3) / 3.0,
        }
