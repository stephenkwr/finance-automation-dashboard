from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, ForeignKey, Float, BigInteger, UniqueConstraint, Date
from sqlalchemy.dialects.postgresql import JSONB
from db import base

class Symbol(base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(16), unique=True, index=True, nullable=False)

    # NEW
    name = Column(String(128), nullable=True)          # "Apple Inc"
    exchange = Column(String(32), nullable=True)       # "NASDAQ NMS"
    country = Column(String(8), nullable=True)         # "US"
    currency = Column(String(8), nullable=True)        # "USD"
    mic = Column(String(16), nullable=True)            # "XNAS"
    type = Column(String(16), nullable=True)           # "Common Stock" / "ETF" etc.

    active = Column(Boolean, nullable=False, server_default="true")
    create_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
class Quote(base):
    __tablename__ = "quotes"
    
    id = Column(Integer, primary_key=True, index=True)
    
    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), index=True, nullable=False)
    
    price = Column(Float, nullable=False)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    prev_close = Column(Float, nullable=True)
    
    quote_ts = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    provider = Column(String(16), nullable=False, server_default='finnhub')

class Bar(base):
    __tablename__ = "bars"

    id = Column(Integer, primary_key=True, index=True)

    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), index=True, nullable=False)

    timeframe = Column(String(8), index=True, nullable=False)   # "1d", "5m"
    ts = Column(DateTime(timezone=True), index=True, nullable=False)

    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=True)

    provider = Column(String(16), nullable=False, server_default="massive")
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol_id", "timeframe", "ts", name="uq_bars_symbol_tf_ts"),
    )

class NewsArticle(base):
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True)
    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), index=True, nullable=False)

    day = Column(Date, index=True, nullable=False)  # day you queried
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    domain = Column(String, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)

    provider = Column(String(32), nullable=False, server_default="gdelt_bigquery")
    raw = Column(JSONB, nullable=True)  # optional “extra fields”

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol_id", "url", name="uq_news_symbol_url"),
    )