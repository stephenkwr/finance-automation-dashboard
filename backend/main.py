# backend/main.py
import os
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from datetime import date, timedelta, datetime, timezone, time as dtime
from typing import Optional, List, Tuple, Dict, Any

from db import get_db
from models import Symbol, Quote, Bar, NewsArticle
from schemas import QuoteOut, SymbolCreate, SymbolOut

from providers.finnhub import fetch_quote, fetch_profile
from providers.massive import fetch_bars, ProviderError
from providers.gdelt import get_headlines_for_day_bigquery

app = FastAPI()

# -------------------------
# Provider constraints / app policy
# -------------------------

# If your provider is delayed, don’t request newer than today - delay.
PROVIDER_DELAY_DAYS = 3

# Your "MAX" is 2 years on free plan
MAX_HISTORY_DAYS = 365 * 2

# limit response size (DB -> frontend)
MAX_CLOSE_POINTS = 20000

# -------------------------
# Helpers
# -------------------------
def json_safe(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(x) for x in obj]
    return obj


def clamp_end_for_provider(d: date) -> date:
    latest_allowed = date.today() - timedelta(days=PROVIDER_DELAY_DAYS)
    return min(d, latest_allowed)


def clamp_start_for_plan(start_d: date, end_d: date) -> date:
    # enforce max history window
    min_allowed = end_d - timedelta(days=MAX_HISTORY_DAYS)
    return max(start_d, min_allowed)


def parse_iso_date(s: Optional[str], field: str) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{field} must be YYYY-MM-DD")


def get_or_create_symbol(db: Session, ticker: str) -> Symbol:
    t = (ticker or "").upper().strip()
    if not t:
        raise ValueError("ticker is empty")

    sym = db.query(Symbol).filter(Symbol.ticker == t).one_or_none()
    if sym:
        return sym

    sym = Symbol(ticker=t)
    db.add(sym)
    db.commit()
    db.refresh(sym)
    return sym


def ensure_symbol_metadata(db: Session, sym: Symbol) -> Symbol:
    if sym.name:
        return sym

    meta = fetch_profile(sym.ticker)

    if meta.get("name"):
        sym.name = meta["name"]
    if meta.get("exchange"):
        sym.exchange = meta["exchange"]
    if meta.get("country"):
        sym.country = meta["country"]
    if meta.get("currency"):
        sym.currency = meta["currency"]
    if meta.get("mic"):
        sym.mic = meta["mic"]
    if meta.get("type"):
        sym.type = meta["type"]

    db.commit()
    db.refresh(sym)
    return sym


