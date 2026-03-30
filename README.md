# Polymarket Scout

Automatically discovers high-quality copy-trade candidates on Polymarket — including wallets
that have recently rotated addresses to avoid detection — before they appear on any leaderboard.

---

## Architecture

```
Data Sources            Scoring Engine           Output
─────────────           ──────────────           ──────
Polymarket CLOB API  →  Win rate + ROI       →   React dashboard
The Graph subgraph   →  Early entry score    →   Browser notifications
Polygon RPC          →  Arb filter           →   Telegram alerts
Dune Analytics       →  Rotation detector    →   JSON persistence
```

The backend runs on FastAPI with APScheduler. Every N minutes it:
1. Fetches recently active wallets from the Polymarket CLOB API
2. Pulls full trade history from The Graph subgraph + CLOB
3. Scores each wallet against configurable thresholds
4. Runs the rotation detector to find wallets that share fingerprints with known good wallets
5. Alerts on new candidates via browser push and/or Telegram
6. Persists results to `backend/data/` as JSON

---

## Quick Start

### 1. Clone and configure

```bash
git clone <this-repo>
cd polymarket-scout
cp backend/.env.example backend/.env
```

Edit `backend/.env` and add your Polygon RPC URL at minimum:

```
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY_HERE
```

Get a free key at [alchemy.com](https://alchemy.com) — free tier is enough to start.

### 2. Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The backend will start an initial scan automatically on startup.

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

---

## Configuration

All scoring parameters can be changed at runtime from the **Config** tab in the dashboard.
No restart required — changes apply on the next scan.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_trades` | 20 | Minimum trade count before evaluating a wallet |
| `min_win_rate` | 55% | Minimum resolved win rate |
| `min_roi` | 10% | Minimum return on investment |
| `min_markets` | 3 | Minimum distinct markets traded |
| `win_rate_weight` | 35% | Weight in composite score |
| `roi_weight` | 20% | Weight in composite score |
| `early_entry_weight` | 35% | Weight in composite score |
| `consistency_weight` | 10% | Weight in composite score |
| `arb_max_hold_seconds` | 300 | Hold time below which trades are flagged as potential arb |
| `rotation_similarity_threshold` | 70% | Minimum combined signal confidence to flag a rotation |
| `scan_interval_minutes` | 60 | How often the background scanner runs |

---

## Telegram Alerts

1. Message [@BotFather](https://t.me/botfather) on Telegram → create a new bot → copy the token
2. Message [@userinfobot](https://t.me/userinfobot) to get your chat ID
3. Add both to `backend/.env`:

```
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

The alert engine fires Telegram messages when the dashboard isn't open (detected via the
browser notification polling — if pending alerts aren't being ACK'd, Telegram kicks in).

---

## Rotation Detection

The rotation detector compares every new wallet against all previously scored good wallets
using four signals:

| Signal | Weight | Method |
|--------|--------|--------|
| Funding source | 35% | Traces the first deposit tx on Polygon via The Graph |
| Bet sizing | 25% | Cosine similarity of log-binned trade size histograms |
| Market selection | 25% | Jaccard similarity of market IDs traded |
| Activity timing | 15% | Cosine similarity of hour-of-day activity profiles |

The combined score is compared against `rotation_similarity_threshold`. When a link is
detected, the new wallet is flagged with a confidence score and its rotation signals are
shown in the detail panel.

**Note:** Funding source lookup requires a reliable Polygon indexer. The subgraph query
used here is a best-effort heuristic. For production use, replace
`fetcher.get_wallet_funding_source()` with an Alchemy `alchemy_getAssetTransfers` call
for higher accuracy.

---

## Arbitrage Filter

Wallets are filtered out from copy-trade candidates if they exhibit:
- **Fast round-trips**: >40% of trades closed in under `arb_max_hold_seconds`
- **Opposing positions**: Both YES and NO in the same market
- **Micro-sizing**: Average trade < $5 with 50+ trades (likely market maker)

Flagged wallets are still visible in the dashboard with the `ARB` badge — they're just
excluded from the default candidate list. You can disable this filter in the Config tab.

---

## Data Persistence

Results are written to:
```
backend/data/
  candidates.json   — all scored wallets
  rotations.json    — detected rotation links
  scan_log.json     — last 50 scan results
```

These are loaded on startup so you don't lose data between restarts.

---

## Project Structure

```
polymarket-scout/
├── backend/
│   ├── main.py                    FastAPI app + scheduler
│   ├── config.py                  Settings (env vars + defaults)
│   ├── requirements.txt
│   ├── .env.example
│   ├── models/
│   │   └── wallet.py              Pydantic models
│   ├── routers/
│   │   └── api.py                 REST endpoints
│   ├── services/
│   │   ├── fetcher.py             Polymarket CLOB + subgraph + RPC
│   │   ├── scorer.py              Composite scoring + arb detection
│   │   ├── rotation_detector.py   Multi-signal wallet fingerprinting
│   │   ├── alerter.py             Browser push + Telegram
│   │   └── scanner.py             Orchestration loop + persistence
│   └── data/                      Auto-created on first run
└── frontend/
    ├── src/
    │   ├── App.jsx                 Layout + navigation
    │   ├── lib/api.js              API client
    │   ├── hooks/useAlerts.js      Alert polling + browser push
    │   ├── components/
    │   │   ├── WalletDetail.jsx    Slide-out detail panel + radar chart
    │   │   ├── ConfigPanel.jsx     Runtime scoring config
    │   │   ├── ScoreBar.jsx        Score visualisation
    │   │   └── StatPill.jsx        Stat chip
    │   └── pages/
    │       ├── CandidatesPage.jsx  Main sortable/filterable table
    │       ├── RotationsPage.jsx   Rotation link explorer
    │       └── ScanLogPage.jsx     Scan history + manual trigger
    └── package.json
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/candidates` | List candidates (filter: `min_score`, `rotated_only`) |
| GET | `/api/candidates/{wallet}` | Get single wallet detail |
| GET | `/api/rotations` | List detected rotation links |
| GET | `/api/alerts/pending` | Pending browser alerts |
| POST | `/api/alerts/ack/{id}` | Acknowledge an alert |
| POST | `/api/scan` | Trigger a manual scan |
| GET | `/api/scan/log` | Last 50 scan results |
| GET | `/api/config` | Get current scoring config |
| POST | `/api/config` | Update scoring config |
| GET | `/api/health` | Health check |
