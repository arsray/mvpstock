from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

TWELVE_DATA_TIME_SERIES = "https://api.twelvedata.com/time_series"


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


def _twelvedata_close_series(
    symbol: str,
    *,
    api_key: str,
    outputsize: int,
) -> pd.Series:
    """One `time_series` call per symbol (1 API credit per call on typical plans)."""
    params = {
        "symbol": symbol,
        "interval": "1day",
        "apikey": api_key,
        "outputsize": max(1, min(int(outputsize), 5000)),
        "order": "asc",
    }
    for attempt in range(4):
        r = requests.get(TWELVE_DATA_TIME_SERIES, params=params, timeout=90)
        if r.status_code == 429 and attempt < 3:
            time.sleep(65.0)
            continue
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "error":
            msg = str(data.get("message") or data)
            if "api credit" in msg.lower() or "limit" in msg.lower() or "rate" in msg.lower():
                if attempt < 3:
                    time.sleep(65.0)
                    continue
            raise RuntimeError(f"Twelve Data {symbol}: {msg}")
        values = data.get("values") or []
        if not values:
            return pd.Series(dtype=float, name=symbol)
        idx: list[pd.Timestamp] = []
        vals: list[float] = []
        for row in values:
            if row.get("close") is None:
                continue
            idx.append(pd.Timestamp(row["datetime"]).normalize())
            vals.append(float(row["close"]))
        if not idx:
            return pd.Series(dtype=float, name=symbol)
        s = pd.Series(vals, index=idx, name=symbol, dtype=float)
        s = s[~s.index.duplicated(keep="last")]
        s.index = pd.to_datetime(s.index).tz_localize(None)
        return s.sort_index()


def fetch_closes_twelvedata(
    tickers: Iterable[str],
    *,
    api_key: str,
    min_interval_sec: float = 11.0,
    outputsize: int = 2000,
) -> pd.DataFrame:
    """
    Columns = tickers, index = date. One REST request per ticker.
    Default 11s gap keeps under 6 requests/minute (Twelve Data free tier friendly).
    """
    syms = list(dict.fromkeys(tickers))
    if not syms:
        return pd.DataFrame()
    if not api_key.strip():
        raise ValueError("Twelve Data api_key is empty")

    out: dict[str, pd.Series] = {}
    for i, sym in enumerate(syms):
        if i > 0 and min_interval_sec > 0:
            time.sleep(float(min_interval_sec))
        out[sym] = _twelvedata_close_series(sym, api_key=api_key.strip(), outputsize=outputsize)
    return pd.DataFrame(out).sort_index()


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