def dedupe_headlines(items: List[Dict[str, Any]], limit: int = 25) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for h in items:
        title = (h.get("title") or "").strip()
        url = (h.get("url") or "").strip()
        key = (url.lower() if url else title.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(h)
        if len(out) >= limit:
            break
    return out


# -------------------------
# CORS (local + deployed)
# -------------------------
# Set FRONTEND_ORIGINS like:
#   http://localhost:5173,https://your-frontend.vercel.app
origins_env = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173")
allow_origins = [o.strip() for o in origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Basic endpoints
# -------------------------
@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/ping")
def ping():
    return {"message": "pong"}


# -------------------------
# Symbols
# -------------------------
@app.post("/symbols", response_model=SymbolOut)
def add_symbol(payload: SymbolCreate, db: Session = Depends(get_db)):
    ticker = payload.ticker.strip().upper()
    sym = Symbol(ticker=ticker)
    db.add(sym)
    db.commit()
    db.refresh(sym)
    return sym


@app.get("/symbols", response_model=list[SymbolOut])
def list_symbols(db: Session = Depends(get_db)):
    return db.query(Symbol).order_by(Symbol.ticker.asc()).all()


# -------------------------
# Quotes
# -------------------------
@app.post("/ingest/quote/{ticker}", response_model=QuoteOut)
def ingest_quote(ticker: str, db: Session = Depends(get_db)):
    ticker = ticker.upper().strip()

    sym = db.query(Symbol).filter(Symbol.ticker == ticker).first()
    if not sym:
        raise HTTPException(status_code=404, detail="Ticker not found. Add it via POST /symbols first.")

    q = fetch_quote(ticker)

    row = Quote(
        symbol_id=sym.id,
        price=q["price"],
        open=q["open"],
        high=q["high"],
        low=q["low"],
        prev_close=q["prev_close"],
        quote_ts=q["quote_ts"],
        provider="finnhub",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/quotes/latest/{ticker}", response_model=QuoteOut)
def latest_quote(ticker: str, db: Session = Depends(get_db)):
    ticker = ticker.upper().strip()

    sym = db.query(Symbol).filter(Symbol.ticker == ticker).first()
    if not sym:
        raise HTTPException(status_code=404, detail="Ticker not found.")

    row = (
        db.query(Quote)
        .filter(Quote.symbol_id == sym.id)
        .order_by(Quote.quote_ts.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No quotes stored yet. Call POST /ingest/quote/{ticker}.")
    return row


# -------------------------
# Prices
# -------------------------
@app.get("/prices/close")
def get_close_series(
    ticker: str,
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(10000, ge=10, le=MAX_CLOSE_POINTS),
    db: Session = Depends(get_db),
):
    t = ticker.upper().strip()

    sym = db.query(Symbol).filter(Symbol.ticker == t).first()
    if not sym:
        raise HTTPException(status_code=404, detail="Ticker not found.")

    start_date = parse_iso_date(start, "start")
    end_date = parse_iso_date(end, "end")

    q = db.query(Bar.ts, Bar.close).filter(
        Bar.symbol_id == sym.id,
        Bar.timeframe == "1d",
    )

    if start_date:
        q = q.filter(Bar.ts >= datetime.combine(start_date, dtime.min, tzinfo=timezone.utc))
    if end_date:
        q = q.filter(Bar.ts <= datetime.combine(end_date, dtime.max, tzinfo=timezone.utc))

    rows = q.order_by(Bar.ts.asc()).limit(limit).all()
    return [{"date": ts.date().isoformat(), "close": close} for (ts, close) in rows]


@app.get("/prices/range")
def prices_range(ticker: str, db: Session = Depends(get_db)):
    t = ticker.upper().strip()
    sym = db.query(Symbol).filter(Symbol.ticker == t).first()
    if not sym:
        raise HTTPException(status_code=404, detail="Ticker not found")

    row_min = (
        db.query(Bar.ts)
        .filter(Bar.symbol_id == sym.id, Bar.timeframe == "1d")
        .order_by(Bar.ts.asc())
        .first()
    )
    row_max = (
        db.query(Bar.ts)
        .filter(Bar.symbol_id == sym.id, Bar.timeframe == "1d")
        .order_by(Bar.ts.desc())
        .first()
    )
    count = (
        db.query(Bar.id)
        .filter(Bar.symbol_id == sym.id, Bar.timeframe == "1d")
        .count()
    )

    if not row_min or not row_max:
        return {"ticker": t, "min": None, "max": None, "count": 0}

    return {
        "ticker": t,
        "min": row_min[0].date().isoformat(),
        "max": row_max[0].date().isoformat(),
        "count": count,
    }


# -------------------------
# News (BigQuery + Postgres cache)
# -------------------------
@app.get("/news")
def news_for_day(
    ticker: str = Query(..., min_length=1),
    day: str = Query(...),
    limit: int = Query(25, ge=5, le=50),
    db: Session = Depends(get_db),
):
    day_date = parse_iso_date(day, "day")
    assert day_date is not None

    sym = get_or_create_symbol(db, ticker)
    sym = ensure_symbol_metadata(db, sym)

    cached = (
        db.query(NewsArticle)
        .filter(NewsArticle.symbol_id == sym.id, NewsArticle.day == day_date)
        .order_by(NewsArticle.published_at.desc().nullslast(), NewsArticle.created_at.desc())
        .limit(limit * 3)  # pull more then dedupe
        .all()
    )

    if cached:
        raw = [
            {
                "title": a.title,
                "source": a.domain,
                "url": a.url,
                "published_at": a.published_at.isoformat() if a.published_at else None,
            }
            for a in cached
        ]
        headlines = dedupe_headlines(raw, limit=limit)
        return {"ticker": sym.ticker, "date": day_date.isoformat(), "headlines": headlines}

    try:
        headlines = get_headlines_for_day_bigquery(
            ticker=sym.ticker,
            company_name=sym.name,
            day=day_date,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BigQuery error: {e}")

    norm = []
    for h in (headlines or []):
        norm.append(
            {
                "title": (h.get("title") or "").strip(),
                "source": (h.get("domain") or "").strip(),
                "url": (h.get("url") or "").strip(),
                "published_at": h.get("published_at"),
            }
        )

    norm = dedupe_headlines(norm, limit=limit)

    to_insert = []
    for h in norm:
        a = NewsArticle(
            symbol_id=sym.id,
            day=day_date,
            title=h.get("title") or "",
            url=h.get("url") or "",
            domain=h.get("source") or "",
            published_at=h.get("published_at"),
            provider="gdelt_bigquery",
            raw=json_safe(h),
        )
        to_insert.append(a)

    db.add_all(to_insert)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()

    return {"ticker": sym.ticker, "date": day_date.isoformat(), "headlines": norm}


# -------------------------
# Confirm endpoint (cache-safe; clamps to 2y; avoids wasted calls)
# -------------------------
@app.post("/symbols/confirm")
def confirm_symbol(
    ticker: str = Query(..., min_length=1),
    start: Optional[str] = Query(None, description="YYYY-MM-DD (optional)"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD (optional)"),
    db: Session = Depends(get_db),
):
    t = ticker.upper().strip()
    sym = get_or_create_symbol(db, t)
    sym = ensure_symbol_metadata(db, sym)

    desired_end = parse_iso_date(end, "end") or date.today()
    desired_end = clamp_end_for_provider(desired_end)

    desired_start = parse_iso_date(start, "start")
    if desired_start is None:
        desired_start = desired_end - timedelta(days=365)

    desired_start = clamp_start_for_plan(desired_start, desired_end)

    if desired_start > desired_end:
        raise HTTPException(status_code=400, detail="start must be <= end")

    # cheap quote ingest
    try:
        q = fetch_quote(t)
        db.add(
            Quote(
                symbol_id=sym.id,
                price=q["price"],
                open=q["open"],
                high=q["high"],
                low=q["low"],
                prev_close=q["prev_close"],
                quote_ts=q["quote_ts"],
                provider="finnhub",
            )
        )
        db.commit()
    except Exception:
        db.rollback()

    oldest = (
        db.query(Bar.ts)
        .filter(Bar.symbol_id == sym.id, Bar.timeframe == "1d")
        .order_by(Bar.ts.asc())
        .first()
    )
    latest = (
        db.query(Bar.ts)
        .filter(Bar.symbol_id == sym.id, Bar.timeframe == "1d")
        .order_by(Bar.ts.desc())
        .first()
    )

    have_start = oldest[0].date() if oldest else None
    have_end = latest[0].date() if latest else None

    missing_ranges: List[Tuple[date, date]] = []
    if have_start is None or have_end is None:
        missing_ranges.append((desired_start, desired_end))
    else:
        if desired_start < have_start:
            missing_ranges.append((desired_start, have_start - timedelta(days=1)))
        if desired_end > have_end:
            missing_ranges.append((have_end + timedelta(days=1), desired_end))

    missing_ranges = [(a, b) for (a, b) in missing_ranges if a <= b]

    bars_fetched = 0
    bars_inserted = 0

    for (rng_start, rng_end) in missing_ranges:
        try:
            rows = fetch_bars(
                ticker=t,
                date_from=rng_start.isoformat(),
                date_to=rng_end.isoformat(),
                multiplier=1,
                duration="day",
            )
        except ProviderError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Provider error: {e}")

        bars_fetched += len(rows)

        batch = []
        for r in rows:
            batch.append(
                Bar(
                    symbol_id=sym.id,
                    timeframe="1d",
                    ts=r["ts"],
                    open=r["open"],
                    high=r["high"],
                    low=r["low"],
                    close=r["close"],
                    volume=r.get("volume"),
                    provider="massive",
                )
            )

        db.add_all(batch)
        try:
            db.commit()
            bars_inserted += len(batch)
        except IntegrityError:
            db.rollback()
            for b in batch:
                db.add(b)
                try:
                    db.commit()
                    bars_inserted += 1
                except IntegrityError:
                    db.rollback()

    row_min = (
        db.query(Bar.ts)
        .filter(Bar.symbol_id == sym.id, Bar.timeframe == "1d")
        .order_by(Bar.ts.asc())
        .first()
    )
    row_max = (
        db.query(Bar.ts)
        .filter(Bar.symbol_id == sym.id, Bar.timeframe == "1d")
        .order_by(Bar.ts.desc())
        .first()
    )

    return {
        "ticker": sym.ticker,
        "name": sym.name,
        "desired_range": {"start": desired_start.isoformat(), "end": desired_end.isoformat()},
        "missing_ranges": [{"start": a.isoformat(), "end": b.isoformat()} for a, b in missing_ranges],
        "bars_fetched": bars_fetched,
        "bars_inserted": bars_inserted,
        "have_range_after": {
            "start": row_min[0].date().isoformat() if row_min else None,
            "end": row_max[0].date().isoformat() if row_max else None,
        },
    }
