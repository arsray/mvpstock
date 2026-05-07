"""Build examples/sample_closes_wide.csv (synthetic) for offline pipeline tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pathlib import Path

rng = np.random.default_rng(42)
root = Path(__file__).resolve().parents[1]
days = pd.bdate_range("2025-01-02", periods=140, freq="B")
tickers = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "NVDA",
    "JPM",
    "V",
    "UNH",
    "JNJ",
    "XOM",
    "COST",
    "HD",
    "PG",
    "KO",
    "PEP",
    "DIS",
    "NFLX",
    "TSLA",
    "AMD",
    "SPY",
]
prices: dict[str, np.ndarray] = {}
for sym in tickers:
    r = rng.normal(0, 0.012, size=len(days))
    p = 100.0 * np.exp(np.cumsum(r))
    prices[sym] = np.round(p, 4)
df = pd.DataFrame(prices, index=days)
df.index.name = "Date"
out = root / "examples" / "sample_closes_wide.csv"
out.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(out, date_format="%Y-%m-%d")
print("wrote", out, df.shape)
