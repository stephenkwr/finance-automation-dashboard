from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import Session

from db import get_db
from models import Symbol
from schemas import QuoteOut, SymbolCreate, SymbolOut

from providers.finnhub import fetch_quote

app = FastAPI()

# allow your frontend (5173) to call your backend (8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/ping")
def ping():
    return {"message": "pong"}

@app.post("/symbols", response_model=SymbolOut)
def add_symbol(payload: SymbolCreate, db : Session = Depends(get_db)):
    ticker = payload.ticker.strip().upper()
    sym = Symbol(ticker=ticker)
    db.add(sym)
    db.commit()
    db.refresh(sym)
    return sym

@app.get("/symbols", response_model=list[SymbolOut])
def list_symbols(db : Session = Depends(get_db)):
    return db.query(Symbol).order_by(Symbol.ticker.asc()).all()

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
