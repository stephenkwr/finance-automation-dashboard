from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, ForeignKey, Float
from db import base

class Symbol(base):
    __tablename__ = "symbols"
    
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(16), unique=True, index=True, nullable=False)
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
    