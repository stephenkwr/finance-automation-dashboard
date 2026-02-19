# backend/providers/massive.py
import os
import time
import requests
from datetime import date, datetime, timezone
from typing import List, Dict, Any, Optional

from providers.rate_limit import polygon_limiter  # keep your existing limiter file as-is


# Massive is Polygon-compatible in your project, but the key name is MASSIVE_API_KEY.
MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "").strip()

# If you ever change provider base, you can override this:
MASSIVE_BASE_URL = os.getenv("MASSIVE_BASE_URL", "https://api.polygon.io").rstrip("/")

# Aggregate endpoint max limit per request
MASSIVE_AGG_LIMIT = 50_000

# Provider constraints
UNIX_EPOCH = date(1970, 1, 1)


class ProviderError(RuntimeError):
    pass


def _require_key():
    if not MASSIVE_API_KEY:
        raise ProviderError("MASSIVE_API_KEY is missing. Set it in your environment (.env).")


def _agg_url(
    ticker: str,
    multiplier: int,
    timespan: str,
    date_from: str,
    date_to: str,
) -> str:
    # Polygon-compatible agg endpoint
    return (
        f"{MASSIVE_BASE_URL}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{date_from}/{date_to}"
        f"?adjusted=true&sort=asc&limit={MASSIVE_AGG_LIMIT}&apiKey={MASSIVE_API_KEY}"
    )


def fetch_bars(
    ticker: str,
    date_from: str,
    date_to: str,
    multiplier: int = 1,
    duration: str = "day",
    max_retries: int = 3,
    retry_backoff_s: float = 0.8,
) -> List[Dict[str, Any]]:
    """
    Fetch OHLCV bars from Massive (Polygon-compatible aggregates).

    Returns list of dicts:
      { ts: datetime(UTC), open, high, low, close, volume }

    Raises ProviderError on provider/auth/plan errors.
    """
    _require_key()

    t = (ticker or "").upper().strip()
    if not t:
        return []

    # Parse and clamp to avoid provider errors / pointless calls
    try:
        df = date.fromisoformat(date_from)
        dt_ = date.fromisoformat(date_to)
    except ValueError:
        raise ProviderError("date_from/date_to must be YYYY-MM-DD")

    if df > dt_:
        return []

    # Massive/Polygon rejects dates before Unix epoch
    if dt_ < UNIX_EPOCH:
        return []
    if df < UNIX_EPOCH:
        df = UNIX_EPOCH
        date_from = df.isoformat()

    url = _agg_url(t, multiplier, duration, date_from, date_to)

    last_exc: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            # Respect your 5 calls/min limiter
            polygon_limiter.wait()

            resp = requests.get(url, timeout=25)

            # Auth/plan errors
            if resp.status_code in (401, 403):
                raise ProviderError(f"Provider access error {resp.status_code}: {resp.text[:400]}")

            # Bad request (often from invalid date ranges)
            if resp.status_code == 400:
                raise ProviderError(f"Provider 400 Bad Request: {resp.text[:600]}")

            resp.raise_for_status()

            payload = resp.json() or {}
            results = payload.get("results") or []

            out: List[Dict[str, Any]] = []
            for r in results:
                ts = datetime.fromtimestamp((r["t"] / 1000.0), tz=timezone.utc)
                out.append(
                    {
                        "ts": ts,
                        "open": float(r.get("o", 0.0)),
                        "high": float(r.get("h", 0.0)),
                        "low": float(r.get("l", 0.0)),
                        "close": float(r.get("c", 0.0)),
                        "volume": (float(r["v"]) if r.get("v") is not None else None),
                    }
                )

            return out

        except ProviderError:
            # Don't retry auth/plan/400 – it's not transient
            raise
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(retry_backoff_s * attempt)
                continue
            raise ProviderError(f"Provider fetch failed: {e}") from e

    if last_exc:
        raise ProviderError(f"Provider fetch failed: {last_exc}")
    return []
