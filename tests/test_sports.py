from sports.nba import NBAModule


class TestNBAModule:
    def setup_method(self):
        self.nba = NBAModule()

    def test_sport_key(self):
        assert self.nba.sport_key == "nba"

    def test_espn_paths(self):
        assert self.nba.espn_sport == "basketball"
        assert self.nba.espn_league == "nba"

    def test_extract_features(self):
        home = {
            "wins": 45, "losses": 20, "wins_l10": 7, "losses_l10": 3,
            "home_wins": 28, "home_losses": 5, "points_for": 112.5,
            "points_against": 106.2, "streak": 3, "rest_days": 2,
        }
        away = {
            "wins": 30, "losses": 35, "wins_l10": 4, "losses_l10": 6,
            "away_wins": 12, "away_losses": 20, "points_for": 105.1,
            "points_against": 110.3, "streak": -2, "rest_days": 1,
        }
        features = self.nba.extract_features(home, away)
        assert "home_win_pct" in features
        assert "away_win_pct" in features
        assert "home_pts_diff" in features
        assert "home_rest_advantage" in features
        assert 0 <= features["home_win_pct"] <= 1
        assert 0 <= features["away_win_pct"] <= 1

    def test_features_handle_zero_games(self):
        empty = {
            "wins": 0, "losses": 0, "wins_l10": 0, "losses_l10": 0,
            "home_wins": 0, "home_losses": 0,
            "away_wins": 0, "away_losses": 0,
            "points_for": 0, "points_against": 0,
            "streak": 0, "rest_days": 1,
        }
        features = self.nba.extract_features(empty, empty)
        assert features["home_win_pct"] == 0.5  # default when no games
