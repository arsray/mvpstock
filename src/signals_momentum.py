from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SignalRow:
    ticker: str
    score: float
    rank: int  # 1 = best among universe
    zone: str  # buy | sell | hold


def momentum_signals(
    closes: pd.DataFrame,
    lookback_days: int,
    buy_top_n: int,
    sell_bottom_n: int,
) -> tuple[dict[str, SignalRow], pd.Timestamp]:
    """
    Placeholder strategy: rank by lookback total return.
    Top buy_top_n -> buy; bottom sell_bottom_n -> sell; rest hold.
    """
    if closes.empty:
        raise ValueError("closes empty")

    as_of = pd.Timestamp(closes.index[-1]).normalize()
    scores: dict[str, float] = {}
    for col in closes.columns:
        s = closes[col].dropna()
        if len(s) < lookback_days + 1:
            scores[col] = float("nan")
            continue
        recent = s.iloc[-1]
        past = s.iloc[-lookback_days - 1]
        scores[col] = float(recent / past - 1.0)

    ranked = sorted(
        ((t, scores[t]) for t in scores if scores[t] == scores[t]),
        key=lambda x: x[1],
        reverse=True,
    )
    tickers_sorted = [t for t, _ in ranked]
    n = len(tickers_sorted)
    if n == 0:
        raise ValueError("No valid scores")

    buy_set = set(tickers_sorted[: max(0, min(buy_top_n, n))])
    sell_set = set(tickers_sorted[max(0, n - sell_bottom_n) :]) if sell_bottom_n > 0 else set()
    buy_set -= sell_set

    rows: dict[str, SignalRow] = {}
    for r, t in enumerate(tickers_sorted, start=1):
        sc = scores[t]
        if t in buy_set:
            z = "buy"
        elif t in sell_set:
            z = "sell"
        else:
            z = "hold"
        rows[t] = SignalRow(ticker=t, score=sc, rank=r, zone=z)

    for t in closes.columns:
        if t not in rows:
            rows[t] = SignalRow(ticker=t, score=float("nan"), rank=9999, zone="hold")

    return rows, as_of
