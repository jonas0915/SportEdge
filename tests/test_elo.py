from engine.elo import expected_score, update_elo, elo_win_probability


class TestEloMath:
    def test_equal_ratings(self):
        assert abs(expected_score(1500, 1500) - 0.5) < 0.001

    def test_higher_rating_favored(self):
        assert expected_score(1600, 1400) > 0.7

    def test_lower_rating_underdog(self):
        assert expected_score(1400, 1600) < 0.3

    def test_update_winner_gains(self):
        new_a, new_b = update_elo(1500, 1500, a_won=True, k=20)
        assert new_a > 1500
        assert new_b < 1500
        assert abs((new_a - 1500) - (1500 - new_b)) < 0.01  # zero-sum

    def test_update_upset_bigger_change(self):
        # Underdog wins = bigger Elo swing
        new_a, _ = update_elo(1400, 1600, a_won=True, k=20)
        normal_a, _ = update_elo(1600, 1400, a_won=True, k=20)
        assert (new_a - 1400) > (normal_a - 1600)

    def test_win_probability_with_home_advantage(self):
        prob = elo_win_probability(1500, 1500, home_advantage=100)
        assert prob > 0.5  # home team favored
        assert prob < 0.7

    def test_win_probability_no_advantage(self):
        prob = elo_win_probability(1500, 1500, home_advantage=0)
        assert abs(prob - 0.5) < 0.001
