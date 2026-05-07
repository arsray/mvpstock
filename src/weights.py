from __future__ import annotations

from typing import Iterable

from .signals_momentum import SignalRow


def rank_weights_linear(n: int) -> list[float]:
    """Weights for ranks 1..n within buy bucket: n, n-1, ..., 1."""
    if n <= 0:
        return []
    return [float(n - i + 1) for i in range(1, n + 1)]


def target_weights_for_day(
    *,
    signals: dict[str, SignalRow],
    tickers: Iterable[str],
    aum_usd: float,
    positions_mv: dict[str, float],
    stock_weight_cap: float,
) -> dict[str, float]:
    """
    - sell -> 0
    - hold -> current MV / AUM (maintain slice; minimal intentional drift )
    - buy -> split remaining budget up to `stock_weight_cap` rank-weighted among buys.
    """
    if aum_usd <= 0:
        raise ValueError("AUM must be positive")

    W = float(stock_weight_cap)
    tickers = list(tickers)
    sell = {t for t in tickers if signals[t].zone == "sell"}
    buy = [t for t in tickers if signals[t].zone == "buy"]
    hold = [t for t in tickers if signals[t].zone == "hold"]

    tw: dict[str, float] = {t: 0.0 for t in tickers}

    for t in sell:
        tw[t] = 0.0

    for t in hold:
        if t in sell:
            continue
        mv = float(positions_mv.get(t, 0.0))
        tw[t] = mv / aum_usd if aum_usd else 0.0

    used = sum(tw[t] for t in hold if t not in sell)
    remain = W - used
    if remain < 0:
        scale = W / used if used > 0 else 0.0
        for t in hold:
            if t not in sell:
                tw[t] *= scale
        remain = W - sum(tw[t] for t in hold if t not in sell)

    if not buy:
        return _renormalize_stock_sleeve(tw, tickers, W)

    buy_sorted = sorted(
        buy,
        key=lambda t: signals[t].rank,
    )
    n = len(buy_sorted)
    raw = rank_weights_linear(n)
    ssum = sum(raw)
    for t, wpart in zip(buy_sorted, raw):
        tw[t] = remain * (wpart / ssum) if ssum > 0 and remain > 0 else 0.0

    return _renormalize_stock_sleeve(tw, tickers, W)


def _renormalize_stock_sleeve(tw: dict[str, float], tickers: Iterable[str], W: float) -> dict[str, float]:
    tickers = list(tickers)
    s = sum(max(0.0, tw[t]) for t in tickers)
    if s <= 1e-12:
        return tw
    if s > W + 1e-9:
        k = W / s
        return {t: max(0.0, tw[t]) * k for t in tickers}
    return tw
