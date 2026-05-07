from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError


def _closes_from_download(raw: pd.DataFrame, syms: list[str]) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    if len(syms) == 1:
        sym = syms[0]
        if "Close" not in raw.columns:
            return pd.DataFrame()
        s = raw["Close"].copy()
        s.name = sym
        s.index = pd.to_datetime(s.index).tz_localize(None)
        return pd.DataFrame({sym: s}).sort_index()
    close = raw.xs("Close", axis=1, level=1)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.sort_index()


def load_closes_csv(path: Path) -> pd.DataFrame:
    """
    Wide CSV: first column `Date` (or index), then one column per ticker (Close).
    """
    p = Path(path)
    raw = pd.read_csv(p)
    if "Date" in raw.columns:
        raw = raw.set_index("Date")
    raw.index = pd.to_datetime(raw.index).tz_localize(None)
    raw = raw.sort_index()
    for c in raw.columns:
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    return raw


def fetch_closes(
    tickers: Iterable[str],
    period: str = "1y",
    interval: str = "1d",
    pause_sec: float = 0.55,
) -> pd.DataFrame:
    """
    Columns = tickers, index = date (naive datetime).
    Tries one batch download; on failure or empty result, falls back to sequential
    requests (more reliable when Yahoo rate-limits batch calls).
    """
    syms = list(dict.fromkeys(tickers))
    if not syms:
        return pd.DataFrame()

    try:
        raw = yf.download(
            tickers=" ".join(syms),
            period=period,
            interval=interval,
            auto_adjust=False,
            group_by="ticker",
            threads=False,
            progress=False,
        )
        frame = _closes_from_download(raw, syms)
        if not frame.empty and frame.notna().any().any():
            return frame
    except Exception:
        pass

    out: dict[str, pd.Series] = {}
    for sym in syms:
        hist = pd.DataFrame()
        for attempt in range(6):
            try:
                hist = yf.Ticker(sym).history(period=period, interval=interval, auto_adjust=False)
                break
            except YFRateLimitError:
                backoff = min(90.0, (2**attempt) + random.uniform(0.0, 1.5))
                time.sleep(backoff)
        if hist.empty:
            out[sym] = pd.Series(dtype=float)
        else:
            s = hist["Close"].copy()
            s.index = pd.to_datetime(s.index).tz_localize(None)
            s.name = sym
            out[sym] = s
        if pause_sec > 0:
            time.sleep(pause_sec)
    return pd.DataFrame(out).sort_index()


def latest_trade_date(closes: pd.DataFrame) -> pd.Timestamp:
    if closes.empty:
        raise ValueError("No price history")
    return pd.Timestamp(closes.index[-1]).normalize()


def price_on_or_before(closes: pd.Series, as_of: pd.Timestamp) -> float | None:
    s = closes.dropna()
    if s.empty:
        return None
    as_of = pd.Timestamp(as_of).normalize()
    sub = s.loc[:as_of]
    if sub.empty:
        return None
    return float(sub.iloc[-1])
