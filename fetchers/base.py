import time
import logging
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("fetchers")


class CircuitOpenError(Exception):
    pass


class BaseFetcher:
    def __init__(self, max_failures: int = 5, circuit_timeout: int = 1800):
        self._consecutive_failures = 0
        self._max_failures = max_failures
        self._circuit_timeout = circuit_timeout
        self._circuit_opened_at: float | None = None
        self._client = httpx.AsyncClient(timeout=10.0)

    def _circuit_open(self) -> bool:
        if self._consecutive_failures < self._max_failures:
            return False
        if self._circuit_opened_at is None:
            return False
        elapsed = time.time() - self._circuit_opened_at
        if elapsed > self._circuit_timeout:
            logger.info("Circuit breaker half-open, allowing retry")
            self._consecutive_failures = 0
            self._circuit_opened_at = None
            return False
        return True

    def _record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._max_failures:
            self._circuit_opened_at = time.time()
            logger.warning(
                f"Circuit breaker OPEN after {self._consecutive_failures} failures"
            )

    def _record_success(self):
        self._consecutive_failures = 0
        self._circuit_opened_at = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=4))
    async def _request(self, method: str, url: str, **kwargs) -> dict:
        if self._circuit_open():
            raise CircuitOpenError(f"Circuit open for {url}")
        try:
            response = await self._client.request(method, url, **kwargs)
            response.raise_for_status()
            self._record_success()
            return response.json()
        except Exception as e:
            self._record_failure()
            logger.warning(f"Request failed: {url} — {e}")
            raise

    async def close(self):
        await self._client.aclose()
