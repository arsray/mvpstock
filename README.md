# StockPaperMVP

Personal **US equity paper portfolio** runner: discrete signals (placeholder = momentum), **rank-weighted targets** among buys, integer-share rebalance, HTML report. Uses **yfinance** (free, unofficial); Yahoo may **rate-limit** heavy same-day testing—wait and retry, run **once daily** in CI, or swap `src/market_data.py` for another provider later.

This is **not investment advice**.

## Quick start

```bash
cd StockPaperMVP
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m src.run
```

Outputs (see `config.yaml`):

- `output/report.html` — open on desktop or phone.
- `output/latest_signals.json`
- Updates `data/portfolio.json` and appends `data/equity_history.jsonl`.

Dry run (no files written):

```bash
python -m src.run --dry-run
```

### Offline / Yahoo blocked

Yahoo Finance often rate-limits automated pulls. You can:

1. Wait and retry later, run **once per day**, or run from a residential IP.
2. Use a cached wide CSV (Date column + one column per ticker):

```bash
python -m src.run --prices-csv examples/sample_closes_wide.csv
```

Regenerate the synthetic sample with `python scripts/build_sample_closes.py`. Replace it with your own export when you have a working upstream.

GitHub Actions uses the bundled sample CSV so the workflow stays reliable; switch the workflow step to plain `python -m src.run` when you accept occasional Yahoo failures.

## Customize

- **Universe**: `watchlist.yaml`
- **Caps / signal thresholds**: `config.yaml` (`buy_top_n`, `sell_bottom_n`, `lookback_days`, `stock_weight_cap`)
- **Replace the signal engine**: implement your own module and swap the call in `src/run.py` (today: `signals_momentum.momentum_signals`)

## Rank weights

Among tickers with zone `buy`, weights are linear in rank (first gets weight \(n\), last gets \(1\)), scaled to the remaining stock sleeve after `hold` / `sell` handling. See `src/weights.py`.

## GitHub Actions

Workflow `.github/workflows/stock-paper-daily.yml` (repo root) runs on a weekday cron and uploads `report.html` as an artifact. **State**: either commit `data/portfolio.json` (and accept bot pushes) or treat each CI run as stateless (starts from `data/portfolio.json` in the repo). For a continuous simulation, keep `portfolio.json` in git between runs.

## GitHub Pages (optional)

Publish `output/report.html` with your preferred Pages action; ensure you are comfortable with **public** visibility or use a private hosting path instead.
