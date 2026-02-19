"""
Earshot API Client for Frank Bot

HTTP client for querying earshot's transcript search, LLM-powered query,
and date-parsing endpoints.  Follows the same patterns as claudia_client.py.

Earshot API docs (from ~/dev/earshot/api/src/main.py):
- GET  /transcripts                         # List/search transcripts
- GET  /transcripts/{transcript_id}         # Get transcript by ID
- POST /transcript/transform                # LLM-transform a single transcript
- POST /transcript/query                    # Create async LLM query
- GET  /transcript/query/{id}/first         # First result (resets cursor)
- GET  /transcript/query/{id}/next          # Next result
- GET  /transcript/query/{id}/results       # All results (blocks until done)
- GET  /transcript/count                    # Count transcripts in date range
- POST /transcript/date-parse               # Natural-language date parsing
- POST /worker/trigger                      # Trigger worker run
- GET  /worker/status                       # Worker run status
- GET  /dashboard/grid                      # Dashboard grid data
- GET  /diagnostics/summary                 # Transcript count + git commit
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from config import get_settings
from services.stats import stats

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0


class EarshotAPIError(RuntimeError):
    """Raised when the Earshot API returns an error response."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class EarshotClient:
    """HTTP client for the Earshot transcript API."""

    def __init__(self) -> None:
        settings = get_settings()
        self.api_url = settings.earshot_api_url
        self.api_key = settings.earshot_api_key

        if not self.api_url:
            raise ValueError(
                "Earshot is not configured. "
                "Set Vault secret "
                "`secret/frank-bot/earshot` (api_url, api_key)."
            )
        if not self.api_key:
            raise ValueError(
                "Earshot is not configured. "
                "Set Vault secret `secret/frank-bot/earshot` (api_key)."
            )

        self.session = requests.Session()
        self.session.headers["X-API-Key"] = self.api_key
        self.session.headers["Content-Type"] = "application/json"

    # ------------------------------------------------------------------ #
    # Core request helpers
    # ------------------------------------------------------------------ #

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> tuple[dict[str, Any] | list[Any], int]:
        url = f"{self.api_url.rstrip('/')}/{path.lstrip('/')}"

        logger.info("EARSHOT_REQUEST: %s %s params=%s", method, path, params)

        last_error: Exception | None = None
        earshot_stats = stats.get_service_stats("earshot")

        for attempt in range(MAX_RETRIES):
            start_time = time.time()
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    timeout=timeout,
                )
                elapsed_ms = (time.time() - start_time) * 1000
                response_bytes = len(response.content)

                logger.info(
                    "EARSHOT_RESPONSE: %s %s status=%d elapsed=%.0fms",
                    method, path, response.status_code, elapsed_ms,
                )

                if response.status_code == 204:
                    earshot_stats.record_request(
                        elapsed_ms, success=True, bytes_received=0,
                    )
                    return {}, 204

                try:
                    data = response.json() if response.content else {}
                except ValueError as exc:
                    logger.error("EARSHOT_ERROR: %s invalid JSON", path)
                    earshot_stats.record_request(
                        elapsed_ms, success=False, error="Invalid JSON",
                    )
                    raise EarshotAPIError("Earshot API: invalid JSON") from exc

                if response.status_code >= 400:
                    error_detail = "Unknown error"
                    if isinstance(data, dict):
                        detail = data.get("detail")
                    if isinstance(detail, dict):
                        error_detail = detail.get("message", "")
                    else:
                        error_detail = str(
                            detail or f"HTTP {response.status_code}"
                        )

                    if response.status_code in (429, 500, 502, 503, 504):
                        if attempt < MAX_RETRIES - 1:
                            sleep_time = RETRY_BACKOFF_BASE * (2 ** attempt)
                            logger.info("EARSHOT_RETRY: %.1fs", sleep_time)
                            time.sleep(sleep_time)
                            continue

                    earshot_stats.record_request(
                        elapsed_ms,
                        success=False,
                        error=f"{response.status_code}: {error_detail}",
                    )
                    raise EarshotAPIError(
                        f"Earshot ({response.status_code}): {error_detail}",
                        status_code=response.status_code,
                    )

                earshot_stats.record_request(
                    elapsed_ms, success=True, bytes_received=response_bytes,
                )
                return data, response.status_code

            except requests.RequestException as exc:
                elapsed_ms = (time.time() - start_time) * 1000
                last_error = exc
                logger.warning("EARSHOT_NETWORK_ERROR: %s error=%s", path, exc)

                if attempt < MAX_RETRIES - 1:
                    sleep_time = RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.info("EARSHOT_RETRY: sleep %.1fs", sleep_time)
                    time.sleep(sleep_time)
                    continue

                earshot_stats.record_request(
                    elapsed_ms, success=False, error=f"Network: {exc}",
                )
                raise EarshotAPIError(f"Network error: {exc}") from exc

        msg = f"Earshot API failed after {MAX_RETRIES} attempts: {last_error}"
        raise EarshotAPIError(msg)

    def _get(
        self, path: str, params: dict[str, Any] | None = None, **kw: Any,
    ) -> dict[str, Any] | list[Any]:
        data, _ = self._request("GET", path, params=params, **kw)
        return data

    def _post(
        self, path: str, json_data: dict[str, Any] | None = None, **kw: Any,
    ) -> tuple[dict[str, Any] | list[Any], int]:
        return self._request("POST", path, json_data=json_data, **kw)

    # ------------------------------------------------------------------ #
    # Transcript retrieval
    # ------------------------------------------------------------------ #

    def list_transcripts(
        self,
        *,
        q: str | None = None,
        source: str | None = None,
        location: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search / list transcripts with optional filters."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if q:
            params["q"] = q
        if source:
            params["source"] = source
        if location:
            params["location"] = location
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        data = self._get("/transcripts", params=params)
        return data if isinstance(data, list) else []

    def get_transcript(self, transcript_id: int) -> dict[str, Any]:
        """Get a single transcript by ID."""
        data = self._get(f"/transcripts/{transcript_id}")
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data

    # ------------------------------------------------------------------ #
    # LLM-powered query pipeline
    # ------------------------------------------------------------------ #

    def query_create(
        self,
        *,
        earliest: str,
        latest: str,
        prompt: str,
        terms: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create an async LLM query across transcripts in a date range.

        Returns ``{queryId, status}`` immediately; poll results with
        ``query_results()`` or page with ``query_first()`` / ``query_next()``.
        """
        payload: dict[str, Any] = {
            "earliest": earliest,
            "latest": latest,
            "transformationPrompt": prompt,
        }
        if terms:
            payload["terms"] = terms

        data, _ = self._post("/transcript/query", json_data=payload)
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data

    def query_results(
        self, query_id: str, *, raw: bool = False,
    ) -> dict[str, Any]:
        """Block until the query completes and return all results."""
        params: dict[str, Any] = {}
        if raw:
            params["raw"] = "true"
        data = self._get(
            f"/transcript/query/{query_id}/results",
            params=params or None,
            timeout=120,
        )
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data

    def query_first(
        self, query_id: str, *, raw: bool = False,
    ) -> dict[str, Any]:
        """Get the first result and reset the cursor."""
        params: dict[str, Any] = {}
        if raw:
            params["raw"] = "true"
        data = self._get(
            f"/transcript/query/{query_id}/first", params=params or None,
        )
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data

    def query_next(
        self, query_id: str, *, raw: bool = False,
    ) -> dict[str, Any]:
        """Advance cursor and get the next result."""
        params: dict[str, Any] = {}
        if raw:
            params["raw"] = "true"
        data = self._get(
            f"/transcript/query/{query_id}/next", params=params or None,
        )
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data

    # ------------------------------------------------------------------ #
    # Single-transcript transform
    # ------------------------------------------------------------------ #

    def transform(
        self, transcript_file: str, prompt: str,
    ) -> dict[str, Any]:
        """Transform a single transcript via LLM."""
        data, _ = self._post(
            "/transcript/transform",
            json_data={
                "transcriptFile": transcript_file,
                "transformationPrompt": prompt,
            },
        )
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data

    # ------------------------------------------------------------------ #
    # Date utilities
    # ------------------------------------------------------------------ #

    def count(self, earliest: str, latest: str) -> dict[str, Any]:
        """Count transcripts in a date range (YYYY-MM-DD)."""
        data = self._get(
            "/transcript/count",
            params={"earliest": earliest, "latest": latest},
        )
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data

    def date_parse(self, text: str) -> dict[str, Any]:
        """Parse natural-language date text into a date range."""
        data, _ = self._post(
            "/transcript/date-parse", json_data={"text": text},
        )
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data

    # ------------------------------------------------------------------ #
    # Worker
    # ------------------------------------------------------------------ #

    def worker_trigger(self, force: bool = False) -> dict[str, Any]:
        """Trigger a worker run (batch evaluation of standard queries)."""
        params: dict[str, Any] = {}
        if force:
            params["force"] = "true"
        data, _ = self._post("/worker/trigger")
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data

    def worker_status(self) -> dict[str, Any]:
        """Get latest worker run status."""
        data = self._get("/worker/status")
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data

    # ------------------------------------------------------------------ #
    # Dashboard / diagnostics
    # ------------------------------------------------------------------ #

    def dashboard_grid(
        self, page: int = 1, limit: int = 50,
    ) -> dict[str, Any]:
        """Get the merged transcript + standard-queries dashboard grid."""
        data = self._get(
            "/dashboard/grid", params={"page": page, "limit": limit},
        )
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data

    def diagnostics(self) -> dict[str, Any]:
        """Get earshot diagnostics summary (transcript count, git commit)."""
        data = self._get("/diagnostics/summary")
        if not isinstance(data, dict):
            raise EarshotAPIError("Unexpected response format")
        return data


__all__ = [
    "EarshotClient",
    "EarshotAPIError",
]
