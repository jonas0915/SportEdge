from engine.value_finder import (
    american_to_implied_prob,
    implied_prob_to_american,
    find_consensus_prob,
    find_value_bets,
)


class TestOddsConversion:
    def test_negative_odds(self):
        # -180 implies ~64.3% probability
        prob = american_to_implied_prob(-180)
        assert abs(prob - 0.643) < 0.001

    def test_positive_odds(self):
        # +150 implies ~40% probability
        prob = american_to_implied_prob(150)
        assert abs(prob - 0.4) < 0.001

    def test_even_odds(self):
        prob = american_to_implied_prob(100)
        assert abs(prob - 0.5) < 0.001

    def test_round_trip(self):
        for odds in [-200, -110, 100, 150, 300]:
            prob = american_to_implied_prob(odds)
            back = implied_prob_to_american(prob)
            assert abs(back - odds) < 1


class TestConsensus:
    def test_consensus_from_multiple_books(self):
        odds_list = [
            {"bookmaker": "dk", "selection": "home", "price": -180},
            {"bookmaker": "fd", "selection": "home", "price": -165},
            {"bookmaker": "mgm", "selection": "home", "price": -175},
        ]
        prob = find_consensus_prob(odds_list)
        # Average of implied probs: (64.3 + 62.3 + 63.6) / 3 ≈ 63.4%
        assert 0.62 < prob < 0.65


class TestValueBets:
    def test_finds_value_when_book_diverges(self):
        game_odds = [
            {"bookmaker": "dk", "selection": "home", "price": 150, "bet_type": "h2h", "point": None},
            {"bookmaker": "fd", "selection": "home", "price": -110, "bet_type": "h2h", "point": None},
            {"bookmaker": "mgm", "selection": "home", "price": -120, "bet_type": "h2h", "point": None},
            {"bookmaker": "dk", "selection": "away", "price": -180, "bet_type": "h2h", "point": None},
            {"bookmaker": "fd", "selection": "away", "price": -110, "bet_type": "h2h", "point": None},
            {"bookmaker": "mgm", "selection": "away", "price": 100, "bet_type": "h2h", "point": None},
        ]
        values = find_value_bets(game_odds, min_edge=0.03)
        # DK has home at +150 (40% implied) while consensus is ~50% → value on home
        assert len(values) > 0
        home_value = [v for v in values if v["selection"] == "home"]
        assert len(home_value) > 0
        assert home_value[0]["best_book"] == "dk"

    def test_no_value_when_books_agree(self):
        game_odds = [
            {"bookmaker": "dk", "selection": "home", "price": -110, "bet_type": "h2h", "point": None},
            {"bookmaker": "fd", "selection": "home", "price": -112, "bet_type": "h2h", "point": None},
            {"bookmaker": "dk", "selection": "away", "price": -110, "bet_type": "h2h", "point": None},
            {"bookmaker": "fd", "selection": "away", "price": -108, "bet_type": "h2h", "point": None},
        ]
        values = find_value_bets(game_odds, min_edge=0.05)
        assert len(values) == 0


from engine.ranker import compute_kelly, compute_score, rank_predictions


class TestKelly:
    def test_positive_edge(self):
        # 60% prob, +150 odds → positive Kelly
        f = compute_kelly(win_prob=0.6, american_odds=150)
        assert f > 0

    def test_no_edge(self):
        # 50% prob, -110 odds → near-zero or negative Kelly
        f = compute_kelly(win_prob=0.5, american_odds=-110)
        assert f <= 0.05

    def test_fractional_kelly(self):
        # Use values where full kelly doesn't hit the max_stake_pct cap
        f = compute_kelly(win_prob=0.51, american_odds=105, fraction=0.25)
        full = compute_kelly(win_prob=0.51, american_odds=105, fraction=1.0)
        assert full <= 0.05  # ensure full doesn't hit cap
        assert abs(f - full * 0.25) < 0.001


class TestScore:
    def test_score_formula(self):
        s = compute_score(edge=0.10, confidence=0.8, kelly=0.05)
        expected = 0.10 * 0.8 * 0.05
        assert abs(s - expected) < 0.0001

    def test_zero_edge(self):
        s = compute_score(edge=0.0, confidence=1.0, kelly=0.1)
        assert s == 0.0


class TestRanker:
    def test_ranks_by_score_descending(self):
        bets = [
            {"edge": 0.05, "model_prob": 0.55, "best_odds": 120},
            {"edge": 0.12, "model_prob": 0.62, "best_odds": 150},
            {"edge": 0.08, "model_prob": 0.58, "best_odds": 130},
        ]
        ranked = rank_predictions(bets, confidence=0.5, kelly_fraction=0.25)
        scores = [r["score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)
        assert all("rank" in r for r in ranked)
