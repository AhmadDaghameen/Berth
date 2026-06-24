"""FinanceIQ API — demo FastAPI backend."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FinanceIQ API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.test",
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "healthy", "version": os.environ.get("APP_VERSION", "dev")}


@app.get("/api/securities")
def list_securities():
    return {"data": [
        {"ticker": "AAPL", "name": "Apple Inc.", "price": 189.30},
        {"ticker": "MSFT", "name": "Microsoft Corp.", "price": 415.20},
        {"ticker": "GOOGL", "name": "Alphabet Inc.", "price": 175.90},
    ]}
