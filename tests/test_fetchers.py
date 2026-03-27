import pytest
from unittest.mock import AsyncMock, patch
from fetchers.base import BaseFetcher, CircuitOpenError


class DummyFetcher(BaseFetcher):
    async def fetch(self):
        return await self._request("GET", "https://httpbin.org/get")


class TestCircuitBreaker:
    def test_circuit_opens_after_consecutive_failures(self):
        fetcher = DummyFetcher(max_failures=3, circuit_timeout=60)
        for _ in range(3):
            fetcher._record_failure()
        assert fetcher._circuit_open() is True

    def test_circuit_closed_initially(self):
        fetcher = DummyFetcher()
        assert fetcher._circuit_open() is False

    def test_success_resets_failures(self):
        fetcher = DummyFetcher(max_failures=3)
        fetcher._record_failure()
        fetcher._record_failure()
        fetcher._record_success()
        assert fetcher._consecutive_failures == 0


import json
from pathlib import Path
from fetchers.odds_fetcher import OddsFetcher, CreditBudget, parse_odds_response

FIXTURES = Path(__file__).parent / "fixtures"


class TestCreditBudget:
    def test_has_credits(self, temp_db):
        budget = CreditBudget(monthly_limit=500)
        assert budget.can_spend(1) is True

    def test_over_budget(self, temp_db):
        budget = CreditBudget(monthly_limit=10)
        budget.spend(10)
        assert budget.can_spend(1) is False

    def test_daily_tracking(self, temp_db):
        budget = CreditBudget(monthly_limit=500)
        budget.spend(5)
        assert budget.spent_today == 5


class TestParseOdds:
    def test_parse_fixture(self):
        data = json.loads((FIXTURES / "odds_response.json").read_text())
        games = parse_odds_response(data, sport="nba", league="nba")
        assert len(games) == 1
        game = games[0]
        assert game["home_team"] == "Los Angeles Lakers"
        assert game["away_team"] == "Boston Celtics"
        assert len(game["odds"]) == 4  # 2 books × 2 outcomes
        dk_home = [o for o in game["odds"] if o["bookmaker"] == "draftkings" and o["selection"] == "home"][0]
        assert dk_home["price"] == 150
