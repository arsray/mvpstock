from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .load_config import AppConfig
from .signals_momentum import SignalRow
from .weights import target_weights_for_day


@dataclass
class PortfolioState:
    cash_usd: float
    positions_shares: dict[str, int]
    as_of_trade_date: str | None
    initial_cash_usd: float
    bench_units: float | None
    bench_anchor_date: str | None


def load_portfolio(path: Path, initial_cash: float) -> PortfolioState:
    if not path.exists():
        return PortfolioState(
            cash_usd=initial_cash,
            positions_shares={},
            as_of_trade_date=None,
            initial_cash_usd=initial_cash,
            bench_units=None,
            bench_anchor_date=None,
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PortfolioState(
        cash_usd=float(raw.get("cash_usd") or initial_cash),
        positions_shares={k: int(v) for k, v in (raw.get("positions_shares") or {}).items()},
        as_of_trade_date=raw.get("as_of_trade_date"),
        initial_cash_usd=float(raw.get("initial_cash_usd") or initial_cash),
        bench_units=(float(raw["bench_units"]) if raw.get("bench_units") is not None else None),
        bench_anchor_date=raw.get("bench_anchor_date"),
    )


def save_portfolio(path: Path, p: PortfolioState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {
        "schema_version": 1,
        "cash_usd": round(p.cash_usd, 2),
        "positions_shares": {k: int(v) for k, v in sorted(p.positions_shares.items()) if v != 0},
        "as_of_trade_date": p.as_of_trade_date,
        "initial_cash_usd": round(p.initial_cash_usd, 2),
        "bench_units": round(p.bench_units, 6) if p.bench_units is not None else None,
        "bench_anchor_date": p.bench_anchor_date,
    }
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def compute_aum(
    cash: float,
    positions: dict[str, int],
    prices: dict[str, float],
) -> float:
    mv = sum(float(positions.get(t, 0)) * float(prices[t]) for t in positions if t in prices)
    return float(cash + mv)


def positions_market_value(positions: dict[str, int], prices: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for t, sh in positions.items():
        if sh and t in prices:
            out[t] = float(sh) * float(prices[t])
    return out


def maybe_init_benchmark(
    p: PortfolioState,
    bench_px: float,
    as_of: pd.Timestamp,
) -> PortfolioState:
    if p.bench_units is not None:
        return p
    units = p.initial_cash_usd / bench_px if bench_px > 0 else 0.0
    return PortfolioState(
        cash_usd=p.cash_usd,
        positions_shares=dict(p.positions_shares),
        as_of_trade_date=p.as_of_trade_date,
        initial_cash_usd=p.initial_cash_usd,
        bench_units=units,
        bench_anchor_date=str(as_of.date()),
    )


def rebalance_integer_shares(
    *,
    cash: float,
    positions: dict[str, int],
    target_weights: dict[str, float],
    prices: dict[str, float],
    tickers: list[str],
) -> tuple[float, dict[str, int], list[dict[str, Any]]]:
    """
    Sell-first then buy. Whole shares only at given prices.
    Target dollar amounts use AUM at the start of the session (constant notionals).
    """
    positions = {k: int(v) for k, v in positions.items() if v != 0}
    aum0 = compute_aum(cash, positions, prices)
    ledger: list[dict[str, Any]] = []

    tgt_mv: dict[str, float] = {}
    for t in tickers:
        if t not in prices:
            continue
        tgt_mv[t] = float(target_weights.get(t, 0.0)) * aum0

    def cur_mv(t: str) -> float:
        return float(positions.get(t, 0)) * float(prices[t])

    def delta_usd(t: str) -> float:
        return tgt_mv.get(t, 0.0) - cur_mv(t)

    sells = sorted([t for t in tickers if t in prices and delta_usd(t) < -1e-6])
    for t in sells:
        px = float(prices[t])
        need_reduce_usd = -delta_usd(t)
        max_sh = int(positions.get(t, 0))
        sh_to_sell = min(max_sh, int(need_reduce_usd / px))
        if sh_to_sell <= 0:
            continue
        positions[t] = max_sh - sh_to_sell
        if positions[t] == 0:
            del positions[t]
        cash += sh_to_sell * px
        ledger.append(
            {
                "side": "sell",
                "ticker": t,
                "shares": sh_to_sell,
                "price": round(px, 4),
                "notional": round(sh_to_sell * px, 2),
            }
        )

    buys = sorted([t for t in tickers if t in prices and delta_usd(t) > 1e-6])
    for t in buys:
        px = float(prices[t])
        d = delta_usd(t)
        if d <= 1e-6:
            continue
        max_afford = int(cash / px)
        sh_to_buy = min(max_afford, int(d / px))
        if sh_to_buy <= 0:
            continue
        cost = sh_to_buy * px
        cash -= cost
        positions[t] = int(positions.get(t, 0)) + sh_to_buy
        ledger.append(
            {
                "side": "buy",
                "ticker": t,
                "shares": sh_to_buy,
                "price": round(px, 4),
                "notional": round(cost, 2),
            }
        )

    return cash, positions, ledger


def apply_strategy_day(
    cfg: AppConfig,
    portfolio_path: Path,
    *,
    signals: dict[str, SignalRow],
    tickers: list[str],
    prices: dict[str, float],
    bench_px: float,
    as_of: pd.Timestamp,
) -> tuple[PortfolioState, dict[str, float], list[dict[str, Any]]]:
    p = load_portfolio(portfolio_path, cfg.initial_cash)
    p = maybe_init_benchmark(p, bench_px, as_of)

    aum = compute_aum(p.cash_usd, p.positions_shares, prices)
    mv_map = positions_market_value(p.positions_shares, prices)

    tw = target_weights_for_day(
        signals=signals,
        tickers=tickers,
        aum_usd=aum,
        positions_mv=mv_map,
        stock_weight_cap=cfg.stock_weight_cap,
    )

    cash, pos, ledger = rebalance_integer_shares(
        cash=p.cash_usd,
        positions=dict(p.positions_shares),
        target_weights=tw,
        prices=prices,
        tickers=tickers,
    )

    p_out = PortfolioState(
        cash_usd=cash,
        positions_shares=pos,
        as_of_trade_date=str(as_of.date()),
        initial_cash_usd=p.initial_cash_usd,
        bench_units=p.bench_units,
        bench_anchor_date=p.bench_anchor_date,
    )
    if p_out.bench_units is None and bench_px > 0:
        p_out = maybe_init_benchmark(p_out, bench_px, as_of)

    return p_out, tw, ledger


def append_equity_history(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
