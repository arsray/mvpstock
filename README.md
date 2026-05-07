# StockPaperMVP

Personal **US equity paper portfolio** runner: discrete signals (placeholder = momentum), **rank-weighted targets** among buys, integer-share rebalance, HTML report. **Daily closes** default to **[Twelve Data](https://twelvedata.com/)** (`time_series`, `interval=1day`), one request per ticker with **≥11s spacing** (under 6 req/min). Optional **`yfinance`** via `config.yaml` if you prefer Yahoo (often rate-limited).

This is **not investment advice**.

## Quick start

This tree is meant to be the **root of its own Git repository** (not nested under a larger monorepo).

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export TWELVE_DATA_API_KEY="your_key_here"
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

### Twelve Data (default)

1. Sign up at Twelve Data and copy your **API key**.
2. Export it (never commit the key):

```bash
export TWELVE_DATA_API_KEY="your_key_here"
python -m src.run
```

3. **Quota**: default pacing is **11 seconds between symbols** (`config.yaml` → `prices.twelvedata.min_interval_sec`). With ~21 tickers + benchmark you use **~22 API credits per run**, well under typical **800/day** free limits.

**GitHub Actions**: add repository secret **`TWELVE_DATA_API_KEY`** (same value). The workflow passes it as an environment variable.

### Offline / CSV / Yahoo instead

Use a cached wide CSV (Date column + one column per ticker):

```bash
python -m src.run --prices-csv examples/sample_closes_wide.csv
```

Regenerate the synthetic sample with `python scripts/build_sample_closes.py`.

To use **yfinance** instead of Twelve Data, set in `config.yaml`: `prices.provider: yfinance` (no API key).

The workflow runs **`python -m src.run`** (Twelve Data) first; if it fails (missing secret, quota, network), it **falls back** to the synthetic CSV so Pages still updates — check the Actions log for which step ran. Remove the fallback job if you want CI to fail instead of publishing synthetic data.

## Customize

- **Universe**: `watchlist.yaml`
- **Caps / signal thresholds**: `config.yaml` (`buy_top_n`, `sell_bottom_n`, `lookback_days`, `stock_weight_cap`)
- **Price source**: `config.yaml` → `prices.provider` (`twelvedata` | `yfinance`) and `prices.twelvedata` (`min_interval_sec`, `outputsize`)
- **Replace the signal engine**: implement your own module and swap the call in `src/run.py` (today: `signals_momentum.momentum_signals`)

## Rank weights

Among tickers with zone `buy`, weights are linear in rank (first gets weight \(n\), last gets \(1\)), scaled to the remaining stock sleeve after `hold` / `sell` handling. See `src/weights.py`.

## Deploy to GitHub (standalone repo)

On GitHub, create an empty **private** repository, then from **this directory**:

```bash
git init
git branch -M main
git add .
git commit -m "Initial StockPaperMVP"
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

Use SSH remote instead if you prefer (`git@github.com:...`).

## GitHub Actions

Workflow `.github/workflows/stock-paper-daily.yml` runs on a weekday cron, uploads `report.html` as an artifact, deploys it to **GitHub Pages**, then **commits and pushes** `data/portfolio.json` and `data/equity_history.jsonl` back to the repo so the **next** scheduled run continues the same paper portfolio (rolling simulation). Commit messages include **`[skip ci]`** so that push does not re-trigger the same workflow.

**Branch protection**: if `main` requires pull requests and blocks direct pushes, grant **`GITHUB_TOKEN`** / Actions permission to bypass for this repo or relax rules for `data/**`; otherwise the commit step will fail.

Ensure **`TWELVE_DATA_API_KEY`** is set under **Settings → Secrets and variables → Actions**.

## GitHub Pages (phone bookmark)

The workflow copies `output/report.html` to the site root as `index.html` and runs `actions/deploy-pages`. **One-time setup** in the GitHub UI:

1. **Settings** → **Pages** → **Build and deployment** → **Source**: select **GitHub Actions** (not “Deploy from a branch”).
2. Push the workflow; after the first successful run, **Settings** → **Pages** shows the public URL (usually `https://<user>.github.io/<repo>/`).
3. On your phone: open that URL in Safari, use **Share → Add to Home Screen** for a one-tap icon. Each daily run refreshes the same URL.

**Privacy**: the Pages URL is generally **world-accessible** unless your org uses private GitHub Pages. Do not put account balances you consider sensitive in the report if the repo or site is public.

If the `deploy` job waits for approval, check **Settings** → **Environments** → **github-pages** and remove required reviewers, or approve the pending deployment in the Actions run.
