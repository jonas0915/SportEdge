import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fetchers.stats_fetcher import StatsFetcher, parse_espn_standings

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseESPNStandings:
    def test_parse_nba_standings(self):
        data = json.loads((FIXTURES / "espn_nba_standings.json").read_text())
        teams = parse_espn_standings(data, sport="nba")
        assert len(teams) >= 1
        bos = [t for t in teams if t["team_name"] == "Boston Celtics"][0]
        assert bos["wins"] == 50
        assert bos["losses"] == 15
        assert bos["points_for"] == 118.5
        assert bos["home_wins"] == 30
        assert bos["home_losses"] == 3
        assert bos["wins_l10"] == 8


class TestStatsFetcher:
    @pytest.mark.asyncio
    async def test_fetch_sport_stats(self):
        fixture = json.loads((FIXTURES / "espn_nba_standings.json").read_text())
        fetcher = StatsFetcher()
        with patch.object(fetcher, "_request", new_callable=AsyncMock) as mock:
            mock.return_value = fixture
            teams = await fetcher.fetch_sport_stats("nba")
            assert len(teams) >= 1
            assert teams[0]["sport"] == "nba"
        await fetcher.close()
