from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .signals_momentum import SignalRow


def write_report(
    path: Path,
    *,
    generated_at: datetime,
    as_of: str,
    cfg_summary: dict[str, Any],
    signals: dict[str, SignalRow],
    target_weights: dict[str, float],
    portfolio: dict[str, Any],
    ledger: list[dict[str, Any]],
    equity: float,
    bench_equity: float | None,
    initial_cash: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    rows_sig = sorted(signals.values(), key=lambda r: r.rank)
    sig_lines = "".join(
        f"<tr><td>{html.escape(r.ticker)}</td><td>{r.rank}</td><td>{r.score:.4f}</td>"
        f"<td>{html.escape(r.zone)}</td></tr>"
        for r in rows_sig
    )

    rows_tw = "".join(
        f"<tr><td>{html.escape(t)}</td><td>{target_weights.get(t, 0.0):.4f}</td></tr>"
        for t in sorted(target_weights.keys())
    )

    rows_ld = "".join(
        f"<tr><td>{html.escape(str(x.get('side')))}</td><td>{html.escape(str(x.get('ticker')))}</td>"
        f"<td>{x.get('shares')}</td><td>{x.get('price')}</td><td>{x.get('notional')}</td></tr>"
        for x in ledger
    )

    ret_pct = (equity / initial_cash - 1.0) * 100.0 if initial_cash else 0.0
    bench_block = ""
    if bench_equity is not None:
        br = (bench_equity / initial_cash - 1.0) * 100.0 if initial_cash else 0.0
        bench_block = (
            f"<p><b>Benchmark ({html.escape(str(cfg_summary.get('benchmark_ticker')))}) "
            f"buy &amp; hold (since anchor):</b> ${bench_equity:,.2f} "
            f"({br:+.2f}% vs initial)</p>"
        )

    disclaimer = (
        "Personal paper simulation using third‑party market data. "
        "Not investment advice. Past performance does not guarantee future results."
    )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>StockPaperMVP — {html.escape(as_of)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 16px; line-height: 1.45; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 960px; }}
    th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
    th {{ background: #f4f4f4; }}
    .muted {{ color: #555; font-size: 0.95rem; }}
    code {{ background: #f0f0f0; padding: 2px 6px; }}
  </style>
</head>
<body>
  <h1>StockPaperMVP</h1>
  <p class="muted">As of trade date: <b>{html.escape(as_of)}</b> · Generated UTC: <b>{html.escape(generated_at.strftime('%Y-%m-%d %H:%M:%SZ'))}</b></p>
  <p><b>Portfolio equity:</b> ${equity:,.2f} &nbsp;·&nbsp; <b>vs initial:</b> {ret_pct:+.2f}%</p>
  {bench_block}
  <p class="muted">{html.escape(disclaimer)}</p>

  <h2>Configuration snapshot</h2>
  <pre>{html.escape(json.dumps(cfg_summary, indent=2))}</pre>

  <h2>Signals (placeholder = momentum)</h2>
  <table>
    <thead><tr><th>Ticker</th><th>Rank</th><th>Score</th><th>Zone</th></tr></thead>
    <tbody>{sig_lines}</tbody>
  </table>

  <h2>Target weights (after rank-weighted buys)</h2>
  <table>
    <thead><tr><th>Ticker</th><th>Weight</th></tr></thead>
    <tbody>{rows_tw}</tbody>
  </table>

  <h2>Trades today (integer shares)</h2>
  <table>
    <thead><tr><th>Side</th><th>Ticker</th><th>Shares</th><th>Price</th><th>Notional</th></tr></thead>
    <tbody>{rows_ld if rows_ld else '<tr><td colspan="5">No trades</td></tr>'}</tbody>
  </table>

  <h2>Portfolio JSON</h2>
  <pre>{html.escape(json.dumps(portfolio, indent=2))}</pre>
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")
