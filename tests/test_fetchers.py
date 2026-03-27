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
