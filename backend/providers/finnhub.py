import os
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://finnhub.io/api/v1"
API_KEY = os.getenv("FINNHUB_API_KEY")

if not API_KEY:
    raise RuntimeError("FINNHUB_API_KEY not set in backend/.env")

def fetch_quote(ticker: str) -> dict:
    """
    Returns a normalized dict:
    price/open/high/low/prev_close/quote_ts
    """
    ticker = ticker.upper().strip()

    url = f"{BASE_URL}/quote"
    params = {"symbol": ticker, "token": API_KEY}

    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()

    data = r.json()
    # Finnhub quote usually: c,h,l,o,pc,t
    # t is unix seconds; sometimes 0 if unavailable
    t = data.get("t", 0)
    quote_ts = datetime.fromtimestamp(t, tz=timezone.utc) if t else datetime.now(timezone.utc)

    return {
        "price": float(data["c"]),
        "open": float(data["o"]) if data.get("o") is not None else None,
        "high": float(data["h"]) if data.get("h") is not None else None,
        "low": float(data["l"]) if data.get("l") is not None else None,
        "prev_close": float(data["pc"]) if data.get("pc") is not None else None,
        "quote_ts": quote_ts,
    }

def fetch_profile(ticker: str) -> dict:
    """
    Returns normalized profile fields for Symbol table.
    Finnhub endpoint name is /stock/profile2.
    """
    ticker = ticker.upper().strip()

    url = f"{BASE_URL}/stock/profile2"
    params = {"symbol": ticker, "token": API_KEY}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    p = r.json() or {}

    return {
        "name": (p.get("name") or "").strip() or None,
        "exchange": (p.get("exchange") or "").strip() or None,
        "country": (p.get("country") or "").strip() or None,
        "currency": (p.get("currency") or "").strip() or None,
        "mic": (p.get("mic") or "").strip() or None,
        "type": (p.get("type") or "").strip() or None,  # keep this as "type"
    }
