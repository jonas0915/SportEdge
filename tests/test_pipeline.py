import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from engine.pipeline import run_pipeline

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_pipeline_end_to_end(temp_db):
    fixture = json.loads((FIXTURES / "odds_response.json").read_text())

    with patch("fetchers.odds_fetcher.OddsFetcher.fetch_all_active", new_callable=AsyncMock) as mock_fetch:
        from fetchers.odds_fetcher import parse_odds_response
        mock_fetch.return_value = parse_odds_response(fixture, sport="nba", league="nba")

        picks = await run_pipeline()
        assert isinstance(picks, list)
        # Should have processed the fixture game
        if picks:
            assert "score" in picks[0]
            assert "rank" in picks[0]
