from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from .load_config import load_app_config, load_watchlist
from .market_data import (
    fetch_closes,
    fetch_closes_twelvedata,
    latest_trade_date,
    load_closes_csv,
    price_on_or_before,
)
from .paths import repo_root
from .portfolio_engine import (
    apply_strategy_day,
    compute_aum,
    append_equity_history,
    save_portfolio,
)
from .report_html import write_report
from .signals_momentum import momentum_signals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="StockPaperMVP daily runner")
    parser.add_argument(
        "--prices-csv",
        type=Path,
        default=None,
        help="Optional wide CSV (Date + tickers) to skip yfinance (offline / tests).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print summary only; do not write files")
    args = parser.parse_args(argv)

    root = repo_root()
    cfg = load_app_config(root / "config.yaml")
    tickers = load_watchlist(root / "watchlist.yaml")
    bench = cfg.benchmark_ticker
    fetch_syms = sorted({*tickers, bench})

    if args.prices_csv is not None:
        path = args.prices_csv if args.prices_csv.is_absolute() else (root / args.prices_csv)
        closes = load_closes_csv(path)
        need = [s for s in fetch_syms if s not in closes.columns]
        if need:
            print(f"prices-csv missing columns: {', '.join(need)}", file=sys.stderr)
            return 2
        closes = closes[[c for c in fetch_syms if c in closes.columns]]
    else:
        prov = cfg.price_provider
        if prov == "twelvedata":
            key = os.environ.get("TWELVE_DATA_API_KEY", "").strip()
            if not key:
                print(
                    "Set environment variable TWELVE_DATA_API_KEY (Twelve Data API key).",
                    file=sys.stderr,
                )
                return 2
            try:
                closes = fetch_closes_twelvedata(
                    fetch_syms,
                    api_key=key,
                    min_interval_sec=cfg.twelvedata_min_interval_sec,
                    outputsize=cfg.twelvedata_outputsize,
                )
            except requests.RequestException as e:
                print(f"Twelve Data HTTP error: {e}", file=sys.stderr)
                return 2
            except (RuntimeError, ValueError, KeyError) as e:
                print(f"Twelve Data error: {e}", file=sys.stderr)
                return 2
        elif prov == "yfinance":
            closes = fetch_closes(fetch_syms, period="400d", interval="1d")
        else:
            print(
                f"Unknown config prices.provider={prov!r} (use twelvedata or yfinance).",
                file=sys.stderr,
            )
            return 2
    if closes.empty:
        print("No market data", file=sys.stderr)
        return 2

    as_of = latest_trade_date(closes)
    sig_cfg = cfg.signals
    mode = str(sig_cfg.get("mode") or "momentum")
    if mode != "momentum":
        print(f"Unknown signals.mode={mode!r}; only 'momentum' is implemented.", file=sys.stderr)
        return 2

    signals, _ = momentum_signals(
        closes[list(tickers)],
        lookback_days=int(sig_cfg.get("lookback_days") or 20),
        buy_top_n=int(sig_cfg.get("buy_top_n") or 8),
        sell_bottom_n=int(sig_cfg.get("sell_bottom_n") or 5),
    )

    prices: dict[str, float] = {}
    missing: list[str] = []
    for t in fetch_syms:
        px = price_on_or_before(closes[t], as_of)
        if px is None or px != px:
            missing.append(t)
        else:
            prices[t] = float(px)
    if missing:
        print(f"Warning: missing prices for: {', '.join(missing)}", file=sys.stderr)

    bench_px = prices.get(bench)
    if bench_px is None:
        print(f"Missing benchmark {bench}; cannot track bench.", file=sys.stderr)

    p_out, tw, ledger = apply_strategy_day(
        cfg,
        cfg.portfolio_path,
        signals=signals,
        tickers=tickers,
        prices=prices,
        bench_px=float(bench_px or 0.0),
        as_of=as_of,
    )

    equity = compute_aum(p_out.cash_usd, p_out.positions_shares, prices)
    bench_equity = (p_out.bench_units * bench_px) if (p_out.bench_units is not None and bench_px) else None

    signals_doc = {
        str(as_of.date()): {
            t: {"rank": signals[t].rank, "score": signals[t].score, "zone": signals[t].zone}
            for t in tickers
        }
    }

    portfolio_doc = {
        "cash_usd": round(p_out.cash_usd, 2),
        "positions_shares": p_out.positions_shares,
        "as_of_trade_date": p_out.as_of_trade_date,
        "equity_usd": round(equity, 2),
        "benchmark_ticker": bench,
        "bench_equity_usd": round(bench_equity, 2) if bench_equity is not None else None,
    }

    cfg_summary = {
        "stock_weight_cap": cfg.stock_weight_cap,
        "signals": cfg.signals,
        "benchmark_ticker": cfg.benchmark_ticker,
        "execution_bar": cfg.execution_bar,
        "prices_provider": cfg.price_provider,
    }

    generated_at = datetime.now(timezone.utc)

    if not args.dry_run:
        cfg.signals_out_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.signals_out_path.write_text(json.dumps(signals_doc, indent=2) + "\n", encoding="utf-8")

        save_portfolio(cfg.portfolio_path, p_out)

        append_equity_history(
            cfg.equity_history_path,
            {
                "date": str(as_of.date()),
                "equity_usd": round(equity, 2),
                "bench_equity_usd": round(bench_equity, 2) if bench_equity is not None else None,
                "cash_usd": round(p_out.cash_usd, 2),
            },
        )

        write_report(
            cfg.report_html_path,
            generated_at=generated_at,
            as_of=str(as_of.date()),
            cfg_summary=cfg_summary,
            signals=signals,
            target_weights=tw,
            portfolio=portfolio_doc,
            ledger=ledger,
            equity=equity,
            bench_equity=bench_equity,
            initial_cash=p_out.initial_cash_usd,
        )

    print(f"As of: {as_of.date()}  Equity: ${equity:,.2f}  Trades: {len(ledger)}")
    if bench_equity is not None:
        print(f"Benchmark ({bench}) buy&hold: ${bench_equity:,.2f}")
    print("Dry run; no files written." if args.dry_run else f"Wrote: {cfg.report_html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
