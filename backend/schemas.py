from pydantic import BaseModel
from datetime import datetime

class SymbolCreate(BaseModel):
    ticker : str
    
class SymbolOut(BaseModel):
    id : int
    ticker : str
    active : bool
    
    class Config:
        from_attributes = True
        

class QuoteOut(BaseModel):
    id : int
    symbol_id : int
    price : float
    open : float | None = None
    high : float | None = None
    low : float | None = None
    prev_close : float | None = None
    quote_ts : datetime
    fetched_at : datetime
    provider : str
    
    class Config:
        from_attributes = True