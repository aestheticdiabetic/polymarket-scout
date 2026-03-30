# Polymarket Scout — Usage Guide

Polymarket Scout scans Polymarket for high-quality copy-trade candidates. It fetches active wallets, scores them across multiple signals, detects when experienced traders rotate to new wallets, and sends alerts via browser notifications or Telegram.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | Backend runtime |
| Node.js | 18+ | Frontend build |
| Alchemy API key | — | Free tier at [alchemy.com](https://alchemy.com) — needed for Polygon RPC |

---

## Setup

### 1. Configure environment

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and set at minimum:

```
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY_HERE
```

See the [Environment Variables](#environment-variables) section for all options.

### 2. Install backend dependencies

```bash
cd backend
python -m venv .venv

# Windows CMD / PowerShell
.venv\Scripts\activate

# Windows Git Bash
source .venv/Scripts/activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

---

## Running the App

Open **two terminals**.

**Terminal 1 — Backend:**
```bash
cd backend
source .venv/Scripts/activate  # Windows Git Bash
# or: .venv\Scripts\activate    (Windows CMD/PowerShell)
# or: source .venv/bin/activate (macOS/Linux)
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Then open your browser:

| URL | Purpose |
|---|---|
| http://localhost:5173 | Main dashboard |
| http://localhost:8000/docs | FastAPI Swagger UI (API explorer) |
| http://localhost:8000/health | Health check |

On startup the backend automatically runs an initial scan (3-second delay) and schedules recurring scans every 60 minutes.

---

## Restarting the App

> **Important:** The Setup section above is for first-time installation only. Running those commands again (e.g. re-creating the venv or reinstalling dependencies) can result in a fresh `backend/data/` directory, wiping all discovered wallets.

To restart after the app is already set up, just re-run the two start commands:

**Terminal 1 — Backend:**
```bash
cd backend
source .venv/Scripts/activate  # Windows Git Bash
# or: .venv\Scripts\activate    (Windows CMD/PowerShell)
# or: source .venv/bin/activate (macOS/Linux)
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

All previously discovered wallets are stored in `backend/data/candidates.json` and loaded automatically on startup — no scan is needed to restore them.

**If wallets are missing from the dashboard after a restart**, check:
1. The backend is actually running on port 8000 (the frontend alone on 5173 is not enough)
2. `backend/data/candidates.json` is not empty — it should be a non-trivial JSON file (~400KB+ when populated)
3. If `candidates.json` is empty (`[]` or `{}`), check whether a previous copy of the data exists elsewhere in the project directory and copy it back

---

## Key Commands

| Action | Command |
|---|---|
| Start backend | `uvicorn main:app --reload --port 8000` |
| Start frontend | `npm run dev` |
| Build frontend for production | `npm run build` |
| Preview production build | `npm run preview` |
| Activate Python venv (Windows Git Bash) | `source .venv/Scripts/activate` |
| Activate Python venv (Windows CMD/PS) | `.venv\Scripts\activate` |
| Activate Python venv (macOS/Linux) | `source .venv/bin/activate` |
| Install Python deps | `pip install -r requirements.txt` |
| Install Node deps | `npm install` |

---

## Dashboard Tabs

### Candidates
Sortable, filterable table of all scored wallets. Click any row to open a detail slide-out panel with a radar chart of the wallet's signals. Filter by minimum score, arb flag, or rotation status.

### Rotations
Visual explorer showing detected wallet rotation links — when an experienced trader is identified moving to a new wallet address.

### Scan Log
History of the last 50 scans (timestamp, wallets scanned, new candidates found, errors). Use the **Trigger Scan** button to run a manual scan immediately without waiting for the scheduler.

### Config
Edit all scoring weights and thresholds in real-time. Changes take effect immediately — no backend restart needed.

---

## Environment Variables

All variables go in `backend/.env`. Scoring variables can also be changed live from the Config tab.

| Variable | Required | Default | Description |
|---|---|---|---|
| `POLYGON_RPC_URL` | **Yes** | `https://polygon-rpc.com` | Polygon RPC endpoint (use Alchemy for reliability) |
| `TELEGRAM_BOT_TOKEN` | No | — | Telegram bot token (create via @BotFather) |
| `TELEGRAM_CHAT_ID` | No | — | Your Telegram chat ID (get from @userinfobot) |
| `DUNE_API_KEY` | No | — | Dune Analytics key (reserved for future use) |
| `MIN_TRADES` | No | `20` | Minimum trades before a wallet is evaluated |
| `MIN_WIN_RATE` | No | `0.55` | Minimum win rate (0–1) |
| `MIN_ROI` | No | `0.10` | Minimum ROI (0.10 = 10%) |
| `MIN_MARKETS` | No | `3` | Minimum distinct markets traded |
| `EARLY_ENTRY_WEIGHT` | No | `0.35` | Weight for early market entry signal |
| `WIN_RATE_WEIGHT` | No | `0.35` | Weight for win rate |
| `ROI_WEIGHT` | No | `0.20` | Weight for ROI |
| `CONSISTENCY_WEIGHT` | No | `0.10` | Weight for market consistency |
| `ARB_MAX_HOLD_SECONDS` | No | `300` | Trades held under this (seconds) flagged as potential arb |
| `ROTATION_SIMILARITY_THRESHOLD` | No | `0.70` | Min similarity score to link wallets (0–1) |
| `ROTATION_LOOKBACK_DAYS` | No | `90` | Days to look back for rotation matches |
| `SCAN_INTERVAL_MINUTES` | No | `60` | How often the background scanner runs |

---

## API Reference

All endpoints are prefixed with `/api/`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/candidates` | List candidates. Params: `min_score`, `arb_only`, `rotated_only`, `limit` (default 100) |
| `GET` | `/candidates/{wallet}` | Get a single wallet's full score detail |
| `GET` | `/rotations` | List all detected wallet rotation links |
| `GET` | `/alerts/pending` | Get pending browser alerts |
| `POST` | `/alerts/ack/{alert_id}` | Acknowledge (dismiss) an alert |
| `POST` | `/scan` | Trigger a manual scan (runs in background, returns immediately) |
| `GET` | `/scan/log` | Last 50 scan results |
| `GET` | `/config` | Get current scoring config |
| `POST` | `/config` | Update scoring config at runtime (JSON body matching `ScoreWeights`) |
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |

**Example: trigger a manual scan via curl**
```bash
curl -X POST http://localhost:8000/api/scan
```

**Example: filter candidates with score ≥ 70**
```bash
curl "http://localhost:8000/api/candidates?min_score=70&limit=20"
```

---

## How Scoring Works

Each wallet receives a **composite score (0–100)** based on four weighted signals:

| Signal | Default Weight | What it measures |
|---|---|---|
| Win rate | 35% | % of resolved trades that won |
| Early entry | 35% | How early the wallet entered before odds shifted |
| ROI | 20% | Return on investment across all trades |
| Consistency | 10% | Number of distinct markets traded |

**Arbitrage detection** flags wallets that show fast round-trip trades (< 300 seconds), opposing YES + NO positions in the same market, or micro-sized positions. Suspected arb wallets receive a 70% score penalty and are labelled in the dashboard.

**Rotation detection** compares wallets across four signals:
- Funding source (35%) — same originating wallet on first deposit
- Bet sizing patterns (25%) — cosine similarity of trade size histograms
- Market selection (25%) — Jaccard similarity of markets traded
- Activity timing (15%) — hour-of-day trading profiles

Wallets above the similarity threshold (default 70%) are linked as a rotation pair.

---

## Alerts

### Browser Push Notifications
Enabled automatically when you open the dashboard. You'll be prompted to allow notifications. Alerts fire when a new high-score candidate is found.

### Telegram Alerts
Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `backend/.env`:

1. Message @BotFather on Telegram → `/newbot` → copy the token
2. Message @userinfobot on Telegram → copy your chat ID
3. Add both to `.env` and restart the backend

Telegram alerts only fire when the dashboard is not actively polling (i.e., when you're not in the browser).

---

## Data Persistence

All data is stored as JSON files in `backend/data/` (auto-created on first run):

| File | Contents |
|---|---|
| `candidates.json` | All discovered wallet scores |
| `rotations.json` | All detected rotation links |
| `scan_log.json` | Last 50 scan results |

Data is loaded on startup and saved after every scan. To **reset all data**, delete the files in `backend/data/`.

---

## Troubleshooting

**Backend fails to start — `POLYGON_RPC_URL` error**
The public fallback `https://polygon-rpc.com` is rate-limited. Sign up at [alchemy.com](https://alchemy.com) and use a dedicated key.

**No candidates after scanning**
- Scoring thresholds may be too strict. Lower `MIN_WIN_RATE` or `MIN_ROI` in the Config tab.
- The initial scan takes a few minutes. Check the Scan Log tab for errors.

**Frontend shows "Unable to connect"**
- Ensure the backend is running on port 8000.
- The frontend proxies `/api` to `http://localhost:8000` via Vite — both must be running.

**Port 5173 or 8000 already in use**
```bash
# Change backend port
uvicorn main:app --reload --port 8001

# Change frontend port in frontend/vite.config.js → server.port
```

**Telegram alerts not arriving**
- Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set correctly in `.env`.
- Send `/start` to your bot on Telegram first to activate it.
- Restart the backend after changing `.env`.
