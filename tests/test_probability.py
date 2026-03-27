from engine.probability import blend_probability, model_probability


class TestBlendProbability:
    def test_equal_blend(self):
        # 50/50 blend of 0.6 Elo and 0.7 logistic
        result = blend_probability(elo_prob=0.6, logistic_prob=0.7, elo_weight=0.5)
        assert abs(result - 0.65) < 0.001

    def test_default_blend_60_40(self):
        # Default: 40% Elo, 60% logistic
        result = blend_probability(elo_prob=0.5, logistic_prob=0.8, elo_weight=0.4)
        expected = 0.4 * 0.5 + 0.6 * 0.8  # 0.2 + 0.48 = 0.68
        assert abs(result - expected) < 0.001

    def test_elo_only(self):
        result = blend_probability(elo_prob=0.65, logistic_prob=0.5, elo_weight=1.0)
        assert abs(result - 0.65) < 0.001

    def test_clamps_to_valid_range(self):
        result = blend_probability(elo_prob=0.99, logistic_prob=0.99, elo_weight=0.5)
        assert result <= 1.0
        assert result >= 0.0


class TestModelProbability:
    def test_returns_probability(self):
        features = {
            "home_win_pct": 0.7, "away_win_pct": 0.4,
            "home_l10_pct": 0.8, "away_l10_pct": 0.3,
            "home_home_pct": 0.85, "away_away_pct": 0.35,
            "home_pts_diff": 6.5, "away_pts_diff": -3.2,
            "home_streak": 0.3, "away_streak": -0.2,
            "home_rest_advantage": 0.33,
        }
        prob = model_probability(features, home_elo=1600, away_elo=1400, home_advantage=100)
        assert 0 < prob < 1
        assert prob > 0.5  # strong home team should be favored

    def test_equal_teams(self):
        features = {
            "home_win_pct": 0.5, "away_win_pct": 0.5,
            "home_l10_pct": 0.5, "away_l10_pct": 0.5,
            "home_home_pct": 0.5, "away_away_pct": 0.5,
            "home_pts_diff": 0, "away_pts_diff": 0,
            "home_streak": 0, "away_streak": 0,
            "home_rest_advantage": 0,
        }
        prob = model_probability(features, home_elo=1500, away_elo=1500, home_advantage=0)
        assert 0.4 < prob < 0.6  # roughly even
