from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .paths import repo_root


@dataclass(frozen=True)
class AppConfig:
    initial_cash: float
    stock_weight_cap: float
    execution_bar: str
    signals: dict[str, Any]
    benchmark_ticker: str
    price_provider: str
    twelvedata_min_interval_sec: float
    twelvedata_outputsize: int
    portfolio_path: Path
    equity_history_path: Path
    signals_out_path: Path
    report_html_path: Path


def load_watchlist(path: Path | None = None) -> list[str]:
    root = repo_root()
    p = path or (root / "watchlist.yaml")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    tickers = data.get("tickers") or []
    out = [str(t).strip().upper() for t in tickers if str(t).strip()]
    if not out:
        raise ValueError("watchlist.yaml: no tickers")
    return sorted(set(out))


def load_app_config(path: Path | None = None) -> AppConfig:
    root = repo_root()
    p = path or (root / "config.yaml")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    paths = raw.get("paths") or {}
    prices = raw.get("prices") or {}
    td = prices.get("twelvedata") or {}
    return AppConfig(
        initial_cash=float(raw.get("initial_cash") or 100_000),
        stock_weight_cap=float(raw.get("stock_weight_cap") or 0.95),
        execution_bar=str(raw.get("execution_bar") or "close"),
        signals=dict(raw.get("signals") or {}),
        benchmark_ticker=str(raw.get("benchmark_ticker") or "SPY"),
        price_provider=str(prices.get("provider") or "twelvedata").strip().lower(),
        twelvedata_min_interval_sec=float(td.get("min_interval_sec") or 11.0),
        twelvedata_outputsize=int(td.get("outputsize") or 2000),
        portfolio_path=root / str(paths.get("portfolio") or "data/portfolio.json"),
        equity_history_path=root / str(paths.get("equity_history") or "data/equity_history.jsonl"),
        signals_out_path=root / str(paths.get("signals_out") or "output/latest_signals.json"),
        report_html_path=root / str(paths.get("report_html") or "output/report.html"),
    )
